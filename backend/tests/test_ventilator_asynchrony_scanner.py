from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.alert_engine.scanner_ventilator_asynchrony import VentilatorAsynchronyScanner


class _Collection:
    def __init__(self, docs: list[dict[str, Any]] | None = None) -> None:
        self.docs = [dict(doc) for doc in (docs or [])]

    async def find_one(self, query: dict[str, Any], sort: list[tuple[str, int]] | None = None) -> dict[str, Any] | None:
        rows = [doc for doc in self.docs if self._match(doc, query)]
        if sort:
            key, direction = sort[0]
            rows.sort(key=lambda item: item.get(key), reverse=direction == -1)
        return dict(rows[0]) if rows else None

    @staticmethod
    def _match(doc: dict[str, Any], query: dict[str, Any]) -> bool:
        for key, value in query.items():
            current = doc.get(key)
            if isinstance(value, dict):
                if "$gte" in value and not (current >= value["$gte"]):
                    return False
                if "$in" in value and current not in value["$in"]:
                    return False
            elif current != value:
                return False
        return True


class _FakeDb:
    def __init__(self, *, score_docs: list[dict[str, Any]] | None = None, alert_docs: list[dict[str, Any]] | None = None) -> None:
        self._collections = {
            "score": _Collection(score_docs),
            "alert_records": _Collection(alert_docs),
        }

    def col(self, name: str) -> _Collection:
        return self._collections.setdefault(name, _Collection())


class _FakeEngine:
    def __init__(self, *, cap_params: dict[str, Any], alert_docs: list[dict[str, Any]] | None = None) -> None:
        self.config = SimpleNamespace(
            yaml_cfg={
                "alert_engine": {
                    "ventilator_asynchrony": {
                        "enabled": True,
                        "scan_interval": 1800,
                        "analysis_window_minutes": 30,
                        "ai_threshold_warning": 0.10,
                        "ai_threshold_high": 0.10,
                        "ai_threshold_critical": 0.30,
                        "double_trigger_vt_ratio": 1.5,
                        "stacked_vt_ml_kg_threshold": 8.0,
                        "double_trigger_interval_ratio_threshold": 0.5,
                        "drive_p0_1_threshold": 3.5,
                        "drive_edi_threshold": 15,
                        "reverse_rass_threshold": -3,
                        "use_llm_analysis": False,
                    },
                    "suppression": {
                        "same_rule_same_patient_seconds": 1800,
                        "max_alerts_per_patient_per_hour": 10,
                    },
                }
            },
            llm_fast_model="test-model",
        )
        self.db = _FakeDb(alert_docs=alert_docs)
        self._cap = {"params": dict(cap_params), "time": datetime.now()}
        self.created_alerts: list[dict[str, Any]] = []
        self.persisted_assessments: list[dict[str, Any]] = []

    def _cfg(self, *path: str, default: Any = None) -> Any:
        cursor: Any = self.config.yaml_cfg
        for key in path:
            if not isinstance(cursor, dict) or key not in cursor:
                return default
            cursor = cursor[key]
        return cursor

    def _predicted_body_weight(self, patient_doc: dict[str, Any]) -> float:
        del patient_doc
        return 60.0

    async def _get_active_vent_bind(self, patient_id: str) -> dict[str, Any] | None:
        return {"deviceID": "vent-1", "pid": patient_id}

    async def _get_latest_device_cap(self, device_id: str, codes: list[str] | None = None) -> dict[str, Any] | None:
        del device_id, codes
        return dict(self._cap)

    async def _get_recent_drug_docs_window(self, patient_id: Any, hours: int = 8, limit: int = 200) -> list[dict[str, Any]]:
        del patient_id, hours, limit
        return []

    async def _get_param_series_by_pid(self, patient_id: Any, code: str, since: datetime, prefer_device_types: list[str] | None = None, limit: int = 600) -> list[dict[str, Any]]:
        del patient_id, since, prefer_device_types, limit
        value = self._cap["params"].get(code)
        if value is None:
            return []
        now = datetime.now()
        return [
            {"time": now - timedelta(minutes=20), "value": value},
            {"time": now - timedelta(minutes=10), "value": value},
            {"time": now, "value": value},
        ]

    async def _latest_diaphragm_drive(self, patient_id: Any, device_id: str) -> dict[str, Any]:
        del patient_id, device_id
        return {"time": datetime.now(), "edi": 8.0, "p0_1": 2.0}

    async def _get_latest_assessment(self, patient_id: Any, kind: str) -> float | None:
        del patient_id
        return -2.0 if kind == "rass" else None

    async def _is_suppressed(self, patient_id: str, rule_id: str | None, same_rule_seconds: int, max_per_hour: int) -> bool:
        del patient_id, rule_id, same_rule_seconds, max_per_hour
        return False

    async def _create_alert(self, **kwargs: Any) -> dict[str, Any]:
        self.created_alerts.append(kwargs)
        return kwargs

    async def _persist_ventilator_asynchrony_assessment(self, *, pid_str: str, patient_doc: dict[str, Any], now: datetime, assessment: dict[str, Any]) -> dict[str, Any]:
        row = {"patient_id": pid_str, "patient_name": patient_doc.get("name"), "calc_time": now, **assessment}
        self.persisted_assessments.append(row)
        return row

    async def _load_patient(self, patient_id: str) -> tuple[dict[str, Any] | None, str]:
        return {"_id": patient_id, "name": "张三", "hisBed": "01", "dept": "ICU"}, patient_id

    def _log_info(self, name: str, count: int) -> None:
        del name, count


@pytest.mark.asyncio
async def test_scan_patient_emits_double_trigger_high_alert() -> None:
    engine = _FakeEngine(
        cap_params={
            "param_HuXiMoShi": "AC-VC",
            "param_vent_set_vt": 450,
            "param_vent_vt": 820,
            "param_HuXiPinLv": 16,
            "param_vent_resp": 28,
            "param_vent_ti": 1.0,
            "param_vent_async_double_count": 120,
            "param_vent_double_trigger_interval_ratio": 0.4,
        }
    )
    scanner = VentilatorAsynchronyScanner(engine)

    fired = await scanner._scan_patient(
        patient_doc={"_id": "p1", "name": "张三", "hisBed": "01", "dept": "ICU"},
        now=datetime.now(),
        same_rule_sec=1800,
        max_per_hour=10,
    )

    assert len(fired) == 1
    assert len(engine.created_alerts) == 1
    assert len(engine.persisted_assessments) == 1
    alert = engine.created_alerts[0]
    assert alert["alert_type"] == "ventilator_asynchrony"
    assert alert["severity"] == "high"
    assert "双触发" in alert["name"]
    assert alert["extra"]["detail"]["asynchrony_type"] == "double_triggering"
    assert alert["extra"]["detail"]["asynchrony_index"] > 10.0


@pytest.mark.asyncio
async def test_scan_patient_marks_critical_when_ai_index_exceeds_thirty_percent() -> None:
    engine = _FakeEngine(
        cap_params={
            "param_HuXiMoShi": "AC-VC",
            "param_vent_set_vt": 450,
            "param_vent_vt": 860,
            "param_HuXiPinLv": 16,
            "param_vent_resp": 28,
            "param_vent_ti": 1.0,
            "param_vent_async_double_count": 320,
            "param_vent_double_trigger_interval_ratio": 0.3,
        },
        alert_docs=[
            {"patient_id": "p1", "alert_type": "ards", "severity": "high", "created_at": datetime.now() - timedelta(hours=1)}
        ],
    )
    scanner = VentilatorAsynchronyScanner(engine)

    fired = await scanner._scan_patient(
        patient_doc={"_id": "p1", "name": "张三", "hisBed": "01", "dept": "ICU"},
        now=datetime.now(),
        same_rule_sec=1800,
        max_per_hour=10,
    )

    assert len(fired) == 1
    alert = engine.created_alerts[0]
    assert alert["severity"] == "critical"
    assert alert["extra"]["detail"]["asynchrony_index"] > 30.0
    assert alert["extra"]["detail"]["module_links"]["ards_lung_protection"] is True


@pytest.mark.asyncio
async def test_scan_single_patient_uses_llm_recommendation_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _FakeEngine(
        cap_params={
            "param_HuXiMoShi": "AC-VC",
            "param_vent_set_vt": 450,
            "param_vent_vt": 820,
            "param_HuXiPinLv": 16,
            "param_vent_resp": 28,
            "param_vent_ti": 1.0,
            "param_vent_async_double_count": 120,
            "param_vent_double_trigger_interval_ratio": 0.4,
        }
    )
    engine.config.yaml_cfg["alert_engine"]["ventilator_asynchrony"]["use_llm_analysis"] = True
    scanner = VentilatorAsynchronyScanner(engine)

    async def fake_safe_llm_call(*args: Any, **kwargs: Any) -> dict[str, Any]:
        if args:
            coro = args[0]
            close = getattr(coro, "close", None)
            if callable(close):
                close()
        del kwargs
        return {
            "text": '{"analysis":"患者存在高驱动与双触发","recommendation":"建议将触发灵敏度从5调至3 L/min，并适度延长吸气时间","parameter_adjustments":[{"parameter":"trigger_sensitivity","from":"5","to":"3 L/min"}]}'
        }

    monkeypatch.setattr(scanner, "_safe_llm_call", fake_safe_llm_call)

    alerts = await scanner.scan("p1")

    assert len(alerts) == 1
    alert = alerts[0]
    assert "触发灵敏度从5调至3" in alert["extra"]["detail"]["suggestion"]
    assert alert["extra"]["detail"]["llm_analysis"]["analysis"] == "患者存在高驱动与双触发"
