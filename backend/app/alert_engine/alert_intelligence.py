"""报警智能降噪与路由。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId


class AlertIntelligenceMixin:
    def _alert_intel_cfg(self) -> dict:
        cfg = self._cfg("alert_engine", "alert_intelligence", default={}) or {}
        return cfg if isinstance(cfg, dict) else {}

    def _is_low_spo2_alert(self, alert_doc: dict) -> bool:
        parameter = str(alert_doc.get("parameter") or "").lower()
        rule_id = str(alert_doc.get("rule_id") or "").lower()
        alert_type = str(alert_doc.get("alert_type") or "").lower()
        condition = alert_doc.get("condition") if isinstance(alert_doc.get("condition"), dict) else {}
        operator = str(condition.get("operator") or "")
        return (
            ("spo2" in parameter or "spo2" in rule_id or "spo2" in alert_type)
            and operator in {"<", "<="}
        )

    def _route_targets_for_alert(self, alert_doc: dict) -> list[str]:
        severity = str(alert_doc.get("severity") or "").lower()
        category = str(alert_doc.get("category") or "").lower()
        alert_type = str(alert_doc.get("alert_type") or "").lower()
        parameter = str(alert_doc.get("parameter") or "").lower()
        targets: list[str] = []
        if severity in {"warning", "high", "critical"}:
            targets.append("nurse")
        if severity in {"high", "critical"}:
            targets.append("doctor")
        if category in {"drug_pk", "antibiotic_stewardship", "drug_safety"} or any(
            x in alert_type or x in parameter
            for x in ["tdm", "vancomycin", "antimicrobial", "coverage", "dose", "pk"]
        ):
            targets.append("pharmacist")
        seen: set[str] = set()
        deduped: list[str] = []
        for item in targets:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return deduped

    def _is_hemo_context_alert(self, alert_doc: dict) -> bool:
        return str(alert_doc.get("alert_type") or "").lower() == "contextual_hemodynamic_deterioration"

    def _normalize_dt(self, value: datetime | None) -> datetime | None:
        if not isinstance(value, datetime):
            return None
        if value.tzinfo is not None:
            try:
                return value.astimezone().replace(tzinfo=None)
            except Exception:
                return value.replace(tzinfo=None)
        return value

    def _alert_signature_text(self, alert_doc: dict) -> str:
        return " ".join(
            [
                str(alert_doc.get("name") or ""),
                str(alert_doc.get("rule_id") or ""),
                str(alert_doc.get("alert_type") or ""),
                str(alert_doc.get("parameter") or ""),
                str(alert_doc.get("category") or ""),
            ]
        ).lower()

    def _similar_alert(self, left: dict, right: dict) -> bool:
        left_rule = str(left.get("rule_id") or "").strip().lower()
        right_rule = str(right.get("rule_id") or "").strip().lower()
        if left_rule and right_rule and left_rule == right_rule:
            return True
        left_type = str(left.get("alert_type") or "").strip().lower()
        right_type = str(right.get("alert_type") or "").strip().lower()
        if left_type and right_type and left_type == right_type:
            return True
        left_param = str(left.get("parameter") or "").strip().lower()
        right_param = str(right.get("parameter") or "").strip().lower()
        if left_param and right_param and left_param == right_param:
            return True
        left_text = self._alert_signature_text(left)
        right_text = self._alert_signature_text(right)
        return bool(left_text and right_text and (left_text in right_text or right_text in left_text))

    def _nursing_plan_keywords_for_alert(self, alert_doc: dict) -> list[str]:
        text = self._alert_signature_text(alert_doc)
        keyword_groups = [
            (
                ["spo2", "sao2", "oxygen", "resp", "airway", "vent", "痰", "呼吸", "氧", "气道", "通气"],
                ["吸痰", "拍背", "翻身拍背", "气道护理", "痰液吸引", "氧疗", "雾化", "呼吸", "俯卧位", "机械通气"],
            ),
            (
                ["map", "sbp", "dbp", "pressure", "shock", "lactate", "低血压", "灌注", "休克", "乳酸"],
                ["血压", "补液", "容量", "升压", "灌注", "循环", "血流动力学"],
            ),
            (
                ["delir", "sedat", "agitat", "意识", "躁动", "谵妄", "镇静", "约束"],
                ["镇静", "约束", "意识", "谵妄", "rass", "cam-icu"],
            ),
            (
                ["urine", "renal", "crrt", "dialysis", "尿", "肾", "液体", "出入量"],
                ["尿量", "导尿", "crrt", "透析", "出入量", "液体管理"],
            ),
            (
                ["skin", "pressure", "ulcer", "压疮", "皮肤", "翻身"],
                ["翻身", "皮肤护理", "压疮", "减压", "体位", "会阴擦洗"],
            ),
        ]
        matched: list[str] = []
        for triggers, plan_keywords in keyword_groups:
            if any(token in text for token in triggers):
                for item in plan_keywords:
                    if item not in matched:
                        matched.append(item)
        if self._is_low_spo2_alert(alert_doc):
            for item in ["吸痰", "拍背", "翻身拍背", "气道护理", "痰液吸引", "氧疗"]:
                if item not in matched:
                    matched.append(item)
        return matched

    def _evaluate_nursing_plan_coverage(self, alert_doc: dict, nursing_context: dict | None, execution_window_minutes: int) -> dict[str, Any]:
        nursing_context = nursing_context if isinstance(nursing_context, dict) else {}
        plans = nursing_context.get("plans") if isinstance(nursing_context.get("plans"), dict) else {}
        recent_plans = plans.get("recent_plans") if isinstance(plans.get("recent_plans"), list) else []
        recent_executions = plans.get("recent_executions") if isinstance(plans.get("recent_executions"), list) else []
        keywords = self._nursing_plan_keywords_for_alert(alert_doc)
        if not keywords:
            return {
                "covered": False,
                "matched_keywords": [],
                "matched_plan_count": 0,
                "matched_execution_count": 0,
                "delayed_plan_count": 0,
                "has_recent_execution": False,
                "matched_plans": [],
            }

        matched_plans: list[dict[str, Any]] = []
        matched_plan_ids: set[str] = set()
        for item in recent_plans:
            text = str(item.get("text") or "").lower()
            if not text:
                continue
            if any(keyword.lower() in text for keyword in keywords):
                matched_plans.append(item)
                plan_id = str(item.get("plan_id") or "").strip()
                if plan_id:
                    matched_plan_ids.add(plan_id)

        now = datetime.now()
        recent_execution_cutoff = now - timedelta(minutes=max(execution_window_minutes, 1))
        matched_executions: list[dict[str, Any]] = []
        recent_execution_count = 0
        delayed_plan_count = 0
        for item in recent_executions:
            order_id = str(item.get("order_id") or "").strip()
            text = str(item.get("text") or "").lower()
            if matched_plan_ids and order_id and order_id in matched_plan_ids:
                matched = True
            else:
                matched = bool(text and any(keyword.lower() in text for keyword in keywords))
            if not matched:
                continue
            matched_executions.append(item)
            if str(item.get("status") or "").lower() == "ready":
                plan_start_time = self._normalize_dt(item.get("plan_start_time"))
                if plan_start_time and plan_start_time <= now and not self._normalize_dt(item.get("start_time")):
                    delayed_plan_count += 1
            event_time = self._normalize_dt(item.get("start_time")) or self._normalize_dt(item.get("time")) or self._normalize_dt(item.get("plan_start_time"))
            if event_time and event_time >= recent_execution_cutoff:
                recent_execution_count += 1

        return {
            "covered": bool(matched_plans),
            "matched_keywords": keywords[:8],
            "matched_plan_count": len(matched_plans),
            "matched_execution_count": len(matched_executions),
            "delayed_plan_count": delayed_plan_count,
            "has_recent_execution": recent_execution_count > 0,
            "recent_execution_count": recent_execution_count,
            "matched_plans": [
                {
                    "text": str(item.get("text") or "")[:120],
                    "status": str(item.get("status") or ""),
                    "frequency": str(item.get("frequency") or ""),
                    "time": item.get("time"),
                }
                for item in matched_plans[:5]
            ],
        }

    async def _detect_post_execution_recurrence(
        self,
        patient_id: str,
        alert_doc: dict,
        coverage: dict[str, Any],
        window_minutes: int,
        threshold: int,
    ) -> dict[str, Any]:
        if not patient_id or not bool(coverage.get("covered")) or int(coverage.get("matched_execution_count") or 0) <= 0:
            return {"is_recurrent": False, "recurrent_count": 0}
        recent = await self._recent_alerts_for_patient(patient_id, max(window_minutes, 1))
        if not recent:
            return {"is_recurrent": False, "recurrent_count": 0}
        count = 0
        for item in recent:
            if not bool(item.get("is_active", True)):
                continue
            if self._similar_alert(item, alert_doc):
                count += 1
        return {
            "is_recurrent": count >= max(threshold, 1),
            "recurrent_count": count,
            "window_minutes": max(window_minutes, 1),
        }

    async def _recent_alerts_for_patient(self, patient_id: str, minutes: int) -> list[dict]:
        since = datetime.now() - timedelta(minutes=max(minutes, 1))
        cursor = self.db.col("alert_records").find(
            {"patient_id": str(patient_id), "created_at": {"$gte": since}},
            {
                "_id": 1,
                "rule_id": 1,
                "name": 1,
                "alert_type": 1,
                "category": 1,
                "severity": 1,
                "parameter": 1,
                "value": 1,
                "created_at": 1,
                "is_active": 1,
                "extra": 1,
            },
        ).sort("created_at", -1).limit(20)
        return [doc async for doc in cursor]

    async def _has_recent_nursing_context(self, pid, keywords: list[str], minutes: int) -> bool:
        events = await self._get_recent_text_events(pid, keywords, hours=max(1, minutes // 60 + 1), limit=200)
        since = datetime.now() - timedelta(minutes=max(minutes, 1))
        return any(isinstance(x.get("time"), datetime) and x["time"] >= since for x in events)

    def _hemo_flags_from_alert(self, alert_doc: dict) -> set[str]:
        parameter = str(alert_doc.get("parameter") or "").lower()
        rule_id = str(alert_doc.get("rule_id") or "").lower()
        alert_type = str(alert_doc.get("alert_type") or "").lower()
        text = " ".join([parameter, rule_id, alert_type, str(alert_doc.get("name") or "").lower()])
        flags: set[str] = set()
        if any(k in text for k in ["hr", "tachy", "心动过速"]):
            flags.add("hr")
        if any(k in text for k in ["map", "sbp", "hypotension", "低血压", "shock"]):
            flags.add("pressure")
        if any(k in text for k in ["lac", "lactate", "乳酸"]):
            flags.add("lactate")
        return flags

    async def _maybe_contextualize_hemodynamic_alert(self, alert_doc: dict) -> dict:
        cfg = self._alert_intel_cfg()
        if not bool(cfg.get("enabled", True)):
            return alert_doc
        if self._is_hemo_context_alert(alert_doc):
            return alert_doc
        if str(alert_doc.get("severity") or "").lower() not in {"warning", "high"}:
            return alert_doc
        patient_id = str(alert_doc.get("patient_id") or "")
        if not patient_id:
            return alert_doc
        window_min = int(cfg.get("fusion_window_minutes", 15))
        recent = await self._recent_alerts_for_patient(patient_id, window_min)
        flags = set(self._hemo_flags_from_alert(alert_doc))
        if not flags:
            return alert_doc
        if any(self._is_hemo_context_alert(row) and bool(row.get("is_active", True)) for row in recent):
            return None
        source_ids: list[str] = []
        for row in recent:
            if not bool(row.get("is_active", True)):
                continue
            if str(row.get("severity") or "").lower() not in {"warning", "high"}:
                continue
            if self._is_hemo_context_alert(row):
                continue
            row_flags = self._hemo_flags_from_alert(row)
            if not row_flags:
                continue
            flags.update(row_flags)
            if row.get("_id") is not None:
                source_ids.append(str(row.get("_id")))
        if len(flags) < 3:
            return alert_doc
        extra = alert_doc.get("extra") if isinstance(alert_doc.get("extra"), dict) else {}
        extra["merged_dimensions"] = sorted(flags)
        extra["merged_source_alert_ids"] = source_ids[:5]
        extra["merged_source_alert_count"] = len(source_ids[:5])
        extra["merged_from_low_level_alerts"] = True
        extra["route_targets"] = self._route_targets_for_alert({"severity": "high", "category": "alert_intelligence", "alert_type": "contextual_hemodynamic_deterioration"})
        alert_doc["rule_id"] = "ALERT_INTEL_CONTEXT_HEMO"
        alert_doc["name"] = "循环灌注恶化综合预警"
        alert_doc["category"] = "alert_intelligence"
        alert_doc["alert_type"] = "contextual_hemodynamic_deterioration"
        alert_doc["severity"] = "high"
        alert_doc["parameter"] = "hemodynamic_context"
        alert_doc["extra"] = extra
        return alert_doc

    async def _mark_source_alerts_merged(self, alert_doc: dict) -> None:
        extra = alert_doc.get("extra") if isinstance(alert_doc.get("extra"), dict) else {}
        source_ids = extra.get("merged_source_alert_ids") if isinstance(extra.get("merged_source_alert_ids"), list) else []
        if not source_ids or alert_doc.get("_id") is None:
            return
        object_ids: list[ObjectId] = []
        for item in source_ids:
            try:
                object_ids.append(ObjectId(str(item)))
            except Exception:
                continue
        if not object_ids:
            return
        now = datetime.now()
        await self.db.col("alert_records").update_many(
            {"_id": {"$in": object_ids}},
            {
                "$set": {
                    "is_active": False,
                    "extra.merged_into_alert_id": alert_doc["_id"],
                    "extra.merged_into_alert_type": alert_doc.get("alert_type"),
                    "extra.merged_into_rule_id": alert_doc.get("rule_id"),
                    "extra.merged_at": now,
                }
            },
        )

    async def _after_alert_persisted(self, alert_doc: dict, patient_doc: dict | None) -> None:
        if self._is_hemo_context_alert(alert_doc):
            await self._mark_source_alerts_merged(alert_doc)

    async def _alert_intelligence_intercept(self, alert_doc: dict, patient_doc: dict | None) -> dict | None:
        cfg = self._alert_intel_cfg()
        if not bool(cfg.get("enabled", True)):
            return alert_doc

        pid = (patient_doc or {}).get("_id")
        patient_id = str(alert_doc.get("patient_id") or "")
        if pid and self._is_low_spo2_alert(alert_doc):
            suction_keywords = cfg.get("suction_keywords", ["吸痰", "拍背", "翻身拍背", "气道护理", "痰液吸引"])
            if isinstance(suction_keywords, list) and await self._has_recent_nursing_context(pid, suction_keywords, int(cfg.get("procedure_suppression_minutes", 10))):
                return None

        alert_doc = await self._maybe_contextualize_hemodynamic_alert(alert_doc)
        if not alert_doc:
            return None
        extra = alert_doc.get("extra") if isinstance(alert_doc.get("extra"), dict) else {}

        if patient_doc and patient_id and hasattr(self, "_collect_nursing_context") and bool(cfg.get("nursing_plan_coverage_enabled", True)):
            lookback_hours = int(cfg.get("nursing_plan_lookback_hours", 12))
            nursing_context = await self._collect_nursing_context(patient_doc, patient_id, hours=lookback_hours)
            coverage = self._evaluate_nursing_plan_coverage(
                alert_doc,
                nursing_context,
                int(cfg.get("nursing_plan_execution_window_minutes", 120)),
            )
            if coverage.get("covered"):
                extra["nursing_plan_coverage"] = coverage
                recurrence = await self._detect_post_execution_recurrence(
                    patient_id,
                    alert_doc,
                    coverage,
                    int(cfg.get("post_execution_recurrence_window_minutes", 180)),
                    int(cfg.get("post_execution_recurrence_threshold", 2)),
                )
                if recurrence.get("is_recurrent"):
                    extra["post_execution_recurrence"] = recurrence
                    coverage["post_execution_recurrence"] = recurrence.get("recurrent_count")
                severity = str(alert_doc.get("severity") or "").lower()
                if (
                    severity == "warning"
                    and coverage.get("has_recent_execution")
                    and not recurrence.get("is_recurrent")
                    and int(coverage.get("delayed_plan_count") or 0) <= 0
                    and bool(cfg.get("suppress_warning_when_plan_active", True))
                ):
                    return None

        route_targets = self._route_targets_for_alert(alert_doc)
        recurrence = extra.get("post_execution_recurrence") if isinstance(extra.get("post_execution_recurrence"), dict) else {}
        if recurrence.get("is_recurrent") and "doctor" not in route_targets:
            route_targets.append("doctor")
        extra["route_targets"] = route_targets
        alert_doc["extra"] = extra
        alert_doc["route_targets"] = route_targets
        if hasattr(self, "_circadian_apply_alert_policy"):
            alert_doc = await self._circadian_apply_alert_policy(alert_doc, patient_doc)
        return alert_doc
