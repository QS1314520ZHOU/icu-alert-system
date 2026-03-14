import unittest
from types import SimpleNamespace

from app.services.rag_service import RagService


class RagServiceSynonymTest(unittest.TestCase):
    def test_tokenize_expands_configured_synonyms(self):
        cfg = SimpleNamespace(
            yaml_cfg={
                "ai_service": {"rag": {"enabled": True}},
                "alert_engine": {"rag": {"synonyms": {"脓毒症": ["sepsis", "感染性休克"]}}},
            }
        )
        service = RagService(cfg, knowledge_dir="tests\\_missing_kb")
        tokens = service._tokenize("脓毒症")
        self.assertIn("脓毒症", tokens)
        self.assertIn("sepsis", tokens)
        self.assertIn("感染性休克", tokens)


if __name__ == "__main__":
    unittest.main()
