from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.alert_engine.scanner_fibrinolysis_monitor import FibrinolysisMonitorScanner
from app.alert_engine.scanner_pics_risk import PicsRiskScanner
from app.alert_engine.scanner_prone_position_monitor import PronePositionMonitorScanner
from app.alert_engine.scanner_sepsis_subphenotype import SepsisSubphenotypeScanner


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
        row = self._docs[self._idx]
        self._idx += 1
        return dict(row)


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
        return _InsertResult(int(row["_id"]))

    async def update_one(self, selector: dict[str, Any], update: dict[str, Any]) -> None:
        for doc in self.docs:
            if self._match(doc, selector):
                for key, value in update.get("$set", {}).items():
                    self._assign(doc, key, value)
                return
        row = dict(selector)
        for key, value in update.get("$set", {}).items():
            self._assign(row, key, value)
        self.docs.append(row)

    async def count_documents(self, query: dict[str, Any]) -> int:
        return len([doc for doc in self.docs if self._match(doc, query)])

    @classmethod
    def _assign(cls, doc: dict[str, Any], dotted: str, value: Any) -> None:
        target = doc
        parts = dotted.split(".")
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
    def _get(doc: dict[str, Any], dotted: str) -> Any:
        target: Any = doc
        for part in dotted.split("."):
            if not isinstance(target, dict):
                return None
            target = target.get(part)
        return target


class _FakeDb:
    def __init__(self, collections: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.collections = {name: _Collection(docs) for name, docs in (collections or {}).items()}

    def col(self, name: str) -> _Collection:
        return self.collections.setdefault(name, _Collection())

    def dc_col(self, name: str) -> _Collection:
        return self.collections.setdefault(name, _Collection())


class _SubphenotypeEngine:
    def __init__(self) -> None:
        self.config = SimpleNamespace(
            yaml_cfg={
                "alert_engine": {
                    "sepsis_subphenotype": {
                        "enabled": True,
                        "scan_interval": 3600,
                        "min_sofa": 2,
                        "confidence_threshold": 0.6,
                        "transition_detection_hours": 12,
                        "diagnosis_keywords": ["脓毒", "感染", "sepsis"],
                        "hyperthermia_threshold": 38.3,
                        "hypothermia_threshold": 36.0,
                        "labels": {
                            "alpha_hyperinflammatory": "α-高炎症型",
                            "beta_immunosuppressed": "β-免疫抑制型",
                            "gamma_hypercoagulable": "γ-高凝型",
                            "delta_mixed": "δ-混合型",
                            "mixed_uncertain": "混合/不确定",
                        },
                        "care_implications": {"alpha_hyperinflammatory": {"summary": "炎症占主导", "care_implications": ["评估糖皮质激素"]}},
                        "feature_order": ["inflammation", "immunosuppression", "coagulopathy", "organ_dysfunction", "hemodynamic_instability", "temperature_pattern"],
                        "feature_reference": {
                            "inflammation": {"mean": 1.0, "std": 0.6},
                            "immunosuppression": {"mean": 1.0, "std": 0.6},
                            "coagulopathy": {"mean": 1.0, "std": 0.6},
                            "organ_dysfunction": {"mean": 1.0, "std": 0.6},
                            "hemodynamic_instability": {"mean": 1.0, "std": 0.6},
                            "temperature_pattern": {"mean": 0.0, "std": 1.0},
                        },
                        "centroids": {
                            "alpha_hyperinflammatory": [1.8, 0.6, 0.0, 0.6, 0.2, 1.0],
                            "beta_immunosuppressed": [0.3, 2.0, 0.2, 0.5, 0.0, -0.8],
                            "gamma_hypercoagulable": [0.7, 0.7, 1.8, 0.9, 0.2, 0.0],
                            "delta_mixed": [1.0, 1.0, 1.0, 1.0, 0.8, 0.2],
                        },
                        "crp_keywords": ["crp"],
                        "il6_keywords": ["il6"],
                        "ferritin_keywords": ["ferritin"],
                        "wbc_keywords": ["wbc"],
                        "neutrophil_keywords": ["neut"],
                        "lymphocyte_keywords": ["lymph"],
                    },
                    "suppression": {"same_rule_same_patient_seconds": 1800, "max_alerts_per_patient_per_hour": 10},
                },
                "vital_signs": {"temperature": {"code": "param_T"}},
            }
        )
        self.db = _FakeDb(
            {
                "alert_records": [{"patient_id": "p1", "rule_id": "SEPSIS_SOFA", "alert_type": "sofa", "created_at": datetime.now() - timedelta(hours=1)}],
                "score": [],
                "patient": [{"_id": "p1", "name": "张三"}],
                "VI_ICU_EXAM_ITEM": [
                    {"hisPid": "H1", "itemName": "crp", "result": 80, "authTime": datetime.now()},
                    {"hisPid": "H1", "itemName": "il6", "result": 120, "authTime": datetime.now()},
                    {"hisPid": "H1", "itemName": "ferritin", "result": 850, "authTime": datetime.now()},
                    {"hisPid": "H1", "itemName": "wbc", "result": 19, "authTime": datetime.now()},
                    {"hisPid": "H1", "itemName": "neut", "result": 16, "authTime": datetime.now()},
                    {"hisPid": "H1", "itemName": "lymph", "result": 0.8, "authTime": datetime.now()},
                ],
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

    async def _get_device_id_for_patient(self, patient_doc: dict[str, Any], device_types: list[str] | None = None) -> str | None:
        del patient_doc, device_types
        return "dev-1"

    async def _calc_sofa(self, patient_doc: dict[str, Any], patient_id: Any, device_id: str | None, his_pid: str) -> dict[str, Any]:
        del patient_doc, patient_id, device_id, his_pid
        return {"score": 7, "delta": 3}

    async def _get_latest_labs_map(self, his_pid: str, lookback_hours: int = 48) -> dict[str, Any]:
        del his_pid, lookback_hours
        return {
            "pct": {"value": 12.0},
            "ddimer": {"value": 4.2},
            "plt": {"value": 95},
            "inr": {"value": 1.4},
            "fib": {"value": 2.5},
            "lac": {"value": 4.8},
            "cr": {"value": 190},
            "bil": {"value": 58},
            "pao2": {"value": 80},
        }

    async def _get_latest_device_cap(self, device_id: str) -> dict[str, Any]:
        del device_id
        return {"params": {"param_HR": 118, "param_FiO2": 60}, "time": datetime.now()}

    def _get_map(self, cap: dict[str, Any]) -> float | None:
        del cap
        return 56.0

    def _vent_param(self, cap: dict[str, Any], name: str, default: str | None = None) -> float | None:
        del name, default
        return float(((cap.get("params") or {}).get("param_FiO2")) or 0)

    async def _get_current_vasopressor_snapshot(self, patient_id: Any, patient_doc: dict[str, Any], hours: int = 8, max_items: int = 4) -> list[dict[str, Any]]:
        del patient_id, patient_doc, hours, max_items
        return [{"drug": "去甲肾上腺素", "dose_ug_kg_min": 0.22}]

    async def _get_param_series_by_pid(self, patient_id: Any, code: str, since: datetime, prefer_device_types: list[str] | None = None, limit: int = 360) -> list[dict[str, Any]]:
        del patient_id, since, prefer_device_types, limit
        if code == "param_T":
            now = datetime.now()
            return [{"time": now - timedelta(hours=2), "value": 38.1}, {"time": now, "value": 39.0}]
        return []

    async def _is_suppressed(self, patient_id: str, rule_id: str | None, same_rule_seconds: int, max_per_hour: int) -> bool:
        del patient_id, rule_id, same_rule_seconds, max_per_hour
        return False

    async def _create_alert(self, **kwargs: Any) -> dict[str, Any]:
        self.created_alerts.append(kwargs)
        return kwargs

    def _log_info(self, name: str, count: int) -> None:
        del name, count


class _FibrinolysisEngine:
    def __init__(self) -> None:
        self.config = SimpleNamespace(yaml_cfg={"alert_engine": {"fibrinolysis_monitor": {"enabled": True}, "suppression": {"same_rule_same_patient_seconds": 1800, "max_alerts_per_patient_per_hour": 10}}})
        self.db = _FakeDb({"score": [], "patient": [{"_id": "p1", "name": "张三"}], "VI_ICU_EXAM_ITEM": []})
        self.created_alerts: list[dict[str, Any]] = []

    def _cfg(self, *path: str, default: Any = None) -> Any:
        cursor: Any = self.config.yaml_cfg
        for key in path:
            if not isinstance(cursor, dict) or key not in cursor:
                return default
            cursor = cursor[key]
        return cursor

    async def _get_latest_labs_map(self, his_pid: str, lookback_hours: int = 72) -> dict[str, Any]:
        del his_pid, lookback_hours
        return {"ddimer": {"value": 8.0}, "fib": {"value": 1.1}, "plt": {"value": 62}, "inr": {"value": 1.8}, "pt": {"value": 18}}

    async def _get_latest_active_alert(self, patient_id: str, alert_types: list[str], hours: int = 24) -> dict[str, Any] | None:
        del patient_id, alert_types, hours
        return {"alert_type": "gi_bleeding"}

    async def _is_suppressed(self, patient_id: str, rule_id: str | None, same_rule_seconds: int, max_per_hour: int) -> bool:
        del patient_id, rule_id, same_rule_seconds, max_per_hour
        return False

    async def _create_alert(self, **kwargs: Any) -> dict[str, Any]:
        self.created_alerts.append(kwargs)
        return kwargs

    def _log_info(self, name: str, count: int) -> None:
        del name, count


class _ProneEngine:
    def __init__(self) -> None:
        self.config = SimpleNamespace(yaml_cfg={"alert_engine": {"prone_position_monitor": {"enabled": True, "position_code": "param_TiWei", "prone_values": ["俯卧位"], "supine_values": ["仰卧位"]}, "suppression": {"same_rule_same_patient_seconds": 1800, "max_alerts_per_patient_per_hour": 10}}})
        self.db = _FakeDb({"score": [], "patient": [{"_id": "p1", "name": "张三"}], "bedside": [
            {"pid": "p1", "code": "param_TiWei", "time": datetime.now() - timedelta(hours=20), "strVal": "俯卧位"},
            {"pid": "p1", "code": "param_TiWei", "time": datetime.now() - timedelta(hours=6), "strVal": "仰卧位"},
        ]})
        self.created_alerts: list[dict[str, Any]] = []

    def _cfg(self, *path: str, default: Any = None) -> Any:
        cursor: Any = self.config.yaml_cfg
        for key in path:
            if not isinstance(cursor, dict) or key not in cursor:
                return default
            cursor = cursor[key]
        return cursor

    async def _get_device_id_for_patient(self, patient_doc: dict[str, Any], device_types: list[str] | None = None) -> str | None:
        del patient_doc, device_types
        return "vent-1"

    async def _get_latest_device_cap(self, device_id: str) -> dict[str, Any]:
        del device_id
        return {"params": {"param_FiO2": 70, "param_vent_measure_peep": 10}, "time": datetime.now()}

    def _vent_param(self, cap: dict[str, Any], name: str, default: str | None = None) -> float | None:
        del name, default
        return float(((cap.get("params") or {}).get("param_FiO2")) or 0)

    def _vent_param_priority(self, cap: dict[str, Any], names: list[str], defaults: list[str]) -> float | None:
        del names, defaults
        return float(((cap.get("params") or {}).get("param_vent_measure_peep")) or 0)

    async def _get_latest_labs_map(self, his_pid: str, lookback_hours: int = 24) -> dict[str, Any]:
        del his_pid, lookback_hours
        return {"pao2": {"value": 72}}

    async def _get_latest_active_alert(self, patient_id: str, alert_types: list[str], hours: int = 24) -> dict[str, Any] | None:
        del patient_id, alert_types, hours
        return None

    async def _get_recent_text_events(self, patient_id: Any, keywords: list[str], hours: int = 48, limit: int = 1200) -> list[dict[str, Any]]:
        del patient_id, keywords, hours, limit
        return []

    async def _is_suppressed(self, patient_id: str, rule_id: str | None, same_rule_seconds: int, max_per_hour: int) -> bool:
        del patient_id, rule_id, same_rule_seconds, max_per_hour
        return False

    async def _create_alert(self, **kwargs: Any) -> dict[str, Any]:
        self.created_alerts.append(kwargs)
        return kwargs

    def _log_info(self, name: str, count: int) -> None:
        del name, count


class _PicsEngine:
    def __init__(self) -> None:
        self.config = SimpleNamespace(yaml_cfg={"alert_engine": {"pics_risk": {"enabled": True}, "suppression": {"same_rule_same_patient_seconds": 1800, "max_alerts_per_patient_per_hour": 10}}})
        self.db = _FakeDb({"score": [], "patient": [{"_id": "p1", "name": "张三"}], "alert_records": [{"patient_id": "p1", "alert_type": "icu_aw_risk", "severity": "high", "created_at": datetime.now() - timedelta(days=1)}]})
        self.created_alerts: list[dict[str, Any]] = []

    def _cfg(self, *path: str, default: Any = None) -> Any:
        cursor: Any = self.config.yaml_cfg
        for key in path:
            if not isinstance(cursor, dict) or key not in cursor:
                return default
            cursor = cursor[key]
        return cursor

    async def _detect_transfer_candidate_signal(self, patient_doc: dict[str, Any], pid_str: str, now: datetime) -> dict[str, Any]:
        del patient_doc, pid_str, now
        return {"candidate": True}

    async def _get_ventilation_days(self, patient_id: Any, now: datetime, admission_time: datetime | None) -> dict[str, Any]:
        del patient_id, now, admission_time
        return {"days": 8}

    def _icu_aw_admission_time(self, patient_doc: dict[str, Any]) -> datetime | None:
        return patient_doc.get("icuAdmissionTime") if isinstance(patient_doc.get("icuAdmissionTime"), datetime) else datetime.now() - timedelta(days=8)

    async def _immobility_hours(self, patient_doc: dict[str, Any], patient_id: Any, now: datetime) -> float:
        del patient_doc, patient_id, now
        return 96.0

    async def _get_latest_assessment(self, patient_id: Any, kind: str) -> float | None:
        del patient_id
        if kind == "gcs":
            return 12.0
        if kind == "rass":
            return -4.0
        return None

    async def latest_nursing_note_analysis(self, patient_id: str, hours: int = 48) -> dict[str, Any] | None:
        del patient_id, hours
        return {"signal_labels": ["家属沟通异常", "意识状态波动"]}

    async def _get_recent_text_events(self, patient_id: Any, keywords: list[str], hours: int = 72, limit: int = 200) -> list[dict[str, Any]]:
        del patient_id, keywords, hours, limit
        return [{"time": datetime.now() - timedelta(hours=6), "code": "nurse", "strVal": "患者焦虑、夜间睡眠差"}]

    async def _is_suppressed(self, patient_id: str, rule_id: str | None, same_rule_seconds: int, max_per_hour: int) -> bool:
        del patient_id, rule_id, same_rule_seconds, max_per_hour
        return False

    async def _create_alert(self, **kwargs: Any) -> dict[str, Any]:
        self.created_alerts.append(kwargs)
        return kwargs

    def _log_info(self, name: str, count: int) -> None:
        del name, count


@pytest.mark.asyncio
async def test_sepsis_subphenotype_scanner_emits_alpha_alert() -> None:
    engine = _SubphenotypeEngine()
    scanner = SepsisSubphenotypeScanner(engine)

    alerts = await scanner._scan_patient(
        patient_doc={"_id": "p1", "name": "张三", "hisPid": "H1", "clinicalDiagnosis": "脓毒症"},
        now=datetime.now(),
        same_rule_sec=1800,
        max_per_hour=10,
    )

    assert len(alerts) == 1
    assert alerts[0]["alert_type"] == "sepsis_subphenotype"
    assert "高炎症" in alerts[0]["name"]


@pytest.mark.asyncio
async def test_fibrinolysis_scanner_emits_hyperfibrinolysis_alert() -> None:
    engine = _FibrinolysisEngine()
    scanner = FibrinolysisMonitorScanner(engine)

    alerts = await scanner._scan_patient(
        patient_doc={"_id": "p1", "name": "张三", "hisPid": "H1"},
        now=datetime.now(),
        same_rule_sec=1800,
        max_per_hour=10,
    )

    assert len(alerts) == 1
    assert alerts[0]["alert_type"] == "hyperfibrinolysis"


@pytest.mark.asyncio
async def test_prone_position_scanner_emits_candidate_alert() -> None:
    engine = _ProneEngine()
    scanner = PronePositionMonitorScanner(engine)

    alerts = await scanner._scan_patient(
        patient_doc={"_id": "p1", "name": "张三", "hisPid": "H1"},
        now=datetime.now(),
        same_rule_sec=1800,
        max_per_hour=10,
    )

    assert any(alert["alert_type"] == "prone_position_candidate" for alert in alerts)


@pytest.mark.asyncio
async def test_pics_scanner_emits_high_risk_alert() -> None:
    engine = _PicsEngine()
    scanner = PicsRiskScanner(engine)

    alerts = await scanner._scan_patient(
        patient_doc={"_id": "p1", "name": "张三", "icuAdmissionTime": datetime.now() - timedelta(days=8)},
        now=datetime.now(),
        same_rule_sec=1800,
        max_per_hour=10,
    )

    assert len(alerts) == 1
    assert alerts[0]["alert_type"] == "pics_risk"
    followup_cases = engine.db.col("followup_cases").docs
    assert len(followup_cases) == 1
    assert followup_cases[0]["source_module"] == "pics_risk"
