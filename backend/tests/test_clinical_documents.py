from __future__ import annotations

import sys
from pathlib import Path
import pytest
import io
from docx import Document

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.clinical_documents.schemas import (
    ProgressNoteContext,
    LabDelta,
    DrugEvent,
    AlertItem,
    Ventilator,
    Scores,
    Basics,
    Vitals,
    VitalStat,
)
from app.clinical_documents.document_generator import ProgressNoteGenerator
from app.clinical_documents.exporter import export_progress_note_docx


def test_collect_valid_ids() -> None:
    dummy_stat = VitalStat(min=60, max=100, trend="平稳")
    ctx = ProgressNoteContext(
        patient_id="123",
        window_start="2026-05-19 09:00",
        window_end="2026-05-20 09:00",
        basics=Basics(name="张三", bed="01", age=65, sex="男", day=3, diagnosis="肺部感染"),
        v=Vitals(hr=dummy_stat, map=dummy_stat, spo2=dummy_stat, temp=dummy_stat, rr=dummy_stat, events=[]),
        labs=[
            LabDelta(id=1, name="乳酸", prev=2.1, curr=3.5, unit="mmol/L", flag="↑")
        ],
        drugs=[
            DrugEvent(id=2, name="去甲肾上腺素", action="升级量", dose_after="0.2 ug/kg/min", time_hm="12:10")
        ],
        alerts=[
            AlertItem(id=3, type="氧饱和度过低", severity="critical", count=2, active=True)
        ],
        vent=Ventilator(
            mode="PRVC",
            fio2=45.0,
            peep=6.0,
            vt=420,
            pplat=22.0,
            pf_ratio=180.0,
            changes=[]
        ),
        scores=Scores(
            gcs=12,
            sofa=6,
            apache=18
        )
    )
    
    gen = ProgressNoteGenerator(None)
    valid_ids = gen._collect_valid_ids(ctx)
    
    assert "V" in valid_ids
    assert "VT0" in valid_ids
    assert "L1" in valid_ids
    assert "D2" in valid_ids
    assert "A3" in valid_ids
    assert "AS1" in valid_ids
    
    assert valid_ids["L1"] == "lab:乳酸"
    assert valid_ids["D2"] == "drug:去甲肾上腺素"
    assert valid_ids["A3"] == "alert:氧饱和度过低"
    assert valid_ids["AS1"] == "scores"


def test_verify_citations() -> None:
    dummy_stat = VitalStat(min=60, max=100, trend="平稳")
    ctx = ProgressNoteContext(
        patient_id="123",
        window_start="2026-05-19 09:00",
        window_end="2026-05-20 09:00",
        basics=Basics(name="张三", bed="01", age=65, sex="男", day=3, diagnosis="肺部感染"),
        v=Vitals(hr=dummy_stat, map=dummy_stat, spo2=dummy_stat, temp=dummy_stat, rr=dummy_stat, events=[]),
        labs=[
            LabDelta(id=1, name="乳酸", prev=2.1, curr=3.5, unit="mmol/L", flag="↑")
        ],
        drugs=[],
        alerts=[],
        vent=None,
        scores=None
    )
    
    gen = ProgressNoteGenerator(None)
    
    draft = {
        "subjective": "患者意识清，无明显胸闷 [V]。",
        "objective": {
            "vitals": "心率 80 次/分 [V]。",
            "labs": "乳酸 3.5 mmol/L [L1]，肌酐未查 [L99]。",
            "drugs": "未提供药物治疗。"
        },
        "assessment": {
            "循环": "循环稳定 [V]。"
        },
        "plan": [
            "继续观察。"
        ],
        "overall_trend": "平稳",
        "key_concerns": ["乳酸升高"]
    }
    
    citations, warnings = gen._verify_citations(draft, ctx)
    
    citation_refs = [c["ref"] for c in citations]
    assert "V" in citation_refs
    assert "L1" in citation_refs
    
    assert len(warnings) == 1
    assert "L99" in warnings[0]


def test_export_progress_note_docx() -> None:
    draft = {
        "patient_id": "P001",
        "status": "finalized",
        "finalized_by": "张医生",
        "finalized_at": "2026-05-20T10:00:00",
        "current_content": {
            "subjective": "患者神志清醒，呼吸平顺",
            "objective": {
                "vitals": "HR 75bpm, MAP 80mmHg",
                "labs": "乳酸 1.2mmol/L"
            },
            "assessment": {
                "呼吸系统": "平稳"
            },
            "plan": [
                "计划今日拔管"
            ],
            "overall_trend": "好转",
            "key_concerns": ["准备拔管"]
        },
        "context_snapshot": {
            "patient_name": "王小明",
            "basics": {
                "bed": "02",
                "age": 45,
                "sex": "男",
                "day": 5,
                "diagnosis": "重症肺炎"
            }
        }
    }
    
    file_bytes = export_progress_note_docx(draft)
    assert len(file_bytes) > 0
    
    # Verify that the generated file can be successfully parsed by python-docx
    doc = Document(io.BytesIO(file_bytes))
    paragraphs_text = [p.text for p in doc.paragraphs]
    
    assert any("ICU 24小时病程记录" in text for text in paragraphs_text)
    assert any("主要诊断：重症肺炎" in text for text in paragraphs_text)
    assert any("王小明" in cell.text for table in doc.tables for row in table.rows for cell in row.cells)


@pytest.mark.asyncio
async def test_export_router_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.routers.clinical_documents import export_draft, ExportRequest
    
    class FakeCollection:
        async def find_one(self, query):
            assert query == {"_id": "draft_123"}
            return {
                "patient_id": "P001",
                "status": "draft",
                "current_content": {
                    "subjective": "测试",
                    "objective": {},
                    "assessment": {},
                    "plan": [],
                    "overall_trend": "平稳",
                    "key_concerns": []
                },
                "context_snapshot": {}
            }
            
    class FakeDb:
        def col(self, name):
            assert name == "clinical_document_drafts"
            return FakeCollection()
            
    req = ExportRequest(format="docx")
    response = await export_draft("draft_123", req, FakeDb())
    
    assert response.media_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert "Content-Disposition" in response.headers
    assert "ProgressNote_P001" in response.headers["Content-Disposition"]


@pytest.mark.asyncio
async def test_get_draft_returns_current_content_as_draft() -> None:
    from app.routers.clinical_documents import get_draft

    content = {
        "subjective": "test",
        "objective": {},
        "assessment": {},
        "plan": [],
        "overall_trend": "平稳",
        "key_concerns": [],
    }

    class FakeCollection:
        async def find_one(self, query):
            assert query == {"_id": "draft_123"}
            return {"_id": "draft_123", "current_content": content, "status": "draft"}

    class FakeDb:
        def col(self, name):
            assert name == "clinical_document_drafts"
            return FakeCollection()

    result = await get_draft("draft_123", FakeDb())

    assert result["draft_id"] == "draft_123"
    assert result["draft"] == content


@pytest.mark.asyncio
async def test_context_builder_queries() -> None:
    from datetime import datetime
    from app.clinical_documents.context_builder import ProgressNoteContextBuilder

    class FakeCursor:
        def __init__(self, items):
            self.items = items
            self.index = 0
        def sort(self, *args, **kwargs):
            return self
        async def to_list(self, length):
            return self.items
        def __aiter__(self):
            return self
        async def __anext__(self):
            if self.index < len(self.items):
                item = self.items[self.index]
                self.index += 1
                return item
            else:
                raise StopAsyncIteration

    class FakeCollection:
        def __init__(self, data=None):
            self.data = data or []
        async def find_one(self, query, sort=None):
            for item in self.data:
                # support $or logic mapping
                if "$or" in query:
                    for clause in query["$or"]:
                        for k, v in clause.items():
                            if isinstance(v, dict) and "$in" in v:
                                if item.get(k) in v["$in"]:
                                    return item
                            elif item.get(k) == v:
                                return item
                # support $and logic mapping
                elif "$and" in query:
                    matched = True
                    for clause in query["$and"]:
                        for k, v in clause.items():
                            if k == "$or":
                                clause_matched = False
                                for or_clause in v:
                                    for ok, ov in or_clause.items():
                                        if isinstance(ov, dict) and "$in" in ov:
                                            if item.get(ok) in ov["$in"]:
                                                clause_matched = True
                                        elif item.get(ok) == ov:
                                            clause_matched = True
                                if not clause_matched:
                                    matched = False
                            elif isinstance(v, dict) and "$in" in v:
                                if item.get(k) not in v["$in"]:
                                    matched = False
                            elif item.get(k) != v:
                                matched = False
                    if matched:
                        return item
                else:
                    for k, v in query.items():
                        if isinstance(v, dict) and "$in" in v:
                            if item.get(k) in v["$in"]:
                                return item
                        elif item.get(k) == v:
                            return item
            return self.data[0] if self.data else None
        def find(self, query):
            return FakeCursor(self.data)
        async def aggregate(self, pipeline):
            return FakeCursor([])

    class FakeDb:
        def __init__(self):
            self.collections = {
                "patient": FakeCollection([{
                    "_id": "P001",
                    "hisPid": "HIS999",
                    "bedNo": "05",
                    "age": 55,
                    "sex": "男",
                    "diagnosis": "重度中暑",
                    "admissionTime": datetime.now()
                }]),
                "bGATemp": FakeCollection([{
                    "mrn": "HIS999",
                    "inputTime": datetime.now(),
                    "param_HR": 85,
                    "param_nibp_m": 90,
                    "param_spo2": 98,
                    "param_T": 37.2,
                    "param_resp": 18,
                }]),
                "drugExe": FakeCollection([{
                    "pid": "P001",
                    "drugName": "去甲肾上腺素",
                    "executeTime": datetime.now(),
                    "dose": 0.1,
                    "doseUnit": "ug/kg/min"
                }]),
                "score": FakeCollection([{
                    "patient_id": "P001",
                    "score_type": "GCS",
                    "score": 15,
                    "calc_time": datetime.now()
                }]),
                "alert_records": FakeCollection([]),
                "VI_ICU_EXAM_ITEM": FakeCollection([{
                    "hisPid": "HIS999",
                    "itemName": "乳酸",
                    "result": "2.5",
                    "refHigh": 2.0,
                    "refLow": 0.5,
                    "authTime": datetime.now()
                }]),
                "VI_ICU_ZYYZ": FakeCollection([])
            }
        def col(self, name):
            return self.collections.get(name, FakeCollection())
        def dc_col(self, name):
            return self.collections.get(name, FakeCollection())

    builder = ProgressNoteContextBuilder(FakeDb())
    ctx = await builder.build("P001", hours=24)
    
    assert ctx.basics.bed == "05"
    assert ctx.basics.age == 55
    assert ctx.basics.sex == "男"
    assert ctx.basics.diagnosis == "重度中暑"
    
    assert len(ctx.labs) == 1
    assert ctx.labs[0].name == "乳酸"
    assert ctx.labs[0].curr == 2.5
    
    assert len(ctx.drugs) == 1
    assert ctx.drugs[0].name == "去甲肾上腺素"
    
    assert ctx.scores is not None
    assert ctx.scores.gcs == 15
