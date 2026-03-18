from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any
def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None
def _severity_rank(sev: str) -> int:
    return {"warning": 1, "high": 2, "critical": 3}.get(str(sev), 0)
from .scanners import BaseScanner, ScannerSpec


class FluidBalanceScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="fluid_balance",
                interval_key="fluid_balance",
                default_interval=600,
                initial_delay=39,
            ),
        )

    async def scan(self) -> None:
        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {
                "_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1,
                "weight": 1, "bodyWeight": 1, "body_weight": 1, "weightKg": 1, "weight_kg": 1,
            },
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        fluid_cfg = self.engine.config.yaml_cfg.get("alert_engine", {}).get("fluid_balance", {})
        windows = fluid_cfg.get("windows_hours", [6, 12, 24]) if isinstance(fluid_cfg, dict) else [6, 12, 24]
        windows = sorted({int(w) for w in windows if isinstance(w, (int, float, str)) and int(w) > 0})
        if not windows:
            windows = [6, 12, 24]

        warning_pct = float(fluid_cfg.get("percent_fluid_overload_warning_pct", fluid_cfg.get("positive_balance_warning_pct", 5)))
        high_pct = float(fluid_cfg.get("percent_fluid_overload_high_pct", fluid_cfg.get("positive_balance_high_pct", fluid_cfg.get("positive_balance_critical_pct", 10))))
        rapid_ml_per_kg_6h = float(fluid_cfg.get("rapid_infusion_ml_per_kg_6h", 30))
        urine_resp_ml_per_kg_h = float(fluid_cfg.get("urine_response_ml_per_kg_h", 0.5))
        linkage_lookback_h = int(fluid_cfg.get("linkage_lookback_hours", 24))

        now = datetime.now()
        lookback = max(windows)
        since = now - timedelta(hours=lookback)
        triggered = 0

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            his_pid = str(patient_doc.get("hisPid") or "").strip() or None
            weight_kg = self.engine._get_weight_kg(patient_doc)
            if not weight_kg:
                continue

            intake_events = await self.engine._collect_intake_events(pid_str, since)
            output_events = await self.engine._collect_output_events(pid_str, since)
            if not intake_events and not output_events:
                continue

            by_window: dict[str, dict[str, float | None]] = {}
            max_positive_pct = 0.0
            for h in windows:
                intake_total = self.engine._sum_window(intake_events, h, now)
                output_total = self.engine._sum_window(output_events, h, now)
                net = round(intake_total - output_total, 1)
                pct_fo = round((net / (weight_kg * 1000.0)) * 100.0, 2)
                if pct_fo > max_positive_pct:
                    max_positive_pct = pct_fo
                by_window[f"{h}h"] = {
                    "intake_ml": intake_total,
                    "output_ml": output_total,
                    "net_ml": net,
                    "pct_body_weight": pct_fo,
                    "percent_fluid_overload": pct_fo,
                }

            intake_6h = self.engine._sum_window(intake_events, 6, now)
            urine_6h = self.engine._sum_window(output_events, 6, now, category="urine")
            rapid_threshold_ml = round(rapid_ml_per_kg_6h * weight_kg, 1)
            urine_response_threshold_ml = round(urine_resp_ml_per_kg_h * weight_kg * 6.0, 1)
            rapid_intake = intake_6h >= rapid_threshold_ml
            no_urine_response = urine_6h < urine_response_threshold_ml
            linked = await self.engine._has_recent_aki_or_ards(pid_str, now, linkage_lookback_h)

            if max_positive_pct >= warning_pct:
                severity = "high" if max_positive_pct >= high_pct else "warning"
                if linked:
                    severity = self.engine._upgrade_once(severity)
                rule_id = f"FLUID_OVERLOAD_{str(severity).upper()}"
                if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    net_24h = by_window.get("24h", {}).get("net_ml")
                    reasons = [f"%FO {max_positive_pct:.2f}%"]
                    if rapid_intake and no_urine_response:
                        reasons.append(f"6h大量补液 {intake_6h:.0f}mL 后尿量仅 {urine_6h:.0f}mL")
                    if linked:
                        reasons.append("近24h伴 AKI/ARDS 风险")
                    explanation = await self.engine._build_fluid_explanation(
                        summary=f"患者已出现液体过负荷征象（%FO {max_positive_pct:.2f}%）。",
                        evidence=reasons,
                        suggestion="建议复核累计液体平衡、评估肺水肿/组织水肿，并结合尿量与器官灌注调整补液策略。",
                    )
                    alert = await self.engine._create_alert(
                        rule_id=rule_id,
                        name="液体过负荷风险",
                        category="fluid_balance",
                        alert_type="fluid_balance",
                        severity=str(severity),
                        parameter="percent_fluid_overload",
                        condition={
                            "weight_kg": weight_kg,
                            "warning_pct": warning_pct,
                            "high_pct": high_pct,
                            "linked_aki_ards": linked,
                        },
                        value=round(max_positive_pct, 2),
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        device_id=None,
                        source_time=now,
                        explanation=explanation,
                        extra={
                            "weight_kg": weight_kg,
                            "percent_fluid_overload": round(max_positive_pct, 2),
                            "max_positive_pct_body_weight": round(max_positive_pct, 2),
                            "windows": by_window,
                            "intake_breakdown_24h": {
                                "iv_ml": self.engine._sum_window(intake_events, 24, now, category="iv"),
                                "enteral_ml": self.engine._sum_window(intake_events, 24, now, category="enteral"),
                                "oral_ml": self.engine._sum_window(intake_events, 24, now, category="oral"),
                            },
                            "output_breakdown_24h": {
                                "urine_ml": self.engine._sum_window(output_events, 24, now, category="urine"),
                                "drainage_ml": self.engine._sum_window(output_events, 24, now, category="drainage"),
                                "ultrafiltration_ml": self.engine._sum_window(output_events, 24, now, category="ultrafiltration"),
                                "gi_decompression_ml": self.engine._sum_window(output_events, 24, now, category="gi_decompression"),
                            },
                            "rapid_infusion_check_6h": {
                                "intake_ml": intake_6h,
                                "urine_ml": urine_6h,
                                "rapid_threshold_ml": rapid_threshold_ml,
                                "urine_response_threshold_ml": urine_response_threshold_ml,
                                "triggered": rapid_intake and no_urine_response,
                            },
                            "reasons": reasons,
                        },
                    )
                    if alert:
                        triggered += 1

            responsiveness_lost = await self.engine._assess_fluid_responsiveness_lost(
                pid=pid,
                pid_str=pid_str,
                his_pid=his_pid,
                now=now,
                intake_6h=intake_6h,
                urine_6h=urine_6h,
                rapid_threshold_ml=rapid_threshold_ml,
                urine_response_threshold_ml=urine_response_threshold_ml,
                cfg=fluid_cfg,
            )
            if responsiveness_lost:
                rule_id = "FLUID_RESPONSIVENESS_LOST"
                if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    explanation = await self.engine._build_fluid_explanation(
                        summary="近期大量补液后，乳酸/血压改善不足，液体反应性可能丧失。",
                        evidence=[
                            f"6h入量 {responsiveness_lost.get('intake_6h_ml')}mL",
                            f"MAP变化 {responsiveness_lost.get('map', {}).get('change')} mmHg",
                            f"乳酸比值 {responsiveness_lost.get('lactate', {}).get('ratio')}",
                            f"尿量 {responsiveness_lost.get('urine_6h_ml')}mL",
                        ],
                        suggestion="建议停止经验性继续扩容，优先复核容量反应性并评估升压药/器官灌注策略。",
                    )
                    alert = await self.engine._create_alert(
                        rule_id=rule_id,
                        name="液体反应性可能丧失",
                        category="fluid_balance",
                        alert_type="fluid_responsiveness_lost",
                        severity=str(responsiveness_lost.get("severity") or "high"),
                        parameter="fluid_responsiveness",
                        condition={
                            "intake_6h_ml": intake_6h,
                            "rapid_threshold_ml": rapid_threshold_ml,
                            "urine_response_threshold_ml": urine_response_threshold_ml,
                        },
                        value=responsiveness_lost.get("corroborators"),
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        device_id=None,
                        source_time=now,
                        explanation=explanation,
                        extra=responsiveness_lost,
                    )
                    if alert:
                        triggered += 1

            net_24h = float(by_window.get("24h", {}).get("net_ml") or 0.0)
            deresuscitation = await self.engine._assess_deresuscitation_window(
                pid=pid,
                pid_str=pid_str,
                patient_doc=patient_doc,
                his_pid=his_pid,
                now=now,
                percent_fluid_overload=round(max_positive_pct, 2),
                net_24h=net_24h,
                cfg=fluid_cfg,
            )
            if deresuscitation:
                enhanced_plan = await self.engine._build_deresuscitation_plan(
                    pid=pid,
                    pid_str=pid_str,
                    patient_doc=patient_doc,
                    his_pid=his_pid,
                    now=now,
                    percent_fluid_overload=round(max_positive_pct, 2),
                    net_24h=net_24h,
                    cfg=fluid_cfg,
                )
                deresuscitation.update(enhanced_plan)
                rule_id = "FLUID_DERESUSCITATION_WINDOW"
                if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    explanation = await self.engine._build_fluid_explanation(
                        summary="休克初始复苏阶段可能已过，可考虑转入去复苏策略。",
                        evidence=[
                            f"MAP稳定 {deresuscitation.get('map_series')}",
                            f"乳酸 {deresuscitation.get('lactate', {}).get('baseline')}→{deresuscitation.get('lactate', {}).get('latest')}",
                            f"%FO {deresuscitation.get('percent_fluid_overload')}%",
                            f"24h净平衡 {deresuscitation.get('net_24h_ml')}mL",
                            f"P/F {((deresuscitation.get('pf_ratio') or {}).get('latest'))}",
                        ],
                        suggestion=f"建议评估限制入量、利尿/超滤与每日负平衡目标，当前建议净负平衡 {(deresuscitation.get('recommendation') or {}).get('net_negative_goal_ml_24h')} mL/24h。",
                    )
                    alert = await self.engine._create_alert(
                        rule_id=rule_id,
                        name="可考虑进入去复苏阶段",
                        category="fluid_balance",
                        alert_type="fluid_deresuscitation",
                        severity=str(deresuscitation.get("severity") or "warning"),
                        parameter="deresuscitation_window",
                        condition={
                            "map_stable": True,
                            "lactate_down": True,
                            "sepsis_context": True,
                        },
                        value=round(max_positive_pct, 2),
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        device_id=None,
                        source_time=now,
                        explanation=explanation,
                        extra=deresuscitation,
                    )
                    if alert:
                        triggered += 1

        if triggered > 0:
            self.engine._log_info("液体平衡", triggered)
