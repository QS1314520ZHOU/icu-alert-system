import unittest

from app.alert_engine.glycemic_control import GlycemicControlMixin


class _DummyGlycemic(GlycemicControlMixin):
    pass


class GlycemicControlTest(unittest.TestCase):
    def test_cv_uses_sample_standard_deviation(self):
        mixin = _DummyGlycemic()
        cv = mixin._calc_cv_percent([6, 8, 10, 12])
        self.assertEqual(cv, 28.69)


if __name__ == "__main__":
    unittest.main()
