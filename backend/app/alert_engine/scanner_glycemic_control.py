from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from typing import Any
def _parse_dt(value: Any) -> datetime | None:
    if not value:
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
from .scanners import BaseScanner, ScannerSpec


class GlycemicControlScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="glycemic_control",
                interval_key="glycemic_control",
                default_interval=300,
                initial_delay=41,
            ),
        )

    async def scan(self) -> None:
        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        cfg = self.engine.config.yaml_cfg.get("alert_engine", {}).get("glycemic_control", {})
        cv_warning_pct = float(cfg.get("cv_warning_pct", 36))
        low_warn = float(cfg.get("low_warning_mmol", 3.9))
        low_critical = float(cfg.get("low_critical_mmol", 2.2))
        drop_rate_warn = float(cfg.get("drop_rate_warning_mmol_per_h", 3))
        insulin_recheck_hours = float(cfg.get("insulin_recheck_hours", 2))
        high_threshold = float(cfg.get("high_threshold_mmol", 10))
        high_consecutive = int(cfg.get("high_consecutive_count", 3))
        insulin_lookback_hours = float(cfg.get("insulin_lookback_hours", 12))
        min_points_for_cv = int(cfg.get("min_points_for_cv", 4))

        insulin_keywords = self.engine._get_cfg_list(
            ("alert_engine", "glycemic_control", "insulin_keywords"),
            ["胰岛素", "insulin", "门冬胰岛素", "甘精胰岛素", "赖脯胰岛素", "地特胰岛素"],
        )
        pump_keywords = self.engine._get_cfg_list(
            ("alert_engine", "glycemic_control", "pump_keywords"),
            ["泵", "微泵", "泵入", "泵注", "insulin pump", "pump"],
        )
        glucose_codes = self.engine._get_cfg_list(
            ("alert_engine", "data_mapping", "glucose", "codes"),
            ["param_blood_glucose", "param_glu", "param_血糖", "blood_glucose"],
        )

        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "deptCode": 1},
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        now = datetime.now()
        since_24h = now - timedelta(hours=24)
        since_12h = now - timedelta(hours=max(insulin_lookback_hours, 12))
        triggered = 0

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            his_pid = str(patient_doc.get("hisPid") or "").strip()

            bedside_points = await self.engine._get_bedside_glucose_points(pid_str, since_24h, glucose_codes)
            lab_points = await self.engine._get_lab_glucose_points(his_pid, since_24h) if his_pid else []
            points = sorted([*bedside_points, *lab_points], key=lambda x: x["time"])
            if not points:
                continue

            latest = points[-1]
            latest_val = float(latest["value"])
            latest_t = latest["time"]

            # (1) 24h CV 波动预警
            cv = self.engine._calc_cv_percent([p["value"] for p in points])
            if cv is not None and len(points) >= min_points_for_cv and cv > cv_warning_pct:
                rule_id = "GLU_VARIABILITY_HIGH"
                if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self.engine._create_alert(
                        rule_id=rule_id,
                        name="血糖波动风险升高(CV异常)",
                        category="glycemic_control",
                        alert_type="glucose_variability",
                        severity="warning",
                        parameter="glucose_cv",
                        condition={"operator": ">", "threshold": cv_warning_pct, "window_h": 24},
                        value=cv,
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        device_id=None,
                        source_time=latest_t,
                        extra={"cv_percent": cv, "points_24h": len(points), "latest_glucose": latest_val},
                    )
                    if alert:
                        triggered += 1

            # (2) 低血糖连续监测 + 快速下降预警
            low_sev = None
            low_rule = None
            low_name = None
            if latest_val < low_critical:
                low_sev = "critical"
                low_rule = "GLU_HYPO_CRITICAL"
                low_name = "重度低血糖"
            elif latest_val < low_warn:
                low_sev = "warning"
                low_rule = "GLU_HYPO_WARNING"
                low_name = "低血糖"
            if low_rule and low_sev and low_name:
                if not await self.engine._is_suppressed(pid_str, low_rule, same_rule_sec, max_per_hour):
                    alert = await self.engine._create_alert(
                        rule_id=low_rule,
                        name=low_name,
                        category="glycemic_control",
                        alert_type="hypoglycemia",
                        severity=low_sev,
                        parameter="glucose",
                        condition={"operator": "<", "threshold": low_critical if low_sev == "critical" else low_warn},
                        value=latest_val,
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        device_id=None,
                        source_time=latest_t,
                        extra={"latest_glucose": latest_val, "unit": "mmol/L"},
                    )
                    if alert:
                        triggered += 1

            # 1小时下降速率
            max_drop_rate = 0.0
            drop_pair: dict | None = None
            for idx in range(1, len(points)):
                p0 = points[idx - 1]
                p1 = points[idx]
                dt_h = (p1["time"] - p0["time"]).total_seconds() / 3600.0
                if dt_h <= 0 or dt_h > 1.0:
                    continue
                dv = float(p0["value"]) - float(p1["value"])
                if dv <= 0:
                    continue
                rate = dv / dt_h
                if rate > max_drop_rate:
                    max_drop_rate = rate
                    drop_pair = {"from": p0, "to": p1, "rate": round(rate, 2)}
            if max_drop_rate > drop_rate_warn and drop_pair:
                rule_id = "GLU_DROP_FAST"
                if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self.engine._create_alert(
                        rule_id=rule_id,
                        name="血糖快速下降预警",
                        category="glycemic_control",
                        alert_type="glucose_drop_fast",
                        severity="warning",
                        parameter="glucose_drop_rate",
                        condition={"operator": ">", "threshold": drop_rate_warn, "window_h": 1},
                        value=round(max_drop_rate, 2),
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        device_id=None,
                        source_time=drop_pair["to"]["time"],
                        extra={
                            "drop_rate_mmol_per_h": round(max_drop_rate, 2),
                            "from": {"time": drop_pair["from"]["time"], "value": drop_pair["from"]["value"]},
                            "to": {"time": drop_pair["to"]["time"], "value": drop_pair["to"]["value"]},
                        },
                    )
                    if alert:
                        triggered += 1

            # 用药记录（胰岛素泵/是否已启胰岛素）
            drug_docs = await self.engine._get_drug_records(pid_str, since_12h)
            insulin_docs = [d for d in drug_docs if self.engine._is_insulin_doc(d, insulin_keywords)]
            insulin_pump_active = any(
                self.engine._is_pump_doc(d, pump_keywords) and (now - d["_event_time"]).total_seconds() <= 6 * 3600
                for d in insulin_docs
            )

            # (3) 胰岛素泵运行中但2h未复测
            if insulin_pump_active:
                no_recheck = (now - latest_t).total_seconds() > insulin_recheck_hours * 3600
                if no_recheck:
                    rule_id = "GLU_RECHECK_OVERDUE_ON_PUMP"
                    if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self.engine._create_alert(
                            rule_id=rule_id,
                            name="胰岛素泵治疗中血糖复查超时",
                            category="glycemic_control",
                            alert_type="glucose_recheck_reminder",
                            severity="warning",
                            parameter="glucose_recheck",
                            condition={"operator": ">", "threshold_hours": insulin_recheck_hours},
                            value=round((now - latest_t).total_seconds() / 3600.0, 2),
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=None,
                            source_time=latest_t,
                            extra={
                                "last_glucose_time": latest_t,
                                "hours_since_last_check": round((now - latest_t).total_seconds() / 3600.0, 2),
                                "insulin_pump_active": True,
                            },
                        )
                        if alert:
                            triggered += 1

            # (4) 连续3次高血糖且未启动胰岛素
            streak = 0
            streak_start_time = None
            for p in reversed(points):  # 从最新往回看
                if p["value"] > high_threshold:
                    streak += 1
                    streak_start_time = p["time"]
                else:
                    break
            if streak >= high_consecutive and streak_start_time:
                has_insulin = any(d["_event_time"] >= streak_start_time for d in insulin_docs)
                if not has_insulin:
                    rule_id = "GLU_PERSISTENT_HIGH_NO_INSULIN"
                    if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self.engine._create_alert(
                            rule_id=rule_id,
                            name="持续高血糖未启胰岛素治疗",
                            category="glycemic_control",
                            alert_type="hyperglycemia_no_insulin",
                            severity="warning",
                            parameter="glucose",
                            condition={
                                "high_threshold_mmol": high_threshold,
                                "consecutive_count": high_consecutive,
                                "insulin_started": False,
                            },
                            value=latest_val,
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=None,
                            source_time=latest_t,
                            extra={
                                "consecutive_high_count": streak,
                                "latest_glucose": latest_val,
                                "high_threshold_mmol": high_threshold,
                                "window_start": streak_start_time,
                            },
                        )
                        if alert:
                            triggered += 1

        if triggered > 0:
            self.engine._log_info("血糖管理", triggered)
