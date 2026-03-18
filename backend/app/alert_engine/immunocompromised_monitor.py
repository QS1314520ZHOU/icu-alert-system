"""免疫抑制 / 粒缺感染风险分层。"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.utils.labs import _lab_time
from app.utils.parse import _parse_number


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
        from .scanner_immunocompromised_monitor import ImmunocompromisedMonitorScanner

        await ImmunocompromisedMonitorScanner(self).scan()
