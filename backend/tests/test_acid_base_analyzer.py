import unittest

from app.alert_engine.acid_base_analyzer import interpret_acid_base


class AcidBaseAnalyzerTest(unittest.TestCase):
    def test_acute_respiratory_acidosis_detected(self):
        snapshot = {
            "fields": {
                "ph": {"value": 7.25},
                "paco2": {"value": 60, "unit": "mmHg"},
                "hco3": {"value": 26, "unit": "mmol/L"},
                "na": {"value": 140, "unit": "mmol/L"},
                "k": {"value": 4.0, "unit": "mmol/L"},
                "cl": {"value": 102, "unit": "mmol/L"},
                "albumin": {"value": 4.0, "unit": "g/dL"},
                "lactate": {"value": 1.2, "unit": "mmol/L"},
                "ica": {"value": 1.2, "unit": "mmol/L"},
                "mg": {"value": 0.9, "unit": "mmol/L"},
            }
        }
        result = interpret_acid_base(snapshot)
        self.assertIsNotNone(result)
        self.assertIn("呼吸性酸中毒(急性)", result["primary"])
        self.assertEqual(result["compensation"], "急性代偿")
        self.assertEqual(result["respiratory_compensation"]["expected_hco3"], 26.0)

    def test_chronic_respiratory_acidosis_detected(self):
        snapshot = {
            "fields": {
                "ph": {"value": 7.33},
                "paco2": {"value": 60, "unit": "mmHg"},
                "hco3": {"value": 31, "unit": "mmol/L"},
                "na": {"value": 140, "unit": "mmol/L"},
                "k": {"value": 4.0, "unit": "mmol/L"},
                "cl": {"value": 101, "unit": "mmol/L"},
                "albumin": {"value": 4.0, "unit": "g/dL"},
                "lactate": {"value": 1.0, "unit": "mmol/L"},
            }
        }
        result = interpret_acid_base(snapshot)
        self.assertIsNotNone(result)
        self.assertIn("呼吸性酸中毒(慢性)", result["primary"])
        self.assertEqual(result["respiratory_compensation"]["expected_hco3"], 31.0)

    def test_stewart_sid_summary_present(self):
        snapshot = {
            "fields": {
                "ph": {"value": 7.28},
                "paco2": {"value": 30, "unit": "mmHg"},
                "hco3": {"value": 14, "unit": "mmol/L"},
                "na": {"value": 138, "unit": "mmol/L"},
                "k": {"value": 3.8, "unit": "mmol/L"},
                "cl": {"value": 115, "unit": "mmol/L"},
                "albumin": {"value": 4.0, "unit": "g/dL"},
                "lactate": {"value": 4.0, "unit": "mmol/L"},
                "ica": {"value": 1.0, "unit": "mmol/L"},
                "mg": {"value": 0.8, "unit": "mmol/L"},
            }
        }
        result = interpret_acid_base(snapshot)
        self.assertIsNotNone(result)
        self.assertLess(result["SID"], 38)
        self.assertIn("SID降低", result["stewart_summary"])


if __name__ == "__main__":
    unittest.main()
