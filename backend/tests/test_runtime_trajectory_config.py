from __future__ import annotations

from app.services.runtime_config_service import RuntimeConfigService


def test_runtime_trajectory_config_filters_alert_codes_to_default_codes() -> None:
    service = RuntimeConfigService(db=None)
    value = service.normalize_trajectory_forecast(
        {
            "default_codes": ["HR", "MAP"],
            "alert_codes": ["MAP", "SpO2"],
            "thresholds": [
                {"code": "MAP", "operator": "<", "threshold": 65, "probability": 0.7, "severity": "high", "horizon_hours": 4},
                {"code": "SpO2", "operator": "<", "threshold": 90, "probability": 0.7, "severity": "high", "horizon_hours": 4},
            ],
        }
    )

    assert value["default_codes"] == ["HR", "MAP"]
    assert value["alert_codes"] == ["MAP"]
    assert [row["code"] for row in value["thresholds"]] == ["MAP"]


def test_runtime_trajectory_config_clamps_probability_and_horizon() -> None:
    service = RuntimeConfigService(db=None)
    value = service.normalize_trajectory_forecast(
        {
            "default_codes": ["MAP"],
            "alert_codes": ["MAP"],
            "horizon_hours": 99,
            "thresholds": [{"code": "MAP", "operator": "bad", "threshold": 65, "probability": 5, "severity": "high", "horizon_hours": 99}],
        }
    )

    assert value["horizon_hours"] == 12
    assert value["thresholds"][0]["operator"] == "<"
    assert value["thresholds"][0]["probability"] == 0.99
    assert value["thresholds"][0]["horizon_hours"] == 12
