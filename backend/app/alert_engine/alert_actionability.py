"""告警可行动性评分与生命周期闭环。"""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId


class AlertActionabilityScorerMixin:
    def _normalize_lifecycle_actor(self, actor: str | None, *, source: str = "") -> str:
        raw = str(actor or "").strip()
        if not raw:
            return ""
        generic_tokens = {
            "ui",
            "websocket",
            "patient_detail",
            "patientdetail",
            "analytics",
            "overview",
            "ai_ops",
            "bigscreen",
            "mdt",
        }
        normalized = raw.lower().replace("-", "_").replace(" ", "_")
        source_token = str(source or "").strip().lower().replace("-", "_").replace(" ", "_")
        if normalized in generic_tokens or (source_token and normalized == source_token):
            return ""
        return raw

    def _actionability_cfg(self) -> dict[str, Any]:
        cfg = self._cfg("alert_engine", "alert_actionability", default={}) or {}
        return cfg if isinstance(cfg, dict) else {}

    def _actionability_clip(self, value: float) -> float:
        return max(0.0, min(1.0, float(value or 0.0)))

    def _actionability_level(self, score_100: float) -> str:
        if score_100 >= 75:
            return "immediate"
        if score_100 >= 50:
            return "prompt"
        return "routine"

    def _actionability_signal_keywords(self, alert_doc: dict[str, Any]) -> list[str]:
        text = " ".join(
            [
                str(alert_doc.get("rule_id") or ""),
                str(alert_doc.get("alert_type") or ""),
                str(alert_doc.get("category") or ""),
                str(alert_doc.get("parameter") or ""),
                str(alert_doc.get("name") or ""),
            ]
        ).lower()
        keyword_groups = [
            (["shock", "hypotension", "map", "lactate", "hemodynamic", "低血压", "休克", "乳酸", "灌注"], ["去甲肾上腺素", "肾上腺素", "血管加压素", "多巴胺", "去氧肾上腺素", "乳酸林格", "氯化钠", "白蛋白"]),
            (["sepsis", "sofa", "qsofa", "感染", "脓毒", "抗菌"], ["美罗培南", "哌拉西林", "他唑巴坦", "头孢", "万古霉素", "替考拉宁", "亚胺培南", "抗生素", "乳酸林格", "氯化钠"]),
            (["ards", "resp", "spo2", "oxygen", "vent", "呼吸", "氧合", "肺", "气道"], ["呋塞米", "布地奈德", "沙丁胺醇", "异丙托溴铵", "甲泼尼龙", "地塞米松", "抗生素"]),
            (["aki", "renal", "cr", "尿量", "肾", "液体"], ["呋塞米", "白蛋白", "碳酸氢钠"]),
            (["bleed", "dic", "plt", "出血", "凝血"], ["氨甲环酸", "纤维蛋白原", "血浆", "红细胞", "血小板"]),
            (["delir", "sedat", "谵妄", "镇静", "躁动"], ["右美托咪定", "丙泊酚", "咪达唑仑", "氟哌啶醇", "奥氮平"]),
        ]
        keywords: list[str] = []
        for triggers, candidates in keyword_groups:
            if any(token in text for token in triggers):
                for item in candidates:
                    if item not in keywords:
                        keywords.append(item)
        return keywords[:12]

    def _actionability_medication_factor(self, matched_actions: list[dict[str, Any]], keywords: list[str]) -> float:
        if matched_actions:
            return 0.92
        if keywords:
            return 0.58
        return 0.4

    def _actionability_circadian_factor(self, alert_doc: dict[str, Any], severity_factor: float, state_factor: float) -> float:
        now = datetime.now()
        severity = str(alert_doc.get("severity") or "").lower()
        if not hasattr(self, "_is_night_window") or not self._is_night_window(now):
            return 1.0
        if severity in {"critical", "high"} or severity_factor >= 0.8 or state_factor >= 0.8:
            return 1.0
        return 0.62

    def _actionability_recent_response_factor(self, recent_same_type: list[dict[str, Any]]) -> float:
        for item in recent_same_type:
            if item.get("acknowledged_at") or item.get("action_taken"):
                return 0.35
        return 1.0

    async def _actionability_recent_same_type_alerts(self, patient_id: str, alert_doc: dict[str, Any], minutes: int) -> list[dict[str, Any]]:
        if not patient_id:
            return []
        since = datetime.now() - timedelta(minutes=max(int(minutes or 60), 1))
        query = {
            "patient_id": patient_id,
            "created_at": {"$gte": since},
            "_id": {"$ne": alert_doc.get("_id")},
            "$or": [],
        }
        rule_id = str(alert_doc.get("rule_id") or "").strip()
        alert_type = str(alert_doc.get("alert_type") or "").strip()
        parameter = str(alert_doc.get("parameter") or "").strip()
        if rule_id:
            query["$or"].append({"rule_id": rule_id})
        if alert_type:
            query["$or"].append({"alert_type": alert_type})
        if parameter:
            query["$or"].append({"parameter": parameter})
        if not query["$or"]:
            return []
        cursor = self.db.col("alert_records").find(
            query,
            {"acknowledged_at": 1, "action_taken": 1, "viewed_at": 1, "created_at": 1, "rule_id": 1, "alert_type": 1, "parameter": 1},
        ).sort("created_at", -1).limit(12)
        return [row async for row in cursor]

    async def _actionability_history_factor(self, alert_doc: dict[str, Any], lookback_days: int, min_samples: int) -> dict[str, Any]:
        now = datetime.now()
        since = now - timedelta(days=max(int(lookback_days or 30), 1))
        match_or: list[dict[str, Any]] = []
        if str(alert_doc.get("rule_id") or "").strip():
            match_or.append({"rule_id": str(alert_doc.get("rule_id"))})
        if str(alert_doc.get("alert_type") or "").strip():
            match_or.append({"alert_type": str(alert_doc.get("alert_type"))})
        if not match_or:
            return {"factor": 0.65, "false_positive_rate": None, "samples": 0, "evaluated_samples": 0}

        cursor = self.db.col("alert_records").find(
            {"created_at": {"$gte": since}, "$or": match_or},
            {"viewed_at": 1, "acknowledged_at": 1, "action_taken": 1, "outcome_delta": 1, "created_at": 1},
        ).sort("created_at", -1).limit(300)
        docs = [doc async for doc in cursor]
        evaluated = []
        non_actionable = 0
        for doc in docs:
            if not any(key in doc for key in ("viewed_at", "acknowledged_at", "action_taken", "outcome_delta")):
                continue
            evaluated.append(doc)
            if not doc.get("acknowledged_at") and not doc.get("action_taken"):
                non_actionable += 1
        if len(evaluated) < max(int(min_samples or 8), 3):
            return {"factor": 0.65, "false_positive_rate": None, "samples": len(docs), "evaluated_samples": len(evaluated)}
        fp_rate = round(non_actionable / max(len(evaluated), 1), 3)
        return {
            "factor": round(self._actionability_clip(1.0 - fp_rate), 3),
            "false_positive_rate": fp_rate,
            "samples": len(docs),
            "evaluated_samples": len(evaluated),
        }

    async def _actionability_patient_state(self, patient_id: str, patient_doc: dict[str, Any] | None) -> dict[str, Any]:
        vitals = await self._get_latest_vitals_by_patient(patient_id)
        his_pid = str((patient_doc or {}).get("hisPid") or (patient_doc or {}).get("hisPID") or "").strip()
        labs = await self._get_latest_labs_map(his_pid, lookback_hours=48) if his_pid else {}
        lactate = ((labs.get("lactate") or {}).get("value") if isinstance(labs, dict) else None)
        sofa_doc = await self.db.col("score_records").find_one(
            {"patient_id": patient_id, "score_type": {"$in": ["sofa", "sepsis_sofa", "sofa_score"]}},
            sort=[("calc_time", -1)],
        )
        sofa = None
        if isinstance(sofa_doc, dict):
            for key in ("score", "sofa_score", "value", "score_value"):
                raw = sofa_doc.get(key)
                if raw is None:
                    continue
                try:
                    sofa = float(raw)
                    break
                except Exception:
                    continue
        map_value = vitals.get("map")
        map_factor = 0.0
        if map_value is not None:
            try:
                map_num = float(map_value)
                if map_num < 55:
                    map_factor = 1.0
                elif map_num < 65:
                    map_factor = 0.82
                elif map_num < 70:
                    map_factor = 0.55
            except Exception:
                pass
        lactate_factor = 0.0
        if lactate is not None:
            try:
                lactate_num = float(lactate)
                if lactate_num >= 4:
                    lactate_factor = 1.0
                elif lactate_num >= 2:
                    lactate_factor = 0.65
            except Exception:
                pass
        sofa_factor = 0.0
        if sofa is not None:
            if sofa >= 12:
                sofa_factor = 1.0
            elif sofa >= 8:
                sofa_factor = 0.72
            elif sofa >= 5:
                sofa_factor = 0.48
        state_factor = round(max(map_factor, lactate_factor, sofa_factor, 0.25), 3)
        return {
            "map": map_value,
            "lactate": lactate,
            "sofa": sofa,
            "factor": state_factor,
            "signals": {
                "map_factor": map_factor,
                "lactate_factor": lactate_factor,
                "sofa_factor": sofa_factor,
            },
        }

    def _alert_drug_time(self, doc: dict[str, Any]) -> datetime | None:
        for key in ("executeTime", "startTime", "orderTime", "updateTime", "createdAt"):
            value = doc.get(key)
            if isinstance(value, datetime):
                return value
            if value in (None, ""):
                continue
            try:
                return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except Exception:
                continue
        return None

    async def _match_action_taken(self, alert_doc: dict[str, Any], patient_doc: dict[str, Any] | None, hours: int = 24) -> dict[str, Any] | None:
        patient_id = str(alert_doc.get("patient_id") or "")
        if not patient_id:
            return None
        created_at = alert_doc.get("created_at") if isinstance(alert_doc.get("created_at"), datetime) else datetime.now() - timedelta(hours=1)
        end_time = created_at + timedelta(hours=max(int(hours or 24), 1))
        keywords = self._actionability_signal_keywords(alert_doc)
        cursor = self.db.col("drugExe").find(
            {"pid": patient_id},
            {"drugName": 1, "orderName": 1, "dose": 1, "doseUnit": 1, "route": 1, "frequency": 1, "status": 1, "executeTime": 1, "startTime": 1, "orderTime": 1},
        ).sort("executeTime", -1).limit(300)
        matches: list[dict[str, Any]] = []
        async for doc in cursor:
            event_time = self._alert_drug_time(doc)
            if not event_time or event_time < created_at or event_time > end_time:
                continue
            haystack = " ".join([str(doc.get("drugName") or ""), str(doc.get("orderName") or "")]).lower()
            if keywords and not any(str(keyword).lower() in haystack for keyword in keywords):
                continue
            matches.append(
                {
                    "drug_name": str(doc.get("drugName") or doc.get("orderName") or "").strip(),
                    "order_name": str(doc.get("orderName") or doc.get("drugName") or "").strip(),
                    "dose": doc.get("dose"),
                    "dose_unit": doc.get("doseUnit"),
                    "route": doc.get("route"),
                    "frequency": doc.get("frequency"),
                    "status": doc.get("status"),
                    "time": event_time,
                }
            )
        if not matches:
            return None
        first = matches[0]
        return {
            "matched": True,
            "matched_keywords": keywords[:8],
            "action_time": first.get("time"),
            "action_count": len(matches),
            "orders": matches[:5],
            "summary": "；".join(item.get("drug_name") or item.get("order_name") or "" for item in matches[:3] if (item.get("drug_name") or item.get("order_name"))),
        }

    async def _metric_near_time(self, patient_id: str, patient_doc: dict[str, Any] | None, metric: str, start: datetime, end: datetime) -> float | None:
        if end <= start:
            return None
        if metric == "map":
            codes = list(self._cfg("vital_signs", "map_priority", default=["param_ibp_m", "param_nibp_m"]) or ["param_ibp_m", "param_nibp_m"])
            for code in codes:
                series = await self._get_param_series_by_pid(patient_id, str(code), start, prefer_device_types=["monitor"], limit=240)
                points = [row for row in series if start <= row.get("time", start) <= end]
                if points:
                    try:
                        return float(points[-1].get("value"))
                    except Exception:
                        continue
            return None
        if metric == "lactate":
            his_pid = str((patient_doc or {}).get("hisPid") or (patient_doc or {}).get("hisPID") or "").strip()
            if not his_pid:
                return None
            rows = await self._get_lab_series(his_pid, "lactate", start, end, limit=30)
            if not rows:
                return None
            try:
                return float(rows[-1].get("value"))
            except Exception:
                return None
        if metric == "sofa":
            doc = await self.db.col("score_records").find_one(
                {"patient_id": patient_id, "score_type": {"$in": ["sofa", "sepsis_sofa", "sofa_score"]}, "calc_time": {"$gte": start, "$lte": end}},
                sort=[("calc_time", -1)],
            )
            if not doc:
                return None
            for key in ("score", "sofa_score", "value", "score_value"):
                raw = doc.get(key)
                if raw is None:
                    continue
                try:
                    return float(raw)
                except Exception:
                    continue
        return None

    async def _build_outcome_delta(self, alert_doc: dict[str, Any], patient_doc: dict[str, Any] | None, action_taken: dict[str, Any]) -> dict[str, Any] | None:
        action_time = action_taken.get("action_time") if isinstance(action_taken.get("action_time"), datetime) else None
        patient_id = str(alert_doc.get("patient_id") or "")
        if not action_time or not patient_id:
            return None
        metrics = {
            "map": "up",
            "lactate": "down",
            "sofa": "down",
        }
        windows = {
            "30m": timedelta(minutes=30),
            "2h": timedelta(hours=2),
        }
        baseline_start = action_time - timedelta(hours=6)
        baseline_end = action_time
        result: dict[str, Any] = {"action_time": action_time, "windows": {}}
        improved_any = False
        for label, delta in windows.items():
            metric_rows: dict[str, Any] = {}
            for metric, direction in metrics.items():
                baseline = await self._metric_near_time(patient_id, patient_doc, metric, baseline_start, baseline_end)
                followup = await self._metric_near_time(patient_id, patient_doc, metric, action_time, action_time + delta)
                if baseline is None or followup is None:
                    continue
                diff = round(float(followup) - float(baseline), 2)
                improved = diff > 0 if direction == "up" else diff < 0
                improved_any = improved_any or improved
                metric_rows[metric] = {
                    "baseline": baseline,
                    "followup": followup,
                    "delta": diff,
                    "direction": direction,
                    "improved": improved,
                }
            if metric_rows:
                result["windows"][label] = metric_rows
        if not result["windows"]:
            return None
        result["improved_any"] = improved_any
        return result

    async def _compute_alert_actionability(self, alert_doc: dict[str, Any], patient_doc: dict[str, Any] | None) -> dict[str, Any]:
        cfg = self._actionability_cfg()
        patient_id = str(alert_doc.get("patient_id") or "")
        severity = str(alert_doc.get("severity") or "warning").lower()
        severity_factor = {
            "info": 0.2,
            "warning": 0.45,
            "high": 0.75,
            "critical": 1.0,
        }.get(severity, 0.45)
        state = await self._actionability_patient_state(patient_id, patient_doc)
        history = await self._actionability_history_factor(
            alert_doc,
            int(cfg.get("history_lookback_days", 30) or 30),
            int(cfg.get("min_history_samples", 8) or 8),
        )
        keywords = self._actionability_signal_keywords(alert_doc)
        matched_action = await self._match_action_taken(alert_doc, patient_doc, hours=int(cfg.get("action_match_hours", 24) or 24))
        medication_factor = self._actionability_medication_factor((matched_action or {}).get("orders") or [], keywords)
        recent_same_type = await self._actionability_recent_same_type_alerts(
            patient_id,
            alert_doc,
            int(cfg.get("recent_response_window_minutes", 60) or 60),
        )
        recent_response_factor = self._actionability_recent_response_factor(recent_same_type)
        circadian_factor = self._actionability_circadian_factor(alert_doc, severity_factor, float(state.get("factor") or 0.0))
        weighted = (
            severity_factor * 0.25 +
            float(state.get("factor") or 0.0) * 0.30 +
            float(history.get("factor") or 0.0) * 0.15 +
            medication_factor * 0.15 +
            recent_response_factor * 0.10 +
            circadian_factor * 0.05
        )
        score = round(self._actionability_clip(weighted) * 100, 1)
        return {
            "score": score,
            "level": self._actionability_level(score),
            "factors": {
                "severity_factor": round(severity_factor, 3),
                "patient_state_factor": round(float(state.get("factor") or 0.0), 3),
                "history_factor": round(float(history.get("factor") or 0.0), 3),
                "medication_factor": round(medication_factor, 3),
                "recent_response_factor": round(recent_response_factor, 3),
                "circadian_factor": round(circadian_factor, 3),
            },
            "patient_state": state,
            "history": history,
            "matched_action_preview": matched_action,
            "matched_order_keywords": keywords[:8],
            "recent_same_type_response_count": len(recent_same_type),
            "generated_at": datetime.now(),
        }

    async def _initialize_alert_actionability(self, alert_doc: dict[str, Any], patient_doc: dict[str, Any] | None) -> dict[str, Any]:
        if not bool(self._actionability_cfg().get("enabled", True)):
            return alert_doc
        alert_doc.setdefault("viewed_at", None)
        alert_doc.setdefault("acknowledged_at", None)
        alert_doc.setdefault("action_taken", None)
        alert_doc.setdefault("outcome_delta", None)
        alert_doc.setdefault("lifecycle_updated_at", datetime.now())
        actionability = await self._compute_alert_actionability(alert_doc, patient_doc)
        alert_doc["actionability_score"] = actionability.get("score")
        alert_doc["actionability_level"] = actionability.get("level")
        alert_doc["actionability_factors"] = actionability.get("factors")
        extra = alert_doc.get("extra") if isinstance(alert_doc.get("extra"), dict) else {}
        extra["actionability"] = {
            "score": actionability.get("score"),
            "level": actionability.get("level"),
            "patient_state": actionability.get("patient_state"),
            "history": actionability.get("history"),
            "matched_order_keywords": actionability.get("matched_order_keywords"),
            "recent_same_type_response_count": actionability.get("recent_same_type_response_count"),
            "generated_at": actionability.get("generated_at"),
        }
        if actionability.get("matched_action_preview"):
            alert_doc["action_taken"] = actionability.get("matched_action_preview")
        alert_doc["extra"] = extra
        return alert_doc

    async def refresh_alert_lifecycle(self, alert_doc: dict[str, Any], patient_doc: dict[str, Any] | None = None, *, persist: bool = False) -> dict[str, Any]:
        if not isinstance(alert_doc, dict):
            return alert_doc
        if not bool(self._actionability_cfg().get("enabled", True)):
            return alert_doc
        patient_id = str(alert_doc.get("patient_id") or "")
        if not patient_doc and patient_id:
            patient_doc, _ = await self._load_patient(patient_id)
        changed = False
        if not alert_doc.get("action_taken"):
            action = await self._match_action_taken(alert_doc, patient_doc, hours=int(self._actionability_cfg().get("action_match_hours", 24) or 24))
            if action:
                alert_doc["action_taken"] = action
                changed = True
        if alert_doc.get("action_taken") and not alert_doc.get("outcome_delta"):
            outcome = await self._build_outcome_delta(alert_doc, patient_doc, alert_doc.get("action_taken") or {})
            if outcome:
                alert_doc["outcome_delta"] = outcome
                changed = True
        if alert_doc.get("_id") is None and not changed:
            return alert_doc
        if changed:
            alert_doc["lifecycle_updated_at"] = datetime.now()
        if persist and changed and alert_doc.get("_id") is not None:
            await self.db.col("alert_records").update_one(
                {"_id": alert_doc.get("_id")},
                {"$set": {"action_taken": alert_doc.get("action_taken"), "outcome_delta": alert_doc.get("outcome_delta"), "lifecycle_updated_at": alert_doc.get("lifecycle_updated_at")}},
            )
        return alert_doc

    async def mark_alerts_viewed(self, alert_ids: list[str], *, actor: str = "", source: str = "ui") -> int:
        object_ids: list[ObjectId] = []
        for item in alert_ids or []:
            try:
                object_ids.append(ObjectId(str(item)))
            except Exception:
                continue
        if not object_ids:
            return 0
        now = datetime.now()
        actor = self._normalize_lifecycle_actor(actor, source=source)
        result = await self.db.col("alert_records").update_many(
            {"_id": {"$in": object_ids}, "$or": [{"viewed_at": None}, {"viewed_at": {"$exists": False}}]},
            {"$set": {"viewed_at": now, "view_source": source, "view_actor": actor, "lifecycle_updated_at": now}},
        )
        return int(result.modified_count or 0)

    async def acknowledge_alert(self, alert_id: str, *, actor: str = "", note: str = "") -> dict[str, Any] | None:
        try:
            oid = ObjectId(str(alert_id))
        except Exception:
            return None
        now = datetime.now()
        actor = self._normalize_lifecycle_actor(actor)
        await self.db.col("alert_records").update_one(
            {"_id": oid},
            {"$set": {"acknowledged_at": now, "ack_actor": actor, "ack_note": note, "lifecycle_updated_at": now}},
        )
        doc = await self.db.col("alert_records").find_one({"_id": oid})
        if not doc:
            return None
        return await self.refresh_alert_lifecycle(doc, persist=True)

    async def alert_lifecycle_analytics(self, *, hours: int = 24, dept: str | None = None, dept_code: str | None = None) -> dict[str, Any]:
        window_hours = max(int(hours or 24), 1)
        since = datetime.now() - timedelta(hours=window_hours)
        query: dict[str, Any] = {"created_at": {"$gte": since}}
        if dept:
            query["dept"] = dept
        elif dept_code:
            query["deptCode"] = dept_code
        docs = [doc async for doc in self.db.col("alert_records").find(query, {"alert_type": 1, "name": 1, "created_at": 1, "viewed_at": 1, "acknowledged_at": 1, "action_taken": 1, "actionability_score": 1})]
        total = len(docs)
        viewed = [doc for doc in docs if doc.get("viewed_at")]
        acked = [doc for doc in docs if doc.get("acknowledged_at")]
        actioned = [doc for doc in docs if doc.get("action_taken")]
        view_minutes = [max((doc.get("viewed_at") - doc.get("created_at")).total_seconds() / 60.0, 0.0) for doc in viewed if isinstance(doc.get("created_at"), datetime) and isinstance(doc.get("viewed_at"), datetime)]
        ack_minutes = [max((doc.get("acknowledged_at") - doc.get("created_at")).total_seconds() / 60.0, 0.0) for doc in acked if isinstance(doc.get("created_at"), datetime) and isinstance(doc.get("acknowledged_at"), datetime)]
        action_minutes = []
        by_type: dict[str, dict[str, Any]] = {}
        for doc in docs:
            key = str(doc.get("alert_type") or doc.get("name") or "unknown")
            row = by_type.setdefault(key, {"alert_type": key, "count": 0, "viewed": 0, "acknowledged": 0, "actioned": 0, "scores": []})
            row["count"] += 1
            if doc.get("viewed_at"):
                row["viewed"] += 1
            if doc.get("acknowledged_at"):
                row["acknowledged"] += 1
            if doc.get("action_taken"):
                row["actioned"] += 1
                action_time = ((doc.get("action_taken") or {}).get("action_time") if isinstance(doc.get("action_taken"), dict) else None)
                if isinstance(action_time, datetime) and isinstance(doc.get("created_at"), datetime):
                    minutes = max((action_time - doc.get("created_at")).total_seconds() / 60.0, 0.0)
                    action_minutes.append(minutes)
                    row.setdefault("action_minutes", []).append(minutes)
            if doc.get("actionability_score") is not None:
                try:
                    row["scores"].append(float(doc.get("actionability_score")))
                except Exception:
                    pass
        top_types = []
        for row in by_type.values():
            action_times = row.pop("action_minutes", []) if isinstance(row.get("action_minutes"), list) else []
            scores = row.pop("scores", []) if isinstance(row.get("scores"), list) else []
            count = max(int(row.get("count") or 0), 1)
            top_types.append({
                **row,
                "view_rate": round(float(row.get("viewed") or 0) / count, 3),
                "ack_rate": round(float(row.get("acknowledged") or 0) / count, 3),
                "action_rate": round(float(row.get("actioned") or 0) / count, 3),
                "median_action_minutes": round(statistics.median(action_times), 1) if action_times else None,
                "avg_actionability_score": round(sum(scores) / len(scores), 1) if scores else None,
            })
        top_types.sort(key=lambda item: (-float(item.get("action_rate") or 0), -int(item.get("count") or 0), item.get("alert_type") or ""))
        bucket_mode = "hour" if window_hours <= 72 else "day"
        bucket_map: dict[str, dict[str, Any]] = {}
        for doc in docs:
            created_at = doc.get("created_at") if isinstance(doc.get("created_at"), datetime) else None
            if not created_at:
                continue
            bucket_key = created_at.strftime("%m-%d %H:00") if bucket_mode == "hour" else created_at.strftime("%m-%d")
            row = bucket_map.setdefault(bucket_key, {"time": bucket_key, "created": 0, "viewed": 0, "acknowledged": 0, "actioned": 0})
            row["created"] += 1
            if doc.get("viewed_at"):
                row["viewed"] += 1
            if doc.get("acknowledged_at"):
                row["acknowledged"] += 1
            if doc.get("action_taken"):
                row["actioned"] += 1
        trend_series = [bucket_map[key] for key in sorted(bucket_map.keys())]
        conversion_series = []
        for item in trend_series:
            created_count = int(item.get("created") or 0)
            viewed_count = int(item.get("viewed") or 0)
            acked_count = int(item.get("acknowledged") or 0)
            actioned_count = int(item.get("actioned") or 0)
            conversion_series.append(
                {
                    "time": item.get("time"),
                    "created": created_count,
                    "viewed": viewed_count,
                    "acknowledged": acked_count,
                    "actioned": actioned_count,
                    "created_to_view_rate": round(viewed_count / created_count, 3) if created_count else 0,
                    "view_to_ack_rate": round(acked_count / viewed_count, 3) if viewed_count else 0,
                    "ack_to_action_rate": round(actioned_count / acked_count, 3) if acked_count else 0,
                    "created_to_action_rate": round(actioned_count / created_count, 3) if created_count else 0,
                }
            )
        return {
            "summary": {
                "window_hours": window_hours,
                "total_alerts": total,
                "viewed_alerts": len(viewed),
                "acknowledged_alerts": len(acked),
                "actioned_alerts": len(actioned),
                "view_rate": round(len(viewed) / total, 3) if total else 0,
                "ack_rate": round(len(acked) / total, 3) if total else 0,
                "action_rate": round(len(actioned) / total, 3) if total else 0,
                "median_view_minutes": round(statistics.median(view_minutes), 1) if view_minutes else None,
                "median_ack_minutes": round(statistics.median(ack_minutes), 1) if ack_minutes else None,
                "median_action_minutes": round(statistics.median(action_minutes), 1) if action_minutes else None,
            },
            "trend": {
                "bucket": bucket_mode,
                "series": trend_series,
            },
            "funnel_trend": {
                "bucket": bucket_mode,
                "series": conversion_series,
            },
            "top_alert_types": top_types[:12],
        }
