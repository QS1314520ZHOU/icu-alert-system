from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.alert_engine.scanner_bleeding import BleedingScanner
from app.alert_engine.scanner_dic import DicScanner
from app.alert_engine.scanner_hai_bundle import HaiBundleScanner
from app.alert_engine.scanner_liberation_bundle import LiberationBundleScanner
from app.alert_engine.scanner_tbi import TbiScanner
from app.alert_engine.scanner_vte_prophylaxis import VteProphylaxisScanner


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
        rows = list(self.docs)
        if projection:
            projected = []
            for doc in rows:
                item = {}
                for key, enabled in projection.items():
                    if enabled and key in doc:
                        item[key] = doc[key]
                if "_id" in doc:
                    item["_id"] = doc["_id"]
                projected.append(item)
            rows = projected
        return _Cursor(rows)


class _FakeDb:
    def __init__(self, collections: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self._collections = {name: _Collection(rows) for name, rows in (collections or {}).items()}

    def col(self, name: str) -> _Collection:
        return self._collections.setdefault(name, _Collection())


class _BaseEngine:
    def __init__(self) -> None:
        self.config = SimpleNamespace(yaml_cfg={"alert_engine": {"suppression": {"same_rule_same_patient_seconds": 1800, "max_alerts_per_patient_per_hour": 10}}})
        self.db = _FakeDb({"patient": [{"_id": "p1", "name": "张三", "hisPid": "H1", "clinicalDiagnosis": "脓毒症 肺炎", "admissionDiagnosis": "感染", "icuAdmissionTime": datetime.now() - timedelta(days=3)}]})
        self.created_alerts: list[dict[str, Any]] = []

    def _active_patient_query(self) -> dict[str, Any]:
        return {}

    async def _is_suppressed(self, patient_id: str, rule_id: str | None, same_rule_seconds: int, max_per_hour: int) -> bool:
        del patient_id, rule_id, same_rule_seconds, max_per_hour
        return False

    async def _create_alert(self, **kwargs: Any) -> dict[str, Any]:
        self.created_alerts.append(kwargs)
        return kwargs

    def _log_info(self, name: str, count: int) -> None:
        del name, count


class _DicEngine(_BaseEngine):
    async def _calc_dic_score(self, his_pid) -> dict[str, Any] | None:
        del his_pid
        return {"score": 5, "time": datetime.now(), "plt": 42, "inr": 1.9, "ddimer": 5.8}


class _BleedingEngine(_BaseEngine):
    async def _get_hb_drop(self, his_pid, hours: int = 24) -> dict[str, Any] | None:
        del his_pid, hours
        return {"drop": 28, "current": 58, "time": datetime.now()}

    async def _get_latest_vitals_by_patient(self, patient_id) -> dict[str, Any]:
        del patient_id
        return {"hr": 122, "sbp": 84}


class _TbiEngine(_BaseEngine):
    def _get_cfg_list(self, path: tuple[str, ...], default: list[str]) -> list[str]:
        del path
        return default

    async def _get_device_id_for_patient(self, patient_doc: dict[str, Any], device_types: list[str] | None = None) -> str | None:
        del patient_doc, device_types
        return "mon-1"

    async def _get_latest_device_cap(self, device_id: str) -> dict[str, Any]:
        del device_id
        return {"params": {"param_ICP": 27, "param_CPP": 54}, "time": datetime.now()}

    async def _get_gcs_drop(self, pid) -> dict[str, Any] | None:
        del pid
        return {"drop": 3, "current": 8, "time": datetime.now()}

    async def _get_pupil_status(self, pid) -> dict[str, Any] | None:
        del pid
        return {"abnormal": True, "time": datetime.now()}


class _LiberationEngine(_BaseEngine):
    async def get_liberation_bundle_status(self, patient_doc: dict[str, Any]) -> dict[str, Any]:
        del patient_doc
        return {"lights": {"A": "green", "B": "red", "C": "yellow", "D": "green", "E": "red", "F": "green"}, "compliance": 0.5, "updated_at": datetime.now()}


class _HaiEngine(_BaseEngine):
    def _cfg(self, *path: str, default: Any = None) -> Any:
        if path == ("alert_engine", "suppression"):
            return self.config.yaml_cfg["alert_engine"]["suppression"]
        return default

    def _hai_cfg(self) -> dict:
        return {}

    async def _hai_insert_time(self, pid, keywords: list[str], hours: int = 24 * 30):
        del pid, keywords, hours
        return datetime.now() - timedelta(days=8)

    async def _latest_temp_value(self, pid):
        del pid
        return 38.6

    async def _latest_positive_culture(self, his_pid: str | None, keywords: list[str], hours: int = 72) -> dict | None:
        del his_pid, keywords, hours
        return {"time": datetime.now() - timedelta(hours=8), "name": "血培养阳性"}

    async def _has_abnormal_urine(self, his_pid: str | None, hours: int = 72) -> bool:
        del his_pid, hours
        return True

    async def _ventilation_start_time(self, patient_doc: dict[str, Any]):
        del patient_doc
        return datetime.now() - timedelta(days=3)

    async def _has_recent_bedside_keyword(self, pid, keywords: list[str], hours: int = 24) -> bool:
        del pid, hours
        return "口腔护理" not in keywords


class _VteEngine(_BaseEngine):
    def __init__(self) -> None:
        super().__init__()
        self.config.yaml_cfg["alert_engine"]["vte_prophylaxis"] = {}

    def _get_cfg_list(self, path: tuple[str, ...], default: list[str]) -> list[str]:
        del path
        return default

    def _parse_age_years(self, patient_doc: dict[str, Any]) -> float | None:
        return 76.0

    def _parse_bmi(self, patient_doc: dict[str, Any]) -> float | None:
        return 31.2

    def _text_join(self, patient_doc: dict[str, Any], keys: list[str]) -> str:
        return " ".join(str(patient_doc.get(key) or "") for key in keys)

    async def _immobility_hours(self, patient_doc: dict[str, Any], pid, now: datetime) -> float:
        del patient_doc, pid, now
        return 96.0

    def _has_recent_surgery(self, patient_doc: dict[str, Any], now: datetime, days: int = 30) -> bool:
        del patient_doc, now, days
        return True

    async def _get_recent_drug_docs(self, pid_str: str, since_proph: datetime) -> list[dict[str, Any]]:
        del pid_str, since_proph
        return []

    def _has_drug_prophylaxis(self, drug_docs: list[dict[str, Any]]) -> bool:
        del drug_docs
        return False

    async def _has_mechanical_prophylaxis(self, pid_str: str, since_proph: datetime) -> bool:
        del pid_str, since_proph
        return False

    def _has_hormonal_tx(self, drug_docs: list[dict[str, Any]]) -> bool:
        del drug_docs
        return False

    def _contains_any(self, text: str, keywords: list[str]) -> bool:
        lowered = text.lower()
        return any(keyword.lower() in lowered for keyword in keywords)

    async def _has_active_bleeding_alert(self, pid_str: str, lookback_hours: int = 72) -> bool:
        del pid_str, lookback_hours
        return False

    async def _get_latest_labs_map(self, his_pid: str, lookback_hours: int = 72) -> dict[str, Any]:
        del his_pid, lookback_hours
        return {"plt": {"value": 135}, "inr": {"value": 1.1}}


@pytest.mark.asyncio
async def test_dic_scanner_emits_overt_alert() -> None:
    engine = _DicEngine()
    await DicScanner(engine).scan()
    assert any(alert["alert_type"] == "dic" and alert["rule_id"] == "DIC_OVERT" for alert in engine.created_alerts)


@pytest.mark.asyncio
async def test_bleeding_scanner_emits_critical_gi_bleed_alert() -> None:
    engine = _BleedingEngine()
    await BleedingScanner(engine).scan()
    assert any(alert["alert_type"] == "gi_bleeding" and alert["severity"] == "critical" for alert in engine.created_alerts)


@pytest.mark.asyncio
async def test_tbi_scanner_emits_icp_cpp_and_neuro_decline_alerts() -> None:
    engine = _TbiEngine()
    await TbiScanner(engine).scan()
    alert_types = {alert["alert_type"] for alert in engine.created_alerts}
    assert {"icp", "cpp", "gcs_drop", "pupil"} <= alert_types


@pytest.mark.asyncio
async def test_liberation_bundle_scanner_emits_overdue_alert() -> None:
    engine = _LiberationEngine()
    await LiberationBundleScanner(engine).scan()
    assert any(alert["alert_type"] == "liberation_bundle" for alert in engine.created_alerts)


@pytest.mark.asyncio
async def test_hai_bundle_scanner_emits_multiple_bundle_alerts() -> None:
    engine = _HaiEngine()
    await HaiBundleScanner(engine).scan()
    alert_types = {alert["alert_type"] for alert in engine.created_alerts}
    assert {"clabsi_bundle_review", "clabsi_suspected", "cauti_risk", "vap_bundle_missing"} <= alert_types


@pytest.mark.asyncio
async def test_vte_scanner_emits_omission_alerts_for_high_risk_immobile_patient() -> None:
    engine = _VteEngine()
    await VteProphylaxisScanner(engine).scan()
    alert_types = {alert["alert_type"] for alert in engine.created_alerts}
    assert "vte_prophylaxis_omission" in alert_types
    assert "vte_immobility_no_prophylaxis" in alert_types

