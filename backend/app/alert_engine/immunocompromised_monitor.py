"""免疫抑制 / 粒缺感染风险分层。"""
from __future__ import annotations

from datetime import datetime, timedelta

from .base import _lab_time, _parse_number


class ImmunocompromisedMonitorMixin:
    def _immuno_cfg(self) -> dict:
        cfg = self._cfg("alert_engine", "immunocompromised_monitor", default={}) or {}
        return cfg if isinstance(cfg, dict) else {}

    async def _recent_drug_names_from_raw(self, pid, hours: int = 24 * 14) -> list[str]:
        pid_str = self._pid_str(pid)
        if not pid_str:
            return []
        since = datetime.now() - timedelta(hours=max(hours, 1))
        cursor = self.db.col("drugExe").find(
            {"pid": pid_str},
            {"drugList": 1, "startTime": 1, "orderTime": 1},
        ).sort("startTime", -1).limit(1200)
        names: list[str] = []
        async for doc in cursor:
            t = doc.get("startTime") or doc.get("orderTime")
            if isinstance(t, datetime) and t < since:
                continue
            for item in doc.get("drugList") or []:
                if isinstance(item, dict) and str(item.get("name") or "").strip():
                    names.append(str(item.get("name") or "").strip())
        return names

    async def _latest_numeric_lab_by_keywords(self, his_pid: str | None, keywords: list[str], hours: int = 72) -> dict | None:
        if not his_pid:
            return None
        since = datetime.now() - timedelta(hours=max(hours, 1))
        cursor = self.db.dc_col("VI_ICU_EXAM_ITEM").find({"hisPid": his_pid}).sort("authTime", -1).limit(2000)
        async for doc in cursor:
            t = _lab_time(doc)
            if not t or t < since:
                continue
            name = " ".join(str(doc.get(k) or "") for k in ("itemCnName", "itemName", "itemCode")).lower()
            if not any(str(k).lower() in name for k in keywords):
                continue
            value = _parse_number(doc.get("result") or doc.get("resultValue") or doc.get("value"))
            if value is None:
                continue
            return {"time": t, "value": value, "name": name}
        return None

    async def _find_first_broad_antibiotic_after(self, pid_str: str, start_time: datetime) -> dict | None:
        _, broad_names = await self._load_antibiotic_dictionary()
        events = await self._get_drug_events(pid_str, start_time)
        for item in events:
            name = str(item.get("name") or "").strip()
            if self._match_name_keywords(name, broad_names):
                return item
        return None

    async def _get_active_neutropenic_bundle_tracker(self, pid_str: str) -> dict | None:
        return await self.db.col("score_records").find_one(
            {
                "patient_id": pid_str,
                "score_type": "sepsis_antibiotic_bundle",
                "bundle_type": "neutropenic_sepsis_1h_antibiotic",
                "is_active": True,
            },
            sort=[("bundle_started_at", -1)],
        )

    async def _start_or_refresh_neutropenic_bundle_tracker(
        self,
        *,
        patient_doc: dict,
        pid_str: str,
        now: datetime,
        trigger_time: datetime,
        anc_value: float | None,
        temp_value: float | None,
        hr: float | None,
        sbp: float | None,
        map_value: float | None,
    ) -> dict:
        cfg = self._cfg("alert_engine", "sepsis_bundle", default={}) or {}
        deadline_1h = trigger_time + timedelta(minutes=int(cfg.get("deadline_minutes", 60)))
        deadline_3h = trigger_time + timedelta(minutes=int(cfg.get("escalation_3h_minutes", 180)))
        payload = {
            "patient_id": pid_str,
            "patient_name": patient_doc.get("name"),
            "bed": patient_doc.get("hisBed"),
            "dept": patient_doc.get("dept") or patient_doc.get("hisDept"),
            "score_type": "sepsis_antibiotic_bundle",
            "bundle_type": "neutropenic_sepsis_1h_antibiotic",
            "bundle_started_at": trigger_time,
            "deadline_1h": deadline_1h,
            "deadline_3h": deadline_3h,
            "status": "pending",
            "is_active": True,
            "compliant_1h": None,
            "source_rules": ["IMMUNO_NEUTROPENIC_SEPSIS"],
            "anc": anc_value,
            "temp": temp_value,
            "hr": hr,
            "sbp": sbp,
            "map": map_value,
            "calc_time": now,
            "updated_at": now,
            "month": now.strftime("%Y-%m"),
            "day": now.strftime("%Y-%m-%d"),
        }
        active = await self._get_active_neutropenic_bundle_tracker(pid_str)
        if active:
            await self.db.col("score_records").update_one({"_id": active["_id"]}, {"$set": payload})
            active.update(payload)
            return active
        payload["created_at"] = now
        res = await self.db.col("score_records").insert_one(payload)
        payload["_id"] = res.inserted_id
        return payload

    async def _evaluate_neutropenic_bundle_compliance(
        self,
        *,
        tracker: dict,
        patient_doc: dict,
        now: datetime,
        first_broad: dict | None,
    ) -> int:
        started = tracker.get("bundle_started_at")
        if not isinstance(started, datetime):
            return 0
        pid_str = str(tracker.get("patient_id") or "")
        if not pid_str:
            return 0
        suppression = self._cfg("alert_engine", "suppression", default={}) or {}
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        if first_broad and isinstance(first_broad.get("time"), datetime):
            elapsed_seconds = (first_broad["time"] - started).total_seconds()
            compliant = elapsed_seconds <= 3600
            await self.db.col("score_records").update_one(
                {"_id": tracker["_id"]},
                {
                    "$set": {
                        "status": "completed" if compliant else "overdue_1h",
                        "compliant_1h": compliant,
                        "is_active": not compliant,
                        "antibiotic_given_at": first_broad["time"],
                        "antibiotic_name": first_broad.get("name"),
                        "resolved_at": first_broad["time"] if compliant else None,
                        "calc_time": now,
                        "updated_at": now,
                    }
                },
            )
            return 0
        if now < tracker.get("deadline_1h", started + timedelta(hours=1)):
            return 0
        if tracker.get("overdue_1h_alerted"):
            return 0

        fired = 0
        rule_id = "IMMUNO_NEUTROPENIC_SEPSIS_ABX_OVER_1H"
        if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
            alert = await self._create_alert(
                rule_id=rule_id,
                name="粒缺性脓毒症经验性广谱抗菌覆盖超1h未执行",
                category="antibiotic_stewardship",
                alert_type="neutropenic_sepsis_abx_overdue_1h",
                severity="critical",
                parameter="neutropenic_sepsis_first_antibiotic",
                condition={"deadline_minutes": 60, "bundle_started_at": started},
                value=round((now - started).total_seconds() / 60.0, 1),
                patient_id=pid_str,
                patient_doc=patient_doc,
                source_time=now,
                extra={
                    "bundle_started_at": started,
                    "elapsed_minutes": round((now - started).total_seconds() / 60.0, 1),
                    "source_rules": ["IMMUNO_NEUTROPENIC_SEPSIS"],
                    "bundle_type": "neutropenic_sepsis_1h_antibiotic",
                },
            )
            if alert:
                fired += 1
        await self.db.col("score_records").update_one(
            {"_id": tracker["_id"]},
            {
                "$set": {
                    "status": "overdue_1h",
                    "overdue_1h_alerted": True,
                    "compliant_1h": False,
                    "calc_time": now,
                    "updated_at": now,
                }
            },
        )
        return fired

    async def scan_immunocompromised_monitor(self) -> None:
        cfg = self._immuno_cfg()
        suppression = self._cfg("alert_engine", "suppression", default={}) or {}
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        patient_cursor = self.db.col("patient").find(
            self._active_patient_query(),
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
            drug_names = await self._recent_drug_names_from_raw(pid, hours=int(cfg.get("drug_lookback_hours", 24 * 14)))
            immuno_keywords = cfg.get("immunosuppressive_keywords", ["环孢素", "他克莫司", "吗替麦考酚酯", "甲氨蝶呤", "化疗", "环磷酰胺", "阿扎胞苷", "移植", "激素"])
            exposure = any(str(k).lower() in " ".join(drug_names).lower() for k in immuno_keywords)

            anc = await self._latest_numeric_lab_by_keywords(his_pid, cfg.get("anc_keywords", ["anc", "中性粒细胞绝对值", "中性粒细胞#", "neut#"]), hours=168)
            lymph = await self._latest_numeric_lab_by_keywords(his_pid, cfg.get("lymphocyte_keywords", ["淋巴细胞绝对值", "lymphocyte", "lymph#"]), hours=168)
            anc_value = float(anc.get("value")) if anc and anc.get("value") is not None else None

            if not exposure and anc_value is None:
                continue

            if anc_value is not None and anc_value < float(cfg.get("neutropenia_threshold", 0.5)):
                rule_id = "IMMUNO_NEUTROPENIA"
                if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self._create_alert(
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

                vitals = await self._get_latest_vitals_by_patient(pid)
                temp = await self._get_latest_param_snapshot_by_pid(pid, codes=[str(self._cfg("vital_signs", "temperature", "code", default="param_T"))])
                temp_code = str(self._cfg("vital_signs", "temperature", "code", default="param_T"))
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
                    first_broad = await self._find_first_broad_antibiotic_after(pid_str, trigger_dt)
                    broad_in_time = bool(first_broad and isinstance(first_broad.get("time"), datetime) and (first_broad["time"] - trigger_dt).total_seconds() <= 3600)
                    tracker = await self._start_or_refresh_neutropenic_bundle_tracker(
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
                    if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self._create_alert(
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
                    triggered += await self._evaluate_neutropenic_bundle_compliance(
                        tracker=tracker,
                        patient_doc=patient_doc,
                        now=datetime.now(),
                        first_broad=first_broad,
                    )

        if triggered > 0:
            self._log_info("免疫抑制感染分层", triggered)
