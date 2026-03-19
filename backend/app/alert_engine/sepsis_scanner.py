from __future__ import annotations

from datetime import datetime

from app.utils.clinical import _extract_param

from .scanners import BaseScanner, ScannerSpec


class SepsisScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="sepsis",
                interval_key="sepsis",
                default_interval=300,
                initial_delay=15,
            ),
        )

    async def scan(self) -> None:
        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1},
        )
        patients = [patient async for patient in patient_cursor]
        if not patients:
            return

        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        triggered = 0
        now = datetime.now()
        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            device_id = await self.engine._get_device_id_for_patient(patient_doc, ["monitor"])

            gcs = await self.engine._get_latest_assessment(pid, "gcs")
            cap_codes = ["param_resp", "param_nibp_s", "param_ibp_s", "param_nibp_m", "param_ibp_m"]
            latest_cap = await self.engine._get_latest_param_snapshot_by_pid(pid, codes=cap_codes)
            if not latest_cap and device_id:
                latest_cap = await self.engine._get_latest_device_cap(device_id, codes=cap_codes)
            if not latest_cap:
                continue

            sbp = self.engine._get_sbp(latest_cap)
            rr = _extract_param(latest_cap, "param_resp")
            qsofa = self.engine._calc_qsofa(sbp, rr, gcs)
            qsofa_triggered = qsofa >= 2

            if qsofa_triggered:
                if not await self.engine._is_suppressed(pid_str, "SEPSIS_QSOFA", same_rule_sec, max_per_hour):
                    alert = await self.engine._create_alert(
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
            sofa = await self.engine._calc_sofa(patient_doc, pid, device_id, his_pid)
            sofa_triggered = False
            if sofa:
                delta = sofa["delta"]
                sofa_triggered = delta >= 2 and (sofa.get("baseline_available") or qsofa_triggered)
                if sofa_triggered:
                    if not await self.engine._is_suppressed(pid_str, "SEPSIS_SOFA", same_rule_sec, max_per_hour):
                        alert = await self.engine._create_alert(
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
                on_vaso = await self.engine._has_vasopressor(pid)
                if on_vaso and lactate is not None and lactate >= 2 and (map_value is None or map_value < 65):
                    if not await self.engine._is_suppressed(pid_str, "SEPSIS_SHOCK", same_rule_sec, max_per_hour):
                        alert = await self.engine._create_alert(
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

            tracker = await self.engine._start_or_refresh_sepsis_bundle_tracker(
                patient_doc=patient_doc,
                pid_str=pid_str,
                now=now,
                qsofa_triggered=qsofa_triggered,
                qsofa=qsofa,
                sbp=sbp,
                rr=rr,
                gcs=gcs,
                sofa_triggered=sofa_triggered,
                sofa=sofa,
            )
            if not tracker:
                tracker = await self.engine._get_active_sepsis_bundle_tracker(pid_str)
            triggered += await self.engine._evaluate_sepsis_bundle_tracker(
                tracker=tracker,
                patient_doc=patient_doc,
                pid_str=pid_str,
                his_pid=his_pid,
                device_id=device_id,
                now=now,
                same_rule_sec=same_rule_sec,
                max_per_hour=max_per_hour,
            )

        if triggered > 0:
            self.engine._log_info("脓毒症预警", triggered)
