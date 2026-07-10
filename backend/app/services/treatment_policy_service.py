"""Offline CQL sepsis treatment policy runtime."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
from bson import ObjectId

from app.services.local_model_paths import local_model_dir


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except Exception:
        return None


class TreatmentPolicyService:
    def __init__(self, *, db, config, alert_engine=None) -> None:
        self.db = db
        self.config = config
        self.alert_engine = alert_engine
        self._loaded = False
        self._torch: Any = None
        self._model: Any = None
        self._model_path: Path | None = None
        self._unavailable_reason = ""
        self._device = "cpu"

    def _model_dir(self) -> Path:
        return local_model_dir(self.config, "cql_sepsis_dir", "cql-sepsis")

    def _candidate_paths(self) -> list[Path]:
        root = self._model_dir()
        return [root / name for name in ("q_network.pt", "model.pt", "policy.pt", "model.pth")]

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        try:
            import torch  # type: ignore
        except Exception as exc:
            self._unavailable_reason = f"torch unavailable: {exc.__class__.__name__}: {str(exc)[:160]}"
            return
        self._torch = torch
        for path in self._candidate_paths():
            if not path.exists():
                continue
            try:
                self._model_path = path
                try:
                    self._model = torch.jit.load(str(path), map_location=self._device)
                except Exception:
                    self._model = torch.load(str(path), map_location=self._device)
                if hasattr(self._model, "eval"):
                    self._model.eval()
                self._unavailable_reason = ""
                return
            except Exception as exc:
                self._model = None
                self._unavailable_reason = f"load failed: {exc.__class__.__name__}: {str(exc)[:120]}"
                return
        self._unavailable_reason = f"no torch weight found under {self._model_dir()}"

    def status(self) -> dict[str, Any]:
        if not self._loaded:
            self._ensure_loaded()
        return {
            "available": bool(self._model is not None),
            "reason": self._unavailable_reason,
            "backend": "torch",
            "model_path": str(self._model_path or ""),
        }

    async def _patient_doc(self, patient_id: str) -> dict[str, Any] | None:
        try:
            return await self.db.col("patient").find_one({"_id": ObjectId(patient_id)})
        except Exception:
            return await self.db.col("patient").find_one({"_id": patient_id})

    async def _state(self, patient_id: str) -> dict[str, Any]:
        patient = await self._patient_doc(patient_id) or {}
        facts: dict[str, Any] = {}
        if self.alert_engine is not None and patient and hasattr(self.alert_engine, "_collect_patient_facts"):
            try:
                facts = await self.alert_engine._collect_patient_facts(patient, patient.get("_id"))
            except Exception:
                facts = {}
        vitals = facts.get("vitals") if isinstance(facts.get("vitals"), dict) else {}
        labs = facts.get("labs") if isinstance(facts.get("labs"), dict) else {}
        drug_docs = []
        if self.alert_engine is not None and hasattr(self.alert_engine, "_get_recent_drug_docs_window"):
            try:
                drug_docs = await self.alert_engine._get_recent_drug_docs_window(patient_id, hours=24, limit=500)
            except Exception:
                drug_docs = []
        norepi = await self._latest_norepi(patient_id, patient)
        fluid_24h = await self._fluid_24h(patient_id)
        return {"patient": patient, "vitals": vitals, "labs": labs, "drug_docs": drug_docs, "norepi": norepi, "fluid_24h_ml": fluid_24h}

    async def _latest_norepi(self, patient_id: str, patient: dict[str, Any]) -> float | None:
        if self.alert_engine is None or not hasattr(self.alert_engine, "_get_norepi_dose_series"):
            return None
        try:
            weight = self.alert_engine._get_patient_weight(patient)
            series = await self.alert_engine._get_norepi_dose_series(
                patient_id,
                datetime.now(),
                12,
                ["去甲肾上腺素", "norepinephrine", "noradrenaline", "去甲"],
                weight,
            )
            return series[-1].get("dose_ug_kg_min") if series else None
        except Exception:
            return None

    async def _fluid_24h(self, patient_id: str) -> float:
        if self.alert_engine is None:
            return 0.0
        try:
            since = datetime.now() - timedelta(hours=24)
            intake = await self.alert_engine._collect_intake_events(patient_id, since)
            return float(self.alert_engine._sum_window(intake, 24, datetime.now()))
        except Exception:
            return 0.0

    def _feature_vector(self, state: dict[str, Any]) -> np.ndarray:
        labs = state.get("labs") if isinstance(state.get("labs"), dict) else {}
        vitals = state.get("vitals") if isinstance(state.get("vitals"), dict) else {}

        def lab(name: str) -> float:
            item = labs.get(name)
            if isinstance(item, dict):
                return _safe_float(item.get("value")) or 0.0
            return _safe_float(item) or 0.0

        values = [
            _safe_float(vitals.get("map")) or 0.0,
            _safe_float(vitals.get("hr")) or 0.0,
            _safe_float(vitals.get("spo2")) or 0.0,
            lab("lac") or lab("lactate"),
            lab("cr"),
            _safe_float(state.get("norepi")) or 0.0,
            _safe_float(state.get("fluid_24h_ml")) or 0.0,
        ]
        arr = np.zeros(32, dtype=np.float32)
        arr[: len(values)] = np.asarray(values, dtype=np.float32)
        return arr

    def _fallback_q_values(self, state: dict[str, Any]) -> np.ndarray:
        vitals = state.get("vitals") if isinstance(state.get("vitals"), dict) else {}
        labs = state.get("labs") if isinstance(state.get("labs"), dict) else {}
        map_value = _safe_float(vitals.get("map")) or 70.0
        lac_row = labs.get("lac") or labs.get("lactate")
        lactate = _safe_float(lac_row.get("value") if isinstance(lac_row, dict) else lac_row) or 1.2
        shock = max(0.0, (65.0 - map_value) / 20.0) + max(0.0, (lactate - 2.0) / 4.0)
        return np.asarray([0.2, 0.35 + shock * 0.15, 0.3 + shock * 0.12, 0.25 + shock * 0.08], dtype=np.float32)

    def _q_values(self, features: np.ndarray, state: dict[str, Any]) -> np.ndarray:
        if self._model is None or self._torch is None:
            return self._fallback_q_values(state)
        try:
            with self._torch.no_grad():
                tensor = self._torch.tensor(features, dtype=self._torch.float32).unsqueeze(0)
                out = self._model(tensor)
                return out.detach().cpu().numpy().reshape(-1).astype(np.float32)
        except Exception:
            return self._fallback_q_values(state)

    def _action_from_q(self, q_values: np.ndarray, state: dict[str, Any]) -> dict[str, Any]:
        actions = [
            {"label": "维持当前治疗", "fluid_bolus_ml": 0, "norepinephrine_ug_kg_min": _safe_float(state.get("norepi")) or 0.0},
            {"label": "小剂量补液评估", "fluid_bolus_ml": 250, "norepinephrine_ug_kg_min": _safe_float(state.get("norepi")) or 0.0},
            {"label": "补液并严密复评", "fluid_bolus_ml": 500, "norepinephrine_ug_kg_min": _safe_float(state.get("norepi")) or 0.0},
            {"label": "升压药小幅上调", "fluid_bolus_ml": 0, "norepinephrine_ug_kg_min": min((_safe_float(state.get("norepi")) or 0.02) + 0.02, 1.0)},
        ]
        idx = int(np.argmax(q_values)) if q_values.size else 0
        chosen = actions[max(0, min(idx, len(actions) - 1))]
        ordered = sorted([float(v) for v in q_values.tolist()], reverse=True)
        delta = ordered[0] - (ordered[1] if len(ordered) > 1 else 0.0)
        return {**chosen, "action_index": idx, "q_values": [round(float(v), 4) for v in q_values.tolist()], "q_value_delta": round(float(delta), 4)}

    def _safety_validation(self, action: dict[str, Any], state: dict[str, Any], q_delta: float) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        norepi = _safe_float(action.get("norepinephrine_ug_kg_min")) or 0.0
        bolus = _safe_float(action.get("fluid_bolus_ml")) or 0.0
        fluid_24h = _safe_float(state.get("fluid_24h_ml")) or 0.0
        allergy_text = " ".join(str(state.get("patient", {}).get(k) or "") for k in ("allergies", "allergyHistory", "drugAllergy"))

        def add(name: str, passed: bool, detail: str) -> None:
            checks.append({"name": name, "passed": bool(passed), "detail": detail})

        add("去甲肾上腺素≤1.0 μg/kg/min", norepi <= 1.0, f"建议 {norepi:.3f}")
        add("单次补液≤2000mL", bolus <= 2000, f"建议 {int(bolus)}mL")
        add("24h累计补液≤5000mL", fluid_24h + bolus <= 5000, f"当前+建议 {int(fluid_24h + bolus)}mL")
        add("避开过敏药物", not any(token in allergy_text for token in ("去甲肾上腺素", "晶体液", "乳酸林格", "氯化钠")), allergy_text[:80] or "未记录相关过敏")
        add("Q置信度≥0.3", q_delta >= 0.3, f"delta {q_delta:.3f}")
        passed = all(item["passed"] for item in checks)
        return {"passed": passed, "checks": checks, "message": "通过安全红线，仅供临床复核" if passed else "未通过安全红线，不提供剂量建议"}

    async def recommend_action(self, patient_state: str | dict[str, Any]) -> dict[str, Any]:
        patient_id = str(patient_state.get("patient_id") if isinstance(patient_state, dict) else patient_state)
        self._ensure_loaded()
        state = await self._state(patient_id)
        features = self._feature_vector(state)
        q_values = self._q_values(features, state)
        action = self._action_from_q(q_values, state)
        validation = self._safety_validation(action, state, float(action["q_value_delta"]))
        status = self.status()
        available = bool(status["available"] and validation["passed"])
        recommendation = None
        if available:
            recommendation = {
                "recommendation_id": f"cql-{uuid4().hex[:12]}",
                "action": action["label"],
                "fluid_bolus_ml": action["fluid_bolus_ml"],
                "norepinephrine_ug_kg_min": round(float(action["norepinephrine_ug_kg_min"]), 3),
                "note": "AI剂量建议仅用于对比和复核，不自动生成医嘱。",
            }
        return {
            "available": available,
            "reason": "" if available else (status["reason"] or validation["message"]),
            "recommendation": recommendation,
            "current_orders": {
                "norepinephrine_ug_kg_min": _safe_float(state.get("norepi")),
                "fluid_24h_ml": round(float(state.get("fluid_24h_ml") or 0.0), 1),
            },
            "q_value_delta": action["q_value_delta"],
            "safety_validation": validation,
            "model_meta": status,
        }


_TREATMENT_POLICY_SINGLETON: TreatmentPolicyService | None = None


def get_treatment_policy_service(*, db, config, alert_engine=None) -> TreatmentPolicyService:
    global _TREATMENT_POLICY_SINGLETON
    if (
        _TREATMENT_POLICY_SINGLETON is None
        or _TREATMENT_POLICY_SINGLETON.db is not db
        or _TREATMENT_POLICY_SINGLETON.config is not config
        or _TREATMENT_POLICY_SINGLETON.alert_engine is not alert_engine
    ):
        _TREATMENT_POLICY_SINGLETON = TreatmentPolicyService(db=db, config=config, alert_engine=alert_engine)
    return _TREATMENT_POLICY_SINGLETON
