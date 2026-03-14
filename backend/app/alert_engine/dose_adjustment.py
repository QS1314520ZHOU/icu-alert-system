"""肾功能相关高危药剂量调整提醒。"""
from __future__ import annotations

from datetime import datetime


class DoseAdjustmentMixin:
    RENAL_DRUG_TABLE = [
        {"name": "万古霉素", "keywords": ["万古霉素", "vancomycin"], "suggestion": "建议结合TDM与肾功能调整给药间隔"},
        {"name": "氨基糖苷类", "keywords": ["阿米卡星", "庆大霉素", "妥布霉素", "依替米星"], "suggestion": "建议延长间隔并结合TDM"},
        {"name": "亚胺培南", "keywords": ["亚胺培南", "imipenem"], "suggestion": "eGFR 10-25：可考虑 0.25-0.5g q6-8h"},
        {"name": "美罗培南", "keywords": ["美罗培南", "meropenem"], "suggestion": "美罗培南 eGFR 10-25：1g q12h → 0.5g q12h"},
        {"name": "氟康唑", "keywords": ["氟康唑", "fluconazole"], "suggestion": "负荷后维持剂量常需减半"},
        {"name": "阿昔洛韦", "keywords": ["阿昔洛韦", "acyclovir"], "suggestion": "重度肾损害需显著延长间隔"},
        {"name": "依诺肝素", "keywords": ["依诺肝素", "enoxaparin"], "suggestion": "eGFR <30 时考虑减量或改 UFH"},
    ]

    async def scan_dose_adjustment(self) -> None:
        patient_cursor = self.db.col("patient").find(
            self._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "age": 1, "gender": 1, "hisSex": 1},
        )
        patients = [p async for p in patient_cursor]
        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        triggered = 0

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            his_pid = patient_doc.get("hisPid")
            if not pid or not his_pid:
                continue
            pid_str = str(pid)
            labs = await self._get_latest_labs_map(his_pid, lookback_hours=72)
            if not labs:
                continue
            aki = await self._calc_aki_stage(patient_doc, pid, his_pid)
            crrt = await self._get_device_id_for_patient(patient_doc, ["crrt"])
            cr = labs.get("cr", {}).get("value")
            egfr = labs.get("egfr", {}).get("value") or self._estimate_egfr(patient_doc, cr)
            renal_risk = bool((egfr is not None and egfr < 30) or (aki and aki.get("stage", 0) >= 2) or crrt)
            if not renal_risk:
                continue

            recent_docs = await self._get_recent_drug_docs_window(pid, hours=24, limit=600)
            for drug in self.RENAL_DRUG_TABLE:
                matched = [d for d in recent_docs if any(k.lower() in self._drug_text(d).lower() for k in drug["keywords"])]
                if not matched:
                    continue
                latest = matched[-1]
                dose_desc = " ".join(str(latest.get(k) or "") for k in ("dose", "doseUnit", "frequency")).strip() or "当前剂量待核对"
                rule_id = f"RENAL_DOSE_{drug['name']}"
                if await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    continue
                alert = await self._create_alert(
                    rule_id=rule_id,
                    name=f"{drug['name']}需评估肾功能剂量调整",
                    category="dose_adjustment",
                    alert_type="renal_dose_adjustment",
                    severity="high",
                    parameter=drug["name"],
                    condition={"renal_risk": True},
                    value=egfr if egfr is not None else (aki.get("stage") if aki else None),
                    patient_id=pid_str,
                    patient_doc=patient_doc,
                    source_time=latest.get("_event_time") or datetime.now(),
                    extra={
                        "drug_name": drug["name"],
                        "current_dose": dose_desc,
                        "suggestion": drug["suggestion"],
                        "reference": "KDIGO / 药品说明书 / 肾功能剂量调整常规参考",
                        "eGFR": egfr,
                        "aki_stage": aki.get("stage") if aki else None,
                        "on_crrt": bool(crrt),
                    },
                )
                if alert:
                    triggered += 1

        if triggered > 0:
            self._log_info("肾功能剂量调整", triggered)

