from __future__ import annotations

import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml
from bson import ObjectId


OUTCOME_WINDOWS = ("6h", "24h", "72h")


def _dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _minutes_between(start: datetime | None, end: datetime | None) -> float | None:
    if not start or not end:
        return None
    return round(max((end - start).total_seconds(), 0.0) / 60.0, 2)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except Exception:
        return None


class AlertOutcomeService:
    """Maintains the alert_outcomes collection and conservative outcome inference."""

    def __init__(self, db, *, rules_dir: str | Path | None = None) -> None:
        self.db = db
        self.rules_dir = Path(rules_dir) if rules_dir else Path(__file__).resolve().parent.parent / "outcome_rules"
        self._rules_cache: dict[str, dict[str, Any]] = {}

    def _alert_id(self, alert_doc: dict[str, Any]) -> str:
        return str(alert_doc.get("_id") or alert_doc.get("alert_id") or "")

    def _scanner_name(self, alert_doc: dict[str, Any]) -> str:
        return str(alert_doc.get("scanner_name") or alert_doc.get("alert_type") or alert_doc.get("rule_id") or "unknown")

    def normalize_disposition(self, value: Any) -> str:
        key = str(value or "").strip().lower()
        return {
            "resolved": "accepted",
            "accepted": "accepted",
            "watching": "partial",
            "partial": "partial",
            "false_positive": "overridden",
            "overridden": "overridden",
            "ignored": "ignored",
            "snooze": "ignored",
            "later": "ignored",
            "auto_resolved": "auto-resolved",
            "auto-resolved": "auto-resolved",
            "escalate": "partial",
        }.get(key, "partial" if key else "unknown")

    def normalize_override_reason(self, disposition: str, reason_code: Any = "", reason_text: Any = "") -> dict[str, str]:
        code = str(reason_code or "").strip().lower()
        if not code:
            code = {
                "overridden": "not_clinically_relevant",
                "ignored": "defer_review",
                "partial": "monitoring_only",
                "accepted": "clinically_actionable",
            }.get(disposition, "unspecified")
        return {"code": code, "text": str(reason_text or "").strip()}

    async def ensure_for_alert(self, alert_doc: dict[str, Any]) -> dict[str, Any] | None:
        alert_id = self._alert_id(alert_doc)
        if not alert_id:
            return None
        now = datetime.now()
        fired_at = _dt(alert_doc.get("created_at") or alert_doc.get("fired_at")) or now
        base_doc = {
            "alert_id": alert_id,
            "patient_id": str(alert_doc.get("patient_id") or ""),
            "scanner_name": self._scanner_name(alert_doc),
            "alert_severity": str(alert_doc.get("severity") or ""),
            "fired_at": fired_at,
            "first_viewed_at": _dt(alert_doc.get("viewed_at")),
            "first_acknowledged_at": _dt(alert_doc.get("acknowledged_at")),
            "time_to_acknowledge_minutes": _minutes_between(fired_at, _dt(alert_doc.get("acknowledged_at"))),
            "disposition": self.normalize_disposition(alert_doc.get("ack_disposition")),
            "override_reason": self.normalize_override_reason(self.normalize_disposition(alert_doc.get("ack_disposition"))),
            "related_order_change_ids": [],
            "related_operation_record_ids": [],
            "outcomes": {key: "unknown" for key in OUTCOME_WINDOWS},
            "manual_review_required": False,
            "inference": {"status": "pending", "updated_at": now},
            "created_at": now,
            "updated_at": now,
        }
        await self.db.col("alert_outcomes").update_one(
            {"alert_id": alert_id},
            {"$setOnInsert": base_doc, "$set": {"updated_at": now}},
            upsert=True,
        )
        return await self.db.col("alert_outcomes").find_one({"alert_id": alert_id})

    async def record_viewed(self, alert_ids: list[str], *, actor: str = "", source: str = "ui") -> int:
        if not alert_ids:
            return 0
        now = datetime.now()
        result = await self.db.col("alert_outcomes").update_many(
            {"alert_id": {"$in": [str(x) for x in alert_ids if str(x or "").strip()]}, "first_viewed_at": {"$in": [None, ""]}},
            {"$set": {"first_viewed_at": now, "view_actor": actor, "view_source": source, "updated_at": now}},
        )
        return int(result.modified_count or 0)

    async def record_acknowledgement(
        self,
        alert_doc: dict[str, Any],
        *,
        actor: str = "",
        disposition: str = "",
        reason_code: str = "",
        reason_text: str = "",
    ) -> dict[str, Any] | None:
        await self.ensure_for_alert(alert_doc)
        alert_id = self._alert_id(alert_doc)
        fired_at = _dt(alert_doc.get("created_at") or alert_doc.get("fired_at"))
        ack_at = _dt(alert_doc.get("acknowledged_at")) or datetime.now()
        normalized = self.normalize_disposition(disposition or alert_doc.get("ack_disposition"))
        update = {
            "first_acknowledged_at": ack_at,
            "time_to_acknowledge_minutes": _minutes_between(fired_at, ack_at),
            "disposition": normalized,
            "override_reason": self.normalize_override_reason(normalized, reason_code, reason_text),
            "ack_actor": actor,
            "updated_at": datetime.now(),
        }
        await self.db.col("alert_outcomes").update_one({"alert_id": alert_id}, {"$set": update}, upsert=False)
        return await self.infer_outcome(alert_doc)

    def _load_rule(self, scanner_name: str) -> dict[str, Any]:
        key = str(scanner_name or "generic").strip().lower()
        if key in self._rules_cache:
            return self._rules_cache[key]
        candidates = [self.rules_dir / f"{key}.outcome_rule.yaml", self.rules_dir / f"{key}.yaml", self.rules_dir / "generic.outcome_rule.yaml"]
        for path in candidates:
            if path.exists():
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                self._rules_cache[key] = data if isinstance(data, dict) else {}
                return self._rules_cache[key]
        self._rules_cache[key] = {}
        return {}

    def _keyword_hit(self, doc: dict[str, Any], keywords: list[str]) -> bool:
        text = " ".join(str(v or "") for v in doc.values()).lower()
        return any(str(k).lower() in text for k in keywords if str(k).strip())

    async def _count_response_signals(self, patient_id: str, fired_at: datetime, rule: dict[str, Any]) -> tuple[int, list[str], list[str]]:
        window_hours = int((rule.get("accepted_if") or {}).get("window_hours") or 6)
        end = fired_at + timedelta(hours=window_hours)
        signals = (rule.get("accepted_if") or {}).get("signals") or []
        matched: list[str] = []
        related_ids: list[str] = []
        if not signals:
            return 0, matched, related_ids

        collections = ["drugexe", "drug", "orders", "order", "operation_records", "nursing_records"]
        for signal in signals:
            keywords = [str(x) for x in (signal.get("keywords") or [])]
            time_fields = [str(x) for x in (signal.get("time_fields") or ["created_at", "orderTime", "startTime", "time", "recordTime"])]
            found = False
            for col_name in collections:
                query = {"$or": [{"patient_id": patient_id}, {"pid": patient_id}, {"patientId": patient_id}]}
                cursor = self.db.col(col_name).find(query).limit(300)
                async for doc in cursor:
                    event_time = next((_dt(doc.get(field)) for field in time_fields if _dt(doc.get(field))), None)
                    if not event_time or event_time < fired_at or event_time > end:
                        continue
                    if self._keyword_hit(doc, keywords):
                        found = True
                        related_ids.append(str(doc.get("_id") or ""))
                        break
                if found:
                    matched.append(str(signal.get("name") or "signal"))
                    break
        return len(matched), matched, [x for x in related_ids if x]

    async def _sofa_delta(self, patient_id: str, fired_at: datetime, hours: int = 24) -> float | None:
        start = fired_at - timedelta(hours=24)
        end = fired_at + timedelta(hours=hours)
        cursor = self.db.col("score").find(
            {
                "$and": [
                    {"$or": [{"patient_id": patient_id}, {"pid": patient_id}]},
                    {"$or": [{"score_type": {"$regex": "sofa", "$options": "i"}}, {"scoreType": {"$regex": "sofa", "$options": "i"}}]},
                    {"$or": [{"calc_time": {"$gte": start, "$lte": end}}, {"created_at": {"$gte": start, "$lte": end}}, {"time": {"$gte": start, "$lte": end}}]},
                ],
            }
        ).sort("calc_time", 1).limit(80)
        before: list[float] = []
        after: list[float] = []
        async for doc in cursor:
            t = _dt(doc.get("calc_time") or doc.get("created_at") or doc.get("time"))
            val = _safe_float(doc.get("sofa_score") or doc.get("score") or doc.get("value"))
            if t is None or val is None:
                continue
            if t <= fired_at:
                before.append(val)
            else:
                after.append(val)
        if not before or not after:
            return None
        return max(after) - before[-1]

    async def infer_outcome(self, alert_doc: dict[str, Any]) -> dict[str, Any] | None:
        alert_id = self._alert_id(alert_doc)
        patient_id = str(alert_doc.get("patient_id") or "")
        fired_at = _dt(alert_doc.get("created_at") or alert_doc.get("fired_at"))
        if not alert_id or not patient_id or not fired_at:
            return None
        rule = self._load_rule(self._scanner_name(alert_doc))
        min_signals = int((rule.get("accepted_if") or {}).get("min_signals") or 1)
        signal_count, matched, related_ids = await self._count_response_signals(patient_id, fired_at, rule)
        sofa_delta = await self._sofa_delta(patient_id, fired_at, hours=24)
        disposition = self.normalize_disposition(alert_doc.get("ack_disposition"))
        outcomes = {key: "unknown" for key in OUTCOME_WINDOWS}
        inference_reason = "insufficient_context"
        if signal_count >= min_signals:
            disposition = "accepted"
            outcomes["6h"] = "averted"
            outcomes["24h"] = "no_change"
            inference_reason = "response_bundle_detected_after_fired_at"
        elif sofa_delta is not None and sofa_delta >= 2:
            if disposition in {"unknown", "partial"}:
                disposition = "overridden"
            outcomes["24h"] = "event_occurred"
            inference_reason = "no_response_signal_and_sofa_increased"
        elif disposition in {"overridden", "ignored"}:
            outcomes["24h"] = "unknown"
            inference_reason = "clinician_overrode_without_detected_event"

        now = datetime.now()
        await self.db.col("alert_outcomes").update_one(
            {"alert_id": alert_id},
            {
                "$set": {
                    "disposition": disposition,
                    "related_order_change_ids": related_ids,
                    "outcomes": outcomes,
                    "manual_review_required": outcomes["24h"] == "event_occurred" or disposition in {"overridden", "ignored"},
                    "inference": {
                        "status": "completed",
                        "matched_signals": matched,
                        "signal_count": signal_count,
                        "sofa_delta_24h": sofa_delta,
                        "reason": inference_reason,
                        "updated_at": now,
                    },
                    "updated_at": now,
                }
            },
            upsert=False,
        )
        return await self.db.col("alert_outcomes").find_one({"alert_id": alert_id})

    async def scanner_health(self, *, days: int = 30, limit_examples: int = 5) -> dict[str, Any]:
        since = datetime.now() - timedelta(days=max(int(days or 30), 1))
        docs = [doc async for doc in self.db.col("alert_outcomes").find({"fired_at": {"$gte": since}}).limit(5000)]
        if not docs:
            result = await self._scanner_health_from_alert_records(since=since, days=days)
            result["rows"] = await self._attach_scanner_run_health(result.get("rows") or [], since=since)
            return result
        by_scanner: dict[str, list[dict[str, Any]]] = {}
        for doc in docs:
            by_scanner.setdefault(str(doc.get("scanner_name") or "unknown"), []).append(doc)
        rows: list[dict[str, Any]] = []
        for scanner, items in by_scanner.items():
            total = len(items)
            accepted = [x for x in items if x.get("disposition") == "accepted"]
            overridden = [x for x in items if x.get("disposition") in {"overridden", "ignored"}]
            ack_minutes = [float(x["time_to_acknowledge_minutes"]) for x in items if isinstance(x.get("time_to_acknowledge_minutes"), (int, float))]
            event_24h = [x for x in items if (x.get("outcomes") or {}).get("24h") == "event_occurred"]
            ppv = len(accepted) / total if total else 0.0
            override_rate = len(overridden) / total if total else 0.0
            drift = "green"
            if total >= 10 and ppv < 0.1 and override_rate > 0.8:
                drift = "red"
            elif total >= 10 and (ppv < 0.2 or override_rate > 0.65):
                drift = "yellow"
            rows.append(
                {
                    "scanner_name": scanner,
                    "fired_count": total,
                    "ppv": round(ppv, 3),
                    "override_rate": round(override_rate, 3),
                    "median_time_to_action_minutes": round(statistics.median(ack_minutes), 1) if ack_minutes else None,
                    "event_24h_rate": round(len(event_24h) / total, 3) if total else 0.0,
                    "nnt": round(total / max(len(accepted), 1), 1) if total else None,
                    "drift_status": drift,
                    "review_suggestion": drift == "red",
                    "threshold_advice": "建议人工复核并考虑上调阈值" if drift == "red" else "",
                    "closure": self._scanner_closure(total=total, accepted=len(accepted), overridden=len(overridden), ack_minutes=ack_minutes, drift=drift),
                    "recent_overrides": [
                        {
                            "alert_id": x.get("alert_id"),
                            "patient_id": x.get("patient_id"),
                            "fired_at": x.get("fired_at"),
                            "reason": x.get("override_reason"),
                        }
                        for x in sorted(overridden, key=lambda y: y.get("fired_at") or datetime.min, reverse=True)[:limit_examples]
                    ],
                }
            )
        rows.sort(key=lambda row: (row["drift_status"] != "red", row["drift_status"] != "yellow", -row["fired_count"]))
        rows = await self._attach_scanner_run_health(rows, since=since)
        return {"days": days, "source": "alert_outcomes", "rows": rows, "total_scanners": len(rows)}

    async def _scanner_health_from_alert_records(self, *, since: datetime, days: int) -> dict[str, Any]:
        cursor = self.db.col("alert_records").find(
            {"created_at": {"$gte": since}},
            {
                "_id": 1,
                "alert_type": 1,
                "rule_id": 1,
                "severity": 1,
                "created_at": 1,
                "acknowledged_at": 1,
                "ack_disposition": 1,
                "patient_id": 1,
                "override_reason": 1,
            },
        ).sort("created_at", -1).limit(5000)
        grouped: dict[str, list[dict[str, Any]]] = {}
        async for doc in cursor:
            scanner = str(doc.get("alert_type") or doc.get("rule_id") or "unknown")
            grouped.setdefault(scanner, []).append(doc)
        rows: list[dict[str, Any]] = []
        for scanner, items in grouped.items():
            total = len(items)
            accepted = [x for x in items if self.normalize_disposition(x.get("ack_disposition")) == "accepted"]
            overridden = [x for x in items if self.normalize_disposition(x.get("ack_disposition")) in {"overridden", "ignored"}]
            ack_minutes = []
            for item in items:
                minutes = _minutes_between(_dt(item.get("created_at")), _dt(item.get("acknowledged_at")))
                if minutes is not None:
                    ack_minutes.append(minutes)
            ppv = len(accepted) / total if total else 0.0
            override_rate = len(overridden) / total if total else 0.0
            drift = "green"
            if total >= 10 and ppv < 0.1 and override_rate > 0.8:
                drift = "red"
            elif total >= 10 and (ppv < 0.2 or override_rate > 0.65):
                drift = "yellow"
            rows.append(
                {
                    "scanner_name": scanner,
                    "fired_count": total,
                    "ppv": round(ppv, 3),
                    "override_rate": round(override_rate, 3),
                    "median_time_to_action_minutes": round(statistics.median(ack_minutes), 1) if ack_minutes else None,
                    "event_24h_rate": 0.0,
                    "nnt": round(total / max(len(accepted), 1), 1) if total else None,
                    "drift_status": drift,
                    "review_suggestion": drift == "red",
                    "threshold_advice": "建议人工复核并考虑上调阈值" if drift == "red" else "",
                    "closure": self._scanner_closure(total=total, accepted=len(accepted), overridden=len(overridden), ack_minutes=ack_minutes, drift=drift),
                    "recent_overrides": [
                        {
                            "alert_id": str(x.get("_id") or ""),
                            "patient_id": x.get("patient_id"),
                            "fired_at": x.get("created_at"),
                            "reason": x.get("override_reason") or self.normalize_override_reason(self.normalize_disposition(x.get("ack_disposition"))),
                        }
                        for x in sorted(overridden, key=lambda y: y.get("created_at") or datetime.min, reverse=True)[:5]
                    ],
                }
            )
        rows.sort(key=lambda row: (row["drift_status"] != "red", row["drift_status"] != "yellow", -row["fired_count"]))
        return {"days": days, "source": "alert_records_fallback", "rows": rows, "total_scanners": len(rows)}

    async def _attach_scanner_run_health(self, rows: list[dict[str, Any]], *, since: datetime) -> list[dict[str, Any]]:
        runs_by_scanner: dict[str, list[dict[str, Any]]] = {}
        cursor = self.db.col("scanner_runs").find(
            {"created_at": {"$gte": since}},
            {"scanner_name": 1, "status": 1, "duration_ms": 1, "error": 1, "created_at": 1},
        ).sort("created_at", -1).limit(10000)
        async for run in cursor:
            scanner = str(run.get("scanner_name") or "unknown")
            runs_by_scanner.setdefault(scanner, []).append(run)

        existing = {str(row.get("scanner_name") or "") for row in rows}
        for scanner, runs in runs_by_scanner.items():
            if scanner not in existing:
                rows.append(
                    {
                        "scanner_name": scanner,
                        "fired_count": 0,
                        "ppv": 0.0,
                        "override_rate": 0.0,
                        "median_time_to_action_minutes": None,
                        "event_24h_rate": 0.0,
                        "nnt": None,
                        "drift_status": "green",
                        "review_suggestion": False,
                        "threshold_advice": "",
                        "closure": {"percent": 100, "tasks": [], "label": "暂无触发"},
                        "recent_overrides": [],
                    }
                )

        for row in rows:
            scanner = str(row.get("scanner_name") or "unknown")
            runs = runs_by_scanner.get(scanner, [])
            if not runs:
                row["runtime_health"] = {
                    "run_count": 0,
                    "success_rate": None,
                    "error_rate": None,
                    "avg_duration_ms": None,
                    "p95_duration_ms": None,
                    "last_run_at": None,
                    "last_status": "unknown",
                    "last_error": "",
                    "tone": "unknown",
                }
                continue
            durations = sorted(float(run.get("duration_ms") or 0) for run in runs)
            errors = [run for run in runs if str(run.get("status") or "") != "success"]
            p95_index = min(len(durations) - 1, max(0, int(round(len(durations) * 0.95)) - 1))
            error_rate = len(errors) / len(runs)
            tone = "red" if error_rate >= 0.2 else "yellow" if error_rate >= 0.05 else "green"
            row["runtime_health"] = {
                "run_count": len(runs),
                "success_rate": round(1 - error_rate, 3),
                "error_rate": round(error_rate, 3),
                "avg_duration_ms": round(sum(durations) / len(durations), 1) if durations else None,
                "p95_duration_ms": round(durations[p95_index], 1) if durations else None,
                "last_run_at": runs[0].get("created_at"),
                "last_status": str(runs[0].get("status") or "unknown"),
                "last_error": str((errors[0] if errors else {}).get("error") or "")[:200],
                "tone": tone,
            }
            if tone == "red":
                row["review_suggestion"] = True
                row["threshold_advice"] = row.get("threshold_advice") or "该规则执行失败率偏高，建议先排查数据源或扫描器异常"
        return rows

    def _scanner_closure(self, *, total: int, accepted: int, overridden: int, ack_minutes: list[float], drift: str) -> dict[str, Any]:
        if total <= 0:
            return {"percent": 100, "tasks": [], "label": "暂无触发"}
        acked = len(ack_minutes)
        ack_rate = acked / total
        disposition_rate = (accepted + overridden) / total
        drift_score = 1.0 if drift == "green" else 0.7 if drift == "yellow" else 0.35
        percent = round((ack_rate * 0.45 + disposition_rate * 0.35 + drift_score * 0.2) * 100)
        tasks: list[dict[str, Any]] = []
        if drift == "red":
            tasks.append({"title": "主任复核阈值", "priority": "high", "action": "看覆盖样例"})
        elif drift == "yellow":
            tasks.append({"title": "抽查误报原因", "priority": "medium", "action": "看覆盖样例"})
        if ack_rate < 0.8:
            tasks.append({"title": "补齐响应闭环", "priority": "medium", "action": "追踪未响应"})
        if disposition_rate < 0.8:
            tasks.append({"title": "补齐反馈标签", "priority": "medium", "action": "补录结局"})
        return {
            "percent": max(0, min(100, percent)),
            "tasks": tasks[:3],
            "label": f"响应{round(ack_rate * 100)}% · 反馈{round(disposition_rate * 100)}%",
        }
