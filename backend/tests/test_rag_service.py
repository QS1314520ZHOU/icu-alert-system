import unittest
import json
import tempfile
from pathlib import Path
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

    def test_manifest_loader_accepts_legacy_list_documents(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            kb = Path(tmp_dir) / "kb"
            docs = kb / "docs"
            docs.mkdir(parents=True)
            (kb / "manifest.json").write_text(
                json.dumps(
                    {
                        "package_id": "test_kb",
                        "name": "Test KB",
                        "version": "1",
                        "documents": [
                            {
                                "doc_id": "legacy_doc",
                                "title": "Legacy Document",
                                "filename": "docs/legacy_doc.json",
                                "tags": ["aki"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            (docs / "legacy_doc.json").write_text(
                json.dumps(
                    [
                        {
                            "id": "legacy_section",
                            "title": "Legacy Section",
                            "recommendation": "Legacy Recommendation",
                            "text": "AKI CRRT legacy list document should be searchable.",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            cfg = SimpleNamespace(yaml_cfg={"ai_service": {"rag": {"enabled": True}}, "alert_engine": {"rag": {}}})
            service = RagService(cfg, knowledge_dir=str(kb))

            doc = service.get_document("legacy_doc")
            self.assertIsNotNone(doc)
            self.assertEqual(len(doc["chunks"]), 1)
            self.assertEqual(doc["chunks"][0]["chunk_id"], "legacy_section")


if __name__ == "__main__":
    unittest.main()
