import asyncio
import unittest

from app.services.clinical_knowledge_graph import ClinicalKnowledgeGraph


class _FakeAlertEngine:
    def _drug_text(self, doc):
        return " ".join(str(doc.get(k) or "") for k in ("drugName", "orderName", "route"))

    def _infer_rag_tags(self, patient_doc, facts):
        return ["sepsis", "aki"]


class _FakeRag:
    def search(self, query, *, top_k=5, tags=None):
        return [
            {
                "chunk_id": "kg-1",
                "source": "Surviving Sepsis",
                "recommendation": f"{query} 相关推荐",
                "recommendation_grade": "strong",
                "topic": "sepsis",
                "content": "建议结合灌注、乳酸与感染控制做动态评估。",
                "score": 0.88,
            }
        ][:top_k]


class _FakeDB:
    class _Col:
        async def find_one(self, *args, **kwargs):
            return None

        async def insert_one(self, *args, **kwargs):
            return None

    def col(self, _name):
        return self._Col()


class _TestGraph(ClinicalKnowledgeGraph):
    async def _load_recent_cached_result(self, patient_id: str, finding_key: str):
        return None

    async def _persist_result(self, patient_id: str, finding_key: str, abnormal_finding: str, result: dict):
        return None

    async def _patient_context(self, patient_id: str):
        return self._context


class ClinicalKnowledgeGraphTest(unittest.TestCase):
    def setUp(self):
        self.service = _TestGraph(
            db=_FakeDB(),
            config=type("Cfg", (), {"yaml_cfg": {"ai_service": {"knowledge_graph": {"persist_window_minutes": 60}}}})(),
            alert_engine=_FakeAlertEngine(),
            rag_service=_FakeRag(),
        )
        self.service._context = {
            "patient": {"name": "测试患者", "clinicalDiagnosis": "脓毒症休克", "hisBed": "01", "dept": "ICU"},
            "facts": {"labs": {}, "vitals": {}},
            "labs": {"lac": {"value": 4.8}, "cr": {"value": 210}, "ddimer": {"value": 3.4}, "inr": {"value": 1.8}, "plt": {"value": 68}},
            "vitals": {"map": 58, "sbp": 82, "hr": 122, "rr": 30, "spo2": 89},
            "recent_alerts": [{"alert_type": "septic_shock", "name": "脓毒性休克"}, {"alert_type": "aki", "name": "AKI"}],
            "drugs": [{"drugName": "去甲肾上腺素"}, {"drugName": "肝素"}, {"drugName": "万古霉素"}],
            "plt_series": [{"value": 160}, {"value": 70}],
            "hb_series": [{"value": 120}, {"value": 88}],
            "cr_series": [{"value": 98}, {"value": 210}],
            "tbil_series": [{"value": 18}, {"value": 52}],
        }

    def test_findings_are_normalized(self):
        self.assertEqual(self.service._normalize_finding("乳酸升高"), "lactate_rise")
        self.assertEqual(self.service._normalize_finding("肌酐升高"), "creatinine_rise")
        self.assertEqual(self.service._normalize_finding("胆红素升高"), "bilirubin_rise")

    def test_lactate_analysis_prefers_septic_shock_path(self):
        result = asyncio.run(self.service.causal_chain_analysis("p1", "乳酸升高"))
        self.assertEqual(result["finding_key"], "lactate_rise")
        self.assertTrue(result["candidate_causes"])
        top = result["candidate_causes"][0]
        self.assertEqual(top["cause_key"], "septic_shock")
        self.assertIn("脓毒症相关信号", top["matched_evidence"])
        self.assertTrue(result["guideline_evidence"])

    def test_platelet_analysis_contains_hit_and_dic(self):
        result = asyncio.run(self.service.causal_chain_analysis("p1", "血小板下降"))
        keys = [item["cause_key"] for item in result["candidate_causes"]]
        self.assertIn("dic", keys)
        self.assertIn("hit", keys)
        self.assertTrue(result["evidence_profile"])


if __name__ == "__main__":
    unittest.main()
