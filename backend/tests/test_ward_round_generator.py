from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
from bson import ObjectId

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.ward_round_generator import WardRoundGenerator


class FakeInsertResult:
    def __init__(self, inserted_id):
        self.inserted_id = inserted_id


class FakeCollection:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.inserted = []

    async def find_one(self, query, *args, **kwargs):
        return self.rows[0] if self.rows else None

    async def insert_one(self, doc):
        self.inserted.append(doc)
        return FakeInsertResult(ObjectId())


class FakeDb:
    def __init__(self):
        self.patient_id = ObjectId()
        self.score = FakeCollection()
        self.patient = FakeCollection([
            {
                "_id": self.patient_id,
                "name": "张三",
                "hisBed": "ICU-01",
                "dept": "ICU",
                "clinicalDiagnosis": "脓毒症",
            }
        ])

    def col(self, name):
        if name == "score":
            return self.score
        if name == "patient":
            return self.patient
        return FakeCollection()


class FakeConfig:
    yaml_cfg = {}


class FakeDocGen:
    async def extract_structured_data(self, patient_id, required_fields, time_range):
        return {
            "patient": {"id": patient_id, "name": "张三", "bed": "ICU-01", "dept": "ICU", "diagnosis": "脓毒症"},
            "latest_vitals": {"hr": 88, "spo2": 96, "rr": 20, "temp": 37.2, "sbp": 120, "dbp": 70},
            "labs_24h": [{"itemCnName": "乳酸", "result": "1.7", "unit": "mmol/L"}],
            "drugs_24h": [{"drugName": "去甲肾上腺素", "dose": "0.05", "route": "泵入"}],
            "alerts_24h": [{"name": "感染风险", "severity": "high", "value": "2"}],
            "respiratory": {"mode": "SIMV", "fio2": 0.4, "peep": 5},
            "devices": [{"name": "气管插管", "days": 3}],
            "recent_scores": [{"score_type": "GCS", "score": 15}],
            "clinical_reasoning": {"problem_list": ["感染控制"]},
            "trend_24h": {"summary": "乳酸下降"},
        }


def make_generator(db=None):
    return WardRoundGenerator(
        db=db or FakeDb(),
        config=FakeConfig(),
        alert_engine=object(),
        document_generator=FakeDocGen(),
    )


def test_audit_numbers_allows_structured_values_and_round_time():
    gen = make_generator()
    sd = {
        "latest_vitals": {"hr": 88, "spo2": 96},
        "labs_24h": [{"result": "1.7"}],
        "drugs_24h": [{"dose": "0.05"}],
        "alerts_24h": [{"value": "2"}],
        "recent_scores": [{"score": 15}],
    }

    audit = gen._audit_numbers("2026-06-18 09:30 查房：心率88次/分，SpO2 96%，乳酸1.7mmol/L。", sd, "2026-06-18 09:30")

    assert audit["status"] == "ok"
    assert audit["hallucinated_numbers"] == []


def test_audit_numbers_blocks_unstructured_values():
    gen = make_generator()
    sd = {"latest_vitals": {"hr": 88}, "labs_24h": [], "drugs_24h": [], "alerts_24h": [], "recent_scores": []}

    audit = gen._audit_numbers("2026-06-18 09:30 查房：心率88次/分，血压110/70mmHg。", sd, "2026-06-18 09:30")

    assert audit["status"] == "blocked"
    assert audit["hallucinated_numbers"] == ["110", "70"]


@pytest.mark.asyncio
async def test_generate_falls_back_when_llm_hallucinates_number(monkeypatch):
    async def fake_call_llm_chat(**kwargs):
        round_time = re.search(r"查房时间：(.+)", kwargs["user_prompt"]).group(1).strip()
        return {
            "model": "fake-medical",
            "text": json.dumps({
                "document_text": f"{round_time} 主治医师查房：心率88次/分，血压110/70mmHg。查房后指示：继续治疗。李医生",
                "key_facts_used": ["心率 88次/分"],
            }, ensure_ascii=False),
        }

    monkeypatch.setattr("app.services.ward_round_generator.call_llm_chat", fake_call_llm_chat)
    db = FakeDb()
    record = await make_generator(db).generate(str(db.patient_id), doctor="李医生")

    assert record is not None
    assert record["document"]["degraded"] is True
    assert record["document"]["number_audit"]["status"] == "blocked"
    assert "结构化数据模板生成的草稿" in record["document"]["document_text"]
    assert db.score.inserted[0]["document"]["degraded"] is True


@pytest.mark.asyncio
async def test_generate_persists_llm_text_when_number_audit_passes(monkeypatch):
    async def fake_call_llm_chat(**kwargs):
        round_time = re.search(r"查房时间：(.+)", kwargs["user_prompt"]).group(1).strip()
        return {
            "model": "fake-medical",
            "text": json.dumps({
                "document_text": f"{round_time} 主治医师查房：心率88次/分，SpO2 96%，乳酸1.7mmol/L。查房后指示：继续抗感染治疗。李医生 主治医师",
                "key_facts_used": ["心率 88次/分", "SpO2 96%", "乳酸 1.7mmol/L"],
            }, ensure_ascii=False),
        }

    monkeypatch.setattr("app.services.ward_round_generator.call_llm_chat", fake_call_llm_chat)
    db = FakeDb()
    record = await make_generator(db).generate(str(db.patient_id), doctor="李医生")

    assert record is not None
    assert record["doc_type"] == "ward_round"
    assert record["document"]["degraded"] is False
    assert record["document"]["number_audit"]["status"] == "ok"
    assert record["document"]["key_facts_used"] == ["心率 88次/分", "SpO2 96%", "乳酸 1.7mmol/L"]
