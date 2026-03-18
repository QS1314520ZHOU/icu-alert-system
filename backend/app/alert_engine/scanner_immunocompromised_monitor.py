from __future__ import annotations

from datetime import datetime, timedelta
from app.utils.labs import _lab_time
from app.utils.parse import _parse_number
from .scanners import BaseScanner, ScannerSpec


class ImmunocompromisedMonitorScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="immunocompromised_monitor",
                interval_key="immunocompromised_monitor",
                default_interval=600,
                initial_delay=52,
            ),
        )

    async def scan(self) -> None:
        cfg = self.engine._immuno_cfg()
        suppression = self.engine._cfg("alert_engine", "suppression", default={}) or {}
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "age": 1},
        )
        patients = [p async for p in patient_cursor]
        triggered = 0

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            his_pid = str(patient_doc.get("hisPid") or "").strip() or None
            drug_names = await self.engine._recent_drug_names_from_raw(pid, hours=int(cfg.get("drug_lookback_hours", 24 * 14)))
            immuno_keywords = cfg.get("immunosuppressive_keywords", ["环孢素", "他克莫司", "吗替麦考酚酯", "甲氨蝶呤", "化疗", "环磷酰胺", "阿扎胞苷", "移植", "激素"])
            exposure = any(str(k).lower() in " ".join(drug_names).lower() for k in immuno_keywords)

            anc = await self.engine._latest_numeric_lab_by_keywords(his_pid, cfg.get("anc_keywords", ["anc", "中性粒细胞绝对值", "中性粒细胞#", "neut#"]), hours=168)
            lymph = await self.engine._latest_numeric_lab_by_keywords(his_pid, cfg.get("lymphocyte_keywords", ["淋巴细胞绝对值", "lymphocyte", "lymph#"]), hours=168)
            anc_value = float(anc.get("value")) if anc and anc.get("value") is not None else None

            if not exposure and anc_value is None:
                continue

            if anc_value is not None and anc_value < float(cfg.get("neutropenia_threshold", 0.5)):
                rule_id = "IMMUNO_NEUTROPENIA"
                if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self.engine._create_alert(
                        rule_id=rule_id,
                        name="粒细胞缺乏警戒",
                        category="immunocompromised",
                        alert_type="neutropenia_alert",
                        severity="high",
                        parameter="anc",
                        condition={"operator": "<", "threshold": float(cfg.get("neutropenia_threshold", 0.5))},
                        value=anc_value,
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        source_time=anc.get("time") if anc else datetime.now(),
                        extra={"anc": anc, "lymphocyte": lymph, "immunosuppressive_exposure": exposure, "drug_names": drug_names[:8]},
                    )
                    if alert:
                        triggered += 1

                vitals = await self.engine._get_latest_vitals_by_patient(pid)
                temp = await self.engine._get_latest_param_snapshot_by_pid(pid, codes=[str(self.engine._cfg("vital_signs", "temperature", "code", default="param_T"))])
                temp_code = str(self.engine._cfg("vital_signs", "temperature", "code", default="param_T"))
                temp_value = ((temp or {}).get("params") or {}).get(temp_code)
                hr = vitals.get("hr")
                sbp = vitals.get("sbp")
                map_value = vitals.get("map")
                trigger_time = vitals.get("time") or (anc.get("time") if anc else datetime.now())
                if (
                    (temp_value is not None and float(temp_value) >= float(cfg.get("fever_threshold_c", 38.0)))
                    or (map_value is not None and float(map_value) < float(cfg.get("map_threshold", 65)))
                    or (sbp is not None and float(sbp) < float(cfg.get("sbp_threshold", 90)))
                    or (hr is not None and float(hr) >= float(cfg.get("tachy_threshold", 110)))
                ):
                    trigger_dt = trigger_time if isinstance(trigger_time, datetime) else datetime.now()
                    first_broad = await self.engine._find_first_broad_antibiotic_after(pid_str, trigger_dt)
                    broad_in_time = bool(first_broad and isinstance(first_broad.get("time"), datetime) and (first_broad["time"] - trigger_dt).total_seconds() <= 3600)
                    tracker = await self.engine._start_or_refresh_neutropenic_bundle_tracker(
                        patient_doc=patient_doc,
                        pid_str=pid_str,
                        now=datetime.now(),
                        trigger_time=trigger_dt,
                        anc_value=anc_value,
                        temp_value=temp_value,
                        hr=hr,
                        sbp=sbp,
                        map_value=map_value,
                    )
                    rule_id = "IMMUNO_NEUTROPENIC_SEPSIS"
                    if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self.engine._create_alert(
                            rule_id=rule_id,
                            name="疑似粒缺性脓毒症",
                            category="immunocompromised",
                            alert_type="neutropenic_sepsis",
                            severity="critical",
                            parameter="neutropenic_sepsis_risk",
                            condition={"anc_lt": float(cfg.get("neutropenia_threshold", 0.5)), "fever_threshold": float(cfg.get("fever_threshold_c", 38.0))},
                            value=anc_value,
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            source_time=trigger_dt,
                            extra={
                                "anc": anc_value,
                                "temp": temp_value,
                                "hr": hr,
                                "sbp": sbp,
                                "map": map_value,
                                "immunosuppressive_exposure": exposure,
                                "broad_spectrum_in_1h": broad_in_time,
                                "first_broad_spectrum_event": first_broad,
                            },
                        )
                        if alert:
                            triggered += 1
                    triggered += await self.engine._evaluate_neutropenic_bundle_compliance(
                        tracker=tracker,
                        patient_doc=patient_doc,
                        now=datetime.now(),
                        first_broad=first_broad,
                    )

        if triggered > 0:
            self.engine._log_info("免疫抑制感染分层", triggered)
