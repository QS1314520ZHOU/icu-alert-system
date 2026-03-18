"""右心功能恶化早期预警。"""
from __future__ import annotations

from datetime import datetime, timedelta


class RightHeartMonitorMixin:
    def _right_heart_cfg(self) -> dict:
        cfg = self._cfg("alert_engine", "right_heart_monitor", default={}) or {}
        return cfg if isinstance(cfg, dict) else {}

    async def _get_cvp_trend(self, pid, since: datetime) -> dict:
        codes = ["param_cvp", "cvp", "CVP"]
        series = []
        for code in codes:
            rows = await self._get_param_series_by_pid(pid, code, since, prefer_device_types=["monitor"], limit=200)
            if rows:
                series = rows
                break
        values = [float(row.get("value")) for row in series if row.get("value") is not None]
        if len(values) < 2:
            return {"latest": None, "baseline": None, "delta": None, "series": []}
        baseline = sum(values[: min(3, len(values))]) / min(3, len(values))
        latest = sum(values[-min(3, len(values)) :]) / min(3, len(values))
        return {
            "latest": round(latest, 2),
            "baseline": round(baseline, 2),
            "delta": round(latest - baseline, 2),
            "series": values[-6:],
        }

    async def _liver_kidney_worsening(self, patient_doc: dict, pid, his_pid: str | None) -> dict:
        result = {"aki_stage": None, "bilirubin_latest": None, "bilirubin_ratio": None, "worsening": False}
        aki = await self._calc_aki_stage(patient_doc, pid, his_pid) if his_pid else None
        if aki:
            result["aki_stage"] = aki.get("stage")
            if (aki.get("stage") or 0) >= 2:
                result["worsening"] = True
        if his_pid:
            bil_series = await self._get_lab_series(his_pid, "bil", datetime.now() - timedelta(hours=72), limit=60)
            if bil_series:
                latest = bil_series[-1].get("value")
                baseline = min(float(row.get("value")) for row in bil_series if row.get("value") is not None)
                ratio = round(float(latest) / float(baseline), 2) if latest is not None and baseline not in (None, 0) else None
                result["bilirubin_latest"] = latest
                result["bilirubin_ratio"] = ratio
                if ratio is not None and ratio >= 1.5:
                    result["worsening"] = True
        return result

    async def scan_right_heart_monitor(self) -> None:
        cfg = self._right_heart_cfg()
        suppression = self._cfg("alert_engine", "suppression", default={}) or {}
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        now = datetime.now()

        patient_cursor = self.db.col("patient").find(
            self._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "clinicalDiagnosis": 1, "admissionDiagnosis": 1},
        )
        patients = [p async for p in patient_cursor]
        triggered = 0

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            his_pid = str(patient_doc.get("hisPid") or "").strip() or None
            cvp = await self._get_cvp_trend(pid, now - timedelta(hours=int(cfg.get("cvp_window_hours", 24))))
            bnp = await self._get_bnp_trend(his_pid, now, hours=int(cfg.get("bnp_window_hours", 72))) if hasattr(self, "_get_bnp_trend") else {}
            active_bind = await self._get_active_vent_bind(pid_str) if hasattr(self, "_get_active_vent_bind") else None
            cap = await self._get_latest_device_cap(active_bind.get("deviceID")) if active_bind else None
            peep = self._vent_param_priority(cap or {}, ["peep_measured", "peep_set"], ["param_vent_measure_peep", "param_vent_peep"]) if cap else None
            pe_alert = await self._get_latest_active_alert(pid_str, ["pe_suspected", "pe_wells_high"], hours=72)
            organ = await self._liver_kidney_worsening(patient_doc, pid, his_pid)

            factors: list[str] = []
            if cvp.get("delta") is not None and float(cvp["delta"]) >= float(cfg.get("cvp_rise_threshold", 3)):
                factors.append(f"CVP {cvp.get('baseline')}→{cvp.get('latest')} cmH2O")
            if (bnp.get("ratio") or 0) >= float(cfg.get("bnp_ratio_threshold", 2.0)):
                factors.append(f"BNP {bnp.get('baseline')}→{bnp.get('latest')} (x{bnp.get('ratio')})")
            if peep is not None and float(peep) >= float(cfg.get("peep_threshold", 10)):
                factors.append(f"PEEP {peep} cmH2O")
            if pe_alert:
                factors.append("近72h 存在 PE/右心负荷风险报警")
            if organ.get("worsening"):
                if organ.get("aki_stage") is not None and organ.get("aki_stage") >= 2:
                    factors.append(f"AKI stage {organ.get('aki_stage')}")
                if organ.get("bilirubin_ratio") is not None and organ.get("bilirubin_ratio") >= 1.5:
                    factors.append(f"胆红素倍增 x{organ.get('bilirubin_ratio')}")

            if len(factors) < int(cfg.get("min_factor_count", 2)):
                continue

            severity = "critical" if len(factors) >= int(cfg.get("critical_factor_count", 4)) else "high"
            rule_id = "RIGHT_HEART_DETERIORATION"
            if await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                continue

            explanation = await self._polish_structured_alert_explanation(
                {
                    "summary": "患者出现右心负荷/右心功能恶化的组合信号。",
                    "evidence": factors[:5],
                    "suggestion": "建议尽快复核容量状态、床旁超声/心超、PEEP策略与是否存在肺栓塞，并评估肝肾淤血表现。",
                    "text": "",
                }
            )
            alert = await self._create_alert(
                rule_id=rule_id,
                name="右心功能恶化预警",
                category="hemodynamic",
                alert_type="right_heart_deterioration",
                severity=severity,
                parameter="right_heart_risk",
                condition={
                    "cvp_rise_threshold": float(cfg.get("cvp_rise_threshold", 3)),
                    "bnp_ratio_threshold": float(cfg.get("bnp_ratio_threshold", 2.0)),
                    "peep_threshold": float(cfg.get("peep_threshold", 10)),
                },
                value=len(factors),
                patient_id=pid_str,
                patient_doc=patient_doc,
                device_id=active_bind.get("deviceID") if active_bind else None,
                source_time=now,
                extra={
                    "factor_count": len(factors),
                    "factors": factors,
                    "cvp": cvp,
                    "bnp": bnp,
                    "peep": peep,
                    "recent_pe_alert": bool(pe_alert),
                    "organ_worsening": organ,
                },
                explanation=explanation,
            )
            if alert:
                triggered += 1

        if triggered > 0:
            self._log_info("右心功能监测", triggered)
