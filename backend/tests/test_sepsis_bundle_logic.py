from datetime import datetime

from app.alert_engine.syndrome_sepsis import SepsisMixin


class _Sepsis(SepsisMixin):
    config = type("Cfg", (), {"yaml_cfg": {"alert_engine": {"sepsis_bundle": {}}}})()

    def _get_patient_weight(self, patient_doc):
        return None


def test_bundle_completion_and_on_time_ratios_split_late_items():
    mixin = _Sepsis()
    elements = {
        "abx": {"status": "met", "completed_at": datetime.now()},
        "culture": {"status": "met_late", "completed_at": datetime.now()},
        "fluid": {"status": "pending"},
    }
    assert mixin._bundle_completion_ratio(elements) == 0.667
    assert mixin._bundle_on_time_ratio(elements) == 0.333
