from __future__ import annotations

from datetime import datetime
from typing import Any

MDRO_FEATURE_SCHEMA_VERSION = "mdro_screening_features.v1"


def _completeness(required: list[str], present: list[str]) -> dict[str, Any]:
    present_unique = list(dict.fromkeys(present))
    missing = [item for item in required if item not in present_unique]
    return {
        "required": required,
        "present": present_unique,
        "missing": missing,
        "completeness_ratio": round(len(present_unique) / len(required), 4) if required else 1.0,
    }


def build_mdro_screening_features(
    *,
    patient: dict[str, Any],
    susceptibility_reports: list[dict[str, Any]],
    current_drugs: list[dict[str, Any]],
    prior_mdro_alert: dict[str, Any] | None = None,
    now: datetime | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del now
    cfg = cfg or {}
    broad_keywords = [str(x).lower() for x in (cfg.get("broad_antibiotic_keywords") or ["meropenem", "imipenem", "vancomycin", "linezolid", "tigecycline"])]
    diagnosis_blob = " ".join(str(patient.get(k) or "") for k in ("clinicalDiagnosis", "admissionDiagnosis", "diagnosis")).lower()
    drug_names = [str(item.get("name") or "").lower() for item in current_drugs]
    recent_resistant = [
        row for row in susceptibility_reports
        if str(row.get("result") or "").upper() in {"R", "I"}
    ]
    broad_abx = [name for name in drug_names if any(keyword and keyword in name for keyword in broad_keywords)]
    factors: list[dict[str, Any]] = []
    if prior_mdro_alert:
        factors.append({"key": "prior_mdro", "label": "prior MDRO alert", "weight": 2, "evidence": str(prior_mdro_alert.get("alert_type") or "mdro")})
    if recent_resistant:
        factors.append({"key": "recent_resistance", "label": "recent resistant susceptibility result", "weight": 2, "evidence": f"{len(recent_resistant)} resistant/intermediate result(s)"})
    if broad_abx:
        factors.append({"key": "broad_antibiotics", "label": "broad antibiotic exposure", "weight": 1, "evidence": ", ".join(broad_abx[:3])})
    if any(token in diagnosis_blob for token in ["sepsis", "脓毒", "感染", "shock"]):
        factors.append({"key": "infection_context", "label": "infection context", "weight": 1, "evidence": "infection/sepsis diagnosis text"})
    score = sum(int(item.get("weight") or 0) for item in factors)
    threshold = int(cfg.get("trigger_score_threshold", 3) or 3)
    required = ["patient_context", "microbiology_or_prior_mdro", "drug_exposure"]
    present = ["patient_context"]
    if susceptibility_reports or prior_mdro_alert:
        present.append("microbiology_or_prior_mdro")
    if current_drugs:
        present.append("drug_exposure")
    return {
        "feature_schema_version": MDRO_FEATURE_SCHEMA_VERSION,
        "data_source": "mongo",
        "validation_status": "internal_only",
        "score": score,
        "threshold": threshold,
        "trigger": score >= threshold,
        "factors": factors,
        "feature_vector": {
            "prior_mdro": bool(prior_mdro_alert),
            "recent_resistant_results": len(recent_resistant),
            "current_antibiotics": len(current_drugs),
            "broad_antibiotics": len(broad_abx),
        },
        "data_completeness": _completeness(required, present),
    }
