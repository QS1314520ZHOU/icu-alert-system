from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.alert_engine.scanner_beta_blocker_advisor import BetaBlockerAdvisorScanner
from app.alert_engine.scanner_integrated_risk_reasoning import IntegratedRiskReasoningScanner
from app.alert_engine.scanner_metabolic_phase_detector import MetabolicPhaseDetectorScanner
from app.alert_engine.scanner_noninvasive_respiratory_support import NoninvasiveRespiratorySupportScanner
from app.alert_engine.scanner_nutrition_monitor import NutritionMonitorScanner
from app.alert_engine.nutrition_monitor import NutritionMonitorMixin
from app.alert_engine.scanner_ventilator_weaning import VentilatorWeaningScanner
from app.services.respiratory_service import _infer_airway_risk, _laryngeal_edema_risk


class _InsertResult:
    def __init__(self, inserted_id: int) -> None:
        self.inserted_id = inserted_id


class _Cursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = list(docs)
        self._idx = 0

    def sort(self, key: str, direction: int) -> "_Cursor":
        self._docs.sort(key=lambda row: row.get(key), reverse=direction == -1)
        return self

    def limit(self, count: int) -> "_Cursor":
        self._docs = self._docs[:count]
        return self

    def __aiter__(self) -> "_Cursor":
        self._idx = 0
        return self

    async def __anext__(self) -> dict[str, Any]:
        if self._idx >= len(self._docs):
            raise StopAsyncIteration
        item = self._docs[self._idx]
        self._idx += 1
        return dict(item)


class _Collection:
    def __init__(self, docs: list[dict[str, Any]] | None = None) -> None:
        self.docs = [dict(doc) for doc in (docs or [])]

    def find(self, query: dict[str, Any] | None = None, projection: dict[str, int] | None = None) -> _Cursor:
        query = query or {}
        rows = [doc for doc in self.docs if self._match(doc, query)]
        if projection:
            projected = []
            for doc in rows:
                row = {}
                for key, enabled in projection.items():
                    if enabled and key in doc:
                        row[key] = doc[key]
                if "_id" in doc:
                    row["_id"] = doc["_id"]
                projected.append(row)
            rows = projected
        return _Cursor(rows)

    async def find_one(self, query: dict[str, Any], sort: list[tuple[str, int]] | None = None) -> dict[str, Any] | None:
        rows = [doc for doc in self.docs if self._match(doc, query)]
        if sort:
            key, direction = sort[0]
            rows.sort(key=lambda row: row.get(key), reverse=direction == -1)
        return dict(rows[0]) if rows else None

    async def insert_one(self, doc: dict[str, Any]) -> _InsertResult:
        row = dict(doc)
        row.setdefault("_id", len(self.docs) + 1)
        self.docs.append(row)
        return _InsertResult(row["_id"])

    async def update_one(self, selector: dict[str, Any], update: dict[str, Any]) -> None:
        for doc in self.docs:
            if self._match(doc, selector):
                for key, value in update.get("$set", {}).items():
                    self._assign(doc, key, value)
                return
        if "$set" in update:
            row = dict(selector)
            for key, value in update["$set"].items():
                self._assign(row, key, value)
            self.docs.append(row)

    @classmethod
    def _assign(cls, doc: dict[str, Any], dotted_key: str, value: Any) -> None:
        parts = dotted_key.split(".")
        target = doc
        for part in parts[:-1]:
            if not isinstance(target.get(part), dict):
                target[part] = {}
            target = target[part]
        target[parts[-1]] = value

    @classmethod
    def _match(cls, doc: dict[str, Any], query: dict[str, Any]) -> bool:
        for key, value in query.items():
            if key == "$or":
                if not any(cls._match(doc, item) for item in value):
                    return False
                continue
            current = cls._get(doc, key)
            if isinstance(value, dict):
                if "$gte" in value and not (current >= value["$gte"]):
                    return False
                if "$in" in value and current not in value["$in"]:
                    return False
            elif current != value:
                return False
        return True

    @staticmethod
    def _get(doc: dict[str, Any], dotted_key: str) -> Any:
        target: Any = doc
        for part in dotted_key.split("."):
            if not isinstance(target, dict):
                return None
            target = target.get(part)
        return target


class _FakeDb:
    def __init__(self, collections: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self._collections = {name: _Collection(docs) for name, docs in (collections or {}).items()}

    def col(self, name: str) -> _Collection:
        return self._collections.setdefault(name, _Collection())

    def dc_col(self, name: str) -> _Collection:
        return self._collections.setdefault(name, _Collection())


class _FakeWs:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def broadcast(self, message: dict[str, Any], roles: Any = None) -> None:
        del roles
        self.messages.append(message)


class _IntegratedEngine:
    def __init__(self) -> None:
        self.config = SimpleNamespace(
            yaml_cfg={
                "alert_engine": {
                    "integrated_risk_reasoning": {
                        "enabled": True,
                        "scan_interval": 3600,
                        "force_trigger_on_new_critical": True,
                        "lookback_window": 7200,
                        "cooldown": 7200,
                        "rag_top_k": 3,
                        "max_tokens": 1000,
                    }
                },
                "ai_service": {"llm": {"timeout": 10}},
            },
            llm_fast_model="test-model",
            settings=SimpleNamespace(LLM_MODEL="test-model"),
        )
        self.db = _FakeDb(
            {
                "alert_records": [
                    {"_id": "a1", "patient_id": "p1", "is_active": True, "name": "脓毒性休克", "category": "syndrome", "alert_type": "septic_shock", "severity": "critical", "created_at": datetime.now() - timedelta(minutes=20), "extra": {}},
                    {"_id": "a2", "patient_id": "p1", "is_active": True, "name": "AKI 2期", "category": "syndrome", "alert_type": "aki", "severity": "high", "created_at": datetime.now() - timedelta(minutes=10), "extra": {}},
                ],
                "integrated_risk_reports": [],
                "patient": [{"_id": "p1", "name": "张三"}],
            }
        )
        self.ws = _FakeWs()
        self.created_alerts: list[dict[str, Any]] = []

    def _cfg(self, *path: str, default: Any = None) -> Any:
        cursor: Any = self.config.yaml_cfg
        for key in path:
            if not isinstance(cursor, dict) or key not in cursor:
                return default
            cursor = cursor[key]
        return cursor

    async def _collect_patient_facts(self, patient_doc: dict[str, Any], patient_id: Any) -> dict[str, Any]:
        del patient_doc, patient_id
        return {"labs": {"lac": {"value": 4.2}, "cr": {"value": 180}}, "vitals": {"hr": 118}}

    async def _get_param_series_by_pid(self, patient_id: Any, code: str, since: datetime, prefer_device_types: list[str] | None = None, limit: int = 240) -> list[dict[str, Any]]:
        del patient_id, since, prefer_device_types, limit
        mapping = {
            "param_HR": [110, 118],
            "param_ibp_m": [68, 62],
            "param_spo2": [95, 93],
            "param_resp": [24, 28],
            "param_T": [37.8, 38.3],
        }
        values = mapping.get(code, [])
        now = datetime.now()
        return [{"time": now - timedelta(hours=1), "value": values[0]}, {"time": now, "value": values[-1]}] if values else []

    async def _get_active_vent_bind(self, patient_id: str) -> dict[str, Any] | None:
        del patient_id
        return None

    async def _get_device_id_for_patient(self, patient_doc: dict[str, Any], device_types: list[str] | None = None) -> str | None:
        del patient_doc, device_types
        return None

    async def _get_current_vasopressor_snapshot(self, patient_id: Any, patient_doc: dict[str, Any], hours: int = 8, max_items: int = 4) -> list[dict[str, Any]]:
        del patient_id, patient_doc, hours, max_items
        return [{"drug": "去甲肾上腺素", "dose_ug_kg_min": 0.12}]

    async def _create_alert(self, **kwargs: Any) -> dict[str, Any]:
        self.created_alerts.append(kwargs)
        return kwargs

    def _log_info(self, name: str, count: int) -> None:
        del name, count


class _MetabolicEngine:
    def __init__(self, *, score_docs: list[dict[str, Any]] | None = None, nutrition_events: list[dict[str, Any]] | None = None) -> None:
        self.config = SimpleNamespace(
            yaml_cfg={
                "alert_engine": {
                    "metabolic_phase_detector": {
                        "enabled": True,
                        "scan_interval": 3600,
                        "thresholds": {
                            "lactate_elevated": 2.0,
                            "glucose_cv_high": 36,
                            "glucose_stabilizing_cv": 30,
                            "crp_rising_delta": 5,
                            "crp_falling_delta": 5,
                            "crp_normal_threshold": 10,
                            "bun_high_threshold": 12,
                            "bun_daily_rise_threshold": 2,
                            "sofa_unstable_delta": 1,
                            "sofa_low": 3,
                            "prealbumin_rise_delta": 2,
                            "vasopressor_taper_ratio": 0.1,
                            "positive_nitrogen_protein_floor": 1.2,
                        },
                        "phase_weights": {
                            "ebb": {"lactate_elevated": 0.2, "glucose_cv_high": 0.15, "crp_rising": 0.15, "sofa_unstable": 0.2, "bun_generation_high": 0.15, "vasopressor_use": 0.15},
                            "transition": {"lactate_normalizing": 0.2, "glucose_stabilizing": 0.2, "crp_falling": 0.2, "sofa_stable_or_falling": 0.2, "vasopressor_weaning": 0.2},
                            "anabolic": {"crp_normal": 0.15, "prealbumin_rising": 0.2, "sofa_low": 0.2, "no_vasopressor": 0.15, "spontaneous_activity": 0.15, "positive_nitrogen": 0.15},
                        },
                        "calorie_targets": {"ebb": [10, 15], "transition": [20, 25], "anabolic": [25, 30]},
                        "protein_targets": {"ebb": [0.5, 0.8], "transition": [1.0, 1.3], "anabolic": [1.3, 1.5]},
                    },
                    "suppression": {"same_rule_same_patient_seconds": 1800, "max_alerts_per_patient_per_hour": 10},
                }
            }
        )
        self.db = _FakeDb({"score": score_docs or [], "patient": [{"_id": "p1", "name": "张三"}]})
        self.created_alerts: list[dict[str, Any]] = []
        self._nutrition_events = nutrition_events or []

    def _cfg(self, *path: str, default: Any = None) -> Any:
        cursor: Any = self.config.yaml_cfg
        for key in path:
            if not isinstance(cursor, dict) or key not in cursor:
                return default
            cursor = cursor[key]
        return cursor

    def _get_cfg_list(self, path: tuple[str, ...], default: list[str]) -> list[str]:
        value = self._cfg(*path, default=None)
        if isinstance(value, list):
            return value
        return default

    def _get_patient_weight(self, patient_doc: dict[str, Any]) -> float:
        del patient_doc
        return 70.0

    def _admission_time(self, patient_doc: dict[str, Any]) -> datetime:
        return patient_doc.get("icuAdmissionTime") or datetime.now() - timedelta(days=2)

    async def _get_latest_labs_map(self, his_pid: str, lookback_hours: int = 96) -> dict[str, Any]:
        del his_pid, lookback_hours
        return {"lac": {"value": 1.5}}

    async def _get_bedside_glucose_points(self, pid_str: str, since: datetime, codes: list[str]) -> list[dict[str, Any]]:
        del pid_str, since, codes
        now = datetime.now()
        return [{"time": now - timedelta(hours=3), "value": 7.0}, {"time": now, "value": 8.0}]

    async def _get_lab_glucose_points(self, his_pid: str, since: datetime) -> list[dict[str, Any]]:
        del his_pid, since
        return []

    def _calc_cv_percent(self, values: list[float]) -> float:
        del values
        return 18.0

    async def _get_drug_records(self, pid_str: str, since: datetime) -> list[dict[str, Any]]:
        del pid_str, since
        return []

    def _is_insulin_doc(self, doc: dict[str, Any], insulin_keywords: list[str]) -> bool:
        del doc, insulin_keywords
        return False

    async def _get_nutrition_drug_events(self, pid_str: str, since: datetime, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        del pid_str, since, cfg
        return list(self._nutrition_events)

    async def _calc_sofa(self, patient_doc: dict[str, Any], pid: Any, device_id: Any, his_pid: str) -> dict[str, Any]:
        del patient_doc, pid, device_id, his_pid
        return {"score": 4}

    async def _get_device_id_for_patient(self, patient_doc: dict[str, Any], device_types: list[str] | None = None) -> str | None:
        del patient_doc, device_types
        return None

    async def _get_current_vasopressor_snapshot(self, patient_id: Any, patient_doc: dict[str, Any], hours: int = 12, max_items: int = 4) -> list[dict[str, Any]]:
        del patient_id, patient_doc, hours, max_items
        return []

    async def _get_norepi_dose_series(self, pid_str: str, now: datetime, lookback_hours: float, keywords: list[str], weight_kg: float | None) -> list[dict[str, Any]]:
        del pid_str, now, lookback_hours, keywords, weight_kg
        return []

    def _is_series_tapering(self, points: list[dict[str, Any]], min_drop_ratio: float = 0.1) -> bool:
        del points, min_drop_ratio
        return False

    async def _get_last_activity_time(self, pid_str: str, now: datetime, lookback_hours: float, keywords: list[str]) -> datetime | None:
        del pid_str, now, lookback_hours, keywords
        return None

    async def _is_suppressed(self, patient_id: str, rule_id: str | None, same_rule_seconds: int, max_per_hour: int) -> bool:
        del patient_id, rule_id, same_rule_seconds, max_per_hour
        return False

    async def _create_alert(self, **kwargs: Any) -> dict[str, Any]:
        self.created_alerts.append(kwargs)
        return kwargs

    def _log_info(self, name: str, count: int) -> None:
        del name, count


class _NutritionEngine(NutritionMonitorMixin):
    def __init__(
        self,
        *,
        patient: dict[str, Any] | None = None,
        nutrition_events: list[dict[str, Any]] | None = None,
        lab_docs: list[dict[str, Any]] | None = None,
        drug_docs: list[dict[str, Any]] | None = None,
        score_docs: list[dict[str, Any]] | None = None,
    ) -> None:
        self.config = SimpleNamespace(
            yaml_cfg={
                "alert_engine": {
                    "nutrition_monitor": {
                        "start_delay_hours": 48,
                        "calorie_coverage_threshold": 0.6,
                        "calorie_under_target_persist_hours": 24,
                        "protein_coverage_threshold": 0.6,
                        "protein_under_target_persist_hours": 24,
                        "refeeding_monitor_hours": 72,
                        "feeding_intolerance_lookback_hours": 72,
                    },
                    "suppression": {"same_rule_same_patient_seconds": 0, "max_alerts_per_patient_per_hour": 20},
                }
            }
        )
        now = datetime.now()
        default_patient = {
            "_id": "p1",
            "name": "张三",
            "hisPid": "H1",
            "weight": 70,
            "height": 170,
            "icuAdmissionTime": now - timedelta(days=5),
        }
        self.db = _FakeDb(
            {
                "patient": [patient or default_patient],
                "drugExe": drug_docs or [],
                "bedside": [],
                "VI_ICU_EXAM_ITEM": lab_docs or [],
                "score": score_docs or [],
            }
        )
        self.created_alerts: list[dict[str, Any]] = []
        self._nutrition_events = nutrition_events or []

    def _cfg(self, *path: str, default: Any = None) -> Any:
        cursor: Any = self.config.yaml_cfg
        for key in path:
            if not isinstance(cursor, dict) or key not in cursor:
                return default
            cursor = cursor[key]
        return cursor

    def _get_cfg_list(self, path: tuple[str, ...], default: list[str]) -> list[str]:
        value = self._cfg(*path, default=None)
        return value if isinstance(value, list) else default

    def _active_patient_query(self) -> dict[str, Any]:
        return {}

    def _get_patient_weight(self, patient_doc: dict[str, Any]) -> float | None:
        for key in ("weight", "bodyWeight", "weight_kg"):
            if patient_doc.get(key) is not None:
                return float(patient_doc[key])
        return None

    async def _get_nutrition_drug_events(self, pid_str: str, since: datetime, cfg: dict[str, Any]) -> list[dict[str, Any]]:
        del pid_str, since, cfg
        return list(self._nutrition_events)

    async def _get_lab_series(self, his_pid: str, key: str, since: datetime, end: datetime, limit: int = 600) -> list[dict[str, Any]]:
        del limit
        keywords = {"k": ["钾", "k"]}.get(key, [key])
        return await self._get_lab_series_by_keywords(his_pid, since, end, keywords)

    async def _is_suppressed(self, patient_id: str, rule_id: str | None, same_rule_seconds: int, max_per_hour: int) -> bool:
        del patient_id, rule_id, same_rule_seconds, max_per_hour
        return False

    async def _create_alert(self, **kwargs: Any) -> dict[str, Any]:
        self.created_alerts.append(kwargs)
        return kwargs

    def _log_info(self, name: str, count: int) -> None:
        del name, count


class _BetaEngine:
    def __init__(self) -> None:
        self.config = SimpleNamespace(
            yaml_cfg={
                "alert_engine": {
                    "beta_blocker_advisor": {
                        "enabled": True,
                        "scan_interval": 3600,
                        "hr_threshold": 95,
                        "tachy_ratio": 0.8,
                        "map_threshold": 65,
                        "troponin_upper_limit": 0.04,
                        "bnp_threshold": 300,
                        "norepi_threshold": 0.2,
                        "norepi_taper_ratio": 0.1,
                        "fever_threshold": 38.3,
                        "cpot_threshold": 3,
                        "bps_threshold": 5,
                        "brady_history_threshold": 60,
                        "cardiac_index_code": "param_ci",
                        "cardiac_index_threshold": 2.0,
                    },
                    "suppression": {"same_rule_same_patient_seconds": 1800, "max_alerts_per_patient_per_hour": 10},
                },
                "nurse_reminders": {"early_mobility": {"norepi_keywords": ["去甲肾上腺素"], "norepi_threshold_ug_kg_min": 0.2}},
            }
        )
        self.db = _FakeDb(
            {
                "alert_records": [{"patient_id": "p1", "rule_id": "SEPSIS_SOFA", "alert_type": "sofa", "created_at": datetime.now() - timedelta(hours=1)}],
                "score": [],
                "patient": [{"_id": "p1", "name": "张三"}],
            }
        )
        self.created_alerts: list[dict[str, Any]] = []

    def _cfg(self, *path: str, default: Any = None) -> Any:
        cursor: Any = self.config.yaml_cfg
        for key in path:
            if not isinstance(cursor, dict) or key not in cursor:
                return default
            cursor = cursor[key]
        return cursor

    async def _get_param_series_by_pid(self, patient_id: Any, code: str, since: datetime, prefer_device_types: list[str] | None = None, limit: int = 1200) -> list[dict[str, Any]]:
        del patient_id, since, prefer_device_types, limit
        now = datetime.now()
        if code == "param_HR":
            return [{"time": now - timedelta(hours=2), "value": 102}, {"time": now, "value": 108}]
        if code == "param_ci":
            return [{"time": now - timedelta(hours=2), "value": 2.4}, {"time": now, "value": 2.2}]
        return []

    async def _get_latest_labs_map(self, his_pid: str, lookback_hours: int = 72) -> dict[str, Any]:
        del his_pid, lookback_hours
        return {"trop": {"value": 0.12}, "bnp": {"value": 450}}

    async def _get_map_series(self, patient_id: Any, since: datetime) -> list[dict[str, Any]]:
        del patient_id, since
        now = datetime.now()
        return [{"time": now - timedelta(hours=3), "value": 68}, {"time": now, "value": 72}]

    async def _get_current_vasopressor_snapshot(self, patient_id: Any, patient_doc: dict[str, Any], hours: int = 8, max_items: int = 4) -> list[dict[str, Any]]:
        del patient_id, patient_doc, hours, max_items
        return [{"drug": "去甲肾上腺素", "dose_ug_kg_min": 0.12}]

    def _get_patient_weight(self, patient_doc: dict[str, Any]) -> float:
        del patient_doc
        return 70.0

    async def _get_norepi_dose_series(self, pid_str: str, now: datetime, lookback_hours: float, keywords: list[str], weight_kg: float | None) -> list[dict[str, Any]]:
        del pid_str, now, lookback_hours, keywords, weight_kg
        base = datetime.now() - timedelta(hours=4)
        return [{"time": base, "dose_ug_kg_min": 0.18}, {"time": datetime.now(), "dose_ug_kg_min": 0.12}]

    def _is_series_tapering(self, points: list[dict[str, Any]], min_drop_ratio: float = 0.1) -> bool:
        del min_drop_ratio
        return points[-1]["dose_ug_kg_min"] < points[0]["dose_ug_kg_min"]

    async def _get_latest_param_snapshot_by_pid(self, patient_id: Any, codes: list[str] | None = None, lookback_minutes: int = 180, limit: int = 200) -> dict[str, Any]:
        del patient_id, codes, lookback_minutes, limit
        return {"params": {"param_T": 37.0}}

    async def _get_latest_assessment(self, patient_id: Any, kind: str) -> float | None:
        del patient_id, kind
        return None

    async def _get_recent_text_events(self, patient_id: Any, keywords: list[str], hours: int = 24, limit: int = 200) -> list[dict[str, Any]]:
        del patient_id, keywords, hours, limit
        return []

    async def _get_recent_drug_docs_window(self, patient_id: Any, hours: int = 24, limit: int = 200) -> list[dict[str, Any]]:
        del patient_id, hours, limit
        return []

    async def _is_suppressed(self, patient_id: str, rule_id: str | None, same_rule_seconds: int, max_per_hour: int) -> bool:
        del patient_id, rule_id, same_rule_seconds, max_per_hour
        return False

    async def _create_alert(self, **kwargs: Any) -> dict[str, Any]:
        self.created_alerts.append(kwargs)
        return kwargs

    def _log_info(self, name: str, count: int) -> None:
        del name, count


class _NoninvasiveEngine:
    def __init__(self) -> None:
        self.config = SimpleNamespace(
            yaml_cfg={
                "alert_engine": {
                    "noninvasive_respiratory_support": {},
                    "suppression": {"same_rule_same_patient_seconds": 0, "max_alerts_per_patient_per_hour": 20},
                }
            }
        )
        self.db = _FakeDb(
            {
                "patient": [{"_id": "p1", "name": "张三", "hisPid": "H1", "age": 70}],
                "deviceBind": [{"pid": "p1", "type": "HFNC 高流量鼻导管", "deviceID": "hfnc1", "bindTime": datetime.now() - timedelta(hours=2), "unBindTime": None}],
                "bedside": [
                    {"pid": "p1", "code": "param_spo2", "time": datetime.now(), "fVal": 90},
                    {"pid": "p1", "code": "param_resp", "time": datetime.now(), "fVal": 32},
                    {"pid": "p1", "code": "param_FiO2", "time": datetime.now(), "fVal": 80},
                    {"pid": "p1", "code": "param_hfnc_flow", "time": datetime.now(), "fVal": 50},
                ],
                "VI_ICU_EXAM_ITEM": [],
            }
        )
        self.created_alerts: list[dict[str, Any]] = []

    def _cfg(self, *path: str, default: Any = None) -> Any:
        cursor: Any = self.config.yaml_cfg
        for key in path:
            if not isinstance(cursor, dict) or key not in cursor:
                return default
            cursor = cursor[key]
        return cursor

    def _active_patient_query(self) -> dict[str, Any]:
        return {}

    async def _get_latest_param_snapshot_by_pid(self, patient_id: str, codes: list[str] | None = None, lookback_minutes: int = 120, limit: int = 1000) -> dict[str, Any]:
        del codes, lookback_minutes, limit
        params = {}
        latest = None
        for row in self.db.col("bedside").docs:
            if row.get("pid") != patient_id:
                continue
            params[row["code"]] = row.get("fVal")
            latest = row.get("time")
        return {"params": params, "time": latest}

    async def _get_latest_labs_map(self, his_pid: str, lookback_hours: int = 6) -> dict[str, Any]:
        del his_pid, lookback_hours
        return {}

    async def _is_suppressed(self, patient_id: str, rule_id: str | None, same_rule_seconds: int, max_per_hour: int) -> bool:
        del patient_id, rule_id, same_rule_seconds, max_per_hour
        return False

    async def _create_alert(self, **kwargs: Any) -> dict[str, Any]:
        self.created_alerts.append(kwargs)
        return kwargs

    def _log_info(self, name: str, count: int) -> None:
        del name, count


@pytest.mark.asyncio
async def test_integrated_risk_reasoning_generates_report_and_broadcast() -> None:
    engine = _IntegratedEngine()
    scanner = IntegratedRiskReasoningScanner(engine)
    scanner._call_reasoning_llm = lambda **kwargs: __import__("asyncio").sleep(0, result={
        "summary": "患者以感染性休克合并肾损伤为主要矛盾。",
        "causal_chain": "脓毒症导致低灌注并推动 AKI。",
        "deterioration_forecast": "未来 4-12h 需警惕循环进一步恶化。",
        "top3_actions": [{"priority": 1, "action": "立即优化循环复苏", "rationale": "存在脓毒性休克", "urgency": 20}],
        "differential_diagnosis": ["需排除隐匿失血"],
    })

    report = await scanner._scan_patient(
        patient_doc={"_id": "p1", "name": "张三", "clinicalDiagnosis": "脓毒症"},
        now=datetime.now(),
    )

    assert report is not None
    assert report["risk_level"] == "critical"
    assert len(engine.db.col("integrated_risk_reports").docs) == 1
    assert engine.created_alerts[0]["alert_type"] == "integrated_risk_reasoning"
    assert engine.ws.messages[0]["type"] == "integrated_risk_report"


@pytest.mark.asyncio
async def test_metabolic_phase_detector_triggers_transition_alert() -> None:
    engine = _MetabolicEngine(
        score_docs=[{"patient_id": "p1", "score_type": "metabolic_phase_detector", "phase": "ebb", "calc_time": datetime.now() - timedelta(hours=4)}],
        nutrition_events=[
            {"time": datetime.now() - timedelta(hours=3), "kcal": 1400, "raw": {"protein": 84}},
            {"time": datetime.now() - timedelta(hours=1), "kcal": 200, "raw": {"protein": 12}},
        ],
    )
    scanner = MetabolicPhaseDetectorScanner(engine)
    scanner._raw_lab_series = lambda his_pid, keywords, since: __import__("asyncio").sleep(0, result=(
        [{"time": datetime.now() - timedelta(days=1), "value": 60.0}, {"time": datetime.now(), "value": 40.0}] if "crp" in keywords[0].lower()
        else [{"time": datetime.now() - timedelta(days=1), "value": 18.0}, {"time": datetime.now(), "value": 22.0}] if "前白蛋白" in keywords[0] or "prealbumin" in keywords[0].lower()
        else [{"time": datetime.now() - timedelta(days=1), "value": 8.0}, {"time": datetime.now(), "value": 7.0}]
    ))

    alerts = await scanner._scan_patient(
        patient_doc={"_id": "p1", "name": "张三", "hisPid": "H1", "icuAdmissionTime": datetime.now() - timedelta(days=2)},
        now=datetime.now(),
        same_rule_sec=1800,
        max_per_hour=10,
    )

    assert any(alert["alert_type"] == "metabolic_phase_transition" for alert in alerts)
    assert engine.db.col("score").docs[-1]["phase"] == "transition"


@pytest.mark.asyncio
async def test_nutrition_monitor_uses_metabolic_phase_targets_and_checks_protein() -> None:
    now = datetime.now()
    engine = _NutritionEngine(
        nutrition_events=[
            {"time": now - timedelta(hours=30), "type": "enteral", "kcal": 200, "raw": {"protein": 4}},
            {"time": now - timedelta(hours=3), "type": "enteral", "kcal": 200, "raw": {"protein": 4}},
        ],
        score_docs=[
            {
                "patient_id": "p1",
                "score_type": "metabolic_phase_detector",
                "phase": "transition",
                "nutrition_target": {"kcal": [20, 25], "protein": [1.0, 1.3]},
                "calc_time": now - timedelta(hours=1),
            }
        ],
    )

    await NutritionMonitorScanner(engine).scan()

    calorie_alert = next(alert for alert in engine.created_alerts if alert["alert_type"] == "nutrition_calorie_not_reached")
    protein_alert = next(alert for alert in engine.created_alerts if alert["alert_type"] == "nutrition_protein_not_reached")
    assert calorie_alert["extra"]["target_strategy"] == "metabolic_phase_detector"
    assert calorie_alert["extra"]["target_kcal_per_kg_day_range"] == [20.0, 25.0]
    assert protein_alert["extra"]["target_protein_g_kg_day_range"] == [1.0, 1.3]


@pytest.mark.asyncio
async def test_nutrition_monitor_obesity_adjusts_calorie_target() -> None:
    now = datetime.now()
    engine = _NutritionEngine(
        patient={
            "_id": "p1",
            "name": "张三",
            "hisPid": "H1",
            "weight": 120,
            "height": 170,
            "bmi": 41.5,
            "icuAdmissionTime": now - timedelta(days=5),
        },
        nutrition_events=[
            {"time": now - timedelta(hours=30), "type": "enteral", "kcal": 500, "raw": {"protein": 20}},
            {"time": now - timedelta(hours=3), "type": "enteral", "kcal": 100, "raw": {"protein": 4}},
        ],
    )

    await NutritionMonitorScanner(engine).scan()

    calorie_alert = next(alert for alert in engine.created_alerts if alert["alert_type"] == "nutrition_calorie_not_reached")
    assert calorie_alert["extra"]["obesity_adjusted"] is True
    assert calorie_alert["extra"]["target_kcal_per_kg_day_range"] == [11.0, 14.0]
    assert calorie_alert["extra"]["target_weight_kg"] == 120.0


@pytest.mark.asyncio
async def test_nutrition_monitor_refeeding_prevention_and_start_speed() -> None:
    now = datetime.now()
    start = now - timedelta(hours=10)
    labs = [
        {"hisPid": "H1", "authTime": now - timedelta(hours=8), "itemCnName": "血磷", "result": "0.55", "unit": "mmol/L"},
        {"hisPid": "H1", "authTime": now - timedelta(hours=8), "itemCnName": "血钾", "result": "3.2", "unit": "mmol/L"},
        {"hisPid": "H1", "authTime": now - timedelta(hours=8), "itemCnName": "血镁", "result": "0.7", "unit": "mmol/L"},
    ]
    engine = _NutritionEngine(
        patient={
            "_id": "p1",
            "name": "张三",
            "hisPid": "H1",
            "weight": 50,
            "height": 170,
            "bmi": 15.5,
            "icuAdmissionTime": now - timedelta(days=2),
        },
        nutrition_events=[
            {"time": start, "type": "enteral", "kcal": 800, "raw": {"protein": 20}},
        ],
        lab_docs=labs,
    )

    await NutritionMonitorScanner(engine).scan()

    alert_types = {alert["alert_type"] for alert in engine.created_alerts}
    assert "nutrition_refeeding_prevention" in alert_types
    assert "nutrition_refeeding_start_too_fast" in alert_types


@pytest.mark.asyncio
async def test_nutrition_monitor_early_phase_target_is_not_fixed_25() -> None:
    engine = _NutritionEngine(
        patient={
            "_id": "p1",
            "weight": 70,
            "height": 170,
            "icuAdmissionTime": datetime.now() - timedelta(days=2),
        }
    )
    scanner = NutritionMonitorScanner(engine)
    target = await scanner._dynamic_nutrition_target(engine.db.col("patient").docs[0], "p1", 48, 70, {})

    assert target["phase"] == "acute_early"
    assert target["target_kcal_per_kg_day_range"] == [10.0, 20.0]


@pytest.mark.asyncio
async def test_beta_blocker_advisor_emits_high_alert_when_all_conditions_met() -> None:
    engine = _BetaEngine()
    scanner = BetaBlockerAdvisorScanner(engine)

    alerts = await scanner._scan_patient(
        patient_doc={"_id": "p1", "name": "张三", "hisPid": "H1", "clinicalDiagnosis": "脓毒症"},
        now=datetime.now(),
        same_rule_sec=1800,
        max_per_hour=10,
    )

    assert len(alerts) == 1
    assert alerts[0]["severity"] == "high"
    assert alerts[0]["alert_type"] == "beta_blocker_advisor"
    assert "艾司洛尔" in alerts[0]["explanation"]["suggestion"]


def test_ventilator_mechanical_power_uses_mode_specific_formula() -> None:
    scanner = VentilatorWeaningScanner(SimpleNamespace())
    vcv = scanner._mechanical_power(
        mode="VCV",
        rr=24,
        vte_ml=420,
        peep=10,
        pip=32,
        pplat=28,
        pc_above_peep=None,
        pbw=60,
    )
    psv = scanner._mechanical_power(
        mode="PSV",
        rr=24,
        vte_ml=420,
        peep=10,
        pip=22,
        pplat=None,
        pc_above_peep=12,
        pbw=60,
    )

    assert vcv is not None and vcv["mode"] == "VCV"
    assert psv is not None and psv["mode"] == "PSV"
    assert vcv["components"]["peep_static_j_min"] > 0
    assert psv["mechanical_power_j_min_kg_pbw"] is not None
    assert "pressure_support" in psv["formula"]


def test_ventilator_mode_classifier_handles_common_labels() -> None:
    scanner = VentilatorWeaningScanner(SimpleNamespace())

    assert scanner._classify_vent_mode("PSV 压力支持") == "PSV"
    assert scanner._classify_vent_mode("PCV 压力控制") == "PCV"
    assert scanner._classify_vent_mode("AC-VC 容量控制") == "VCV"


@pytest.mark.asyncio
async def test_noninvasive_support_scanner_triggers_hfnc_rox_alert() -> None:
    engine = _NoninvasiveEngine()
    await NoninvasiveRespiratorySupportScanner(engine).scan()

    assert engine.created_alerts
    assert engine.created_alerts[0]["alert_type"] == "hfnc_failure_risk"
    assert engine.created_alerts[0]["extra"]["rox_index"] < 4.88


def test_airway_risk_helpers_include_cuff_leak_and_difficult_airway() -> None:
    assert _laryngeal_edema_risk({"leak_volume_ml": 80}) == "high"
    risk = _infer_airway_risk(
        {"difficult_airway": True},
        {"mallampati": "IV", "prior_difficult_intubation": True},
        {"latest_cuff_leak_test": {"leak_percent": 8}},
    )
    assert risk == "critical"
