from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.alert_engine.features.mdro_features import MDRO_FEATURE_SCHEMA_VERSION, build_mdro_screening_features
from app.alert_engine.features.respiratory_features import RESPIRATORY_FEATURE_SCHEMA_VERSION, build_respiratory_forecast_features
from app.data_adapters.base import StandardizedObservation
from app.data_adapters.eicu_adapter import EicuClinicalDataAdapter


class FakeAdapter:
    data_source = "mongo"

    def __init__(self, now: datetime) -> None:
        self.now = now

    async def get_vitals_series(self, patient, concept, start, end=None):
        if concept != "spo2":
            return []
        return [
            StandardizedObservation(concept="spo2", value=96, unit="%", timestamp=self.now - timedelta(hours=3), source="bedside", match_method="code"),
            StandardizedObservation(concept="spo2", value=92, unit="%", timestamp=self.now - timedelta(hours=2), source="bedside", match_method="code"),
            StandardizedObservation(concept="spo2", value=90, unit="%", timestamp=self.now - timedelta(hours=1), source="bedside", match_method="code"),
            StandardizedObservation(concept="spo2", value=88, unit="%", timestamp=self.now, source="bedside", match_method="code"),
        ]

    async def get_devices(self, patient, concepts, start, end=None):
        return [
            StandardizedObservation(concept="fio2", value=0.4, unit="fraction", timestamp=self.now - timedelta(hours=3), source="deviceCap", match_method="code"),
            StandardizedObservation(concept="fio2", value=0.5, unit="fraction", timestamp=self.now - timedelta(hours=2), source="deviceCap", match_method="code"),
            StandardizedObservation(concept="fio2", value=0.6, unit="fraction", timestamp=self.now - timedelta(hours=1), source="deviceCap", match_method="code"),
            StandardizedObservation(concept="fio2", value=0.7, unit="fraction", timestamp=self.now, source="deviceCap", match_method="code"),
        ]


@pytest.mark.asyncio
async def test_respiratory_feature_builder_contract_and_version():
    now = datetime(2026, 1, 1, 8, 0, 0)
    result = await build_respiratory_forecast_features(FakeAdapter(now), {"_id": "p1"}, now=now, cfg={"min_points": 4})
    assert result["feature_schema_version"] == RESPIRATORY_FEATURE_SCHEMA_VERSION
    assert result["data_completeness"]["missing"] == []
    assert result["feature_vector"]["latest_sf_ratio"] == pytest.approx(125.7, abs=0.1)
    assert result["feature_vector"]["sf_drop"] > 100


def test_mdro_feature_builder_triggers_with_shared_schema():
    result = build_mdro_screening_features(
        patient={"clinicalDiagnosis": "sepsis"},
        susceptibility_reports=[{"result": "R", "organism": "Klebsiella"}],
        current_drugs=[{"name": "meropenem"}],
        prior_mdro_alert=None,
        cfg={"trigger_score_threshold": 3},
    )
    assert result["feature_schema_version"] == MDRO_FEATURE_SCHEMA_VERSION
    assert result["trigger"] is True
    assert result["data_completeness"]["completeness_ratio"] == 1


@pytest.mark.asyncio
async def test_eicu_adapter_placeholder_is_explicit():
    adapter = EicuClinicalDataAdapter()
    with pytest.raises(NotImplementedError) as exc:
        await adapter.get_vitals_series({}, "spo2", datetime(2026, 1, 1))
    assert "external validation" in str(exc.value)
