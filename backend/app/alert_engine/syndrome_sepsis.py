"""脓毒症筛查"""
from __future__ import annotations

from datetime import datetime

from .base import _extract_param


class SepsisMixin:
    async def scan_sepsis(self) -> None:
        patient_cursor = self.db.col("patient").find(
            self._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1},
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        triggered = 0
        now = datetime.now()
        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            device_id = await self._get_device_id_for_patient(patient_doc, ["monitor"])

            gcs = await self._get_latest_assessment(pid, "gcs")
            cap_codes = ["param_resp", "param_nibp_s", "param_ibp_s", "param_nibp_m", "param_ibp_m"]
            latest_cap = await self._get_latest_param_snapshot_by_pid(pid, codes=cap_codes)
            if not latest_cap and device_id:
                latest_cap = await self._get_latest_device_cap(device_id, codes=cap_codes)
            if not latest_cap:
                continue

            sbp = self._get_sbp(latest_cap)
            rr = _extract_param(latest_cap, "param_resp")
            qsofa = self._calc_qsofa(sbp, rr, gcs)

            if qsofa >= 2:
                if not await self._is_suppressed(pid_str, "SEPSIS_QSOFA", same_rule_sec, max_per_hour):
                    alert = await self._create_alert(
                        rule_id="SEPSIS_QSOFA",
                        name="疑似脓毒症(qSOFA≥2)",
                        category="syndrome",
                        alert_type="qsofa",
                        severity="warning",
                        parameter="qsofa",
                        condition={"qsofa": qsofa},
                        value=qsofa,
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        device_id=device_id,
                        source_time=now,
                        extra={"sbp": sbp, "rr": rr, "gcs": gcs},
                    )
                    if alert:
                        triggered += 1

            his_pid = patient_doc.get("hisPid")
            sofa = await self._calc_sofa(patient_doc, pid, device_id, his_pid)
            if sofa:
                delta = sofa["delta"]
                if delta >= 2 and (sofa.get("baseline_available") or qsofa >= 2):
                    if not await self._is_suppressed(pid_str, "SEPSIS_SOFA", same_rule_sec, max_per_hour):
                        alert = await self._create_alert(
                            rule_id="SEPSIS_SOFA",
                            name="脓毒症确认(SOFA Δ≥2)",
                            category="syndrome",
                            alert_type="sofa",
                            severity="high",
                            parameter="sofa",
                            condition={"delta": delta, "score": sofa["score"]},
                            value=sofa["score"],
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=device_id,
                            source_time=now,
                            extra=sofa,
                        )
                        if alert:
                            triggered += 1

                lactate = sofa.get("labs", {}).get("lac", {}).get("value")
                map_value = sofa.get("vitals", {}).get("map")
                on_vaso = await self._has_vasopressor(pid)
                if on_vaso and lactate is not None and lactate >= 2 and (map_value is None or map_value < 65):
                    if not await self._is_suppressed(pid_str, "SEPSIS_SHOCK", same_rule_sec, max_per_hour):
                        alert = await self._create_alert(
                            rule_id="SEPSIS_SHOCK",
                            name="脓毒性休克",
                            category="syndrome",
                            alert_type="septic_shock",
                            severity="critical",
                            parameter="shock",
                            condition={"vasopressor": True, "lactate": lactate, "map": map_value},
                            value=lactate,
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=device_id,
                            source_time=now,
                            extra={"sofa": sofa},
                        )
                        if alert:
                            triggered += 1

        if triggered > 0:
            self._log_info("脓毒症预警", triggered)

