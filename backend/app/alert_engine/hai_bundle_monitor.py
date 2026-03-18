"""院感预防 bundle 监测。"""
from __future__ import annotations

from datetime import datetime, timedelta

from .base import _lab_time, _parse_number


class HaiBundleMonitorMixin:
    def _hai_cfg(self) -> dict:
        cfg = self._cfg("alert_engine", "hai_bundle", default={}) or {}
        return cfg if isinstance(cfg, dict) else {}

    async def _hai_insert_time(self, pid, keywords: list[str], hours: int = 24 * 30) -> datetime | None:
        if hasattr(self, "_infer_device_insert_time"):
            return await self._infer_device_insert_time(pid, keywords, hours=hours)
        events = await self._get_recent_text_events(pid, keywords, hours=hours, limit=2000)
        times = [x.get("time") for x in events if isinstance(x.get("time"), datetime)]
        return min(times) if times else None

    async def _latest_temp_value(self, pid) -> float | None:
        code = str(self._cfg("vital_signs", "temperature", "code", default="param_T"))
        snap = await self._get_latest_param_snapshot_by_pid(pid, codes=[code])
        if not snap:
            return None
        return (snap.get("params") or {}).get(code)

    async def _has_recent_bedside_keyword(self, pid, keywords: list[str], hours: int = 24) -> bool:
        rows = await self._get_recent_text_events(pid, keywords, hours=hours, limit=400)
        return bool(rows)

    async def _latest_positive_culture(self, his_pid: str | None, keywords: list[str], hours: int = 72) -> dict | None:
        if not his_pid:
            return None
        since = datetime.now() - timedelta(hours=max(hours, 1))
        positive_keywords = ["阳性", "positive", "生长", "检出", "分离出"]
        cursor = self.db.dc_col("VI_ICU_EXAM_ITEM").find({"hisPid": his_pid}).sort("authTime", -1).limit(2000)
        for doc in [d async for d in cursor]:
            t = _lab_time(doc)
            if not t or t < since:
                continue
            name = " ".join(str(doc.get(k) or "") for k in ("itemCnName", "itemName", "itemCode")).lower()
            if not any(str(k).lower() in name for k in keywords):
                continue
            result = str(doc.get("result") or doc.get("resultValue") or "").lower()
            if any(k in result for k in positive_keywords):
                return {"time": t, "name": name, "result": result}
        return None

    async def _has_abnormal_urine(self, his_pid: str | None, hours: int = 72) -> bool:
        if not his_pid:
            return False
        since = datetime.now() - timedelta(hours=max(hours, 1))
        keywords = ["尿白细胞", "白细胞酯酶", "亚硝酸盐", "细菌", "尿培养", "尿常规"]
        abnormal_keywords = ["阳性", "异常", "positive", "+", "检出", "增高"]
        cursor = self.db.dc_col("VI_ICU_EXAM_ITEM").find({"hisPid": his_pid}).sort("authTime", -1).limit(1000)
        async for doc in cursor:
            t = _lab_time(doc)
            if not t or t < since:
                continue
            name = " ".join(str(doc.get(k) or "") for k in ("itemCnName", "itemName", "itemCode")).lower()
            if not any(k in name for k in keywords):
                continue
            result = str(doc.get("result") or doc.get("resultValue") or "").lower()
            if any(k in result for k in abnormal_keywords):
                return True
            num = _parse_number(doc.get("result") or doc.get("resultValue"))
            if num is not None and num > 0:
                return True
        return False

    async def _ventilation_start_time(self, patient_doc: dict) -> datetime | None:
        pid = patient_doc.get("_id")
        pid_str = str(pid) if pid is not None else ""
        if pid_str:
            bind = await self.db.col("deviceBind").find_one(
                {"pid": pid_str, "unBindTime": None, "type": {"$in": ["vent", "Vent", "ventilator", "呼吸机"]}},
                {"bindTime": 1},
                sort=[("bindTime", 1)],
            )
            if bind and isinstance(bind.get("bindTime"), datetime):
                return bind.get("bindTime")
        return await self._hai_insert_time(pid, self._hai_cfg().get("vent_keywords", ["气管插管", "ett", "endotracheal", "机械通气"]))

    async def scan_hai_bundle(self) -> None:
        cfg = self._hai_cfg()
        suppression = self._cfg("alert_engine", "suppression", default={}) or {}
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        patient_cursor = self.db.col("patient").find(
            self._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1},
        )
        patients = [p async for p in patient_cursor]
        now = datetime.now()
        triggered = 0

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            his_pid = str(patient_doc.get("hisPid") or "").strip() or None

            cvc_time = await self._hai_insert_time(pid, cfg.get("cvc_keywords", ["中心静脉", "cvc", "picc", "深静脉"]))
            if cvc_time:
                cvc_days = max(1, (now - cvc_time).days + 1)
                if cvc_days >= int(cfg.get("cvc_review_days", 7)):
                    rule_id = "HAI_CVC_REVIEW"
                    if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self._create_alert(
                            rule_id=rule_id,
                            name="中心静脉导管必要性评估",
                            category="hai_bundle",
                            alert_type="clabsi_bundle_review",
                            severity="warning",
                            parameter="cvc_days",
                            condition={"operator": ">=", "threshold": int(cfg.get("cvc_review_days", 7))},
                            value=cvc_days,
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            source_time=cvc_time,
                            extra={"line_days": cvc_days, "bundle": "CLABSI"},
                        )
                        if alert:
                            triggered += 1

                temp = await self._latest_temp_value(pid)
                blood_culture = await self._latest_positive_culture(his_pid, cfg.get("blood_culture_keywords", ["血培养", "blood culture"]), hours=72)
                if cvc_days >= 3 and temp is not None and float(temp) >= float(cfg.get("fever_threshold", 38.0)) and blood_culture:
                    rule_id = "HAI_CLABSI_SUSPECTED"
                    if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self._create_alert(
                            rule_id=rule_id,
                            name="疑似 CLABSI",
                            category="hai_bundle",
                            alert_type="clabsi_suspected",
                            severity="high",
                            parameter="clabsi_risk",
                            condition={"cvc_days": cvc_days, "fever": temp, "blood_culture_positive": True},
                            value=cvc_days,
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            source_time=blood_culture.get("time") or now,
                            extra={"line_days": cvc_days, "temp": temp, "blood_culture": blood_culture},
                        )
                        if alert:
                            triggered += 1

            foley_time = await self._hai_insert_time(pid, cfg.get("foley_keywords", ["导尿", "foley", "尿管", "导尿管"]))
            if foley_time:
                foley_hours = max((now - foley_time).total_seconds() / 3600.0, 0.0)
                if foley_hours >= float(cfg.get("foley_hours_threshold", 48)) and await self._has_abnormal_urine(his_pid, hours=72):
                    rule_id = "HAI_CAUTI_RISK"
                    if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self._create_alert(
                            rule_id=rule_id,
                            name="CAUTI 风险升高",
                            category="hai_bundle",
                            alert_type="cauti_risk",
                            severity="warning",
                            parameter="foley_hours",
                            condition={"operator": ">=", "threshold": float(cfg.get("foley_hours_threshold", 48))},
                            value=round(foley_hours, 1),
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            source_time=foley_time,
                            extra={"foley_hours": round(foley_hours, 1), "urine_abnormal": True},
                        )
                        if alert:
                            triggered += 1

            vent_time = await self._ventilation_start_time(patient_doc)
            if vent_time:
                vent_days = max(1, (now - vent_time).days + 1)
                missing_items: list[str] = []
                if not await self._has_recent_bedside_keyword(pid, cfg.get("hob_keywords", ["床头抬高", "抬高床头", "半卧位", "30°", "45°"]), hours=24):
                    missing_items.append("床头抬高")
                if not await self._has_recent_bedside_keyword(pid, cfg.get("oral_care_keywords", ["口腔护理", "口护", "口腔清洁"]), hours=24):
                    missing_items.append("口腔护理")
                if vent_days >= 2 and missing_items:
                    rule_id = "HAI_VAP_BUNDLE_MISSING"
                    if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self._create_alert(
                            rule_id=rule_id,
                            name="VAP Bundle 缺项提醒",
                            category="hai_bundle",
                            alert_type="vap_bundle_missing",
                            severity="warning",
                            parameter="vap_bundle",
                            condition={"missing_items": missing_items},
                            value=len(missing_items),
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            source_time=now,
                            extra={"vent_days": vent_days, "missing_items": missing_items},
                        )
                        if alert:
                            triggered += 1

        if triggered > 0:
            self._log_info("HAI Bundle", triggered)
