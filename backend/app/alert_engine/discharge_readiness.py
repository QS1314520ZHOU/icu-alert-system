"""ICU转出风险评估。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


class DischargeReadinessMixin:
    async def evaluate_discharge_readiness(self, patient_doc: dict) -> dict[str, Any]:
        pid = patient_doc.get("_id")
        his_pid = patient_doc.get("hisPid")
        if not pid:
            return {"risk": "unknown", "score": 0, "checks": {}}
        pid_str = str(pid)
        now = datetime.now()
        since_12h = now - timedelta(hours=12)
        since_24h = now - timedelta(hours=24)
        since_6h = now - timedelta(hours=6)

        high_alerts = await self.db.col("alert_records").count_documents(
            {
                "patient_id": pid_str,
                "created_at": {"$gte": since_12h},
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
        urine_6h = await self._get_urine_rate(pid, patient_doc, 6)
        on_vaso = await self._has_vasopressor(pid)

        current_sofa = await self._calc_sofa(patient_doc, pid, device_id, his_pid) if his_pid else None
        sofa_trend = "stable"
        if current_sofa and current_sofa.get("delta") is not None:
            sofa_delta = current_sofa.get("delta", 0)
            if sofa_delta > 0:
                sofa_trend = "up"
            elif sofa_delta < 0:
                sofa_trend = "down"

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
                "on_vasopressor": on_vaso,
                "fio2": fio2,
                "peep": peep,
                "gcs": gcs,
                "urine_6h_ml_kg_h": urine_6h,
            },
        }

