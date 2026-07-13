"""告警结局服务 v2 — 观察、人工复核统计、规则健康。

核心变更：
- infer_outcome() 只记录观察信号和疑似关联，不自动写 accepted/overridden/averted。
- scanner_health() 基于 alert_adjudications 人工复核（非 disposition 代理）。
- FDP (false discovery proportion) = FP / reviewed，非 FPR。
- 真正 FPR 需要非告警对照样本 → 返回 null。
- PPV 标注为 "已复核样本PPV"，附带 Wilson CI、review_coverage、sampling_method。
- min_review_threshold 可配置展示阈值，不宣称统计可靠。
- 快速反馈 (alert_feedback) 不进入正式统计。
"""
from __future__ import annotations

import math
import re
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

_INTERNAL_ERR_RE = re.compile(
    r"cursor\s+id\s+\d+\s+not\s+found|CursorNotFound|connection\s+(?:pool\s+)?(?:closed|reset)"
    r"|ServerSelectionTimeoutError|NetworkTimeout|WiredTigerError|BackgroundOperationInProgress",
    re.IGNORECASE,
)


def _sanitize_display_error(text: str) -> str:
    if not text:
        return ""
    if _INTERNAL_ERR_RE.search(text):
        return "数据源查询超时或游标失效，请稍后重试"
    return text


OUTCOME_WINDOWS = ("6h", "24h", "72h")
DEFAULT_MIN_REVIEW_THRESHOLD = 30


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


def _wilson_ci(numerator: int, denominator: int, z: float = 1.96) -> dict[str, Any]:
    """Wilson score confidence interval for a proportion."""
    if denominator <= 0:
        return {"lower": None, "upper": None, "method": "wilson", "z": z}
    p = numerator / denominator
    n = denominator
    z2 = z * z
    denominator_adj = 1.0 + z2 / n
    centre = (p + z2 / (2.0 * n)) / denominator_adj
    margin = z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n) / denominator_adj
    return {
        "lower": round(max(0.0, centre - margin), 4),
        "upper": round(min(1.0, centre + margin), 4),
        "method": "wilson",
        "z": z,
    }


class AlertOutcomeService:
    """告警结局服务 — 观察与人工复核统计（不再自动推断因果）。"""

    def __init__(self, db, *, rules_dir: str | Path | None = None) -> None:
        self.db = db
        self.rules_dir = (
            Path(rules_dir) if rules_dir
            else Path(__file__).resolve().parent.parent / "outcome_rules"
        )
        self._rules_cache: dict[str, dict[str, Any]] = {}

    def _alert_id(self, alert_doc: dict[str, Any]) -> str:
        return str(alert_doc.get("_id") or alert_doc.get("alert_id") or "")

    def _scanner_name(self, alert_doc: dict[str, Any]) -> str:
        return str(
            alert_doc.get("scanner_name")
            or alert_doc.get("alert_type")
            or alert_doc.get("rule_id")
            or "unknown"
        )

    def _text(self, value: Any) -> str:
        return str(value or "").strip()

    def _dept_scope_query(
        self, *, dept: str | None = None, dept_code: str | None = None,
    ) -> dict[str, Any] | None:
        dept_text = self._text(dept)
        dept_code_text = self._text(dept_code)
        if dept_text and not dept_code_text and dept_text.isdigit():
            dept_code_text = dept_text
            dept_text = ""
        clauses: list[dict[str, Any]] = []
        if dept_code_text:
            codes = [item.strip() for item in dept_code_text.split(",") if item.strip()]
            if codes:
                clauses.append({"deptCode": {"$in": codes}})
        if dept_text:
            clauses.append({
                "$or": [
                    {"dept": dept_text}, {"hisDept": dept_text},
                    {"department": dept_text}, {"deptName": dept_text},
                ],
            })
        if not clauses:
            return None
        return clauses[0] if len(clauses) == 1 else {"$or": clauses}

    async def _patient_keys_for_dept(
        self, *, dept: str | None = None, dept_code: str | None = None,
    ) -> set[str]:
        scope = self._dept_scope_query(dept=dept, dept_code=dept_code)
        if not scope:
            return set()
        cursor = self.db.col("patient").find(
            scope, {"_id": 1, "patientId": 1, "pid": 1, "hisPid": 1, "hisPID": 1},
        )
        keys: set[str] = set()
        async for patient in cursor:
            for field in ("_id", "patientId", "pid", "hisPid", "hisPID"):
                value = self._text(patient.get(field))
                if value:
                    keys.add(value)
        return keys

    def normalize_disposition(self, value: Any) -> str:
        """Keep for backward compat; no longer used for PPV/FPR inference."""
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

    def normalize_override_reason(
        self, disposition: str, reason_code: Any = "", reason_text: Any = "",
    ) -> dict[str, str]:
        code = str(reason_code or "").strip().lower()
        if not code:
            code = {
                "overridden": "not_clinically_relevant",
                "ignored": "defer_review",
                "partial": "monitoring_only",
                "accepted": "clinically_actionable",
            }.get(disposition, "unspecified")
        return {"code": code, "text": str(reason_text or "").strip()}

    # ── ensure / record basic lifecycle ────────────────────────────────────

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
            "time_to_acknowledge_minutes": _minutes_between(
                fired_at, _dt(alert_doc.get("acknowledged_at")),
            ),
            "disposition": self.normalize_disposition(alert_doc.get("ack_disposition")),
            "override_reason": self.normalize_override_reason(
                self.normalize_disposition(alert_doc.get("ack_disposition")),
            ),
            "related_order_change_ids": [],
            "related_operation_record_ids": [],
            "outcomes": {key: "unknown" for key in OUTCOME_WINDOWS},
            "manual_review_required": False,
            "inference": {"status": "pending", "updated_at": now},
            # New: adjudication summary (populated from alert_adjudications)
            "adjudication_summary": {
                "total_reviewed": 0,
                "true_positives": 0,
                "false_positives": 0,
                "indeterminate": 0,
                "actionable": 0,
                "already_addressed": 0,
                "helpful": 0,
                "neutral": 0,
                "harmful": 0,
                "insufficient_review_samples": True,
                "actionable_rate": None,
                "false_discovery_proportion": None,
                "review_sample_count": 0,
            },
            "created_at": now,
            "updated_at": now,
        }
        await self.db.col("alert_outcomes").update_one(
            {"alert_id": alert_id},
            {"$setOnInsert": base_doc, "$set": {"updated_at": now}},
            upsert=True,
        )
        return await self.db.col("alert_outcomes").find_one({"alert_id": alert_id})

    async def record_viewed(
        self, alert_ids: list[str], *, actor: str = "", source: str = "ui",
    ) -> int:
        if not alert_ids:
            return 0
        now = datetime.now()
        result = await self.db.col("alert_outcomes").update_many(
            {
                "alert_id": {
                    "$in": [str(x) for x in alert_ids if str(x or "").strip()],
                },
                "first_viewed_at": {"$in": [None, ""]},
            },
            {
                "$set": {
                    "first_viewed_at": now, "view_actor": actor,
                    "view_source": source, "updated_at": now,
                },
            },
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
        """Record acknowledgement WITHOUT auto-inferring outcome."""
        await self.ensure_for_alert(alert_doc)
        alert_id = self._alert_id(alert_doc)
        fired_at = _dt(alert_doc.get("created_at") or alert_doc.get("fired_at"))
        ack_at = _dt(alert_doc.get("acknowledged_at")) or datetime.now()
        normalized = self.normalize_disposition(
            disposition or alert_doc.get("ack_disposition"),
        )
        update = {
            "first_acknowledged_at": ack_at,
            "time_to_acknowledge_minutes": _minutes_between(fired_at, ack_at),
            "disposition": normalized,
            "override_reason": self.normalize_override_reason(
                normalized, reason_code, reason_text,
            ),
            "ack_actor": actor,
            "updated_at": datetime.now(),
        }
        await self.db.col("alert_outcomes").update_one(
            {"alert_id": alert_id}, {"$set": update}, upsert=False,
        )
        # No longer call infer_outcome here — observations are handled by
        # refresh_alert_lifecycle separately.
        return await self.db.col("alert_outcomes").find_one({"alert_id": alert_id})

    # ── observation-only outcome inference ─────────────────────────────────

    def _load_rule(self, scanner_name: str) -> dict[str, Any]:
        key = str(scanner_name or "generic").strip().lower()
        if key in self._rules_cache:
            return self._rules_cache[key]
        candidates = [
            self.rules_dir / f"{key}.outcome_rule.yaml",
            self.rules_dir / f"{key}.yaml",
            self.rules_dir / "generic.outcome_rule.yaml",
        ]
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

    async def _count_observed_signals(
        self, patient_id: str, fired_at: datetime, rule: dict[str, Any],
    ) -> tuple[int, list[str], list[str]]:
        """Count post-alert observed signals (NOT 'accepted' signals).

        These are observations only — no causal inference.
        """
        window_hours = int(
            (rule.get("suspected_response_signals") or rule.get("accepted_if") or {})
            .get("window_hours") or 6,
        )
        end = fired_at + timedelta(hours=window_hours)
        signals = (
            (rule.get("suspected_response_signals") or rule.get("accepted_if") or {})
            .get("signals") or []
        )
        matched: list[str] = []
        related_ids: list[str] = []
        if not signals:
            return 0, matched, related_ids

        collections = [
            "drugexe", "drug", "orders", "order",
            "operation_records", "nursing_records",
        ]
        for signal in signals:
            keywords = [str(x) for x in (signal.get("keywords") or [])]
            time_fields = [
                str(x) for x in (
                    signal.get("time_fields")
                    or ["created_at", "orderTime", "startTime", "time", "recordTime"]
                )
            ]
            found = False
            for col_name in collections:
                query = {
                    "$or": [
                        {"patient_id": patient_id},
                        {"pid": patient_id},
                        {"patientId": patient_id},
                    ],
                }
                cursor = self.db.col(col_name).find(query).limit(300)
                async for doc in cursor:
                    event_time = next(
                        (_dt(doc.get(field)) for field in time_fields if _dt(doc.get(field))),
                        None,
                    )
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

    async def infer_outcome(self, alert_doc: dict[str, Any]) -> dict[str, Any] | None:
        """Observe post-alert signals and SOFA delta WITHOUT writing
        accepted/overridden/averted disposition.

        This method now ONLY records observations:
        - observed_signals: keyword+time-matched post-alert events
        - sofa_delta: SOFA change (if available and window appropriate)
        - NONE of these are interpreted as causal or disposition-changing.
        """
        alert_id = self._alert_id(alert_doc)
        patient_id = str(alert_doc.get("patient_id") or "")
        fired_at = _dt(alert_doc.get("created_at") or alert_doc.get("fired_at"))
        if not alert_id or not patient_id or not fired_at:
            return None

        rule = self._load_rule(self._scanner_name(alert_doc))
        min_signals = int(
            (rule.get("suspected_response_signals") or rule.get("accepted_if") or {})
            .get("min_signals") or 1,
        )
        signal_count, matched, related_ids = await self._count_observed_signals(
            patient_id, fired_at, rule,
        )

        # SOFA delta observation (24h only — no short-term)
        sofa_delta = await self._sofa_delta(patient_id, fired_at, hours=24)

        # NEVER auto-write disposition — only record observations
        disposition = self.normalize_disposition(alert_doc.get("ack_disposition"))
        outcomes = {key: "unknown" for key in OUTCOME_WINDOWS}
        inference_reason = "observation_only"
        observation_notes = []

        if signal_count >= min_signals:
            observation_notes.append(
                f"observed_{signal_count}_post_alert_signals"
                f" (suspected only — not confirmed as response to alert)",
            )
            inference_reason = "post_alert_signals_observed"

        if sofa_delta is not None:
            observation_notes.append(
                f"sofa_delta_24h={sofa_delta}"
                f" (observation only — not attributed to alert or treatment)",
            )

        now = datetime.now()
        update = {
            "disposition": disposition,
            "related_order_change_ids": related_ids,
            "outcomes": outcomes,
            "manual_review_required": bool(
                sofa_delta is not None
                and sofa_delta >= 2
                and disposition in {"unknown", "partial"},
            ),
            "inference": {
                "status": "completed",
                "observed_signals": matched,
                "signal_count": signal_count,
                "sofa_delta_24h": sofa_delta,
                "reason": inference_reason,
                "observation_notes": observation_notes,
                "causal_inference": "NOT_PERFORMED",
                "updated_at": now,
            },
            "updated_at": now,
        }
        await self.db.col("alert_outcomes").update_one(
            {"alert_id": alert_id}, {"$set": update}, upsert=False,
        )
        return await self.db.col("alert_outcomes").find_one({"alert_id": alert_id})

    async def _sofa_delta(
        self, patient_id: str, fired_at: datetime, hours: int = 24,
    ) -> float | None:
        start = fired_at - timedelta(hours=24)
        end = fired_at + timedelta(hours=hours)
        cursor = self.db.col("score").find(
            {
                "$and": [
                    {"$or": [{"patient_id": patient_id}, {"pid": patient_id}]},
                    {
                        "$or": [
                            {"score_type": {"$regex": "sofa", "$options": "i"}},
                            {"scoreType": {"$regex": "sofa", "$options": "i"}},
                        ],
                    },
                    {
                        "$or": [
                            {"calc_time": {"$gte": start, "$lte": end}},
                            {"created_at": {"$gte": start, "$lte": end}},
                            {"time": {"$gte": start, "$lte": end}},
                        ],
                    },
                ],
            },
        ).sort("calc_time", 1).limit(80)
        before: list[float] = []
        after: list[float] = []
        async for doc in cursor:
            t = _dt(doc.get("calc_time") or doc.get("created_at") or doc.get("time"))
            val = _safe_float(
                doc.get("sofa_score") or doc.get("score") or doc.get("value"),
            )
            if t is None or val is None:
                continue
            if t <= fired_at:
                before.append(val)
            else:
                after.append(val)
        if not before or not after:
            return None
        return max(after) - before[-1]

    # ── scanner health (adjudication-based) ────────────────────────────────

    async def scanner_health(
        self,
        *,
        days: int = 30,
        limit_examples: int = 5,
        dept: str | None = None,
        dept_code: str | None = None,
    ) -> dict[str, Any]:
        """Scanner health based on alert_adjudications + alert_records.

        Key changes from v1:
        - PPV = TP/reviewed (reviewed sample PPV, NOT system-inferred).
        - FDP = FP/reviewed (NOT FPR; true FPR requires non-alert samples).
        - Wilson 95% CI included for all proportions.
        - review_coverage = reviewed_count / total_fired.
        - sampling_method always reported.
        - min_review_threshold only controls display hint, not statistical claims.
        """
        since = datetime.now() - timedelta(days=max(int(days or 30), 1))
        cfg = self._load_config()
        min_threshold = int(cfg.get("min_review_threshold", DEFAULT_MIN_REVIEW_THRESHOLD))

        # ── 1. Aggregate adjudications ──
        adj_pipeline = [
            {"$match": {"created_at": {"$gte": since}}},
            {
                "$group": {
                    "_id": "$scanner_name",
                    "total_adjudicated": {"$sum": 1},
                    "true_positives": {
                        "$sum": {"$cond": [{"$eq": ["$alert_validity", "true_positive"]}, 1, 0]},
                    },
                    "false_positives": {
                        "$sum": {"$cond": [{"$eq": ["$alert_validity", "false_positive"]}, 1, 0]},
                    },
                    "indeterminate": {
                        "$sum": {"$cond": [{"$eq": ["$alert_validity", "indeterminate"]}, 1, 0]},
                    },
                    "actionable": {
                        "$sum": {"$cond": [{"$eq": ["$clinical_actionability", "actionable"]}, 1, 0]},
                    },
                    "already_addressed": {
                        "$sum": {"$cond": [{"$eq": ["$workflow_context", "already_addressed"]}, 1, 0]},
                    },
                    "helpful": {
                        "$sum": {"$cond": [{"$eq": ["$clinical_helpfulness", "helpful"]}, 1, 0]},
                    },
                    "neutral": {
                        "$sum": {"$cond": [{"$eq": ["$clinical_helpfulness", "neutral"]}, 1, 0]},
                    },
                    "harmful": {
                        "$sum": {"$cond": [{"$eq": ["$clinical_helpfulness", "harmful"]}, 1, 0]},
                    },
                },
            },
            {"$sort": {"total_adjudicated": -1}},
        ]
        adj_rows = [
            doc async for doc in self.db.col("alert_adjudications").aggregate(adj_pipeline)
        ]
        adj_by_scanner: dict[str, dict[str, Any]] = {
            str(row["_id"] or "unknown"): row for row in adj_rows
        }

        # ── 2. Alert record counts ──
        record_pipeline = [
            {"$match": {"created_at": {"$gte": since}}},
            {
                "$group": {
                    "_id": {
                        "$ifNull": [
                            "$alert_type",
                            {"$ifNull": ["$scanner_name", {"$ifNull": ["$rule_id", "unknown"]}]},
                        ],
                    },
                    "fired_count": {"$sum": 1},
                    "acknowledged_count": {
                        "$sum": {"$cond": [{"$ifNull": ["$acknowledged_at", False]}, 1, 0]},
                    },
                },
            },
        ]
        record_rows = [
            doc async for doc in self.db.col("alert_records").aggregate(record_pipeline)
        ]
        fired_by_scanner: dict[str, int] = {}
        ack_by_scanner: dict[str, int] = {}
        for row in record_rows:
            scanner = str(row["_id"] or "unknown")
            fired_by_scanner[scanner] = int(row.get("fired_count") or 0)
            ack_by_scanner[scanner] = int(row.get("acknowledged_count") or 0)

        all_scanners = sorted(set(list(adj_by_scanner.keys()) + list(fired_by_scanner.keys())))

        rows: list[dict[str, Any]] = []
        for scanner in all_scanners:
            adj = adj_by_scanner.get(scanner, {})
            fired = fired_by_scanner.get(scanner, 0)
            ack_count = ack_by_scanner.get(scanner, 0)

            all_reviewed = int(adj.get("total_adjudicated") or 0)
            tp = int(adj.get("true_positives") or 0)
            fp = int(adj.get("false_positives") or 0)
            indeterminate = int(adj.get("indeterminate") or 0)
            determinate = tp + fp  # TP + FP, EXCLUDES indeterminate

            # FDP = FP / (TP + FP) — indeterminate excluded
            fdp = round(fp / determinate, 3) if determinate > 0 else None
            # PPV = TP / (TP + FP) — indeterminate excluded
            ppv = round(tp / determinate, 3) if determinate > 0 else None
            ppv_ci = _wilson_ci(tp, determinate) if determinate > 0 else {"lower": None, "upper": None}
            # Indeterminate proportion
            indet_prop = round(indeterminate / all_reviewed, 3) if all_reviewed > 0 else None

            review_coverage = round(all_reviewed / fired, 3) if fired > 0 else 0.0
            # Use formally_reviewed_count (all_reviewed), not coverage
            insufficient = all_reviewed < min_threshold

            drift = "green"
            if determinate >= min_threshold and ppv is not None and ppv < 0.1 and (
                fdp is not None and fdp > 0.8
            ):
                drift = "red"
            elif determinate >= min_threshold and (
                (ppv is not None and ppv < 0.2) or (fdp is not None and fdp > 0.65)
            ):
                drift = "yellow"
            if insufficient:
                drift = "green"  # Don't flag when we have insufficient data

            # Acknowledgement times from alert_records
            ack_minutes: list[float] = []
            ack_cursor = self.db.col("alert_records").find(
                {
                    "created_at": {"$gte": since},
                    "alert_type": scanner,
                    "acknowledged_at": {"$ne": None},
                },
                {"created_at": 1, "acknowledged_at": 1},
            ).limit(500)
            async for doc in ack_cursor:
                created = _dt(doc.get("created_at"))
                acked = _dt(doc.get("acknowledged_at"))
                if created and acked:
                    ack_minutes.append(max((acked - created).total_seconds() / 60.0, 0.0))

            rows.append({
                "scanner_name": scanner,
                "fired_count": fired,
                "acknowledged_count": ack_count,
                "formally_reviewed_count": all_reviewed,
                "determinate_reviewed": determinate,
                "review_coverage": review_coverage,
                "min_review_count": min_threshold,
                "min_review_coverage": round(min_threshold / fired, 3) if fired > 0 else None,
                # PPV = TP/(TP+FP)
                "reviewed_sample_ppv": ppv,
                "ppv_note": f"PPV={tp}/{determinate}=TP/(TP+FP) — indeterminate excluded",
                "ppv_ci_lower": ppv_ci.get("lower"),
                "ppv_ci_upper": ppv_ci.get("upper"),
                # FDP = FP/(TP+FP)
                "false_discovery_proportion": fdp,
                "fdp_note": f"FDP={fp}/{determinate}=FP/(TP+FP) — not FPR; true FPR requires non-alert samples",
                "true_fpr": None,
                "true_fpr_note": "FPR=FP/(FP+TN) cannot be computed without non-alert control samples",
                # Indeterminate
                "indeterminate_proportion": indet_prop,
                "indeterminate_count": indeterminate,
                # Other stats
                "true_positive_count": tp,
                "false_positive_count": fp,
                "actionable_count": int(adj.get("actionable") or 0),
                "already_addressed_count": int(adj.get("already_addressed") or 0),
                "helpful_count": int(adj.get("helpful") or 0),
                "neutral_count": int(adj.get("neutral") or 0),
                "harmful_count": int(adj.get("harmful") or 0),
                # Review sufficiency
                "insufficient_review_samples": insufficient,
                "min_review_threshold": min_threshold,
                "min_review_threshold_note": (
                    "Configurable display threshold — does NOT guarantee statistical reliability. "
                    "Always consider numerator, denominator, and CI."
                ),
                # Sampling
                "sampling_method": "convenience",
                "sampling_note": "Based on available human adjudications — not random sampling",
                "representativeness": "unknown",
                # Response time
                "median_time_to_acknowledge_minutes": (
                    round(statistics.median(ack_minutes), 1) if ack_minutes else None
                ),
                # Drift
                "drift_status": drift,
                "review_suggestion": drift == "red",
                "threshold_advice": "建议人工复核并考虑上调阈值" if drift == "red" else "",
                "closure": self._scanner_closure(
                    total=fired, reviewed=all_reviewed, tp=tp, fp=fp,
                    ack_minutes=ack_minutes, drift=drift,
                ),
            })

        rows.sort(key=lambda row: (
            row["drift_status"] != "red",
            row["drift_status"] != "yellow",
            -row["fired_count"],
        ))
        rows = await self._attach_scanner_run_health(rows, since=since)

        return {
            "days": days,
            "source": "alert_adjudications",
            "rows": rows,
            "total_scanners": len(rows),
            "statistical_notes": {
                "fpr_unavailable": True,
                "fpr_reason": "No non-alert control samples — true FPR (=FP/(FP+TN)) cannot be computed.",
                "ppv_scope": "Reviewed sample PPV only — not population PPV.",
                "sampling": "Convenience sample from human adjudications.",
                "ci_method": "Wilson score interval (95%)",
            },
        }

    async def _scanner_health_from_alert_records(
        self, *, since: datetime, days: int,
        patient_keys: set[str] | None = None,
    ) -> dict[str, Any]:
        """Fallback when alert_adjudications is empty — returns review_coverage=0."""
        query: dict[str, Any] = {"created_at": {"$gte": since}}
        if patient_keys is not None:
            if patient_keys:
                query = {"$and": [query, {"patient_id": {"$in": list(patient_keys)}}]}
            else:
                query = {"_id": {"$exists": False}}
        cursor = self.db.col("alert_records").find(
            query,
            {
                "_id": 1, "alert_type": 1, "rule_id": 1, "severity": 1,
                "created_at": 1, "acknowledged_at": 1, "ack_disposition": 1,
                "patient_id": 1, "override_reason": 1,
            },
        ).sort("created_at", -1).limit(5000)
        grouped: dict[str, list[dict[str, Any]]] = {}
        async for doc in cursor:
            scanner = str(doc.get("alert_type") or doc.get("rule_id") or "unknown")
            grouped.setdefault(scanner, []).append(doc)
        rows: list[dict[str, Any]] = []
        for scanner, items in grouped.items():
            total = len(items)
            ack_minutes = []
            for item in items:
                minutes = _minutes_between(
                    _dt(item.get("created_at")), _dt(item.get("acknowledged_at")),
                )
                if minutes is not None:
                    ack_minutes.append(minutes)
            rows.append({
                "scanner_name": scanner,
                "fired_count": total,
                "formally_reviewed_count": 0,
                "determinate_reviewed": 0,
                "review_coverage": 0.0,
                "min_review_count": DEFAULT_MIN_REVIEW_THRESHOLD,
                "min_review_coverage": None,
                "reviewed_sample_ppv": None,
                "ppv_ci_lower": None,
                "ppv_ci_upper": None,
                "false_discovery_proportion": None,
                "indeterminate_proportion": None,
                "true_fpr": None,
                "insufficient_review_samples": True,
                "min_review_threshold": DEFAULT_MIN_REVIEW_THRESHOLD,
                "sampling_method": "none",
                "sampling_note": "No human adjudications available yet",
                "median_time_to_acknowledge_minutes": (
                    round(statistics.median(ack_minutes), 1) if ack_minutes else None
                ),
                "drift_status": "green",
                "review_suggestion": False,
                "threshold_advice": "",
                "closure": self._scanner_closure(
                    total=total, reviewed=0, tp=0, fp=0,
                    ack_minutes=ack_minutes, drift="green",
                ),
            })
        rows.sort(key=lambda row: -row["fired_count"])
        return {
            "days": days, "source": "alert_records_fallback",
            "rows": rows, "total_scanners": len(rows),
            "note": "No adjudication data yet — showing alert record counts only."
                     " All PPV/FDP values are null.",
        }

    async def _attach_scanner_run_health(
        self, rows: list[dict[str, Any]], *, since: datetime,
    ) -> list[dict[str, Any]]:
        runs_by_scanner: dict[str, list[dict[str, Any]]] = {}
        cursor = self.db.col("scanner_runs").find(
            {"created_at": {"$gte": since}},
            {
                "scanner_name": 1, "status": 1, "duration_ms": 1,
                "error": 1, "created_at": 1,
            },
        ).sort("created_at", -1).limit(10000)
        async for run in cursor:
            scanner = str(run.get("scanner_name") or "unknown")
            runs_by_scanner.setdefault(scanner, []).append(run)

        existing = {str(row.get("scanner_name") or "") for row in rows}
        for scanner, runs in runs_by_scanner.items():
            if scanner not in existing:
                rows.append({
                    "scanner_name": scanner,
                    "fired_count": 0,
                    "reviewed_count": 0,
                    "review_coverage": 0.0,
                    "reviewed_sample_ppv": None,
                    "ppv_ci_lower": None,
                    "ppv_ci_upper": None,
                    "false_discovery_proportion": None,
                    "true_fpr": None,
                    "insufficient_review_samples": True,
                    "min_review_threshold": DEFAULT_MIN_REVIEW_THRESHOLD,
                    "sampling_method": "none",
                    "median_time_to_acknowledge_minutes": None,
                    "drift_status": "green",
                    "review_suggestion": False,
                    "threshold_advice": "",
                    "closure": {"percent": 100, "tasks": [], "label": "暂无触发"},
                })

        for row in rows:
            scanner = str(row.get("scanner_name") or "unknown")
            runs = runs_by_scanner.get(scanner, [])
            if not runs:
                row["runtime_health"] = {
                    "run_count": 0, "success_rate": None, "error_rate": None,
                    "avg_duration_ms": None, "p95_duration_ms": None,
                    "last_run_at": None, "last_status": "unknown",
                    "last_error": "", "tone": "unknown",
                }
                continue
            durations = sorted(float(run.get("duration_ms") or 0) for run in runs)
            errors = [run for run in runs if str(run.get("status") or "") != "success"]
            p95_index = min(
                len(durations) - 1,
                max(0, int(round(len(durations) * 0.95)) - 1),
            )
            error_rate = len(errors) / len(runs) if runs else 0.0
            tone = "red" if error_rate >= 0.2 else "yellow" if error_rate >= 0.05 else "green"
            row["runtime_health"] = {
                "run_count": len(runs),
                "success_rate": round(1 - error_rate, 3),
                "error_rate": round(error_rate, 3),
                "avg_duration_ms": round(sum(durations) / len(durations), 1) if durations else None,
                "p95_duration_ms": round(durations[p95_index], 1) if durations else None,
                "last_run_at": runs[0].get("created_at"),
                "last_status": str(runs[0].get("status") or "unknown"),
                "last_error": _sanitize_display_error(
                    str((errors[0] if errors else {}).get("error") or ""),
                )[:200],
                "tone": tone,
            }
            if tone == "red":
                row["review_suggestion"] = True
                row["threshold_advice"] = (
                    row.get("threshold_advice")
                    or "该规则执行失败率偏高，建议先排查数据源或扫描器异常"
                )
        return rows

    def _scanner_closure(
        self, *, total: int, reviewed: int, tp: int, fp: int,
        ack_minutes: list[float], drift: str,
    ) -> dict[str, Any]:
        if total <= 0:
            return {"percent": 100, "tasks": [], "label": "暂无触发"}
        acked = len(ack_minutes)
        ack_rate = acked / total
        review_rate = reviewed / total if total > 0 else 0.0
        drift_score = 1.0 if drift == "green" else 0.7 if drift == "yellow" else 0.35
        percent = round((ack_rate * 0.40 + review_rate * 0.40 + drift_score * 0.20) * 100)
        tasks: list[dict[str, Any]] = []
        if drift == "red":
            tasks.append({"title": "主任复核阈值", "priority": "high", "action": "看覆盖样例"})
        elif drift == "yellow":
            tasks.append({"title": "抽查误报原因", "priority": "medium", "action": "看覆盖样例"})
        if ack_rate < 0.8:
            tasks.append({"title": "补齐响应闭环", "priority": "medium", "action": "追踪未响应"})
        if review_rate < 0.3:
            tasks.append({"title": "增加人工复核样本", "priority": "medium", "action": "发起复核"})
        return {
            "percent": max(0, min(100, percent)),
            "tasks": tasks[:3],
            "label": f"响应{round(ack_rate * 100)}% · 复核{round(review_rate * 100)}%",
        }

    # ── config ─────────────────────────────────────────────────────────────

    def _load_config(self) -> dict[str, Any]:
        """Load scanner_health config from yaml or defaults."""
        try:
            path = self.rules_dir / "scanner_health.yaml"
            if path.exists():
                return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            pass
        return {}
