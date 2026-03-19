import unittest
from pathlib import Path

import yaml

from app.alert_engine.extended_scenario_engine import ExtendedScenarioMixin


class _DummyScenarioEngine(ExtendedScenarioMixin):
    def __init__(self):
        self.config = type("Cfg", (), {"yaml_cfg": {}})()


class ExtendedScenarioCatalogTest(unittest.TestCase):
    def test_catalog_expanded_beyond_seventy(self):
        cfg = yaml.safe_load(Path("backend/config.yaml").read_text(encoding="utf-8"))
        scenario_cfg = cfg.get("extended_scenarios", {}) or {}
        total = 0
        names: list[str] = []
        for _, items in scenario_cfg.items():
            if isinstance(items, list):
                total += len(items)
                names.extend(str(item).strip() for item in items if str(item).strip())

        self.assertGreaterEqual(total, 70)
        self.assertEqual(len(names), len(set(names)))

    def test_new_titles_are_exposed(self):
        engine = _DummyScenarioEngine()
        self.assertEqual(engine._scenario_title("septic_shock_escalation"), "脓毒性休克升级风险")
        self.assertEqual(engine._scenario_title("refractory_hypoxemia"), "难治性低氧血症风险")
        self.assertEqual(engine._scenario_title("dic_progression"), "DIC 进展风险")
        self.assertEqual(engine._scenario_title("crrt_filter_clotting"), "CRRT 滤器凝血风险")


if __name__ == "__main__":
    unittest.main()
