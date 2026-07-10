from __future__ import annotations

from datetime import datetime
from .scanners import BaseScanner, ScannerSpec


class HemodynamicAdvisorScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="hemodynamic_advisor",
                interval_key="hemodynamic_advisor",
                default_interval=300,
                initial_delay=55,
            ),
        )

    async def scan(self) -> None:
        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {"_id": 1, "name": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "height": 1, "heightCm": 1},
        )
        patients = [p async for p in patient_cursor]
        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        triggered = 0

        ppv_codes = ["param_ppv", "ppv", "PPV"]
        svv_codes = ["param_svv", "svv", "SVV"]
        rhythm_codes = ["param_xinLvLv", "rhythm_type", "param_rhythm_type"]

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            snapshot = await self.engine._get_latest_param_snapshot_by_pid(pid, codes=ppv_codes + svv_codes)
            if not snapshot:
                continue
            ppv = None
            svv = None
            for c in ppv_codes:
                ppv = snapshot["params"].get(c)
                if ppv is not None:
                    break
            for c in svv_codes:
                svv = snapshot["params"].get(c)
                if svv is not None:
                    break
            if ppv is None and svv is None:
                continue

            device_id = await self.engine._get_device_id_for_patient(patient_doc, ["vent"])
            vent_cap = await self.engine._get_latest_device_cap(device_id) if device_id else None
            vte = self.engine._vent_param_priority(vent_cap or {}, ["vte", "vt_set"], ["param_vent_vt", "param_vent_set_vt"]) if vent_cap else None
            rr_set = self.engine._vent_param(vent_cap or {}, "rr_set", "param_HuXiPinLv") if vent_cap else None
            rr_measured = self.engine._vent_param(vent_cap or {}, "rr_measured", "param_vent_resp") if vent_cap else None
            weight = self.engine._get_patient_weight(patient_doc) or 70.0
            vt_ml_kg = round(vte / weight, 2) if (vte is not None and weight > 0) else None

            rhythm_text = ""
            rhythm_doc = await self.engine.db.col("bedside").find_one(
                {"pid": pid_str, "code": {"$in": rhythm_codes}},
                sort=[("time", -1)],
            )
            if rhythm_doc:
                rhythm_text = str(rhythm_doc.get("strVal") or rhythm_doc.get("value") or "")
            sinus = not any(k in rhythm_text.lower() for k in ["房颤", "af", "arrhythmia", "irregular"])
            spontaneous = bool(rr_measured and rr_set and rr_measured > rr_set + 2)
            prerequisites_ok = sinus and (vt_ml_kg is not None and vt_ml_kg >= 8.0) and (not spontaneous)

            value = ppv if ppv is not None else svv
            if value is None:
                continue
            if value < 9 and (svv is None or svv < 12):
                continue

            message = ""
            severity = "warning"
            if not prerequisites_ok:
                message = "PPV/SVV 前提条件不足（需窦性心律、VT≥8 mL/kg、无自主呼吸）"
            elif (ppv is not None and ppv > 13) or (svv is not None and svv > 12):
                message = "可能有容量反应性，建议液体负荷试验"
                if (ppv is not None and ppv > 15) and await self.engine._has_recent_drug(pid, ["去甲肾上腺素", "norepinephrine"], hours=12):
                    severity = "high"
                    message = "血管活性药物使用中且仍有容量空间——优先评估补液后再调升压药"
            elif (ppv is not None and 9 <= ppv <= 13):
                message = "PPV灰区，建议PLR试验确认"
            else:
                message = "容量反应性低，补液可能无效"

            rule_id = "HEMODYNAMIC_FLUID_RESPONSIVENESS"
            if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                continue
            alert = await self.engine._create_alert(
                rule_id=rule_id,
                name="血流动力学容量反应性评估",
                category="hemodynamic",
                alert_type="fluid_responsiveness",
                severity=severity,
                parameter="ppv_svv",
                condition={"ppv": ppv, "svv": svv, "prerequisites_ok": prerequisites_ok},
                value=value,
                patient_id=pid_str,
                patient_doc=patient_doc,
                device_id=device_id,
                source_time=snapshot.get("time") or datetime.now(),
                extra={
                    "ppv": ppv,
                    "svv": svv,
                    "vt_ml_kg": vt_ml_kg,
                    "sinus_rhythm": sinus,
                    "spontaneous_breathing": spontaneous,
                    "message": message,
                },
            )
            if alert:
                triggered += 1

        if triggered > 0:
            self.engine._log_info("血流动力学建议", triggered)
