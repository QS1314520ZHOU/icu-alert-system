from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.waveform_service import WaveformService


class _FakeDb:
    def col(self, name: str):
        raise RuntimeError(name)


def test_waveform_quality_flags_repeated_signal_as_poor() -> None:
    service = WaveformService(db=_FakeDb(), config=None, alert_engine=None)
    now = datetime.now()
    series = [{"time": now - timedelta(minutes=idx), "value": 80.0} for idx in range(20)]
    qc = service.assess_quality(series, channel="param_HR")
    assert qc["band"] == "poor"
    assert qc["score"] < 0.55


def test_waveform_event_detector_identifies_desaturation_pattern() -> None:
    service = WaveformService(db=_FakeDb(), config=None, alert_engine=None)
    now = datetime.now()
    values = [98, 98, 97, 96, 92, 88]
    series = [{"time": now - timedelta(minutes=5 - idx), "value": value} for idx, value in enumerate(values)]
    events = service.detect_events(series, channel="param_spo2")
    assert any(event["type"] == "desaturation_pattern" for event in events)
