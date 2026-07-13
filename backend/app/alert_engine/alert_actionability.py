"""告警启发式优先级评分（frozen at trigger）、疑似关联检测、指标观察与人工复核。

核心设计原则：
- heuristic_attention_score 在告警触发时冻结，后续事件不反向修改（禁止未来信息泄漏）。
- 告警后药物匹配仅标记为 suspected（疑似关联），不自动视为 action_taken。
- 指标变化仅记录观察（attribution=not_assessed），不自动声称因果效应。
- 人工复核写入 append-only alert_adjudications 集合；alert_records 仅保存最新汇总投影。
- 快速反馈写入 alert_feedback，不进入正式 PPV/误报统计。
"""
from __future__ import annotations

import math
import statistics
from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId
from app.services.alert_outcome_service import AlertOutcomeService

# ── metric observation configuration ──────────────────────────────────────────
# Each metric defines allowed observation windows and improvement_direction.
# SOFA is explicitly excluded from short-term windows (not clinically meaningful).
_METRIC_OBSERVATION_CONFIG: dict[str, dict[str, Any]] = {
    "map": {
        "windows_minutes": [30, 120, 360],
        "improvement_direction": "toward_range",
        "target_range": [65, 100],
        "baseline_window_hours": 1,
        "description": "MAP (mmHg)",
    },
    "lactate": {
        "windows_minutes": [120, 360, 720],
        "improvement_direction": "decrease",
        "baseline_window_hours": 2,
        "description": "Lactate (mmol/L)",
    },
    "urine_output": {
        "windows_minutes": [120, 360, 720],
        "improvement_direction": "increase",
        "baseline_window_hours": 2,
        "description": "Urine output (mL/kg/h)",
    },
    "creatinine": {
        "windows_minutes": [720, 1440],
        "improvement_direction": "decrease",
        "baseline_window_hours": 24,
        "description": "Creatinine (µmol/L)",
    },
    "sofa": {
        "windows_minutes": [1440],
        "improvement_direction": "decrease",
        "baseline_window_hours": 24,
        "description": "SOFA score (24h only — short-term delta not meaningful)",
        "min_observation_gap_hours": 24,
    },
}


def _observe_metric_direction(
    baseline: float,
    followup: float,
    direction: str,
    target_range: list[float] | None = None,
) -> dict[str, Any]:
    """Return observation direction label without claiming improvement."""
    delta = round(float(followup) - float(baseline), 2)
    if direction == "increase":
        label = "上升" if delta > 0 else "下降" if delta < 0 else "无变化"
    elif direction == "decrease":
        label = "下降" if delta < 0 else "上升" if delta > 0 else "无变化"
    elif direction == "toward_range" and target_range and len(target_range) == 2:
        lo, hi = target_range
        if baseline < lo and followup >= lo:
            label = "进入目标范围"
        elif baseline > hi and followup <= hi:
            label = "进入目标范围"
        elif (baseline < lo and followup > baseline) or (baseline > hi and followup < baseline):
            label = "趋向目标范围"
        else:
            label = "偏离目标范围"
    else:
        label = "变化"
    return {"delta": delta, "direction_label": label, "direction": direction}


def _wilson_ci(numerator: int, denominator: int, z: float = 1.96) -> dict[str, float | None]:
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


class AlertActionabilityScorerMixin:
    # ═══════════════════════════════════════════════════════════════════════════
    # utility helpers (keep unchanged)
    # ═══════════════════════════════════════════════════════════════════════════

    def _normalize_lifecycle_actor(self, actor: str | None, *, source: str = "") -> str:
        raw = str(actor or "").strip()
        if not raw:
            return ""
        generic_tokens = {
            "ui", "websocket", "patient_detail", "patientdetail",
            "analytics", "overview", "ai_ops", "bigscreen", "mdt",
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

    def _attention_level(self, score_100: float) -> str:
        """Heuristic attention level (not clinical actionability)."""
        if score_100 >= 75:
            return "immediate"
        if score_100 >= 50:
            return "prompt"
        return "routine"

    def _metric_config(self, metric: str) -> dict[str, Any]:
        """Retrieve observation config for a metric, with runtime overrides."""
        base = dict(_METRIC_OBSERVATION_CONFIG.get(metric, {}))
        cfg = self._actionability_cfg()
        overrides = cfg.get("metric_observation_overrides", {})
        if isinstance(overrides, dict) and metric in overrides:
            if isinstance(overrides[metric], dict):
                base.update(overrides[metric])
        return base

    # ═══════════════════════════════════════════════════════════════════════════
    # keyword generation for suspected action detection (keep)
    # ═══════════════════════════════════════════════════════════════════════════

    def _actionability_signal_keywords(self, alert_doc: dict[str, Any]) -> list[str]:
        text = " ".join([
            str(alert_doc.get("rule_id") or ""),
            str(alert_doc.get("alert_type") or ""),
            str(alert_doc.get("category") or ""),
            str(alert_doc.get("parameter") or ""),
            str(alert_doc.get("name") or ""),
        ]).lower()
        keyword_groups = [
            (["shock", "hypotension", "map", "lactate", "hemodynamic", "低血压", "休克", "乳酸", "灌注"],
             ["去甲肾上腺素", "肾上腺素", "血管加压素", "多巴胺", "去氧肾上腺素", "乳酸林格", "氯化钠", "白蛋白"]),
            (["sepsis", "sofa", "qsofa", "感染", "脓毒", "抗菌"],
             ["美罗培南", "哌拉西林", "他唑巴坦", "头孢", "万古霉素", "替考拉宁", "亚胺培南", "抗生素", "乳酸林格", "氯化钠"]),
            (["ards", "resp", "spo2", "oxygen", "vent", "呼吸", "氧合", "肺", "气道"],
             ["呋塞米", "布地奈德", "沙丁胺醇", "异丙托溴铵", "甲泼尼龙", "地塞米松", "抗生素"]),
            (["aki", "renal", "cr", "尿量", "肾", "液体"],
             ["呋塞米", "白蛋白", "碳酸氢钠"]),
            (["bleed", "dic", "plt", "出血", "凝血"],
             ["氨甲环酸", "纤维蛋白原", "血浆", "红细胞", "血小板"]),
            (["delir", "sedat", "谵妄", "镇静", "躁动"],
             ["右美托咪定", "丙泊酚", "咪达唑仑", "氟哌啶醇", "奥氮平"]),
        ]
        keywords: list[str] = []
        for triggers, candidates in keyword_groups:
            if any(token in text for token in triggers):
                for item in candidates:
                    if item not in keywords:
                        keywords.append(item)
        return keywords[:12]

    # ═══════════════════════════════════════════════════════════════════════════
    # heuristic attention score (FROZEN at alert trigger time)
    # ═══════════════════════════════════════════════════════════════════════════

    async def _heuristic_history_factor(
        self, alert_doc: dict[str, Any], lookback_days: int, min_samples: int,
    ) -> dict[str, Any]:
        """History factor: only pre-trigger formal adjudications, grouped by rule_id.

        - Filters to created_at < alert trigger time (no future leakage).
        - Groups by rule_id/scanner_name.
        - Uses determinate_reviewed = TP + FP (excludes indeterminate).
        - Low sample: neutral prior 0.65, weight NOT applied (applied=False).
        - NEVER uses feedback, old accepted, or unacknowledged proxies.
        """
        now = datetime.now()
        # Only look at adjudications BEFORE this alert's trigger time
        trigger_time = (
            alert_doc.get("created_at")
            if isinstance(alert_doc.get("created_at"), datetime)
            else now
        )
        since = trigger_time - timedelta(days=max(int(lookback_days or 30), 1))

        match_or: list[dict[str, Any]] = []
        scanner_name = str(alert_doc.get("scanner_name") or "").strip()
        rule_id = str(alert_doc.get("rule_id") or "").strip()
        alert_type = str(alert_doc.get("alert_type") or "").strip()
        if scanner_name:
            match_or.append({"scanner_name": scanner_name})
        if rule_id:
            match_or.append({"rule_id": rule_id})
        if alert_type:
            match_or.append({"alert_type": alert_type})
        if not match_or:
            return {
                "factor": None, "applied": False,
                "sample_count": 0, "source": "formal_adjudications_pre_trigger",
                "confidence": "low", "note": "no rule_id/scanner_name — neutral prior",
            }

        cursor = self.db.col("alert_adjudications").find(
            {
                "created_at": {"$gte": since, "$lt": trigger_time},
                "$or": match_or,
            },
            {
                "alert_validity": 1, "review_tier": 1,
                "created_at": 1, "scanner_name": 1,
            },
        ).sort("created_at", -1).limit(300)
        docs = [doc async for doc in cursor]

        # Only final adjudications, exclude feedback / preliminary only
        formally_reviewed = [
            d for d in docs
            if d.get("alert_validity") in {"true_positive", "false_positive", "indeterminate"}
        ]
        tp_count = sum(1 for d in formally_reviewed if d.get("alert_validity") == "true_positive")
        fp_count = sum(1 for d in formally_reviewed if d.get("alert_validity") == "false_positive")
        indeterminate_count = sum(1 for d in formally_reviewed if d.get("alert_validity") == "indeterminate")
        determinate = tp_count + fp_count
        all_reviewed = len(formally_reviewed)

        min_needed = max(int(min_samples or 8), 3)
        # Need enough determinate (TP+FP) reviews for a meaningful factor
        if determinate < min_needed:
            return {
                "factor": None, "applied": False,
                "sample_count": determinate,
                "all_reviewed_count": all_reviewed,
                "indeterminate_count": indeterminate_count,
                "min_needed": min_needed,
                "source": "formal_adjudications_pre_trigger",
                "confidence": "low",
                "note": f"insufficient determinate reviews ({determinate} < {min_needed}) — neutral prior, weight NOT applied",
            }

        fdp = round(fp_count / max(determinate, 1), 3)
        return {
            "factor": round(self._actionability_clip(1.0 - fdp), 3),
            "applied": True,
            "sample_count": determinate,
            "all_reviewed_count": all_reviewed,
            "indeterminate_count": indeterminate_count,
            "true_positive_count": tp_count,
            "false_positive_count": fp_count,
            "false_discovery_proportion": fdp,
            "source": "formal_adjudications_pre_trigger",
            "confidence": "moderate" if determinate >= 30 else "low",
            "note": "FDP=FP/(TP+FP) — not FPR. Based on pre-trigger formal adjudications only.",
        }

    async def _attention_patient_state(
        self, patient_id: str, patient_doc: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Patient state factor based on vitals/labs/SOFA at alert time."""
        vitals = await self._get_latest_vitals_by_patient(patient_id)
        his_pid = str((patient_doc or {}).get("hisPid") or (patient_doc or {}).get("hisPID") or "").strip()
        labs = await self._get_latest_labs_map(his_pid, lookback_hours=48) if his_pid else {}
        lactate = ((labs.get("lactate") or {}).get("value") if isinstance(labs, dict) else None)
        sofa_doc = await self.db.col("score").find_one(
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

    async def _compute_heuristic_attention_score(
        self, alert_doc: dict[str, Any], patient_doc: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Compute heuristic attention score FROZEN at alert trigger time.

        Formula uses only data available AT trigger time:
        - severity (25%)
        - patient state (MAP/lactate/SOFA at trigger) (45%)
        - history of human adjudications (30%)

        Medication matches, circadian, and recent-ack factors are EXCLUDED
        (moved to notification_policy). This prevents future-information leakage.
        """
        cfg = self._actionability_cfg()
        patient_id = str(alert_doc.get("patient_id") or "")
        severity = str(alert_doc.get("severity") or "warning").lower()
        severity_factor = {
            "info": 0.2, "normal": 0.3, "warning": 0.45,
            "high": 0.75, "critical": 1.0,
        }.get(severity, 0.45)

        state = await self._attention_patient_state(patient_id, patient_doc)
        history = await self._heuristic_history_factor(
            alert_doc,
            int(cfg.get("history_lookback_days", 30) or 30),
            int(cfg.get("min_history_samples", 8) or 8),
        )
        # When history factor is not applied (insufficient samples), redistribute:
        # severity 0.35 + state 0.65 — neutral on history
        if history.get("applied") and history.get("factor") is not None:
            weighted = (
                severity_factor * 0.25
                + float(state.get("factor") or 0.0) * 0.45
                + float(history.get("factor") or 0.0) * 0.30
            )
        else:
            weighted = (
                severity_factor * 0.35
                + float(state.get("factor") or 0.0) * 0.65
            )
        score = round(self._actionability_clip(weighted) * 100, 1)
        return {
            "score": score,
            "level": self._attention_level(score),
            "factors": {
                "severity_factor": round(severity_factor, 3),
                "patient_state_factor": round(float(state.get("factor") or 0.0), 3),
                "history_factor": round(float(history.get("factor") or 0.0), 3),
            },
            "patient_state": state,
            "history": history,
            "validated": False,
            "note": "heuristic rule-based priority reference — NOT clinical actionability."
                     " Clinical actionability requires human adjudication.",
            "frozen_at": datetime.now(),
        }

    async def _initialize_alert_attention_score(
        self, alert_doc: dict[str, Any], patient_doc: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Compute and FREEZE heuristic attention score at alert creation.

        The score is never backfilled or modified by post-alert events.
        """
        if not bool(self._actionability_cfg().get("enabled", True)):
            return alert_doc
        alert_doc.setdefault("viewed_at", None)
        alert_doc.setdefault("acknowledged_at", None)
        alert_doc.setdefault("lifecycle_updated_at", datetime.now())

        # Compute and freeze
        attention = await self._compute_heuristic_attention_score(alert_doc, patient_doc)

        # Write as heuristic_attention_score (new field name)
        alert_doc["heuristic_attention_score"] = attention.get("score")
        alert_doc["heuristic_attention_level"] = attention.get("level")
        alert_doc["heuristic_attention_factors"] = attention.get("factors")
        alert_doc["heuristic_attention_validated"] = False
        alert_doc["heuristic_attention_frozen_at"] = attention.get("frozen_at")

        # Backward-compat: also write old field names for readers that haven't migrated
        alert_doc["actionability_score"] = attention.get("score")
        alert_doc["actionability_level"] = attention.get("level")
        alert_doc["actionability_factors"] = attention.get("factors")

        extra = alert_doc.get("extra") if isinstance(alert_doc.get("extra"), dict) else {}
        extra["heuristic_attention"] = {
            "score": attention.get("score"),
            "level": attention.get("level"),
            "validated": False,
            "patient_state": attention.get("patient_state"),
            "history": attention.get("history"),
            "frozen_at": attention.get("frozen_at"),
        }
        alert_doc["extra"] = extra
        return alert_doc

    # ═══════════════════════════════════════════════════════════════════════════
    # SUSPECTED action detection (NOT action_taken)
    # ═══════════════════════════════════════════════════════════════════════════

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

    async def _detect_suspected_actions(
        self, alert_doc: dict[str, Any], patient_doc: dict[str, Any] | None,
        hours: int = 24,
    ) -> dict[str, Any] | None:
        """Detect suspected post-alert actions via keyword+time match.

        Returns action_linkage with status="suspected" — NEVER "action_taken".
        Does NOT modify alert_doc.
        """
        patient_id = str(alert_doc.get("patient_id") or "")
        if not patient_id:
            return None
        created_at = (
            alert_doc.get("created_at")
            if isinstance(alert_doc.get("created_at"), datetime)
            else datetime.now() - timedelta(hours=1)
        )
        cfg = self._actionability_cfg()
        lookback_minutes = max(int(cfg.get("action_match_lookback_minutes", 30) or 30), 0)
        start_time = created_at - timedelta(minutes=lookback_minutes)
        end_time = created_at + timedelta(hours=max(int(hours or 24), 1))
        keywords = self._actionability_signal_keywords(alert_doc)

        cursor = self.db.col("drugExe").find(
            {"pid": patient_id},
            {
                "drugName": 1, "orderName": 1, "dose": 1, "doseUnit": 1,
                "route": 1, "frequency": 1, "status": 1,
                "executeTime": 1, "startTime": 1, "orderTime": 1,
                "orderId": 1, "order_id": 1, "prescNo": 1,
            },
        ).sort("executeTime", -1).limit(300)
        matches: list[dict[str, Any]] = []
        async for doc in cursor:
            event_time = self._alert_drug_time(doc)
            if not event_time:
                continue
            # Only orders AFTER the alert (within window). Pre-alert orders
            # within lookback are recorded separately as pre_existing.
            if event_time > end_time:
                continue
            haystack = " ".join([str(doc.get("drugName") or ""), str(doc.get("orderName") or "")]).lower()
            if keywords and not any(str(keyword).lower() in haystack for keyword in keywords):
                continue

            match_keyword = next(
                (k for k in keywords if str(k).lower() in haystack), ""
            )
            delay_minutes = (
                round((event_time - created_at).total_seconds() / 60.0, 1)
                if event_time >= created_at
                else round((event_time - created_at).total_seconds() / 60.0, 1)
            )
            matches.append({
                "drug_name": str(doc.get("drugName") or doc.get("orderName") or "").strip(),
                "order_name": str(doc.get("orderName") or doc.get("drugName") or "").strip(),
                "dose": doc.get("dose"),
                "dose_unit": doc.get("doseUnit"),
                "route": doc.get("route"),
                "frequency": doc.get("frequency"),
                "status": doc.get("status"),
                "order_id": str(doc.get("orderId") or doc.get("order_id") or doc.get("prescNo") or "").strip() or None,
                "order_time": event_time,
                "match_keyword": match_keyword,
                "delay_minutes": delay_minutes,
            })

        if not matches:
            return None

        post_alert = [m for m in matches if m["delay_minutes"] >= 0]
        return {
            "status": "suspected",
            "method": "keyword_time_match",
            "confidence": None,
            "confidence_calibrated": False,
            "evidence_strength": "weak",
            "matched_orders": matches[:10],
            "temporal_relation": {
                "alert_time": created_at,
                "first_order_time": matches[0]["order_time"],
                "delay_minutes": matches[0]["delay_minutes"],
            },
            "alternative_indications": [],
            "confirmed_by": None,
            "confirmed_at": None,
            "confirmation_note": (
                "System-detected keyword+time match — NOT confirmed as clinically related."
                " Requires clinician confirmation."
            ),
            "match_summary": "；".join(
                item.get("drug_name") or item.get("order_name") or ""
                for item in matches[:3]
                if (item.get("drug_name") or item.get("order_name"))
            ),
        }

    # ═══════════════════════════════════════════════════════════════════════════
    # POST-ALERT METRIC OBSERVATION (NOT outcome_delta)
    # ═══════════════════════════════════════════════════════════════════════════

    async def _metric_near_time(
        self, patient_id: str, patient_doc: dict[str, Any] | None,
        metric: str, start: datetime, end: datetime,
    ) -> float | None:
        if end <= start:
            return None
        if metric == "map":
            codes = list(self._cfg("vital_signs", "map_priority",
                                    default=["param_ibp_m", "param_nibp_m"])
                         or ["param_ibp_m", "param_nibp_m"])
            for code in codes:
                series = await self._get_param_series_by_pid(
                    patient_id, str(code), start,
                    prefer_device_types=["monitor"], limit=240,
                )
                points = [row for row in series if start <= row.get("time", start) <= end]
                if points:
                    try:
                        return float(points[-1].get("value"))
                    except Exception:
                        continue
            return None
        if metric in ("lactate", "creatinine"):
            his_pid = str((patient_doc or {}).get("hisPid") or (patient_doc or {}).get("hisPID") or "").strip()
            if not his_pid:
                return None
            rows = await self._get_lab_series(his_pid, metric, start, end, limit=30)
            if not rows:
                return None
            try:
                return float(rows[-1].get("value"))
            except Exception:
                return None
        if metric == "urine_output":
            # Use nursing records or bedside data
            his_pid = str((patient_doc or {}).get("hisPid") or (patient_doc or {}).get("hisPID") or "").strip()
            if not his_pid:
                return None
            rows = await self._get_lab_series(his_pid, "urine_output", start, end, limit=30)
            if not rows:
                return None
            try:
                return float(rows[-1].get("value"))
            except Exception:
                return None
        if metric == "sofa":
            doc = await self.db.col("score").find_one(
                {
                    "patient_id": patient_id,
                    "score_type": {"$in": ["sofa", "sepsis_sofa", "sofa_score"]},
                    "calc_time": {"$gte": start, "$lte": end},
                },
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

    async def _metric_window_summary(
        self, patient_id: str, patient_doc: dict[str, Any] | None,
        metric: str, start: datetime, end: datetime,
    ) -> dict[str, Any] | None:
        if end <= start:
            return None
        values: list[float] = []
        if metric == "map":
            codes = list(self._cfg("vital_signs", "map_priority",
                                    default=["param_ibp_m", "param_nibp_m"])
                         or ["param_ibp_m", "param_nibp_m"])
            for code in codes:
                series = await self._get_param_series_by_pid(
                    patient_id, str(code), start,
                    prefer_device_types=["monitor"], limit=240,
                )
                points = [row for row in series if start <= row.get("time", start) <= end]
                if not points:
                    continue
                for row in points:
                    try:
                        values.append(float(row.get("value")))
                    except Exception:
                        continue
                if values:
                    break
        elif metric in ("lactate", "creatinine"):
            his_pid = str((patient_doc or {}).get("hisPid") or (patient_doc or {}).get("hisPID") or "").strip()
            if not his_pid:
                return None
            rows = await self._get_lab_series(his_pid, metric, start, end, limit=30)
            for row in rows or []:
                try:
                    values.append(float(row.get("value")))
                except Exception:
                    continue
        elif metric == "urine_output":
            his_pid = str((patient_doc or {}).get("hisPid") or (patient_doc or {}).get("hisPID") or "").strip()
            if not his_pid:
                return None
            rows = await self._get_lab_series(his_pid, "urine_output", start, end, limit=30)
            for row in rows or []:
                try:
                    values.append(float(row.get("value")))
                except Exception:
                    continue
        elif metric == "sofa":
            rows = [
                row async for row in self.db.col("score").find(
                    {
                        "patient_id": patient_id,
                        "score_type": {"$in": ["sofa", "sepsis_sofa", "sofa_score"]},
                        "calc_time": {"$gte": start, "$lte": end},
                    },
                    {"score": 1, "sofa_score": 1, "value": 1, "score_value": 1},
                ).sort("calc_time", 1).limit(40)
            ]
            for row in rows:
                for key in ("score", "sofa_score", "value", "score_value"):
                    raw = row.get(key)
                    if raw is None:
                        continue
                    try:
                        values.append(float(raw))
                        break
                    except Exception:
                        continue
        if not values:
            return None
        mean_value = round(sum(values) / len(values), 2)
        median_value = round(statistics.median(values), 2)
        return {
            "count": len(values),
            "mean": mean_value,
            "median": median_value,
            "representative": median_value,
        }

    async def _observe_post_alert_metrics(
        self,
        alert_doc: dict[str, Any],
        patient_doc: dict[str, Any] | None,
        anchor_time: datetime,
        anchor_type: str = "alert_time",
    ) -> dict[str, Any] | None:
        """Observe post-alert metric changes WITHOUT claiming causality.

        Configurable per-metric observation windows.
        anchor_type: "alert_time" | "suspected_action_time" | "clinician_confirmed_action_time"
        """
        patient_id = str(alert_doc.get("patient_id") or "")
        if not patient_id:
            return None

        result: dict[str, Any] = {
            "status": "not_available",
            "anchor": {
                "type": anchor_type,
                "time": anchor_time,
            },
            "metrics": {},
            "observation_windows": {},
            "attribution": "not_assessed",
            "limitations": [
                "Observational only — no causal inference.",
                "Confounding by concurrent treatments, disease progression, and measurement variability.",
            ],
        }

        any_observed = False
        for metric, config in _METRIC_OBSERVATION_CONFIG.items():
            # Skip SOFA for short-term anchors unless enough time has passed
            if metric == "sofa":
                min_gap = config.get("min_observation_gap_hours", 24)
                if anchor_type in ("alert_time", "suspected_action_time"):
                    continue  # SOFA not suitable for these anchors

            metric_cfg = self._metric_config(metric)
            if not metric_cfg:
                metric_cfg = config

            windows_minutes = metric_cfg.get("windows_minutes", [])
            baseline_hours = metric_cfg.get("baseline_window_hours", 1)
            direction = metric_cfg.get("improvement_direction", "decrease")
            target_range = metric_cfg.get("target_range")

            baseline_start = anchor_time - timedelta(hours=baseline_hours)
            baseline_end = anchor_time
            baseline_meta = await self._metric_window_summary(
                patient_id, patient_doc, metric, baseline_start, baseline_end,
            )
            baseline = (baseline_meta or {}).get("representative")
            if baseline is None:
                continue

            window_results: dict[str, Any] = {}
            for window_min in windows_minutes:
                followup = await self._metric_near_time(
                    patient_id, patient_doc, metric,
                    anchor_time, anchor_time + timedelta(minutes=window_min),
                )
                if followup is None:
                    continue
                obs = _observe_metric_direction(baseline, followup, direction, target_range)
                obs["baseline"] = baseline
                obs["baseline_meta"] = baseline_meta
                obs["followup"] = followup
                obs["observation_window_minutes"] = window_min
                window_key = f"{window_min}m"
                window_results[window_key] = obs
                any_observed = True

            if window_results:
                result["metrics"][metric] = {
                    "config": {
                        "improvement_direction": direction,
                        "target_range": target_range,
                        "baseline_window_hours": baseline_hours,
                    },
                    "windows": window_results,
                }

        if any_observed:
            result["status"] = "observed"
        if not result["metrics"]:
            return None
        return result

    # ═══════════════════════════════════════════════════════════════════════════
    # alert lifecycle refresh (observations only — never modifies frozen score)
    # ═══════════════════════════════════════════════════════════════════════════

    async def refresh_alert_lifecycle(
        self,
        alert_doc: dict[str, Any],
        patient_doc: dict[str, Any] | None = None,
        *,
        persist: bool = False,
    ) -> dict[str, Any]:
        """Refresh post-alert observations WITHOUT modifying frozen attention score.

        Only populates:
        - action_linkage (suspected actions)
        - outcome_observation (metric changes)
        """
        if not isinstance(alert_doc, dict):
            return alert_doc
        if not bool(self._actionability_cfg().get("enabled", True)):
            return alert_doc
        patient_id = str(alert_doc.get("patient_id") or "")
        if not patient_doc and patient_id and hasattr(self, "_load_patient"):
            patient_doc, _ = await self._load_patient(patient_id)
        changed = False

        # Detect suspected actions → action_linkage (NOT action_taken)
        if not alert_doc.get("action_linkage"):
            suspected = await self._detect_suspected_actions(
                alert_doc, patient_doc,
                hours=int(self._actionability_cfg().get("action_match_hours", 24) or 24),
            )
            if suspected:
                alert_doc["action_linkage"] = suspected
                changed = True

        # Observe post-alert metrics → outcome_observation (NOT outcome_delta)
        if not alert_doc.get("outcome_observation"):
            # Use alert_time as anchor
            alert_time = (
                alert_doc.get("created_at")
                if isinstance(alert_doc.get("created_at"), datetime)
                else datetime.now()
            )
            observation = await self._observe_post_alert_metrics(
                alert_doc, patient_doc, alert_time, anchor_type="alert_time",
            )
            if observation:
                alert_doc["outcome_observation"] = observation
                changed = True

        if alert_doc.get("_id") is None and not changed:
            return alert_doc
        if changed:
            alert_doc["lifecycle_updated_at"] = datetime.now()

        # Persist only observation fields — NEVER backfill heuristic_attention_score
        if persist and changed and alert_doc.get("_id") is not None:
            persist_fields: dict[str, Any] = {
                "lifecycle_updated_at": alert_doc.get("lifecycle_updated_at"),
            }
            if alert_doc.get("action_linkage"):
                persist_fields["action_linkage"] = alert_doc["action_linkage"]
            if alert_doc.get("outcome_observation"):
                persist_fields["outcome_observation"] = alert_doc["outcome_observation"]
            await self.db.col("alert_records").update_one(
                {"_id": alert_doc.get("_id")},
                {"$set": persist_fields},
            )
        return alert_doc

    # ═══════════════════════════════════════════════════════════════════════════
    # viewed / acknowledgement / disposition / review (largely unchanged)
    # ═══════════════════════════════════════════════════════════════════════════

    async def mark_alerts_viewed(
        self, alert_ids: list[str], *, actor: str = "", source: str = "ui",
    ) -> int:
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
            {"_id": {"$in": object_ids},
             "$or": [{"viewed_at": None}, {"viewed_at": {"$exists": False}}]},
            {"$set": {"viewed_at": now, "view_source": source,
                       "view_actor": actor, "lifecycle_updated_at": now}},
        )
        try:
            await AlertOutcomeService(self.db).record_viewed(
                [str(oid) for oid in object_ids], actor=actor, source=source,
            )
        except Exception:
            pass
        return int(result.modified_count or 0)

    async def acknowledge_alert(
        self,
        alert_id: str,
        *,
        actor: str = "",
        note: str = "",
        disposition: str = "",
        override_reason_code: str = "",
        override_reason_text: str = "",
    ) -> dict[str, Any] | None:
        VALID_DISPOSITIONS = {
            "resolved", "accepted", "watching", "later",
            "false_positive", "override", "overridden", "escalate", "ignored", "",
        }
        disposition = str(disposition or "").strip().lower()
        if disposition not in VALID_DISPOSITIONS:
            disposition = ""
        try:
            oid = ObjectId(str(alert_id))
        except Exception:
            return None
        now = datetime.now()
        actor = self._normalize_lifecycle_actor(actor)
        update_fields: dict[str, Any] = {
            "acknowledged_at": now,
            "ack_actor": actor,
            "ack_note": note,
            "lifecycle_updated_at": now,
        }
        if disposition:
            update_fields["ack_disposition"] = disposition
        if override_reason_code or override_reason_text:
            update_fields["override_reason"] = {
                "code": str(override_reason_code or "").strip(),
                "text": str(override_reason_text or "").strip(),
            }
        await self.db.col("alert_records").update_one(
            {"_id": oid}, {"$set": update_fields},
        )
        doc = await self.db.col("alert_records").find_one({"_id": oid})
        if not doc:
            return None
        doc = await self.refresh_alert_lifecycle(doc, persist=True)
        try:
            await AlertOutcomeService(self.db).record_acknowledgement(
                doc, actor=actor, disposition=disposition,
                reason_code=override_reason_code,
                reason_text=override_reason_text or note,
            )
        except Exception:
            pass
        return doc

    async def disposition_alert(
        self,
        alert_id: str,
        *,
        action: str = "",
        reason: str = "",
        actor: str = "",
        review_after_minutes: int | None = None,
        review_metrics: list[str] | None = None,
    ) -> dict[str, Any] | None:
        try:
            oid = ObjectId(str(alert_id))
        except Exception:
            return None
        now = datetime.now()
        actor = self._normalize_lifecycle_actor(actor)
        action = str(action or "handled").strip().lower()
        review_minutes = int(review_after_minutes or 0)
        review_due_at = now + timedelta(minutes=review_minutes) if review_minutes > 0 else None
        update_fields: dict[str, Any] = {
            "acknowledged_at": now,
            "ack_actor": actor,
            "ack_note": reason,
            "ack_disposition": action,
            "disposition": {
                "action": action, "reason": reason, "actor": actor,
                "time": now, "review_after_minutes": review_minutes,
                "review_metrics": review_metrics or [],
            },
            "lifecycle_updated_at": now,
        }
        if review_due_at:
            update_fields["review_due_at"] = review_due_at
            update_fields["review_status"] = "pending"
        if action in {"handled", "resolved", "false_positive", "duplicate", "data_error", "ignore"}:
            update_fields["is_active"] = False
        await self.db.col("alert_records").update_one({"_id": oid}, {"$set": update_fields})
        doc = await self.db.col("alert_records").find_one({"_id": oid})
        if not doc:
            return None
        doc = await self.refresh_alert_lifecycle(doc, persist=True)
        try:
            await AlertOutcomeService(self.db).record_acknowledgement(
                doc, actor=actor, disposition=action, reason_text=reason,
            )
        except Exception:
            pass
        return doc

    async def review_alert(
        self,
        alert_id: str,
        *,
        result: str = "",
        evidence: list[str] | None = None,
        actor: str = "",
    ) -> dict[str, Any] | None:
        try:
            oid = ObjectId(str(alert_id))
        except Exception:
            return None
        now = datetime.now()
        actor = self._normalize_lifecycle_actor(actor)
        result = str(result or "reviewed").strip().lower()
        update_fields = {
            "review_status": result,
            "reviewed_at": now,
            "review_actor": actor,
            "review_result": {
                "result": result,
                "evidence": evidence or [],
                "actor": actor,
                "time": now,
                "improved": result in {"improved", "resolved", "better"},
            },
            "lifecycle_updated_at": now,
        }
        await self.db.col("alert_records").update_one({"_id": oid}, {"$set": update_fields})
        doc = await self.db.col("alert_records").find_one({"_id": oid})
        if not doc:
            return None
        return await self.refresh_alert_lifecycle(doc, persist=True)

    # ═══════════════════════════════════════════════════════════════════════════
    # clinical review (ARDS etc.) — keep existing
    # ═══════════════════════════════════════════════════════════════════════════

    async def clinical_review_alert(
        self,
        alert_id: str,
        *,
        action: str,
        actor: str,
        expected_version: int | None = None,
        alternative_diagnosis: str | None = None,
        review_basis: str | None = None,
        review_note: str = "",
    ) -> dict[str, Any] | None:
        try:
            oid = ObjectId(str(alert_id))
        except Exception:
            return None
        now = datetime.now()
        actor = self._normalize_lifecycle_actor(actor)
        if not actor:
            return None
        valid_actions = {"confirm", "reject", "needs_more_data", "alternative_diagnosis"}
        action = str(action or "").strip().lower()
        if action not in valid_actions:
            return None
        doc = await self.db.col("alert_records").find_one({"_id": oid})
        if not doc:
            return None
        extra = doc.get("extra") if isinstance(doc.get("extra"), dict) else {}
        assessment = extra.get("assessment") if isinstance(extra.get("assessment"), dict) else {}
        current_machine = assessment.get("machine_assessment") if isinstance(assessment.get("machine_assessment"), dict) else {}
        clinician_review = assessment.get("clinician_review") if isinstance(assessment.get("clinician_review"), dict) else {}
        current_version = int(clinician_review.get("version") or 0)
        if expected_version is not None and current_version != int(expected_version):
            return {
                "_id": oid, "conflict": True, "current_version": current_version,
                "message": "复核版本冲突：告警已被其他人更新，请刷新后重试",
            }
        new_version = current_version + 1
        review_status_map = {
            "confirm": "ards_confirmed_by_clinician",
            "reject": "clinician_rejected",
            "needs_more_data": "insufficient_data",
            "alternative_diagnosis": "alternative_diagnosis",
        }
        clinician_review_entry = {
            "action": action,
            "status": review_status_map.get(action, action),
            "reviewed_by": actor,
            "reviewed_at": now,
            "review_basis": str(review_basis or "").strip() or None,
            "alternative_diagnosis": str(alternative_diagnosis or "").strip() or None,
            "review_note": str(review_note or "").strip() or None,
            "version": new_version,
            "machine_assessment_snapshot": current_machine,
            "data_snapshot": {
                "ratio_type": assessment.get("ratio_type"),
                "ratio_value": assessment.get("ratio_value"),
                "oxygenation_grade": assessment.get("oxygenation_grade"),
                "peep": assessment.get("peep"),
                "fio2": assessment.get("fio2"),
                "oxygenation_time": assessment.get("oxygenation_time"),
            },
        }
        update_fields: dict[str, Any] = {
            "extra.assessment.clinician_review": clinician_review_entry,
            "extra.assessment.status": review_status_map.get(action, assessment.get("status")),
            "lifecycle_updated_at": now,
        }
        await self.db.col("alert_records").update_one({"_id": oid}, {"$set": update_fields})
        audit_entry = {
            "alert_id": str(oid),
            "patient_id": doc.get("patient_id"),
            "alert_type": doc.get("alert_type"),
            "action": f"clinical_review_{action}",
            "actor": actor,
            "timestamp": now,
            "details": {
                "previous_version": current_version,
                "new_version": new_version,
                "review_status": review_status_map.get(action, action),
                "alternative_diagnosis": str(alternative_diagnosis or "").strip() or None,
                "review_basis": str(review_basis or "").strip() or None,
                "review_note": str(review_note or "").strip() or None,
            },
        }
        try:
            await self.db.col("audit_log").insert_one(audit_entry)
        except Exception:
            pass
        updated = await self.db.col("alert_records").find_one({"_id": oid})
        if not updated:
            return None
        return await self.refresh_alert_lifecycle(updated, persist=True)

    # ═══════════════════════════════════════════════════════════════════════════
    # FORMAL ADJUDICATION (append-only → alert_adjudications)
    # ═══════════════════════════════════════════════════════════════════════════

    async def adjudicate_alert(
        self,
        alert_id: str,
        *,
        actor: str,
        role: str,
        review_tier: str = "preliminary",
        alert_validity: str,
        clinical_actionability: str = "unreviewed",
        workflow_context: str = "unreviewed",
        clinical_helpfulness: str = "unreviewed",
        action_related: bool | None = None,
        harm_type: str = "",
        harm_description: str = "",
        requires_secondary_review: bool = False,
        missed_by_workflow: bool = False,
        reason_codes: list[str] | None = None,
        comment: str = "",
        expected_version: int | None = None,
    ) -> dict[str, Any] | None:
        """Submit formal adjudication to append-only alert_adjudications collection.

        Two-tier system:
        - preliminary_review: resident/fellow can initiate. Requires final_adjudication.
        - final_adjudication: attending/intensivist/director or authorized clinical reviewer.

        Four INDEPENDENT dimensions:
        - alert_validity: true_positive | false_positive | indeterminate
        - clinical_actionability: actionable | non_actionable | unreviewed
        - workflow_context: already_addressed | new_finding | unreviewed
        - clinical_helpfulness: helpful | neutral | harmful | unreviewed

        Domain-based role authorization:
        - nursing alerts: nurse practitioners / head nurse can formally review
        - pharmacy alerts: pharmacists can formally review
        - data-quality alerts: clinical informatics reviewer can formally review

        If helpfulness="harmful": harm_type and harm_description are REQUIRED,
        and requires_secondary_review must be true.
        """
        try:
            oid = ObjectId(str(alert_id))
        except Exception:
            return None

        actor = self._normalize_lifecycle_actor(actor)
        if not actor:
            return {"error": "unauthenticated", "message": "无法识别操作者身份"}

        # Validate review tier
        valid_tiers = {"preliminary", "final"}
        review_tier = str(review_tier or "preliminary").strip().lower()
        if review_tier not in valid_tiers:
            return {"error": "invalid_review_tier",
                    "message": f"review_tier must be one of {valid_tiers}"}

        # Role authorization for final adjudication
        FINAL_ADJUDICATION_ROLES = {
            "attending", "intensivist", "director", "causal_reviewer",
            "senior_clinician", "consultant",
        }
        PRELIMINARY_ROLES = {
            "resident", "fellow", "doctor", "physician", "clinician",
            "nurse_practitioner", "head_nurse",
            "pharmacist", "clinical_pharmacist",
            "clinical_informatics",
        }
        role_lower = str(role or "").strip().lower()
        if review_tier == "final" and role_lower not in FINAL_ADJUDICATION_ROLES:
            return {
                "error": "insufficient_role_for_final",
                "message": (
                    f"Role '{role_lower}' cannot submit final adjudication. "
                    f"Final requires: {sorted(FINAL_ADJUDICATION_ROLES)}. "
                    f"Please submit as preliminary_review instead."
                ),
            }

        # Domain-based authorization
        alert_type = str(await self._get_alert_field(oid, "alert_type") or "").lower()
        alert_domain = str(await self._get_alert_field(oid, "alert_domain") or "").lower()
        nursing_domains = {"nursing", "care", "nurse_reminder", "vap_bundle", "pressure_ulcer", "fall_risk", "delirium"}
        pharmacy_domains = {"drug", "antibiotic", "tdm", "pk", "dose", "medication", "antimicrobial"}
        data_quality_domains = {"data_quality", "signal_quality", "missing_data"}
        if any(d in alert_type or d in alert_domain for d in nursing_domains):
            if role_lower not in FINAL_ADJUDICATION_ROLES and role_lower not in {
                "nurse_practitioner", "head_nurse", "nurse",
            }:
                pass  # non-blocking: domain-aware but not enforced strictly for preliminary
        if any(d in alert_type or d in alert_domain for d in pharmacy_domains):
            if role_lower not in FINAL_ADJUDICATION_ROLES and role_lower not in {
                "pharmacist", "clinical_pharmacist",
            }:
                pass  # non-blocking for preliminary

        # Validate dimensions
        valid_validity = {"true_positive", "false_positive", "indeterminate", "unreviewed"}
        valid_actionability = {"actionable", "non_actionable", "unreviewed"}
        valid_workflow = {"already_addressed", "new_finding", "unreviewed"}
        valid_helpfulness = {"helpful", "neutral", "harmful", "unreviewed"}

        alert_validity = str(alert_validity or "unreviewed").strip().lower()
        clinical_actionability = str(clinical_actionability or "unreviewed").strip().lower()
        workflow_context = str(workflow_context or "unreviewed").strip().lower()
        clinical_helpfulness = str(clinical_helpfulness or "unreviewed").strip().lower()

        if alert_validity not in valid_validity:
            return {"error": "invalid_alert_validity",
                    "message": f"alert_validity must be one of {valid_validity}"}
        if clinical_actionability not in valid_actionability:
            return {"error": "invalid_clinical_actionability",
                    "message": f"clinical_actionability must be one of {valid_actionability}"}
        if workflow_context not in valid_workflow:
            return {"error": "invalid_workflow_context",
                    "message": f"workflow_context must be one of {valid_workflow}"}
        if clinical_helpfulness not in valid_helpfulness:
            return {"error": "invalid_clinical_helpfulness",
                    "message": f"clinical_helpfulness must be one of {valid_helpfulness}"}

        # Harmful requires harm_type, harm_description, and secondary review
        if clinical_helpfulness == "harmful":
            if not str(harm_type or "").strip():
                return {"error": "harm_type_required",
                        "message": "harm_type is required when clinical_helpfulness=harmful"}
            if not str(harm_description or "").strip():
                return {"error": "harm_description_required",
                        "message": "harm_description is required when clinical_helpfulness=harmful"}
            if not requires_secondary_review:
                return {"error": "secondary_review_required",
                        "message": "requires_secondary_review must be true when clinical_helpfulness=harmful"}

        now = datetime.now()

        # Optimistic lock check
        latest = await self.db.col("alert_adjudications").find_one(
            {"alert_id": str(oid)},
            sort=[("version", -1)],
        )
        current_version = int((latest or {}).get("version") or 0)
        if expected_version is not None and current_version != int(expected_version):
            return {
                "conflict": True,
                "current_version": current_version,
                "message": "复核版本冲突：该告警已被其他人复核，请刷新后重试",
            }
        new_version = current_version + 1

        # Build append-only adjudication document
        adjudication_doc = {
            "alert_id": str(oid),
            "patient_id": str(await self._get_alert_patient_id(oid)),
            "rule_id": str(await self._get_alert_field(oid, "rule_id") or ""),
            "alert_type": str(await self._get_alert_field(oid, "alert_type") or ""),
            "alert_domain": str(await self._get_alert_field(oid, "alert_domain") or ""),
            "scanner_name": str(await self._get_alert_field(oid, "scanner_name")
                                or await self._get_alert_field(oid, "alert_type") or ""),
            "dept": str(await self._get_alert_field(oid, "dept") or ""),
            "dept_code": str(await self._get_alert_field(oid, "deptCode") or ""),
            "version": new_version,
            # Two-tier
            "review_tier": review_tier,
            # Four independent dimensions
            "alert_validity": alert_validity,
            "clinical_actionability": clinical_actionability,
            "workflow_context": workflow_context,
            "clinical_helpfulness": clinical_helpfulness,
            # Action linkage confirmation
            "action_related": action_related,
            # Harmful details
            "harm_type": str(harm_type or "").strip() or None,
            "harm_description": str(harm_description or "").strip() or None,
            "requires_secondary_review": requires_secondary_review,
            # Workflow
            "missed_by_workflow": missed_by_workflow,
            # Meta
            "reason_codes": reason_codes or [],
            "comment": str(comment or "").strip(),
            "reviewer": actor,
            "reviewer_role": str(role or "").strip() or "clinician",
            "reviewed_at": now,
            "created_at": now,
        }
        inserted = await self.db.col("alert_adjudications").insert_one(adjudication_doc)
        adjudication_doc["_id"] = inserted.inserted_id

        # Update alert_records with latest adjudication summary projection
        await self._sync_adjudication_summary_to_alert(str(oid))

        # Write audit log
        try:
            await self.db.col("audit_log").insert_one({
                "alert_id": str(oid),
                "action": "adjudicate_alert",
                "actor": actor,
                "role": role,
                "timestamp": now,
                "details": {
                    "version": new_version,
                    "alert_validity": alert_validity,
                    "clinical_actionability": clinical_actionability,
                    "workflow_context": workflow_context,
                    "clinical_helpfulness": clinical_helpfulness,
                    "action_related": action_related,
                    "requires_secondary_review": requires_secondary_review,
                },
            })
        except Exception:
            pass

        return {
            "adjudication": adjudication_doc,
            "version": new_version,
        }

    async def _get_alert_patient_id(self, oid: ObjectId) -> str:
        doc = await self.db.col("alert_records").find_one(
            {"_id": oid}, {"patient_id": 1},
        )
        return str((doc or {}).get("patient_id") or "")

    async def _get_alert_field(self, oid: ObjectId, field: str) -> str:
        doc = await self.db.col("alert_records").find_one(
            {"_id": oid}, {field: 1},
        )
        return str((doc or {}).get(field) or "")

    async def _sync_adjudication_summary_to_alert(self, alert_id: str) -> None:
        """Sync latest adjudication summary projection to alert_records.

        Uses correct denominators:
        - determinate_reviewed = TP + FP (excludes indeterminate)
        - PPV = TP / (TP + FP)
        - FDP = FP / (TP + FP)
        - indeterminate_proportion = indeterminate / all_formally_reviewed
        """
        try:
            oid = ObjectId(str(alert_id))
        except Exception:
            return

        pipeline = [
            {"$match": {"alert_id": str(oid)}},
            {"$sort": {"version": -1}},
            {"$limit": 1},
        ]
        latest_list = [
            doc async for doc in self.db.col("alert_adjudications").aggregate(pipeline)
        ]
        if not latest_list:
            return
        latest = latest_list[0]

        # Count by validity
        all_cursor = self.db.col("alert_adjudications").find(
            {"alert_id": str(oid)},
            {"alert_validity": 1, "action_related": 1, "review_tier": 1},
        )
        all_adjs = [doc async for doc in all_cursor]
        tp = sum(1 for d in all_adjs if d.get("alert_validity") == "true_positive")
        fp = sum(1 for d in all_adjs if d.get("alert_validity") == "false_positive")
        indet = sum(1 for d in all_adjs if d.get("alert_validity") == "indeterminate")
        determinate = tp + fp
        all_reviewed = len(all_adjs)
        final_count = sum(1 for d in all_adjs if d.get("review_tier") == "final")
        action_confirmed = sum(1 for d in all_adjs if d.get("action_related") is True)

        summary = {
            "manual_adjudication": {
                "alert_validity": latest.get("alert_validity"),
                "clinical_actionability": latest.get("clinical_actionability"),
                "workflow_context": latest.get("workflow_context"),
                "clinical_helpfulness": latest.get("clinical_helpfulness"),
                "action_related": latest.get("action_related"),
                "harm_type": latest.get("harm_type"),
                "requires_secondary_review": latest.get("requires_secondary_review"),
                "missed_by_workflow": latest.get("missed_by_workflow"),
                "reviewer": latest.get("reviewer"),
                "reviewer_role": latest.get("reviewer_role"),
                "review_tier": latest.get("review_tier"),
                "reviewed_at": latest.get("reviewed_at"),
                "version": latest.get("version"),
                "total_adjudications": all_reviewed,
                "final_adjudications": final_count,
                "determinate_reviewed": determinate,
                "true_positive_count": tp,
                "false_positive_count": fp,
                "indeterminate_count": indet,
                "action_related_confirmed": action_confirmed,
                "reason_codes": latest.get("reason_codes") or [],
                "comment": latest.get("comment") or "",
            },
            "lifecycle_updated_at": datetime.now(),
        }
        await self.db.col("alert_records").update_one(
            {"_id": oid},
            {"$set": summary},
        )

    async def get_adjudication_history(
        self, alert_id: str, limit: int = 50,
    ) -> list[dict[str, Any]]:
        """Retrieve full adjudication history for an alert."""
        cursor = self.db.col("alert_adjudications").find(
            {"alert_id": str(alert_id)},
        ).sort("version", -1).limit(max(int(limit), 1))
        return [doc async for doc in cursor]

    # ═══════════════════════════════════════════════════════════════════════════
    # QUICK FEEDBACK (→ alert_feedback, NOT included in PPV/FPR stats)
    # ═══════════════════════════════════════════════════════════════════════════

    async def submit_alert_feedback(
        self,
        alert_id: str,
        *,
        actor: str = "",
        feedback_type: str = "",
        quick_label: str = "",
        note: str = "",
    ) -> dict[str, Any] | None:
        """Submit quick feedback (NOT formal adjudication).

        Feedback goes to alert_feedback collection and does NOT enter
        PPV/FPR/clinical actionability statistics.
        """
        try:
            oid = ObjectId(str(alert_id))
        except Exception:
            return None

        actor = self._normalize_lifecycle_actor(actor)
        now = datetime.now()
        valid_types = {"useful", "not_useful", "already_known", "noise", "other"}
        feedback_type = str(feedback_type or "").strip().lower()
        if feedback_type not in valid_types:
            feedback_type = "other"

        doc = {
            "alert_id": str(oid),
            "feedback_type": feedback_type,
            "quick_label": str(quick_label or "").strip()[:120],
            "note": str(note or "").strip()[:500],
            "actor": actor,
            "created_at": now,
            "enters_formal_stats": False,
        }
        result = await self.db.col("alert_feedback").insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc

    # ═══════════════════════════════════════════════════════════════════════════
    # analytics (updated with new terminology)
    # ═══════════════════════════════════════════════════════════════════════════

    async def alert_lifecycle_analytics(
        self, *, hours: int = 24, dept: str | None = None,
        dept_code: str | None = None,
    ) -> dict[str, Any]:
        window_hours = max(int(hours or 24), 1)
        since = datetime.now() - timedelta(hours=window_hours)
        query: dict[str, Any] = {"created_at": {"$gte": since}}
        if dept:
            query["dept"] = dept
        elif dept_code:
            query["deptCode"] = dept_code

        docs = [
            doc async for doc in self.db.col("alert_records").find(
                query,
                {
                    "alert_type": 1, "name": 1, "created_at": 1,
                    "viewed_at": 1, "acknowledged_at": 1,
                    "action_linkage": 1, "heuristic_attention_score": 1,
                    "manual_adjudication": 1,
                },
            )
        ]
        total = len(docs)
        viewed = [doc for doc in docs if doc.get("viewed_at")]
        acked = [doc for doc in docs if doc.get("acknowledged_at")]
        # actioned → has suspected or confirmed linkage
        has_linkage = [
            doc for doc in docs
            if doc.get("action_linkage") and isinstance(doc.get("action_linkage"), dict)
        ]
        adjudicated = [
            doc for doc in docs
            if doc.get("manual_adjudication") and isinstance(doc.get("manual_adjudication"), dict)
            and doc["manual_adjudication"].get("alert_validity") in {
                "true_positive", "false_positive", "indeterminate",
            }
        ]
        determinate_adjudicated = [
            doc for doc in adjudicated
            if doc["manual_adjudication"].get("alert_validity") in {
                "true_positive", "false_positive",
            }
        ]

        view_minutes = [
            max((doc.get("viewed_at") - doc.get("created_at")).total_seconds() / 60.0, 0.0)
            for doc in viewed
            if isinstance(doc.get("created_at"), datetime)
            and isinstance(doc.get("viewed_at"), datetime)
        ]
        ack_minutes = [
            max((doc.get("acknowledged_at") - doc.get("created_at")).total_seconds() / 60.0, 0.0)
            for doc in acked
            if isinstance(doc.get("created_at"), datetime)
            and isinstance(doc.get("acknowledged_at"), datetime)
        ]

        by_type: dict[str, dict[str, Any]] = {}
        for doc in docs:
            key = str(doc.get("alert_type") or doc.get("name") or "unknown")
            row = by_type.setdefault(key, {
                "alert_type": key, "count": 0, "viewed": 0,
                "acknowledged": 0, "suspected_linkage": 0,
                "scores": [], "adjudicated": 0, "determinate": 0,
                "true_positive": 0, "false_positive": 0,
            })
            row["count"] += 1
            if doc.get("viewed_at"):
                row["viewed"] += 1
            if doc.get("acknowledged_at"):
                row["acknowledged"] += 1
            if doc.get("action_linkage") and isinstance(doc.get("action_linkage"), dict):
                row["suspected_linkage"] += 1
            if doc.get("heuristic_attention_score") is not None:
                try:
                    row["scores"].append(float(doc.get("heuristic_attention_score")))
                except Exception:
                    pass
            adj = doc.get("manual_adjudication") if isinstance(doc.get("manual_adjudication"), dict) else {}
            validity = adj.get("alert_validity")
            if validity in {"true_positive", "false_positive", "indeterminate"}:
                row["adjudicated"] += 1
                if validity == "true_positive":
                    row["true_positive"] += 1
                elif validity == "false_positive":
                    row["false_positive"] += 1
                if validity in {"true_positive", "false_positive"}:
                    row["determinate"] += 1

        top_types = []
        for row in by_type.values():
            scores = row.pop("scores", []) if isinstance(row.get("scores"), list) else []
            count = max(int(row.get("count") or 0), 1)
            adjudicated_n = int(row.get("adjudicated") or 0)
            determinate_n = int(row.get("determinate") or 0)
            tp = int(row.get("true_positive") or 0)
            fp = int(row.get("false_positive") or 0)
            fdp = round(fp / determinate_n, 3) if determinate_n > 0 else None
            ppv = round(tp / determinate_n, 3) if determinate_n > 0 else None
            ci = _wilson_ci(tp, determinate_n) if determinate_n > 0 else {"lower": None, "upper": None}
            top_types.append({
                **row,
                "view_rate": round(float(row.get("viewed") or 0) / count, 3),
                "ack_rate": round(float(row.get("acknowledged") or 0) / count, 3),
                "suspected_linkage_rate": round(float(row.get("suspected_linkage") or 0) / count, 3),
                "avg_heuristic_attention_score": round(sum(scores) / len(scores), 1) if scores else None,
                "formally_reviewed_count": adjudicated_n,
                "determinate_reviewed": determinate_n,
                "review_coverage": round(adjudicated_n / count, 3) if count > 0 else 0.0,
                "false_discovery_proportion": fdp,
                "fdp_denominator_note": f"FDP={fp}/{determinate_n}=FP/(TP+FP) — indeterminate excluded. Not FPR.",
                "true_fpr": None,
                "true_fpr_note": "FPR=FP/(FP+TN) cannot be computed without non-alert control samples",
                "reviewed_sample_ppv": ppv,
                "ppv_denominator_note": f"PPV={tp}/{determinate_n}=TP/(TP+FP) — indeterminate excluded",
                "ppv_ci_lower": ci.get("lower"),
                "ppv_ci_upper": ci.get("upper"),
                "insufficient_review_samples": determinate_n < 30,
            })
        top_types.sort(key=lambda item: (
            -(int(item.get("reviewed_count") or 0)),
            -(int(item.get("count") or 0)),
            item.get("alert_type") or "",
        ))

        # Time-bucket trend (unchanged structure, updated field names)
        bucket_mode = "hour" if window_hours <= 72 else "day"
        bucket_map: dict[str, dict[str, Any]] = {}
        bucket_step = timedelta(hours=1) if bucket_mode == "hour" else timedelta(days=1)
        bucket_cursor = (
            since.replace(minute=0, second=0, microsecond=0)
            if bucket_mode == "hour"
            else since.replace(hour=0, minute=0, second=0, microsecond=0)
        )
        end_bucket = (
            datetime.now().replace(minute=0, second=0, microsecond=0)
            if bucket_mode == "hour"
            else datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        )
        while bucket_cursor <= end_bucket:
            bucket_key = (
                bucket_cursor.strftime("%m-%d %H:00")
                if bucket_mode == "hour"
                else bucket_cursor.strftime("%m-%d")
            )
            bucket_map[bucket_key] = {
                "time": bucket_key, "created": 0, "viewed": 0,
                "acknowledged": 0, "suspected_linkage": 0,
            }
            bucket_cursor += bucket_step
        for doc in docs:
            created_at = doc.get("created_at") if isinstance(doc.get("created_at"), datetime) else None
            if not created_at:
                continue
            bucket_key = (
                created_at.strftime("%m-%d %H:00")
                if bucket_mode == "hour"
                else created_at.strftime("%m-%d")
            )
            row = bucket_map.setdefault(bucket_key, {
                "time": bucket_key, "created": 0, "viewed": 0,
                "acknowledged": 0, "suspected_linkage": 0,
            })
            row["created"] += 1
            if doc.get("viewed_at"):
                row["viewed"] += 1
            if doc.get("acknowledged_at"):
                row["acknowledged"] += 1
            if doc.get("action_linkage") and isinstance(doc.get("action_linkage"), dict):
                row["suspected_linkage"] += 1

        trend_series = [bucket_map[key] for key in sorted(bucket_map.keys())]
        conversion_series = []
        for item in trend_series:
            created_count = int(item.get("created") or 0)
            viewed_count = int(item.get("viewed") or 0)
            acked_count = int(item.get("acknowledged") or 0)
            linkage_count = int(item.get("suspected_linkage") or 0)
            conversion_series.append({
                "time": item.get("time"),
                "created": created_count,
                "viewed": viewed_count,
                "acknowledged": acked_count,
                "suspected_linkage": linkage_count,
                "created_to_view_rate": round(viewed_count / created_count, 3) if created_count else 0,
                "view_to_ack_rate": round(acked_count / viewed_count, 3) if viewed_count else 0,
                "ack_to_suspected_linkage_rate": round(linkage_count / acked_count, 3) if acked_count else 0,
            })

        return {
            "summary": {
                "window_hours": window_hours,
                "total_alerts": total,
                "viewed_alerts": len(viewed),
                "acknowledged_alerts": len(acked),
                "suspected_linkage_alerts": len(has_linkage),
                "adjudicated_alerts": len(adjudicated),
                "view_rate": round(len(viewed) / total, 3) if total else 0,
                "ack_rate": round(len(acked) / total, 3) if total else 0,
                "suspected_linkage_rate": round(len(has_linkage) / total, 3) if total else 0,
                "adjudication_rate": round(len(adjudicated) / total, 3) if total else 0,
                "median_view_minutes": round(statistics.median(view_minutes), 1) if view_minutes else None,
                "median_ack_minutes": round(statistics.median(ack_minutes), 1) if ack_minutes else None,
            },
            "trend": {"bucket": bucket_mode, "series": trend_series},
            "funnel_trend": {"bucket": bucket_mode, "series": conversion_series},
            "top_alert_types": top_types[:12],
            "terminology_note": (
                "suspected_linkage = system-detected keyword+time match (NOT confirmed action). "
                "adjudicated = human-reviewed alerts. "
                "FDP = FP / reviewed (not FPR; true FPR requires non-alert control samples). "
                "PPV = reviewed sample PPV only."
            ),
        }
