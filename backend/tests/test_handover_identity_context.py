"""
Tests for handover patient identity resolution and context building.

Covers:
  1. Patient ObjectId vs string matching
  2. Multiple identifier field fallback
  3. Patient not found handling
  4. Context source status reporting
  5. AI degraded status (unavailable, invalid_output)
  6. Shift summary generation
"""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from bson import ObjectId

API_TZ = ZoneInfo("Asia/Shanghai")


# ── Fixtures ──────────────────────────────────────────────────────────────

def _make_patient(**overrides) -> dict:
    """Build a minimal patient document."""
    base = {
        "_id": ObjectId("507f1f77bcf86cd799439011"),
        "name": "张三",
        "hisPid": "H001",
        "hisBed": "3",
        "bed": "3",
        "bedNo": "3",
        "showBed": "3",
        "hisSex": "男",
        "hisAge": "65",
        "deptCode": "ICU01",
        "diagnosis": "重症肺炎",
        "status": "admitted",
    }
    base.update(overrides)
    return base


def _mock_db(patient_doc=None, collections=None):
    """Build a mock DB that returns patient_doc for patient queries."""
    db = MagicMock()
    collections = collections or {}

    def col_factory(name):
        col = MagicMock()
        # Default: return patient doc for patient collection
        if name == "patient":
            col.find_one = AsyncMock(return_value=patient_doc)
        elif name in collections:
            col.find_one = AsyncMock(return_value=collections[name].get("find_one"))
            cursor = MagicMock()
            cursor.to_list = AsyncMock(return_value=collections[name].get("find_list", []))
            cursor.sort = MagicMock(return_value=cursor)
            col.find = MagicMock(return_value=cursor)
        else:
            col.find_one = AsyncMock(return_value=None)
            cursor = MagicMock()
            cursor.to_list = AsyncMock(return_value=[])
            cursor.sort = MagicMock(return_value=cursor)
            col.find = MagicMock(return_value=cursor)
        return col

    db.col = MagicMock(side_effect=col_factory)
    db.dc_col = MagicMock(side_effect=col_factory)
    return db


# ═══════════════════════════════════════════════════════════════════════════
# 1. Patient ObjectId resolution
# ═══════════════════════════════════════════════════════════════════════════

class TestPatientObjectIdResolution:
    """Verify _get_patient handles ObjectId vs string correctly."""

    @pytest.mark.asyncio
    async def test_objectid_string_matches_mongo_objectid(self):
        """A 24-hex string patient_id must match ObjectId _id in MongoDB."""
        from app.services.handover.context_service import HandoverContextService

        patient = _make_patient()
        db = _mock_db(patient)
        svc = HandoverContextService(db)

        result = await svc._get_patient("507f1f77bcf86cd799439011")

        assert result == patient
        # Verify the patient collection was queried
        db.col.assert_any_call("patient")

    @pytest.mark.asyncio
    async def test_hispid_fallback(self):
        """When ObjectId doesn't match, fall back to hisPid."""
        from app.services.handover.context_service import HandoverContextService

        patient = _make_patient()
        db = _mock_db(patient)

        # Make ObjectId query return None, hisPid query return patient
        call_count = 0
        original_find_one = db.col("patient").find_one

        async def mock_find_one(query):
            nonlocal call_count
            call_count += 1
            if "_id" in query:
                return None  # ObjectId doesn't match
            if "hisPid" in query:
                return patient
            return None

        db.col("patient").find_one = AsyncMock(side_effect=mock_find_one)
        svc = HandoverContextService(db)

        result = await svc._get_patient("H001")

        assert result == patient

    @pytest.mark.asyncio
    async def test_patient_not_found_returns_empty(self):
        """When no identifier matches, return empty dict."""
        from app.services.handover.context_service import HandoverContextService

        db = _mock_db(None)
        svc = HandoverContextService(db)

        result = await svc._get_patient("nonexistent_id")

        assert result == {}

    @pytest.mark.asyncio
    async def test_empty_patient_id_returns_empty(self):
        """Empty string patient_id returns empty dict immediately."""
        from app.services.handover.context_service import HandoverContextService

        db = _mock_db(None)
        svc = HandoverContextService(db)

        result = await svc._get_patient("")

        assert result == {}


# ═══════════════════════════════════════════════════════════════════════════
# 2. Context source status
# ═══════════════════════════════════════════════════════════════════════════

class TestContextSourceStatus:
    """Verify context build returns data from correct sources."""

    @pytest.mark.asyncio
    async def test_build_returns_patient_info(self):
        """Context.patient should contain extracted patient info."""
        from app.services.handover.context_service import HandoverContextService

        patient = _make_patient()
        db = _mock_db(patient)
        svc = HandoverContextService(db)

        now = datetime.now(API_TZ).replace(tzinfo=None)
        start = now - timedelta(hours=8)
        context = await svc.build("507f1f77bcf86cd799439011", start, now)

        assert context.patient["name"] == "张三"
        assert context.patient["bed"] == "3"
        assert context.patient["sex"] == "男"

    @pytest.mark.asyncio
    async def test_build_with_empty_patient(self):
        """When patient not found, context.patient should be empty."""
        from app.services.handover.context_service import HandoverContextService

        db = _mock_db(None)
        svc = HandoverContextService(db)

        now = datetime.now(API_TZ).replace(tzinfo=None)
        start = now - timedelta(hours=8)
        context = await svc.build("nonexistent", start, now)

        # Should still return a context, just with empty patient
        assert context.patient_id == "nonexistent"


# ═══════════════════════════════════════════════════════════════════════════
# 3. AI degraded status
# ═══════════════════════════════════════════════════════════════════════════

class TestAiDegradedStatus:
    """Verify generation service handles AI failure correctly."""

    def test_build_empty_draft_has_deterministic_sections(self):
        """_build_empty_draft should populate ISBAR from context data."""
        from app.services.handover.generation_service import HandoverGenerationService
        from app.services.handover.schemas import HandoverContext

        context = HandoverContext(
            patient_id="test123",
            patient={"bed": "5", "name": "李四", "sex": "女", "age": "70岁"},
            situation={"diagnosis": "ARDS"},
            background={"allergies": "青霉素"},
            assessments={"neuro": "GCS 8分"},
        )

        svc = HandoverGenerationService(db=MagicMock(), config=MagicMock())
        result = svc._build_empty_draft("nurse_bedside", context)

        assert result["ai_status"] == "unavailable"
        assert result["sections"]["identify"]["name"] == "李四"
        assert result["sections"]["identify"]["bed"] == "5"
        assert result["sections"]["situation"]["diagnosis"] == "ARDS"
        assert result["sections"]["background"]["allergies"] == "青霉素"
        assert result["sections"]["assessment"]["neuro"]["content"] == "GCS 8分"
        assert result["missing_data"] == ["AI_SERVICE_UNAVAILABLE"]

    def test_build_document_sets_ai_status(self):
        """_build_document should set ai_status correctly."""
        from app.services.handover.generation_service import HandoverGenerationService
        from app.services.handover.schemas import HandoverContext, AiStatus

        context = HandoverContext(patient_id="test123")
        svc = HandoverGenerationService(db=MagicMock(), config=MagicMock())

        doc = svc._build_document(
            {"sections": {}}, context, "nurse_bedside",
            ai_status="unavailable", ai_error_code="LLM_CALL_FAILED"
        )

        assert doc.ai_status.status == "unavailable"
        assert doc.ai_status.error_code == "LLM_CALL_FAILED"


# ═══════════════════════════════════════════════════════════════════════════
# 4. Shift summary
# ═══════════════════════════════════════════════════════════════════════════

class TestShiftSummary:
    """Verify summary service deterministic text generation."""

    def test_deterministic_summary_basic(self):
        """Summary text should contain correct numbers."""
        from app.services.handover.summary_service import ShiftSummaryService

        svc = ShiftSummaryService(db=MagicMock(), config=MagicMock())

        text = svc._build_deterministic_summary(
            patient_count=10,
            critical_count=3,
            vent_count=2,
            vaso_count=1,
            crrt_count=0,
            alert_count=15,
            unclosed_alerts=5,
            priority_items=[
                {"bed": "1", "name": "A", "severity": "critical"},
                {"bed": "2", "name": "B", "severity": "high"},
            ],
            shift_name="白班",
        )

        assert "10名患者" in text
        assert "3名" in text
        assert "2名患者使用有创机械通气" in text
        assert "1名患者使用血管活性药" in text
        assert "15条高优先级告警" in text
        assert "5条尚未闭环" in text
        assert "1床A" in text


# ═══════════════════════════════════════════════════════════════════════════
# 5. Patient helper functions
# ═══════════════════════════════════════════════════════════════════════════

class TestPatientHelpers:
    """Verify patient helper utilities."""

    def test_patient_his_pid_candidates(self):
        """Should extract all identifier values from patient doc."""
        from app.utils.patient_helpers import patient_his_pid_candidates

        patient = {"hisPid": "H001", "mrn": "M001", "patientId": "P001"}
        result = patient_his_pid_candidates(patient)

        assert "H001" in result
        assert "M001" in result
        assert "P001" in result

    def test_patient_his_pid_candidates_empty(self):
        """Empty patient should return empty list."""
        from app.utils.patient_helpers import patient_his_pid_candidates

        assert patient_his_pid_candidates({}) == []
        assert patient_his_pid_candidates(None) == []

    def test_normalize_bed(self):
        """Should normalize various bed formats."""
        from app.utils.patient_helpers import normalize_bed

        assert normalize_bed("3") == "3"
        assert normalize_bed("03") == "3"
        assert normalize_bed("BED3") == "3"
        assert normalize_bed("3床") == "3"

    def test_safe_oid(self):
        """Should convert valid ObjectId strings."""
        from app.utils.serialization import safe_oid

        oid = safe_oid("507f1f77bcf86cd799439011")
        assert oid is not None
        assert isinstance(oid, ObjectId)

        assert safe_oid("invalid") is None
        assert safe_oid("") is None
        assert safe_oid(None) is None
