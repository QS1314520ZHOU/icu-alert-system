"""脓毒症筛查与 Hour-1 Bundle 追踪。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


class SepsisMixin:
    def _sepsis_bundle_cfg(self) -> dict:
        cfg = self.config.yaml_cfg.get("alert_engine", {}).get("sepsis_bundle", {})
        return cfg if isinstance(cfg, dict) else {}

    def _sepsis_bundle_score_types(self) -> list[str]:
        return ["sepsis_bundle_tracker", "sepsis_antibiotic_bundle"]

    def _sepsis_bundle_type_names(self) -> list[str]:
        return ["sepsis_hour1_bundle", "sepsis_1h_antibiotic"]

    def _default_sepsis_bundle_elements(self, patient_doc: dict | None = None) -> dict[str, Any]:
        weight_kg = self._get_patient_weight(patient_doc) if hasattr(self, "_get_patient_weight") else None
        target_volume_ml = round(float(weight_kg) * 30.0, 1) if weight_kg is not None else None
        return {
            "first_antibiotic": {"status": "pending", "completed_at": None, "name": None},
            "lactate_measured": {"status": "pending", "completed_at": None, "value": None},
            "blood_culture": {"status": "pending", "completed_at": None, "name": None, "before_antibiotic": None},
            "fluid_resuscitation": {
                "status": "pending",
                "completed_at": None,
                "target_ml": target_volume_ml,
                "delivered_ml": 0.0,
            },
        }

    def _bundle_element_completed(self, item: Any) -> bool:
        return isinstance(item, dict) and str(item.get("status") or "") in {"met", "met_late", "not_applicable"}

    def _bundle_completion_ratio(self, elements: dict[str, Any]) -> float:
        relevant = [value for value in (elements or {}).values() if isinstance(value, dict)]
        if not relevant:
            return 0.0
        completed = sum(1 for item in relevant if self._bundle_element_completed(item))
        return round(completed / len(relevant), 3)

    def _bundle_pending_items(self, elements: dict[str, Any]) -> list[str]:
        labels = {
            "first_antibiotic": "首剂抗生素",
            "lactate_measured": "乳酸测定/复测",
            "blood_culture": "血培养",
            "fluid_resuscitation": "30 mL/kg 晶体液复苏",
        }
        rows: list[str] = []
        for key, item in (elements or {}).items():
            if not isinstance(item, dict):
                continue
            if self._bundle_element_completed(item):
                continue
            rows.append(labels.get(key, key))
        return rows

    async def _get_active_sepsis_bundle_tracker(self, pid_str: str) -> dict | None:
        return await self.db.col("score_records").find_one(
            {
                "patient_id": pid_str,
                "score_type": {"$in": self._sepsis_bundle_score_types()},
                "bundle_type": {"$in": self._sepsis_bundle_type_names()},
                "is_active": True,
            },
            sort=[("bundle_started_at", -1)],
        )

    async def _get_recent_sepsis_bundle_tracker(self, pid_str: str, now: datetime, hours: int) -> dict | None:
        since = now - timedelta(hours=max(1, hours))
        return await self.db.col("score_records").find_one(
            {
                "patient_id": pid_str,
                "score_type": {"$in": self._sepsis_bundle_score_types()},
                "bundle_type": {"$in": self._sepsis_bundle_type_names()},
                "bundle_started_at": {"$gte": since},
            },
            sort=[("bundle_started_at", -1)],
        )

    async def _start_or_refresh_sepsis_bundle_tracker(
        self,
        *,
        patient_doc: dict,
        pid_str: str,
        now: datetime,
        qsofa_triggered: bool,
        qsofa: int,
        sbp: float | None,
        rr: float | None,
        gcs: float | None,
        sofa_triggered: bool,
        sofa: dict | None,
    ) -> dict | None:
        cfg = self._sepsis_bundle_cfg()
        tracker_window_h = int(cfg.get("tracker_reopen_hours", 24))
        active = await self._get_active_sepsis_bundle_tracker(pid_str)
        recent = active or await self._get_recent_sepsis_bundle_tracker(pid_str, now, tracker_window_h)

        source_rules: list[str] = []
        if qsofa_triggered:
            source_rules.append("SEPSIS_QSOFA")
        if sofa_triggered:
            source_rules.append("SEPSIS_SOFA")
        if not source_rules:
            return active

        bundle_elements = recent.get("bundle_elements") if isinstance(recent, dict) and isinstance(recent.get("bundle_elements"), dict) else self._default_sepsis_bundle_elements(patient_doc)
        bundle_summary = {
            "completion_ratio": self._bundle_completion_ratio(bundle_elements),
            "pending_items": self._bundle_pending_items(bundle_elements),
        }
        tracker_patch = {
            "calc_time": now,
            "updated_at": now,
            "score_type": "sepsis_bundle_tracker",
            "bundle_type": "sepsis_hour1_bundle",
            "source_rules": sorted(set(((recent or {}).get("source_rules") or []) + source_rules)),
            "qsofa": qsofa,
            "sbp": sbp,
            "rr": rr,
            "gcs": gcs,
            "sofa_score": (sofa or {}).get("score") if isinstance(sofa, dict) else None,
            "sofa_delta": (sofa or {}).get("delta") if isinstance(sofa, dict) else None,
            "bundle_elements": bundle_elements,
            "bundle_summary": bundle_summary,
        }

        if recent:
            await self.db.col("score_records").update_one({"_id": recent["_id"]}, {"$set": tracker_patch})
            if active:
                recent.update(tracker_patch)
                return recent
            return None

        deadline_1h = now + timedelta(minutes=int(cfg.get("deadline_minutes", 60)))
        deadline_3h = now + timedelta(minutes=int(cfg.get("escalation_3h_minutes", 180)))
        tracker = {
            "patient_id": pid_str,
            "patient_name": patient_doc.get("name"),
            "bed": patient_doc.get("hisBed"),
            "dept": patient_doc.get("dept") or patient_doc.get("hisDept"),
            "score_type": "sepsis_bundle_tracker",
            "bundle_type": "sepsis_hour1_bundle",
            "bundle_started_at": now,
            "deadline_1h": deadline_1h,
            "deadline_3h": deadline_3h,
            "status": "pending",
            "is_active": True,
            "compliant_1h": None,
            "source_rules": source_rules,
            "qsofa": qsofa,
            "sbp": sbp,
            "rr": rr,
            "gcs": gcs,
            "sofa_score": (sofa or {}).get("score") if isinstance(sofa, dict) else None,
            "sofa_delta": (sofa or {}).get("delta") if isinstance(sofa, dict) else None,
            "bundle_elements": self._default_sepsis_bundle_elements(patient_doc),
            "bundle_summary": {"completion_ratio": 0.0, "pending_items": self._bundle_pending_items(self._default_sepsis_bundle_elements(patient_doc))},
            "calc_time": now,
            "created_at": now,
            "updated_at": now,
            "month": now.strftime("%Y-%m"),
            "day": now.strftime("%Y-%m-%d"),
        }
        res = await self.db.col("score_records").insert_one(tracker)
        tracker["_id"] = res.inserted_id
        return tracker

    async def _find_first_antibiotic_after(self, pid_str: str, start_time: datetime) -> dict | None:
        abx_names, _ = await self._load_antibiotic_dictionary()
        fallback = self._get_cfg_list(
            ("alert_engine", "antibiotic_stewardship", "antibiotic_keywords"),
            ["头孢", "青霉素", "美罗培南", "左氧氟沙星", "万古霉素", "阿奇霉素", "哌拉西林"],
        )
        keywords = sorted(set([*(abx_names or []), *(fallback or [])]))
        if not keywords:
            return None
        events = await self._get_drug_events(pid_str, start_time)
        for item in events:
            name = str(item.get("name") or "").strip()
            if self._match_name_keywords(name, keywords):
                return item
        return None

    async def _find_lactate_measurement_after(self, his_pid: str | None, start_time: datetime) -> dict[str, Any] | None:
        if not his_pid:
            return None
        series = await self._get_lab_series(his_pid, "lac", start_time, limit=40)
        if not series:
            return None
        latest = series[0]
        return {"time": latest.get("time"), "value": latest.get("value")}

    async def _find_blood_culture_around_bundle(
        self,
        his_pid: str | None,
        start_time: datetime,
        antibiotic_time: datetime | None,
    ) -> dict[str, Any] | None:
        if not his_pid:
            return None
        lead_hours = float(self._sepsis_bundle_cfg().get("culture_lead_hours", 6) or 6)
        since = start_time - timedelta(hours=max(1, lead_hours))
        rows = await self._get_culture_records(his_pid, since)
        if not rows:
            return None
        blood_keywords = self._get_cfg_list(
            ("alert_engine", "sepsis_bundle", "blood_culture_keywords"),
            ["血培养", "blood culture"],
        )
        candidates = [row for row in rows if self._match_name_keywords(str(row.get("name") or ""), blood_keywords)]
        if not candidates:
            return None
        candidates.sort(key=lambda x: x.get("time") or datetime.min)
        for row in candidates:
            t = row.get("time")
            if not isinstance(t, datetime):
                continue
            if antibiotic_time and t <= antibiotic_time and t >= since:
                return {**row, "before_antibiotic": True}
            if t >= start_time:
                return {**row, "before_antibiotic": antibiotic_time is None or t <= antibiotic_time}
        return None

    def _is_crystalloid_event(self, event: dict[str, Any]) -> bool:
        text = " ".join(
            str(event.get(key) or "")
            for key in ("name", "drugName", "orderName", "drugSpec", "route", "routeName")
        ).lower()
        keywords = self._get_cfg_list(
            ("alert_engine", "sepsis_bundle", "crystalloid_keywords"),
            [
                "氯化钠",
                "生理盐水",
                "平衡液",
                "乳酸林格",
                "林格",
                "葡萄糖氯化钠",
                "sodium chloride",
                "normal saline",
                "ringer",
                "crystalloid",
            ],
        )
        return any(str(keyword).strip().lower() in text for keyword in keywords if str(keyword).strip())

    async def _estimate_crystalloid_resuscitation(
        self,
        pid_str: str,
        patient_doc: dict,
        start_time: datetime,
        now: datetime,
    ) -> dict[str, Any]:
        target_ml_per_kg = float(self._sepsis_bundle_cfg().get("fluid_target_ml_per_kg", 30) or 30)
        weight_kg = self._get_patient_weight(patient_doc) if hasattr(self, "_get_patient_weight") else None
        target_ml = round(weight_kg * target_ml_per_kg, 1) if weight_kg else None
        if not hasattr(self, "_volume_to_ml"):
            return {"completed_at": None, "delivered_ml": 0.0, "target_ml": target_ml}
        docs: list[dict[str, Any]] = []
        pid_value = patient_doc.get("_id") if isinstance(patient_doc, dict) else pid_str
        if hasattr(self, "_get_recent_drugexe_docs"):
            docs = await self._get_recent_drugexe_docs(pid_value, hours=24, limit=1200)
        elif hasattr(self, "_get_recent_drug_docs_window"):
            docs = await self._get_recent_drug_docs_window(pid_value, hours=24, limit=1200)
        delivered = 0.0
        completed_at = None
        for doc in docs:
            event_time = doc.get("_event_time") or doc.get("executeTime") or doc.get("startTime") or doc.get("orderTime")
            if not isinstance(event_time, datetime):
                continue
            if event_time < start_time or event_time > now:
                continue
            if not self._is_crystalloid_event(doc):
                continue
            volume_ml = None
            vol_unit = doc.get("volumeUnit") or doc.get("unit") or doc.get("doseUnit")
            for field in ("volume", "totalVolume", "inputVolume", "infusionVolume"):
                volume_ml = self._volume_to_ml(doc.get(field), vol_unit, assume_ml=True)
                if volume_ml:
                    break
            if not volume_ml and hasattr(self, "_parse_volume_text_ml"):
                for field in ("dose", "drugSpec", "drugName", "orderName"):
                    volume_ml = self._parse_volume_text_ml(doc.get(field))
                    if volume_ml:
                        break
            if not volume_ml:
                continue
            delivered += float(volume_ml)
            if target_ml is not None and delivered >= target_ml and completed_at is None:
                completed_at = event_time
        return {"completed_at": completed_at, "delivered_ml": round(delivered, 1), "target_ml": target_ml}

    def _merge_bundle_elements(
        self,
        tracker: dict,
        *,
        antibiotic: dict | None,
        lactate: dict | None,
        blood_culture: dict | None,
        fluids: dict[str, Any],
        deadline_1h: datetime,
    ) -> dict[str, Any]:
        elements = tracker.get("bundle_elements") if isinstance(tracker.get("bundle_elements"), dict) else self._default_sepsis_bundle_elements()
        next_elements = {**elements}

        antibiotic_time = antibiotic.get("time") if isinstance(antibiotic, dict) else None
        if isinstance(antibiotic_time, datetime):
            next_elements["first_antibiotic"] = {
                "status": "met" if antibiotic_time <= deadline_1h else "met_late",
                "completed_at": antibiotic_time,
                "name": antibiotic.get("name"),
            }

        lactate_time = lactate.get("time") if isinstance(lactate, dict) else None
        if isinstance(lactate_time, datetime):
            next_elements["lactate_measured"] = {
                "status": "met" if lactate_time <= deadline_1h else "met_late",
                "completed_at": lactate_time,
                "value": lactate.get("value"),
            }

        culture_time = blood_culture.get("time") if isinstance(blood_culture, dict) else None
        if isinstance(culture_time, datetime):
            next_elements["blood_culture"] = {
                "status": "met" if culture_time <= deadline_1h else "met_late",
                "completed_at": culture_time,
                "name": blood_culture.get("name"),
                "before_antibiotic": blood_culture.get("before_antibiotic"),
            }

        fluid_completed_at = fluids.get("completed_at")
        delivered_ml = float(fluids.get("delivered_ml") or 0.0)
        target_ml = fluids.get("target_ml")
        if target_ml is None:
            next_elements["fluid_resuscitation"] = {
                "status": "not_applicable",
                "completed_at": None,
                "target_ml": None,
                "delivered_ml": delivered_ml,
            }
        else:
            next_elements["fluid_resuscitation"] = {
                "status": "met" if isinstance(fluid_completed_at, datetime) and fluid_completed_at <= deadline_1h else "met_late" if isinstance(fluid_completed_at, datetime) else "pending",
                "completed_at": fluid_completed_at,
                "target_ml": target_ml,
                "delivered_ml": delivered_ml,
            }

        return next_elements

    async def _build_sepsis_bundle_explanation(
        self,
        *,
        status: str,
        tracker: dict,
        bundle_elements: dict[str, Any] | None = None,
    ) -> dict:
        started = tracker.get("bundle_started_at")
        started_text = started.strftime("%H:%M") if isinstance(started, datetime) else "—"
        elements = bundle_elements if isinstance(bundle_elements, dict) else tracker.get("bundle_elements") if isinstance(tracker.get("bundle_elements"), dict) else {}
        evidence = [f"脓毒症计时起点 {started_text}"]
        if tracker.get("source_rules"):
            evidence.append("触发来源：" + " / ".join(str(x) for x in tracker.get("source_rules") if x))
        if tracker.get("qsofa") is not None:
            evidence.append(f"qSOFA {tracker.get('qsofa')}")
        if tracker.get("sofa_delta") is not None:
            evidence.append(f"SOFA Δ {tracker.get('sofa_delta')}")
        abx = elements.get("first_antibiotic") if isinstance(elements.get("first_antibiotic"), dict) else {}
        if isinstance(abx.get("completed_at"), datetime):
            evidence.append(f"首剂抗生素 {abx.get('name') or ''} @ {abx['completed_at'].strftime('%H:%M')}".strip())
        lactate = elements.get("lactate_measured") if isinstance(elements.get("lactate_measured"), dict) else {}
        if isinstance(lactate.get("completed_at"), datetime):
            evidence.append(f"乳酸 {lactate.get('value')} @ {lactate['completed_at'].strftime('%H:%M')}")
        culture = elements.get("blood_culture") if isinstance(elements.get("blood_culture"), dict) else {}
        if isinstance(culture.get("completed_at"), datetime):
            suffix = "（抗生素前）" if culture.get("before_antibiotic") else ""
            evidence.append(f"血培养 @ {culture['completed_at'].strftime('%H:%M')}{suffix}")
        fluids = elements.get("fluid_resuscitation") if isinstance(elements.get("fluid_resuscitation"), dict) else {}
        target_ml = fluids.get("target_ml")
        delivered_ml = fluids.get("delivered_ml")
        if target_ml is not None:
            evidence.append(f"晶体液复苏 {delivered_ml}/{target_ml} mL")

        pending_text = "、".join(self._bundle_pending_items(elements)) or "无"
        if status == "met":
            summary = "脓毒症 Hour-1 Bundle 已在时限内完成。"
            suggestion = "请继续完成感染灶控制，并将 Bundle 完成时间纳入科室质控统计。"
        elif status == "met_late":
            summary = "脓毒症 Hour-1 Bundle 已完成，但超过 1 小时时限。"
            suggestion = "请记录延迟原因，复盘采样、开立、执行和补液环节的阻滞点。"
        elif status == "overdue_3h":
            summary = f"脓毒症 Hour-1 Bundle 超 3 小时仍未完成，待补项目：{pending_text}。"
            suggestion = "请立即补齐剩余关键处置并升级上报，优先处理首剂抗生素、血培养和复苏不足。"
        else:
            summary = f"脓毒症 Hour-1 Bundle 超 1 小时未完成，待补项目：{pending_text}。"
            suggestion = "请立即补齐剩余关键处置，尤其关注抗生素、血培养、乳酸和复苏是否同步完成。"

        return await self._polish_structured_alert_explanation(
            {
                "summary": summary,
                "evidence": evidence[:5],
                "suggestion": suggestion,
                "text": "",
            }
        )

    async def _evaluate_sepsis_bundle_tracker(
        self,
        *,
        tracker: dict | None,
        patient_doc: dict,
        pid_str: str,
        his_pid: str | None,
        device_id: str | None,
        now: datetime,
        same_rule_sec: int,
        max_per_hour: int,
    ) -> int:
        if not tracker:
            return 0
        started = tracker.get("bundle_started_at")
        if not isinstance(started, datetime):
            return 0

        deadline_1h = tracker.get("deadline_1h") or (started + timedelta(hours=1))
        deadline_3h = tracker.get("deadline_3h") or (started + timedelta(hours=3))
        abx_event = await self._find_first_antibiotic_after(pid_str, started)
        antibiotic_time = abx_event.get("time") if isinstance(abx_event, dict) else None
        lactate = await self._find_lactate_measurement_after(his_pid, started)
        blood_culture = await self._find_blood_culture_around_bundle(his_pid, started, antibiotic_time if isinstance(antibiotic_time, datetime) else None)
        fluids = await self._estimate_crystalloid_resuscitation(pid_str, patient_doc, started, now)
        elements = self._merge_bundle_elements(
            tracker,
            antibiotic=abx_event,
            lactate=lactate,
            blood_culture=blood_culture,
            fluids=fluids,
            deadline_1h=deadline_1h,
        )
        completion_ratio = self._bundle_completion_ratio(elements)
        pending_items = self._bundle_pending_items(elements)
        fully_completed = not pending_items

        if fully_completed:
            completion_times = [
                value.get("completed_at")
                for value in elements.values()
                if isinstance(value, dict) and isinstance(value.get("completed_at"), datetime)
            ]
            completed_at = max(completion_times) if completion_times else now
            within_1h = isinstance(completed_at, datetime) and completed_at <= deadline_1h
            await self.db.col("score_records").update_one(
                {"_id": tracker["_id"]},
                {
                    "$set": {
                        "status": "met" if within_1h else "met_late",
                        "is_active": False,
                        "compliant_1h": bool(within_1h),
                        "resolved_at": now,
                        "bundle_elements": elements,
                        "bundle_summary": {
                            "completion_ratio": completion_ratio,
                            "pending_items": [],
                            "completed_at": completed_at,
                        },
                        "calc_time": now,
                        "updated_at": now,
                    }
                },
            )
            return 0

        fired = 0
        if now >= deadline_3h and not tracker.get("overdue_3h_alerted"):
            rule_id = "SEPSIS_BUNDLE_OVER_3H"
            if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                explanation = await self._build_sepsis_bundle_explanation(status="overdue_3h", tracker=tracker, bundle_elements=elements)
                alert = await self._create_alert(
                    rule_id=rule_id,
                    name="脓毒症 Hour-1 Bundle 超3h未完成",
                    category="bundle",
                    alert_type="sepsis_bundle_overdue_3h",
                    severity="critical",
                    parameter="sepsis_hour1_bundle",
                    condition={"deadline_minutes": 180, "bundle_started_at": started},
                    value=completion_ratio,
                    patient_id=pid_str,
                    patient_doc=patient_doc,
                    device_id=device_id,
                    source_time=now,
                    explanation=explanation,
                    extra={
                        "bundle_started_at": started,
                        "deadline_1h": deadline_1h,
                        "deadline_3h": deadline_3h,
                        "elapsed_minutes": round((now - started).total_seconds() / 60.0, 1),
                        "source_rules": tracker.get("source_rules") or [],
                        "bundle_status": "overdue_3h",
                        "bundle_elements": elements,
                        "pending_items": pending_items,
                        "completion_ratio": completion_ratio,
                    },
                )
                if alert:
                    fired += 1
            await self.db.col("score_records").update_one(
                {"_id": tracker["_id"]},
                {
                    "$set": {
                        "status": "overdue_3h",
                        "overdue_3h_alerted": True,
                        "compliant_1h": False,
                        "is_active": False,
                        "resolved_at": now,
                        "bundle_elements": elements,
                        "bundle_summary": {"completion_ratio": completion_ratio, "pending_items": pending_items},
                        "calc_time": now,
                        "updated_at": now,
                    }
                },
            )
            return fired

        if now >= deadline_1h and not tracker.get("overdue_1h_alerted"):
            rule_id = "SEPSIS_BUNDLE_OVER_1H"
            if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                explanation = await self._build_sepsis_bundle_explanation(status="overdue_1h", tracker=tracker, bundle_elements=elements)
                alert = await self._create_alert(
                    rule_id=rule_id,
                    name="脓毒症 Hour-1 Bundle 超1h未完成",
                    category="bundle",
                    alert_type="sepsis_bundle_overdue_1h",
                    severity="critical",
                    parameter="sepsis_hour1_bundle",
                    condition={"deadline_minutes": 60, "bundle_started_at": started},
                    value=completion_ratio,
                    patient_id=pid_str,
                    patient_doc=patient_doc,
                    device_id=device_id,
                    source_time=now,
                    explanation=explanation,
                    extra={
                        "bundle_started_at": started,
                        "deadline_1h": deadline_1h,
                        "deadline_3h": deadline_3h,
                        "elapsed_minutes": round((now - started).total_seconds() / 60.0, 1),
                        "source_rules": tracker.get("source_rules") or [],
                        "bundle_status": "overdue_1h",
                        "bundle_elements": elements,
                        "pending_items": pending_items,
                        "completion_ratio": completion_ratio,
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
                        "bundle_elements": elements,
                        "bundle_summary": {"completion_ratio": completion_ratio, "pending_items": pending_items},
                        "calc_time": now,
                        "updated_at": now,
                    }
                },
            )
            return fired

        await self.db.col("score_records").update_one(
            {"_id": tracker["_id"]},
            {
                "$set": {
                    "bundle_elements": elements,
                    "bundle_summary": {"completion_ratio": completion_ratio, "pending_items": pending_items},
                    "calc_time": now,
                    "updated_at": now,
                }
            },
        )
        return fired

    async def scan_sepsis(self) -> None:
        from .sepsis_scanner import SepsisScanner

        await SepsisScanner(self).scan()
