"""ICU转出风险评估。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


class DischargeReadinessMixin:
    def _discharge_cfg(self) -> dict[str, Any]:
        cfg = self.config.yaml_cfg.get("alert_engine", {}).get("discharge_readiness", {})
        return cfg if isinstance(cfg, dict) else {}

    async def _monitoring_density(self, pid_str: str, start: datetime, end: datetime) -> int:
        codes = [
            "param_HR",
            "param_resp",
            "param_spo2",
            "param_nibp_s",
            "param_ibp_s",
            "param_nibp_m",
            "param_ibp_m",
            "param_T",
        ]
        return await self.db.col("bedside").count_documents(
            {"pid": pid_str, "time": {"$gte": start, "$lt": end}, "code": {"$in": codes}}
        )

    async def _detect_transfer_candidate_signal(self, patient_doc: dict, pid_str: str, now: datetime) -> dict[str, Any]:
        cfg = self._discharge_cfg()
        candidate_keywords = self._get_cfg_list(
            ("alert_engine", "discharge_readiness", "candidate_keywords"),
            ["转出", "下转", "普通病房", "stepdown", "hdu", "准备转出", "出icu"],
        )
        recent_texts = await self._get_recent_text_events(pid_str, candidate_keywords, hours=24, limit=400)
        if recent_texts:
            latest = recent_texts[0]
            return {
                "candidate": True,
                "type": "text_keyword",
                "time": latest.get("time"),
                "evidence": " ".join(str(latest.get(k) or "") for k in ("code", "strVal", "value")).strip(),
            }

        window_h = float(cfg.get("monitoring_density_window_hours", 6) or 6)
        drop_ratio = float(cfg.get("monitoring_density_drop_ratio", 0.4) or 0.4)
        recent_start = now - timedelta(hours=window_h)
        prev_start = recent_start - timedelta(hours=window_h)
        prev_count = await self._monitoring_density(pid_str, prev_start, recent_start)
        recent_count = await self._monitoring_density(pid_str, recent_start, now)
        if prev_count >= 12 and recent_count <= max(1, int(prev_count * drop_ratio)):
            return {
                "candidate": True,
                "type": "monitoring_deescalation",
                "time": now,
                "evidence": f"最近{window_h:g}h监测记录 {recent_count} 次，前一窗口 {prev_count} 次",
                "recent_count": recent_count,
                "previous_count": prev_count,
            }

        return {"candidate": False, "type": "", "time": None, "evidence": "", "recent_count": recent_count, "previous_count": prev_count}

    async def evaluate_discharge_readiness(self, patient_doc: dict) -> dict[str, Any]:
        cfg = self._discharge_cfg()
        pid = patient_doc.get("_id")
        his_pid = patient_doc.get("hisPid")
        if not pid:
            return {"risk": "unknown", "score": 0, "checks": {}}
        pid_str = str(pid)
        now = datetime.now()
        recent_high_h = float(cfg.get("high_alert_lookback_hours", 12) or 12)
        sofa_h = float(cfg.get("sofa_lookback_hours", 24) or 24)
        urine_h = float(cfg.get("urine_lookback_hours", 6) or 6)
        since_high = now - timedelta(hours=recent_high_h)

        high_alerts = await self.db.col("alert_records").count_documents(
            {
                "patient_id": pid_str,
                "created_at": {"$gte": since_high},
                "severity": {"$in": ["high", "critical"]},
            }
        )

        device_id = await self._get_device_id_for_patient(patient_doc, ["vent"])
        vent_cap = await self._get_latest_device_cap(device_id) if device_id else None
        fio2 = self._vent_param(vent_cap or {}, "fio2", "param_FiO2") if vent_cap else None
        if fio2 is not None and fio2 > 1:
            fio2 = fio2 / 100.0
        peep = self._vent_param_priority(vent_cap or {}, ["peep_measured", "peep_set"], ["param_vent_measure_peep", "param_vent_peep"]) if vent_cap else None
        gcs = await self._get_latest_assessment(pid, "gcs")
        urine_6h = await self._get_urine_rate(pid, patient_doc, int(max(1, urine_h)))
        on_vaso = await self._has_vasopressor(pid)

        current_sofa = await self._calc_sofa(patient_doc, pid, device_id, his_pid) if his_pid else None
        sofa_trend = "stable"
        sofa_delta = None
        if current_sofa and current_sofa.get("delta") is not None:
            sofa_delta = current_sofa.get("delta", 0)
            if sofa_delta > 0:
                sofa_trend = "up"
            elif sofa_delta < 0:
                sofa_trend = "down"

        transfer_signal = await self._detect_transfer_candidate_signal(patient_doc, pid_str, now)
        checks = {
            "recent_high_alerts": high_alerts == 0,
            "sofa_trend_down": sofa_trend != "up",
            "off_vasopressor": not on_vaso,
            "oxygenation_ok": (fio2 is None or fio2 <= 0.4) and (peep is None or peep <= 5),
            "gcs_ok": gcs is None or gcs >= 13,
            "urine_ok": urine_6h is None or urine_6h > 0.5,
        }
        score = sum(1 for v in checks.values() if v)
        if score >= 5 and high_alerts == 0:
            risk = "low"
            label = "低风险（绿灯）"
        elif score >= 3:
            risk = "medium"
            label = "中风险（黄灯，建议延迟 12-24h 或转 HDU）"
        else:
            risk = "high"
            label = "高风险（红灯，不建议现在转出）"

        return {
            "risk": risk,
            "label": label,
            "score": score,
            "checks": checks,
            "context": {
                "recent_high_alerts_count": high_alerts,
                "sofa_trend": sofa_trend,
                "sofa_delta": sofa_delta,
                "sofa_lookback_hours": sofa_h,
                "on_vasopressor": on_vaso,
                "fio2": fio2,
                "peep": peep,
                "gcs": gcs,
                "urine_6h_ml_kg_h": urine_6h,
                "transfer_signal": transfer_signal,
            },
        }

    async def scan_discharge_readiness(self) -> None:
        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        patient_cursor = self.db.col("patient").find(
            self._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "deptCode": 1, "age": 1, "gender": 1, "hisSex": 1},
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        triggered = 0
        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            now = datetime.now()
            signal = await self._detect_transfer_candidate_signal(patient_doc, pid_str, now)
            if not signal.get("candidate"):
                continue

            result = await self.evaluate_discharge_readiness(patient_doc)
            if result.get("risk") not in {"medium", "high"}:
                continue

            rule_id = f"DISCHARGE_READINESS_{str(result.get('risk')).upper()}"
            if await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                continue
            severity = "warning" if result.get("risk") == "medium" else "high"
            alert = await self._create_alert(
                rule_id=rule_id,
                name="转出前稳定性复核",
                category="discharge_readiness",
                alert_type="discharge_readiness_risk",
                severity=severity,
                parameter="transfer_readiness",
                condition={"transfer_candidate": True, "risk": result.get("risk")},
                value=result.get("score"),
                patient_id=pid_str,
                patient_doc=patient_doc,
                source_time=signal.get("time") or now,
                extra={
                    "label": result.get("label"),
                    "checks": result.get("checks"),
                    "context": result.get("context"),
                    "transfer_signal": signal,
                },
            )
            if alert:
                triggered += 1

        if triggered > 0:
            self._log_info("转出风险评估", triggered)
