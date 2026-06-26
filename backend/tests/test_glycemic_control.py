import unittest

from app.alert_engine.glycemic_control import GlycemicControlMixin


class _DummyGlycemic(GlycemicControlMixin):
    pass


class GlycemicControlTest(unittest.TestCase):
    def test_cv_uses_sample_standard_deviation(self):
        mixin = _DummyGlycemic()
        cv = mixin._calc_cv_percent([6, 8, 10, 12])
        self.assertEqual(cv, 28.69)

    def test_unknown_glucose_unit_is_not_converted(self):
        mixin = _DummyGlycemic()
        value, confidence = mixin._glu_to_mmol_l(36, None)
        self.assertIsNone(value)
        self.assertEqual(confidence, "unknown")

    def test_explicit_glucose_units_convert_only_when_known(self):
        mixin = _DummyGlycemic()
        self.assertEqual(mixin._glu_to_mmol_l(180, "mg/dL"), (10.0, "known"))
        self.assertEqual(mixin._glu_to_mmol_l(2.7, "mmol/L"), (2.7, "known"))


if __name__ == "__main__":
    unittest.main()
