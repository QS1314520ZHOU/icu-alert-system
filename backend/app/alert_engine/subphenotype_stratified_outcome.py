from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger("icu-alert")

# ---------------------------------------------------------------------------
# Drug → treatment_class mapping (single source of truth, aligned with
# _actionability_signal_keywords in alert_actionability.py)
# ---------------------------------------------------------------------------
DRUG_TO_TREATMENT_CLASS: dict[str, str] = {
    # vasopressor
    "去甲肾上腺素": "vasopressor",
    "肾上腺素": "vasopressor",
    "血管加压素": "vasopressor",
    "多巴胺": "vasopressor",
    "去氧肾上腺素": "vasopressor",
    # fluid → other (no independent outcome signal)
    "乳酸林格": "other",
    "氯化钠": "other",
    "白蛋白": "other",
    # antimicrobial
    "美罗培南": "antimicrobial",
    "哌拉西林": "antimicrobial",
    "他唑巴坦": "antimicrobial",
    "头孢": "antimicrobial",
    "万古霉素": "antimicrobial",
    "替考拉宁": "antimicrobial",
    "亚胺培南": "antimicrobial",
    "抗生素": "antimicrobial",
    # steroid
    "甲泼尼龙": "steroid",
    "地塞米松": "steroid",
    "布地奈德": "steroid",
    # diuretic
    "呋塞米": "diuretic",
    # sedation
    "右美托咪定": "sedation",
    "丙泊酚": "sedation",
    "咪达唑仑": "sedation",
    "氟哌啶醇": "sedation",
    "奥氮平": "sedation",
    # hemostatic / other
    "氨甲环酸": "other",
    "纤维蛋白原": "other",
    "血浆": "other",
    "红细胞": "other",
    "血小板": "other",
    # respiratory (non-steroid, non-diuretic)
    "沙丁胺醇": "other",
    "异丙托溴铵": "other",
    # renal
    "碳酸氢钠": "other",
}

# Alert category/keyword → treatment_class (for real-time caution mounting)
_CATEGORY_TO_TREATMENT_CLASS: dict[str, str] = {
    "shock": "vasopressor",
    "hypotension": "vasopressor",
    "map": "vasopressor",
    "lactate": "vasopressor",
    "hemodynamic": "vasopressor",
    "低血压": "vasopressor",
    "休克": "vasopressor",
    "乳酸": "vasopressor",
    "灌注": "vasopressor",
    "sepsis": "antimicrobial",
    "sofa": "antimicrobial",
    "qsofa": "antimicrobial",
    "感染": "antimicrobial",
    "脓毒": "antimicrobial",
    "抗菌": "antimicrobial",
    "ards": "steroid",
    "resp": "steroid",
    "spo2": "steroid",
    "oxygen": "steroid",
    "vent": "steroid",
    "呼吸": "steroid",
    "氧合": "steroid",
    "肺": "steroid",
    "气道": "steroid",
    "aki": "diuretic",
    "renal": "diuretic",
    "cr": "diuretic",
    "尿量": "diuretic",
    "肾": "diuretic",
    "液体": "diuretic",
    "bleed": "other",
    "dic": "other",
    "plt": "other",
    "出血": "other",
    "凝血": "other",
    "delir": "sedation",
    "sedat": "sedation",
    "谵妄": "sedation",
    "镇静": "sedation",
    "躁动": "sedation",
}

TREATMENT_CLASSES = ["vasopressor", "fluid", "steroid", "antimicrobial", "sedation", "diuretic", "other"]

# Conservative reasoning template (no causal language)
_REASONING_TEMPLATE = (
    "该亚表型(n={n})接受该类处置后{window}内改善率为{rate}%，"
    "同期所有亚表型接受同类处置改善率为{cohort_rate}%，差距为{gap}个百分点。"
    "样本量有限且为观察性数据，存在适应症混杂(confounding by indication)、"
    "时序混杂及未测量混杂因素，不可作为因果推断或治疗指令。"
)

_LIMITATIONS = "观察性数据，存在适应症混杂(confounding by indication)，不可作为因果或治疗指令"

# Forbidden causal / directive phrases
_FORBIDDEN_PHRASES = ["应使用", "不应使用", "推荐改用", "导致", "改善了", "建议使用", "不建议", "必须"]


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def classify_order_drug(drug_name: str) -> str:
    """Map a single drug name to a treatment_class.

    Returns 'other' if no match found.
    """
    name = str(drug_name or "").strip()
    if not name:
        return "other"
    # Exact match first
    if name in DRUG_TO_TREATMENT_CLASS:
        return DRUG_TO_TREATMENT_CLASS[name]
    # Substring match (e.g. "头孢曲松" contains "头孢")
    for keyword, tclass in DRUG_TO_TREATMENT_CLASS.items():
        if keyword in name:
            return tclass
    return "other"


def classify_action_taken(orders: list[dict[str, Any]]) -> str:
    """Determine the dominant treatment_class from a list of orders.

    Uses the most frequent class; ties broken by order of TREATMENT_CLASSES.
    """
    if not orders:
        return "other"
    counts: dict[str, int] = {}
    for order in orders:
        drug = str(order.get("drug_name") or order.get("order_name") or "").strip()
        tclass = classify_order_drug(drug)
        counts[tclass] = counts.get(tclass, 0) + 1
    if not counts:
        return "other"
    # Return highest count; ties broken by TREATMENT_CLASSES order
    best_class = "other"
    best_count = 0
    for tclass in TREATMENT_CLASSES:
        c = counts.get(tclass, 0)
        if c > best_count:
            best_count = c
            best_class = tclass
    return best_class


def classify_alert_treatment(alert_doc: dict[str, Any]) -> str:
    """Infer treatment_class from alert metadata (category, parameter, name)."""
    text = " ".join(
        [
            str(alert_doc.get("rule_id") or ""),
            str(alert_doc.get("alert_type") or ""),
            str(alert_doc.get("category") or ""),
            str(alert_doc.get("parameter") or ""),
            str(alert_doc.get("name") or ""),
        ]
    ).lower()
    # Score each treatment_class by keyword hits
    scores: dict[str, int] = {}
    for keyword, tclass in _CATEGORY_TO_TREATMENT_CLASS.items():
        if keyword in text:
            scores[tclass] = scores.get(tclass, 0) + 1
    if not scores:
        return "other"
    return max(scores, key=lambda k: scores[k])


def _validate_reasoning(text: str) -> str:
    """Strip any causal/directive language from reasoning text."""
    clean = str(text or "")
    for phrase in _FORBIDDEN_PHRASES:
        clean = clean.replace(phrase, "...")
    return clean


# ---------------------------------------------------------------------------
# Mixin
# ---------------------------------------------------------------------------

class SubphenotypeStratifiedOutcomeMixin:
    """Statistical subphenotype × treatment_class × outcome stratified analysis.

    This mixin provides:
    1. Batch aggregation of historical alert outcomes by (subphenotype, treatment_class)
    2. Signal persistence to score collection (pending_review → approved/rejected)
    3. Real-time caution mounting on new alerts
    """

    # ---- config helpers ----

    def _stratified_cfg(self) -> dict[str, Any]:
        cfg = self._cfg("alert_engine", "subphenotype_stratified", default={}) or {}
        return cfg if isinstance(cfg, dict) else {}

    # ---- batch computation ----

    async def compute_stratified_signals(self, *, now: datetime | None = None) -> list[dict[str, Any]]:
        """Scan alert_records with action_taken + outcome_delta and compute
        per-(subphenotype, treatment_class, window) signals.

        Returns list of signal docs ready for persistence (or empty if disabled/no data).
        """
        cfg = self._stratified_cfg()
        if not cfg.get("enabled", True):
            return []

        now = now or datetime.now()
        min_sample = int(cfg.get("min_sample", 30) or 30)
        gap_low = float(cfg.get("gap_low", -0.2) or -0.2)
        gap_high = float(cfg.get("gap_high", 0.2) or 0.2)
        persist_neutral = bool(cfg.get("persist_neutral", False))
        outcome_window = str(cfg.get("outcome_window", "2h") or "2h")
        lookback_days = int(cfg.get("lookback_days", 90) or 90)

        since = now - timedelta(days=lookback_days)

        # Fetch alerts that have both action_taken and outcome_delta
        cursor = self.db.col("alert_records").find(
            {
                "created_at": {"$gte": since},
                "action_taken.matched": True,
                "action_taken.orders": {"$exists": True, "$ne": []},
                "outcome_delta": {"$exists": True},
            },
        )

        # Collect (patient_id → subphenotype, treatment_class, improved)
        raw_records: list[tuple[str, str, str, bool]] = []  # (patient_id, subphenotype, tclass, improved)
        async for alert_doc in cursor:
            patient_id = str(alert_doc.get("patient_id") or "")
            if not patient_id:
                continue
            orders = (alert_doc.get("action_taken") or {}).get("orders") or []
            tclass = classify_action_taken(orders)

            outcome_delta = alert_doc.get("outcome_delta") or {}
            windows = outcome_delta.get("windows") or {}
            window_data = windows.get(outcome_window) or {}
            # Use improved_any from the specific window if available, else top-level
            if window_data:
                improved = any(
                    (v or {}).get("improved")
                    for v in window_data.values()
                    if isinstance(v, dict)
                )
            else:
                improved = bool(outcome_delta.get("improved_any"))

            # Look up subphenotype from patient's current_profile at alert time
            # For batch analysis, use the latest known subphenotype
            subphenotype = await self._get_patient_subphenotype(patient_id)
            if not subphenotype:
                continue

            raw_records.append((patient_id, subphenotype, tclass, improved))

        if not raw_records:
            return []

        # Aggregate: (subphenotype, treatment_class) → {total, improved}
        buckets: dict[tuple[str, str], dict[str, int]] = {}
        cohort_buckets: dict[str, dict[str, int]] = {}  # treatment_class → {total, improved}

        for _pid, subphenotype, tclass, improved in raw_records:
            key = (subphenotype, tclass)
            if key not in buckets:
                buckets[key] = {"total": 0, "improved": 0}
            buckets[key]["total"] += 1
            if improved:
                buckets[key]["improved"] += 1

            if tclass not in cohort_buckets:
                cohort_buckets[tclass] = {"total": 0, "improved": 0}
            cohort_buckets[tclass]["total"] += 1
            if improved:
                cohort_buckets[tclass]["improved"] += 1

        # Build signals
        signals: list[dict[str, Any]] = []
        for (subphenotype, tclass), counts in buckets.items():
            n = counts["total"]
            if n < min_sample:
                continue

            improved_rate = round(counts["improved"] / n, 4) if n else 0.0
            cohort = cohort_buckets.get(tclass, {"total": 0, "improved": 0})
            cohort_n = cohort["total"]
            cohort_rate = round(cohort["improved"] / cohort_n, 4) if cohort_n else 0.0
            rate_gap = round(improved_rate - cohort_rate, 4)

            if rate_gap <= gap_low:
                signal = "underperforming"
            elif rate_gap >= gap_high:
                signal = "overperforming"
            else:
                signal = "neutral"

            if signal == "neutral" and not persist_neutral:
                continue

            reasoning = _REASONING_TEMPLATE.format(
                n=n,
                window="30分钟" if outcome_window == "30m" else "2小时",
                rate=round(improved_rate * 100, 1),
                cohort_rate=round(cohort_rate * 100, 1),
                gap=round(rate_gap * 100, 1),
            )
            reasoning = _validate_reasoning(reasoning)

            signals.append({
                "score_type": "subphenotype_treatment_signal",
                "status": "pending_review",
                "subphenotype": subphenotype,
                "treatment_class": tclass,
                "outcome_window": outcome_window,
                "sample_size": n,
                "improved_rate": improved_rate,
                "cohort_improved_rate": cohort_rate,
                "rate_gap": rate_gap,
                "signal": signal,
                "reasoning": reasoning,
                "limitations": _LIMITATIONS,
                "calc_time": now,
                "created_at": now,
                "month": now.strftime("%Y-%m"),
                "day": now.strftime("%Y-%m-%d"),
            })

        return signals

    async def _get_patient_subphenotype(self, patient_id: str) -> str | None:
        """Read the patient's current subphenotype label."""
        try:
            from bson import ObjectId
            pid = ObjectId(patient_id)
        except Exception:
            return None
        patient = await self.db.col("patient").find_one(
            {"_id": pid},
            projection={"current_profile.sepsis_subphenotype.phenotype": 1},
        )
        if not patient:
            return None
        profile = (patient.get("current_profile") or {}).get("sepsis_subphenotype") or {}
        return str(profile.get("phenotype") or "").strip() or None

    async def _persist_signals(self, signals: list[dict[str, Any]]) -> int:
        """Persist computed signals to the score collection. Returns count inserted."""
        if not signals:
            return 0
        # Remove any existing pending_review signals for the same (subphenotype, treatment_class, window)
        for sig in signals:
            await self.db.col("score").delete_many({
                "score_type": "subphenotype_treatment_signal",
                "status": "pending_review",
                "subphenotype": sig["subphenotype"],
                "treatment_class": sig["treatment_class"],
                "outcome_window": sig["outcome_window"],
            })
        result = await self.db.col("score").insert_many(signals)
        return len(result.inserted_ids)

    # ---- real-time caution mounting ----

    async def get_approved_stratified_signals(self, subphenotype: str) -> list[dict[str, Any]]:
        """Retrieve approved underperforming signals for a given subphenotype."""
        if not subphenotype:
            return []
        cursor = self.db.col("score").find({
            "score_type": "subphenotype_treatment_signal",
            "status": "approved",
            "subphenotype": subphenotype,
            "signal": "underperforming",
        })
        return [doc async for doc in cursor]

    async def mount_stratified_caution(self, alert_doc: dict[str, Any], patient_doc: dict[str, Any]) -> None:
        """Mount stratified_caution into alert_doc['extra'] if conditions are met.

        Called from _create_alert flow (via mixin on AlertEngine).
        Mutates alert_doc in place. Never changes severity. Never blocks alert.
        """
        cfg = self._stratified_cfg()
        if not cfg.get("enabled", True):
            return

        # Get patient's current subphenotype
        subphenotype_raw = (patient_doc or {}).get("current_profile", {})
        if isinstance(subphenotype_raw, dict):
            subphenotype = str((subphenotype_raw.get("sepsis_subphenotype") or {}).get("phenotype") or "").strip()
        else:
            subphenotype = ""
        if not subphenotype:
            return

        # Determine treatment_class from alert metadata
        alert_tclass = classify_alert_treatment(alert_doc)

        # Check for approved underperforming signals
        signals = await self.get_approved_stratified_signals(subphenotype)
        for sig in signals:
            if sig.get("treatment_class") == alert_tclass:
                caution = {
                    "subphenotype": subphenotype,
                    "treatment_class": alert_tclass,
                    "note": "该亚表型对此类处置历史改善率偏低，请结合床旁判断",
                    "signal_id": str(sig.get("_id") or ""),
                }
                extra = alert_doc.get("extra")
                if not isinstance(extra, dict):
                    extra = {}
                    alert_doc["extra"] = extra
                extra["stratified_caution"] = caution
                return  # Only mount the first matching signal
