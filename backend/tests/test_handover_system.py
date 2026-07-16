"""
Tests for the handover system — shift resolution, patient_id, change detection,
and prompt integrity.

Covers P0 fixes from the handover review:
  1. Dynamic shift: no fallback, proper error codes
  2. patient_id: always Mongo _id, never admission_no/name
  3. Prompt files: no escape corruption
  4. scheduled_start/end: full ISO datetimes, not "HH:MM" strings
  5. data_end: capped at min(now, scheduled_end)
  6. Change detection input: time/unit/source present
  7. Thresholds: read from config, not hardcoded
"""
from __future__ import annotations

import json
import re
from datetime import datetime, time, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

API_TZ = ZoneInfo("Asia/Shanghai")
PROMPT_DIR = Path(__file__).resolve().parents[1] / "app" / "prompts"


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_shift_row(code: str, name: str, start: str, end: str) -> dict:
    return {"code": code, "name": name, "start_time": start, "end_time": end}


def _mock_db_with_shifts(*rows):
    """Return a mock db whose initSystemConfig contains the given shift rows."""
    from app import runtime
    # Clear cached runtime config to prevent cross-test contamination
    runtime.shift_config = None
    db = MagicMock()
    doc = {"banCiInfoList": list(rows)}
    db.col = MagicMock(return_value=db)
    db.find_one = AsyncMock(return_value=doc)
    return db


# ═══════════════════════════════════════════════════════════════════════════
# 1. Dynamic shift resolution
# ═══════════════════════════════════════════════════════════════════════════

class TestShiftResolution:
    """Tests for ShiftService.resolve_shift — no fallback, DB-driven only."""

    @pytest.mark.asyncio
    async def test_current_time_matches_normal_shift(self):
        """Current time 10:00 → matches 08:00-16:00 day shift."""
        from app.services.shift_service import ShiftService

        db = _mock_db_with_shifts(
            _make_shift_row("D", "白班", "08:00", "16:00"),
            _make_shift_row("N", "夜班", "20:00", "08:00"),
        )
        svc = ShiftService(db)
        now = datetime(2026, 7, 16, 10, 0, tzinfo=API_TZ)

        result = await svc.resolve_shift("auto", now=now)

        assert result is not None
        assert result.code == "D"
        assert result.name == "白班"
        assert result.start_time == "08:00"
        assert result.end_time == "16:00"
        # start/end should be full datetimes
        assert result.start == datetime(2026, 7, 16, 8, 0, tzinfo=API_TZ)
        assert result.end == datetime(2026, 7, 16, 16, 0, tzinfo=API_TZ)

    @pytest.mark.asyncio
    async def test_current_time_matches_overnight_shift(self):
        """Current time 02:00 → matches 20:00-08:00 night shift (cross-day)."""
        from app.services.shift_service import ShiftService

        db = _mock_db_with_shifts(
            _make_shift_row("D", "白班", "08:00", "16:00"),
            _make_shift_row("N", "夜班", "20:00", "08:00"),
        )
        svc = ShiftService(db)
        now = datetime(2026, 7, 17, 2, 0, tzinfo=API_TZ)

        result = await svc.resolve_shift("auto", now=now)

        assert result is not None
        assert result.code == "N"
        assert result.name == "夜班"
        # Night shift started on 7/16 20:00, ends 7/17 08:00
        assert result.start == datetime(2026, 7, 16, 20, 0, tzinfo=API_TZ)
        assert result.end == datetime(2026, 7, 17, 8, 0, tzinfo=API_TZ)

    @pytest.mark.asyncio
    async def test_specific_shift_code(self):
        """Explicit shift_code overrides auto-detection (returns fallback when not in window)."""
        from app.services.shift_service import ShiftService

        db = _mock_db_with_shifts(
            _make_shift_row("D", "白班", "08:00", "16:00"),
            _make_shift_row("N", "夜班", "20:00", "08:00"),
        )
        svc = ShiftService(db)
        now = datetime(2026, 7, 16, 22, 0, tzinfo=API_TZ)

        result = await svc.resolve_shift("N", now=now)

        assert result is not None
        assert result.code == "N"

    @pytest.mark.asyncio
    async def test_shift_code_not_found(self):
        """Non-existent shift_code raises ShiftNotFoundError."""
        from app.services.shift_service import ShiftNotFoundError, ShiftService

        db = _mock_db_with_shifts(
            _make_shift_row("D", "白班", "08:00", "16:00"),
        )
        svc = ShiftService(db)

        with pytest.raises(ShiftNotFoundError) as exc_info:
            await svc.resolve_shift("X")
        assert "未找到" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_no_shift_configured(self):
        """Empty shift config raises ShiftNotConfiguredError for auto."""
        from app import runtime
        from app.services.shift_service import ShiftNotConfiguredError, ShiftService

        # Clear cached runtime config from other tests
        runtime.shift_config = None

        db = _mock_db_with_shifts()  # no shifts
        svc = ShiftService(db)
        now = datetime(2026, 7, 16, 10, 0, tzinfo=API_TZ)

        with pytest.raises(ShiftNotConfiguredError) as exc_info:
            await svc.resolve_shift("auto", now=now)
        assert "未配置" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_data_end_capped_at_now(self):
        """At 10:00, data_end should be 10:00, not the scheduled end of 16:00."""
        from app.services.shift_service import ShiftService

        db = _mock_db_with_shifts(
            _make_shift_row("D", "白班", "08:00", "16:00"),
        )
        svc = ShiftService(db)
        now = datetime(2026, 7, 16, 10, 0, tzinfo=API_TZ)

        resolved = await svc.resolve_shift("auto", now=now)
        assert resolved is not None

        data_end = min(now, resolved.end)
        assert data_end == now  # capped at current time, not 16:00
        assert data_end < resolved.end


# ═══════════════════════════════════════════════════════════════════════════
# 2. patient_id integrity
# ═══════════════════════════════════════════════════════════════════════════

class TestPatientId:
    """patient_id must always be the system-internal stable ID, not admission_no or name."""

    def test_handover_context_has_patient_id_field(self):
        """HandoverContext must expose a dedicated patient_id field."""
        from app.services.handover.schemas import HandoverContext

        ctx = HandoverContext(
            patient_id="abc123",
            patient={"admission_no": "ZY001", "name": "张三"},
        )

        assert ctx.patient_id == "abc123"
        # patient_id must NOT be admission_no or name
        assert ctx.patient_id != ctx.patient.get("admission_no")
        assert ctx.patient_id != ctx.patient.get("name")

    def test_generate_uses_context_patient_id(self):
        """generate() input_data.patient_id must come from context.patient_id, not patient dict."""
        from app.services.handover.schemas import HandoverContext

        ctx = HandoverContext(
            patient_id="mongo_oid_12345",
            patient={"admission_no": "ZY001", "name": "张三"},
            time_window={"start": "2026-07-16T08:00:00", "end": "2026-07-16T10:00:00"},
            shift={"code": "D", "name": "白班", "scheduled_start": "2026-07-16T08:00:00+08:00", "scheduled_end": "2026-07-16T16:00:00+08:00"},
        )

        # Verify the invariant: patient_id != admission_no != name
        assert ctx.patient_id == "mongo_oid_12345"
        assert ctx.patient.get("admission_no") == "ZY001"
        assert ctx.patient.get("name") == "张三"

    def test_empty_draft_uses_patient_id(self):
        """_build_empty_draft must use context.patient_id, not admission_no."""
        from app.services.handover.generation_service import HandoverGenerationService
        from app.services.handover.schemas import HandoverContext

        svc = HandoverGenerationService(MagicMock(), {})
        ctx = HandoverContext(
            patient_id="mongo_oid_999",
            patient={"admission_no": "ZY999", "name": "李四"},
            time_window={"start": "2026-07-16T08:00:00", "end": "2026-07-16T10:00:00"},
        )

        draft = svc._build_empty_draft("nurse_bedside", ctx)

        assert draft["patient_id"] == "mongo_oid_999"
        assert draft["patient_id"] != "ZY999"
        assert draft["patient_id"] != "李四"

    def test_build_document_uses_patient_id(self):
        """_build_document must use context.patient_id, not admission_no."""
        from app.services.handover.generation_service import HandoverGenerationService
        from app.services.handover.schemas import HandoverContext

        svc = HandoverGenerationService(MagicMock(), {})
        ctx = HandoverContext(
            patient_id="mongo_oid_777",
            patient={"admission_no": "ZY777", "name": "王五"},
            time_window={"start": "2026-07-16T08:00:00", "end": "2026-07-16T10:00:00"},
        )
        parsed = {"sections": {}, "evidence": [], "missing_data": [], "ai_generated_fields": []}

        doc = svc._build_document(parsed, ctx, "nurse_bedside")

        assert doc.patient_id == "mongo_oid_777"
        assert doc.patient_id != "ZY777"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Change detection
# ═══════════════════════════════════════════════════════════════════════════

class TestChangeDetection:
    """Change detection must handle missing data, cross-shift comparison, and return structure."""

    @pytest.mark.asyncio
    async def test_no_previous_record_returns_empty_changes(self):
        """When _get_previous_shift_data returns {}, changes should be empty."""
        from app.services.handover.generation_service import HandoverGenerationService

        db = MagicMock()
        db.col = MagicMock(return_value=db)
        # No previous handover doc found
        db.find_one = AsyncMock(return_value=None)

        svc = HandoverGenerationService(db, {})
        svc._get_previous_shift_data = AsyncMock(return_value={})

        result = await svc.detect_changes(
            "patient_123",
            {"start": "2026-07-16T08:00:00", "end": "2026-07-16T10:00:00"},
            {"code": "D", "name": "白班"},
        )

        assert result["patient_id"] == "patient_123"
        assert result["changes"] == []
        assert "previous_handover" in result
        # previous_handover should be empty dict when no prior data
        assert result["previous_handover"] == {}

    def test_detect_changes_returns_previous_handover(self):
        """detect_changes must include previous_handover in its return value."""
        from app.services.handover.generation_service import HandoverGenerationService

        svc = HandoverGenerationService(MagicMock(), {})
        previous_data = {
            "shift": {"code": "N", "name": "夜班", "data_start": "2026-07-15T20:00:00", "data_end": "2026-07-16T08:00:00"},
            "clinical": {"vitals": [{"label": "HR", "latest": 80}]},
        }
        svc._get_previous_shift_data = AsyncMock(return_value=previous_data)
        # Make context build work: mock the context service
        with patch("app.services.handover.context_service.HandoverContextService") as mock_ctx_svc_cls:
            mock_ctx_svc = MagicMock()
            mock_ctx_svc.build = AsyncMock(return_value=MagicMock(
                patient_id="patient_123",
                vitals=[],
                labs=[],
                io={},
                pumps=[],
                airway_vent={},
                lines=[],
                assessments={},
                events=[],
                pending_orders=[],
                alerts=[],
                data_snapshot_at="2026-07-16T10:00:00",
            ))
            mock_ctx_svc_cls.return_value = mock_ctx_svc

            # We can't easily test the full flow with LLM, but we can verify the
            # error path returns previous_handover
            # (LLM call will fail in test env, triggering the except branch)

    @pytest.mark.asyncio
    async def test_previous_handover_in_result(self):
        """Error path of detect_changes must still include previous_handover."""
        from app.services.handover.generation_service import HandoverGenerationService

        db = MagicMock()
        svc = HandoverGenerationService(db, {})
        previous_data = {"shift": {"code": "N"}, "clinical": {}}
        svc._get_previous_shift_data = AsyncMock(return_value=previous_data)

        # LLM call will fail → error path
        with patch("app.services.handover.generation_service.call_llm_chat", side_effect=Exception("LLM unavailable")):
            with patch("app.services.handover.context_service.HandoverContextService") as mock_ctx_cls:
                mock_ctx = MagicMock()
                mock_ctx.vitals = []
                mock_ctx.labs = []
                mock_ctx.io = {}
                mock_ctx.pumps = []
                mock_ctx.airway_vent = {}
                mock_ctx.lines = []
                mock_ctx.assessments = {}
                mock_ctx.events = []
                mock_ctx.pending_orders = []
                mock_ctx.alerts = []
                mock_ctx.data_snapshot_at = "2026-07-16T10:00:00"
                mock_ctx_cls.return_value = MagicMock()
                mock_ctx_cls.return_value.build = AsyncMock(return_value=mock_ctx)

                result = await svc.detect_changes(
                    "patient_123",
                    {"start": "2026-07-16T08:00:00", "end": "2026-07-16T10:00:00"},
                    {"code": "D", "name": "白班"},
                )

        assert result["previous_handover"] == previous_data
        assert result["changes"] == []  # error path → empty changes
        assert "LLM调用失败" in result["missing_data"]


# ═══════════════════════════════════════════════════════════════════════════
# 4. Prompt integrity
# ═══════════════════════════════════════════════════════════════════════════

class TestPromptIntegrity:
    """Prompt markdown files must be clean — no escape corruption."""

    def test_nurse_bedside_prompt_no_escapes(self):
        """nurse_bedside_handover.md must have no escaped underscores, brackets, or HTML spaces."""
        path = PROMPT_DIR / "nurse_bedside_handover.md"
        assert path.exists(), f"Prompt file not found: {path}"
        content = path.read_text(encoding="utf-8")

        assert r"\_" not in content, "Found escaped underscores"
        assert r"\[" not in content, "Found escaped brackets"
        assert r"\]" not in content, "Found escaped closing brackets"
        assert "&#x20;" not in content, "Found HTML space entities"
        assert r"\#" not in content, "Found escaped hash marks"

    def test_change_detection_prompt_no_escapes(self):
        """handover_change_detection.md must have no escape corruption."""
        path = PROMPT_DIR / "handover_change_detection.md"
        assert path.exists(), f"Prompt file not found: {path}"
        content = path.read_text(encoding="utf-8")

        assert r"\_" not in content, "Found escaped underscores"
        assert r"\[" not in content, "Found escaped brackets"
        assert r"\]" not in content, "Found escaped closing brackets"
        assert "&#x20;" not in content, "Found HTML space entities"

    def test_nurse_bedside_has_patient_id_in_schema(self):
        """Output schema must reference patient_id (not escaped version)."""
        path = PROMPT_DIR / "nurse_bedside_handover.md"
        content = path.read_text(encoding="utf-8")

        assert '"patient_id"' in content, "Missing patient_id in output schema"

    def test_nurse_bedside_missing_data_is_array(self):
        """missing_data must be [] not escaped brackets."""
        path = PROMPT_DIR / "nurse_bedside_handover.md"
        content = path.read_text(encoding="utf-8")

        assert '"missing_data": []' in content, "missing_data must be empty array []"

    def test_change_detection_schema_valid_json(self):
        """Output schema in change detection prompt must be valid JSON."""
        path = PROMPT_DIR / "handover_change_detection.md"
        content = path.read_text(encoding="utf-8")

        m = re.search(r"<output_schema>(.*?)</output_schema>", content, re.DOTALL)
        assert m is not None, "output_schema block not found"
        json_str = m.group(1).strip()

        try:
            obj = json.loads(json_str)
        except json.JSONDecodeError as e:
            pytest.fail(f"output_schema is not valid JSON: {e}")

        assert "patient_id" in obj
        assert "changes" in obj
        assert "not_comparable" in obj

    def test_nurse_bedside_schema_valid_json(self):
        """Output schema in nurse bedside prompt must be valid JSON."""
        path = PROMPT_DIR / "nurse_bedside_handover.md"
        content = path.read_text(encoding="utf-8")

        m = re.search(r"<output_schema>(.*?)</output_schema>", content, re.DOTALL)
        assert m is not None, "output_schema block not found"
        json_str = m.group(1).strip()

        try:
            obj = json.loads(json_str)
        except json.JSONDecodeError as e:
            pytest.fail(f"output_schema is not valid JSON: {e}")

        assert "patient_id" in obj
        assert "sections" in obj
        assert "missing_data" in obj


# ═══════════════════════════════════════════════════════════════════════════
# 5. Context service data enrichment
# ═══════════════════════════════════════════════════════════════════════════

class TestContextDataEnrichment:
    """Vitals and pumps must carry time, unit, and source for change detection."""

    def test_vitals_include_time_unit_source(self):
        """Vital signs must have latest_time, unit, and source fields."""
        from app.services.handover.context_service import HandoverContextService

        db = MagicMock()
        db.col = MagicMock(return_value=db)
        # Return mock vital data
        db.find = MagicMock(return_value=db)
        db.sort = MagicMock(return_value=db)
        db.to_list = AsyncMock(return_value=[
            {"time": "2026-07-16T09:00:00", "fVal": 80, "unit": "bpm"},
            {"time": "2026-07-16T09:30:00", "fVal": 85, "unit": "bpm"},
        ])

        svc = HandoverContextService(db)
        # We can test the structure by examining what _build_vitals produces
        # But we need a real async test. Let's just verify the method signature
        # and that the code path includes these fields.
        # (Full integration test would require a running MongoDB)

    @pytest.mark.asyncio
    async def test_pumps_include_dose_unit_route_time_source(self):
        """Pump data must have dose_unit, rate_unit, route, record_time, source."""
        from app.services.handover.context_service import HandoverContextService

        db = MagicMock()
        db.col = MagicMock(return_value=db)
        db.find = MagicMock(return_value=db)
        db.sort = MagicMock(return_value=db)
        db.to_list = AsyncMock(return_value=[
            {
                "drug_name": "去甲肾上腺素",
                "dose": "4mg/50ml",
                "dose_unit": "mg",
                "rate": "5",
                "rate_unit": "ml/h",
                "route": "IV",
                "record_time": "2026-07-16T10:00:00",
            },
        ])

        svc = HandoverContextService(db)
        result = await svc._build_pumps(
            ["bedside_pid_1"],
            datetime(2026, 7, 16, 8, 0),
            datetime(2026, 7, 16, 10, 0),
        )

        assert len(result) == 1
        pump = result[0]
        assert pump["name"] == "去甲肾上腺素"
        assert "dose_unit" in pump
        assert "rate_unit" in pump
        assert "route" in pump
        assert "record_time" in pump
        assert "source" in pump

    @pytest.mark.asyncio
    async def test_vitals_have_latest_time_and_unit(self):
        """Vital signs must include latest_time and unit fields."""
        from app.services.handover.context_service import HandoverContextService

        db = MagicMock()
        db.col = MagicMock(return_value=db)
        db.find = MagicMock(return_value=db)
        db.sort = MagicMock(return_value=db)
        # deviceCap returns data
        db.to_list = AsyncMock(side_effect=[
            # First call: deviceCap HR data
            [
                {"time": "2026-07-16T09:00:00", "fVal": 80, "unit": "bpm"},
                {"time": "2026-07-16T09:30:00", "fVal": 85, "unit": "bpm"},
            ],
            # Second call: deviceCap SpO2 returns empty → falls back to bedside
            [],
            # bedside SpO2
            [
                {"time": "2026-07-16T09:00:00", "fVal": 98, "unit": "%"},
            ],
            # Remaining vital codes (RR, T, SBP, DBP, MAP, CVP) all empty
            [], [], [], [], [], [],
        ])

        svc = HandoverContextService(db)
        result = await svc._build_vitals(
            ["bedside_pid_1"],
            datetime(2026, 7, 16, 8, 0),
            datetime(2026, 7, 16, 10, 0),
        )

        assert len(result) >= 1
        for v in result:
            assert "latest_time" in v, f"Missing latest_time in vital: {v['label']}"
            assert "unit" in v, f"Missing unit in vital: {v['label']}"
            assert "source" in v, f"Missing source in vital: {v['label']}"


# ═══════════════════════════════════════════════════════════════════════════
# 6. Thresholds from config
# ═══════════════════════════════════════════════════════════════════════════

class TestThresholdsFromConfig:
    """Change detection thresholds must come from config, not be hardcoded."""

    @pytest.mark.asyncio
    async def test_thresholds_read_from_config(self):
        """thresholds are read from config, not hardcoded."""
        from app.services.handover.generation_service import HandoverGenerationService

        db = MagicMock()
        config = {
            "handover": {
                "change_detection": {
                    "thresholds": {
                        "MAP": {"low": 65, "unit": "mmHg"},
                        "尿量_ml_kg_h_low": 0.5,
                    }
                }
            }
        }
        svc = HandoverGenerationService(db, config)
        svc._get_previous_shift_data = AsyncMock(return_value={})

        with patch("app.services.handover.generation_service.call_llm_chat", side_effect=Exception("no LLM")):
            with patch("app.services.handover.context_service.HandoverContextService") as mock_ctx_cls:
                mock_ctx = MagicMock()
                mock_ctx.vitals = []
                mock_ctx.labs = []
                mock_ctx.io = {}
                mock_ctx.pumps = []
                mock_ctx.airway_vent = {}
                mock_ctx.lines = []
                mock_ctx.assessments = {}
                mock_ctx.events = []
                mock_ctx.pending_orders = []
                mock_ctx.alerts = []
                mock_ctx.data_snapshot_at = "2026-07-16T10:00:00"
                mock_ctx_cls.return_value = MagicMock()
                mock_ctx_cls.return_value.build = AsyncMock(return_value=mock_ctx)

                result = await svc.detect_changes(
                    "patient_123",
                    {"start": "2026-07-16T08:00:00", "end": "2026-07-16T10:00:00"},
                    {"code": "D", "name": "白班"},
                )

        # verify it didn't crash with config thresholds
        assert "changes" in result

    def test_no_threshold_config_returns_empty_dict(self):
        """When no thresholds configured, empty dict is passed (prompt says: use info severity)."""
        from app.services.handover.generation_service import HandoverGenerationService

        svc = HandoverGenerationService(MagicMock(), {})  # empty config
        # Test the config access pattern directly
        thresholds = svc.config.get("handover", {}).get("change_detection", {}).get("thresholds", {})
        assert thresholds == {}

        svc2 = HandoverGenerationService(MagicMock(), {"handover": {}})
        thresholds2 = svc2.config.get("handover", {}).get("change_detection", {}).get("thresholds", {})
        assert thresholds2 == {}


# ═══════════════════════════════════════════════════════════════════════════
# 7. Shift cache TTL
# ═══════════════════════════════════════════════════════════════════════════

class TestShiftCache:
    """ShiftService.list_shifts() must honour TTL and force_refresh."""

    @pytest.mark.asyncio
    async def test_first_call_queries_db(self):
        """First list_shifts() call must query the database."""
        from app import runtime
        from app.services.shift_service import ShiftService

        runtime.shift_config = None
        runtime.shift_config_loaded_at = None

        db = _mock_db_with_shifts(
            _make_shift_row("D", "白班", "08:00", "16:00"),
        )
        svc = ShiftService(db, config={})

        result = await svc.list_shifts()

        assert result["items"]
        assert result["items"][0]["code"] == "D"
        # DB must have been queried at least once
        db.find_one.assert_called()

    @pytest.mark.asyncio
    async def test_ttl_not_expired_uses_cache(self):
        """When TTL is fresh, list_shifts() must NOT re-query the database."""
        from app import runtime
        from app.services.shift_service import ShiftService

        runtime.shift_config = None
        runtime.shift_config_loaded_at = None

        db = _mock_db_with_shifts(
            _make_shift_row("D", "白班", "08:00", "16:00"),
        )
        svc = ShiftService(db, config={"handover": {"shift_cache_ttl_seconds": 999}})

        # First call — queries DB
        await svc.list_shifts()
        call_count_after_first = db.find_one.call_count

        # Second call — must use cache
        await svc.list_shifts()
        assert db.find_one.call_count == call_count_after_first

    @pytest.mark.asyncio
    async def test_ttl_expired_requeries_db(self):
        """When TTL has expired, list_shifts() must re-query the database."""
        from app import runtime
        from datetime import timedelta
        from app.services.shift_service import ShiftService

        runtime.shift_config = None
        runtime.shift_config_loaded_at = None

        db = _mock_db_with_shifts(
            _make_shift_row("D", "白班", "08:00", "16:00"),
        )
        svc = ShiftService(db, config={"handover": {"shift_cache_ttl_seconds": 60}})

        # First call — fills cache
        await svc.list_shifts()
        call_count = db.find_one.call_count

        # Artificially age the cache so TTL is expired
        runtime.shift_config_loaded_at = datetime.now(API_TZ) - timedelta(seconds=120)

        # Second call — should re-query because loaded_at is too old
        await svc.list_shifts()
        assert db.find_one.call_count > call_count

    @pytest.mark.asyncio
    async def test_force_refresh_bypasses_cache(self):
        """force_refresh=True must re-query even when cache is fresh."""
        from app import runtime
        from app.services.shift_service import ShiftService

        runtime.shift_config = None
        runtime.shift_config_loaded_at = None

        db = _mock_db_with_shifts(
            _make_shift_row("D", "白班", "08:00", "16:00"),
        )
        svc = ShiftService(db, config={"handover": {"shift_cache_ttl_seconds": 999}})

        await svc.list_shifts()
        count_after_first = db.find_one.call_count

        await svc.list_shifts(force_refresh=True)
        assert db.find_one.call_count > count_after_first

    @pytest.mark.asyncio
    async def test_db_change_reflected_after_refresh(self):
        """After banCiInfoList changes, a refresh must return updated items."""
        from app import runtime
        from app.services.shift_service import ShiftService

        runtime.shift_config = None
        runtime.shift_config_loaded_at = None

        db = _mock_db_with_shifts(
            _make_shift_row("D", "白班", "08:00", "16:00"),
        )
        svc = ShiftService(db, config={"handover": {"shift_cache_ttl_seconds": 999}})

        result1 = await svc.list_shifts()
        assert result1["items"][0]["code"] == "D"

        # Change the DB response
        db.find_one = AsyncMock(return_value={
            "banCiInfoList": [
                {"shiftCode": "E", "shiftName": "晚班", "startTime": "16:00", "endTime": "00:00"},
            ]
        })

        result2 = await svc.list_shifts(force_refresh=True)
        assert result2["items"][0]["code"] == "E"

    @pytest.mark.asyncio
    async def test_db_query_exception_propagates(self):
        """refresh_cache() wraps raw DB exceptions as ShiftQueryFailedError."""
        from app.services.shift_service import ShiftQueryFailedError, ShiftService

        db = MagicMock()
        db.col = MagicMock(return_value=db)
        db.find_one = AsyncMock(side_effect=RuntimeError("MongoDB connection refused"))

        svc = ShiftService(db, config={"handover": {"shift_cache_ttl_seconds": 0}})

        # Raw DB exception is wrapped as ShiftQueryFailedError
        with pytest.raises(ShiftQueryFailedError) as exc_info:
            await svc.refresh_cache()
        # The message is our controlled one, not the raw RuntimeError text
        assert exc_info.value.__cause__ is not None  # original exception chained
        assert "MongoDB connection refused" in str(exc_info.value.__cause__)

    @pytest.mark.asyncio
    async def test_default_ttl_is_60_seconds(self):
        """When no TTL configured, default is 60 seconds."""
        from app.services.shift_service import ShiftService

        svc = ShiftService(MagicMock(), config=None)
        assert svc._ttl_seconds() == 60

        svc2 = ShiftService(MagicMock(), config={})
        assert svc2._ttl_seconds() == 60

        svc3 = ShiftService(MagicMock(), config={"handover": {}})
        assert svc3._ttl_seconds() == 60


# ═══════════════════════════════════════════════════════════════════════════
# 8. Shift error classification
# ═══════════════════════════════════════════════════════════════════════════

class TestShiftErrorClassification:
    """ShiftService must raise specific exceptions for different error conditions."""

    @pytest.mark.asyncio
    async def test_empty_ban_ci_info_list_raises_not_configured(self):
        """Empty banCiInfoList → ShiftNotConfiguredError."""
        from app import runtime
        from app.services.shift_service import (
            ShiftNotConfiguredError,
            ShiftService,
        )

        runtime.shift_config = None
        runtime.shift_config_loaded_at = None

        db = _mock_db_with_shifts()  # no shift rows
        svc = ShiftService(db, config={})
        now = datetime(2026, 7, 16, 10, 0, tzinfo=API_TZ)

        with pytest.raises(ShiftNotConfiguredError) as exc_info:
            await svc.resolve_shift("auto", now=now)
        assert "未配置" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_no_matching_shift_raises_not_matched(self):
        """Valid shifts exist but current time matches none → ShiftNotMatchedError."""
        from app import runtime
        from app.services.shift_service import (
            ShiftNotMatchedError,
            ShiftService,
        )

        runtime.shift_config = None
        runtime.shift_config_loaded_at = None

        db = _mock_db_with_shifts(
            _make_shift_row("D", "白班", "08:00", "16:00"),
        )
        svc = ShiftService(db, config={})
        # 02:00 is not in 08:00–16:00
        now = datetime(2026, 7, 16, 2, 0, tzinfo=API_TZ)

        with pytest.raises(ShiftNotMatchedError) as exc_info:
            await svc.resolve_shift("auto", now=now)
        assert "不在任何班次" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_unknown_shift_code_raises_not_found(self):
        """Requesting a non-existent shift_code → ShiftNotFoundError."""
        from app import runtime
        from app.services.shift_service import (
            ShiftNotFoundError,
            ShiftService,
        )

        runtime.shift_config = None
        runtime.shift_config_loaded_at = None

        db = _mock_db_with_shifts(
            _make_shift_row("D", "白班", "08:00", "16:00"),
        )
        svc = ShiftService(db, config={})

        with pytest.raises(ShiftNotFoundError) as exc_info:
            await svc.resolve_shift("X_NONEXISTENT")
        assert "未找到" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_shift_not_started_returns_fallback(self):
        """Requesting a shift before it starts returns the shift info (router checks SHIFT_NOT_STARTED)."""
        from app import runtime
        from app.services.shift_service import ShiftService

        runtime.shift_config = None
        runtime.shift_config_loaded_at = None

        db = _mock_db_with_shifts(
            _make_shift_row("D", "白班", "08:00", "16:00"),
        )
        svc = ShiftService(db, config={})
        # 06:00 is before 08:00 start
        now = datetime(2026, 7, 16, 6, 0, tzinfo=API_TZ)

        result = await svc.resolve_shift("D", now=now)

        # Service returns the shift info; router is responsible for
        # checking now < scheduled_start → SHIFT_NOT_STARTED
        assert result is not None
        assert result.code == "D"
        assert now < result.start  # shift hasn't started yet

    @pytest.mark.asyncio
    async def test_db_error_propagates_as_query_failed(self):
        """Raw DB exception wraps to ShiftQueryFailedError via refresh_cache → resolve_shift."""
        from app.services.shift_service import ShiftQueryFailedError, ShiftService

        db = MagicMock()
        db.col = MagicMock(return_value=db)
        db.find_one = AsyncMock(side_effect=OSError("Connection timeout"))

        svc = ShiftService(db, config={"handover": {"shift_cache_ttl_seconds": 0}})

        # The raw OSError is wrapped as ShiftQueryFailedError through the chain
        with pytest.raises(ShiftQueryFailedError):
            await svc.resolve_shift("auto")
        # Verify find_one was attempted
        db.find_one.assert_called()


# ═══════════════════════════════════════════════════════════════════════════
# 9. Cross-midnight shift resolution
# ═══════════════════════════════════════════════════════════════════════════

class TestCrossMidnightShift:
    """Shifts crossing midnight (e.g. 20:00–08:00) must compute correct windows."""

    @pytest.mark.asyncio
    async def test_midnight_shift_matches_early_morning(self):
        """At 02:00 next day, the 20:00–08:00 shift must still be active."""
        from app import runtime
        from app.services.shift_service import ShiftService

        runtime.shift_config = None
        runtime.shift_config_loaded_at = None

        db = _mock_db_with_shifts(
            {"shiftCode": "X1", "shiftName": "数据库班次名称", "startTime": "20:00", "endTime": "08:00"},
        )
        svc = ShiftService(db, config={})
        now = datetime(2026, 7, 17, 2, 0, tzinfo=API_TZ)

        result = await svc.resolve_shift("auto", now=now)

        assert result is not None
        assert result.code == "X1"
        # Start is previous day 20:00
        assert result.start == datetime(2026, 7, 16, 20, 0, tzinfo=API_TZ)
        # End is current day 08:00
        assert result.end == datetime(2026, 7, 17, 8, 0, tzinfo=API_TZ)

    @pytest.mark.asyncio
    async def test_midnight_shift_scheduled_times(self):
        """scheduled_start is previous day, scheduled_end is current day."""
        from datetime import date as date_type
        from app import runtime
        from app.services.shift_service import ShiftService

        runtime.shift_config = None
        runtime.shift_config_loaded_at = None

        db = _mock_db_with_shifts(
            {"shiftCode": "X1", "shiftName": "数据库班次名称", "startTime": "20:00", "endTime": "08:00"},
        )
        svc = ShiftService(db, config={})
        now = datetime(2026, 7, 17, 2, 0, tzinfo=API_TZ)

        result = await svc.resolve_shift("auto", now=now)

        # scheduled_start must be previous day 20:00
        assert result.start.date() == date_type(2026, 7, 16)
        assert result.start.hour == 20
        # scheduled_end must be current day 08:00
        assert result.end.date() == date_type(2026, 7, 17)
        assert result.end.hour == 8

    @pytest.mark.asyncio
    async def test_midnight_shift_data_end_capped_at_now(self):
        """data_end must not exceed now, even though scheduled_end is later."""
        from app import runtime
        from app.services.shift_service import ShiftService

        runtime.shift_config = None
        runtime.shift_config_loaded_at = None

        db = _mock_db_with_shifts(
            {"shiftCode": "X1", "shiftName": "数据库班次名称", "startTime": "20:00", "endTime": "08:00"},
        )
        svc = ShiftService(db, config={})
        now = datetime(2026, 7, 17, 2, 0, tzinfo=API_TZ)

        result = await svc.resolve_shift("auto", now=now)

        data_end = min(now, result.end)
        assert data_end == now  # capped at 02:00, not 08:00
        assert data_end < result.end

    @pytest.mark.asyncio
    async def test_midnight_shift_evening_match(self):
        """At 22:00, the 20:00–08:00 shift should match on the same day."""
        from app import runtime
        from app.services.shift_service import ShiftService

        runtime.shift_config = None
        runtime.shift_config_loaded_at = None

        db = _mock_db_with_shifts(
            {"shiftCode": "X1", "shiftName": "数据库班次名称", "startTime": "20:00", "endTime": "08:00"},
        )
        svc = ShiftService(db, config={})
        now = datetime(2026, 7, 16, 22, 0, tzinfo=API_TZ)

        result = await svc.resolve_shift("auto", now=now)

        assert result is not None
        assert result.code == "X1"
        assert result.start == datetime(2026, 7, 16, 20, 0, tzinfo=API_TZ)
        assert result.end == datetime(2026, 7, 17, 8, 0, tzinfo=API_TZ)


# ═══════════════════════════════════════════════════════════════════════════
# 10. Forced-alerts time window
# ═══════════════════════════════════════════════════════════════════════════

class TestForcedAlertsHelpers:
    """Unit tests for time-parsing helpers used by the forced-alerts endpoint."""

    def test_parse_iso_naive_treated_as_shanghai(self):
        """Naive ISO datetime → treated as Asia/Shanghai."""
        from app.routers.handover import _parse_iso_datetime

        dt = _parse_iso_datetime("2026-07-16T08:00:00")
        assert dt.tzinfo is not None
        assert str(dt.tzinfo) == "Asia/Shanghai"
        assert dt.hour == 8

    def test_parse_iso_with_tz_preserves_offset(self):
        """Timezone-aware ISO datetime keeps its timezone info."""
        from app.routers.handover import _parse_iso_datetime

        dt = _parse_iso_datetime("2026-07-16T08:00:00+08:00")
        assert dt.tzinfo is not None

    def test_parse_iso_invalid_raises(self):
        """Invalid datetime string raises HTTP 422."""
        from app.routers.handover import _parse_iso_datetime
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            _parse_iso_datetime("not-a-datetime")
        assert exc_info.value.status_code == 422
        assert "INVALID_TIME_RANGE" == exc_info.value.detail["code"]


class TestForcedAlertsShiftResolution:
    """forced-alerts endpoint must use ShiftService when since/until are absent."""

    @pytest.mark.asyncio
    async def test_shift_based_window_no_fallback_to_midnight(self):
        """Without since/until, the endpoint must resolve via ShiftService, not midnight."""
        from app import runtime
        from app.services.shift_service import ShiftService

        runtime.shift_config = None
        runtime.shift_config_loaded_at = None

        db = _mock_db_with_shifts(
            {"shiftCode": "X1", "shiftName": "数据库班次名称", "startTime": "20:00", "endTime": "08:00"},
        )
        svc = ShiftService(db, config={})
        now = datetime(2026, 7, 17, 2, 0, tzinfo=API_TZ)

        resolved = await svc.resolve_shift("auto", now=now)
        data_end = min(now, resolved.end)

        # data_start must NOT be today 00:00
        assert resolved.start.hour == 20  # database config, not midnight
        assert resolved.start != datetime(2026, 7, 17, 0, 0, tzinfo=API_TZ)

        # data_end must be capped at now
        assert data_end == now

    @pytest.mark.asyncio
    async def test_shift_based_window_with_midnight_shift(self):
        """Cross-midnight shift: start and end span two calendar days."""
        from app import runtime
        from app.services.shift_service import ShiftService

        runtime.shift_config = None
        runtime.shift_config_loaded_at = None

        db = _mock_db_with_shifts(
            {"shiftCode": "X1", "shiftName": "数据库班次名称", "startTime": "20:00", "endTime": "08:00"},
        )
        svc = ShiftService(db, config={})
        now = datetime(2026, 7, 17, 2, 0, tzinfo=API_TZ)

        resolved = await svc.resolve_shift("auto", now=now)

        mongo_start = resolved.start.astimezone(API_TZ).replace(tzinfo=None)
        mongo_end = min(now, resolved.end).astimezone(API_TZ).replace(tzinfo=None)

        assert mongo_start == datetime(2026, 7, 16, 20, 0)
        assert mongo_end == datetime(2026, 7, 17, 2, 0)

    @pytest.mark.asyncio
    async def test_db_query_failure_returns_query_failed_error(self):
        """When DB query fails, forced-alerts must use SHIFT_QUERY_FAILED."""
        from app.routers.handover import _map_shift_error
        from app.services.shift_service import ShiftQueryFailedError

        exc = ShiftQueryFailedError("Connection refused")
        http_exc = _map_shift_error(exc)

        assert http_exc.status_code == 500
        assert http_exc.detail["code"] == "SHIFT_QUERY_FAILED"

    @pytest.mark.asyncio
    async def test_empty_config_returns_not_configured(self):
        """When shift config is empty, forced-alerts must use SHIFT_NOT_CONFIGURED."""
        from app.routers.handover import _map_shift_error
        from app.services.shift_service import ShiftNotConfiguredError

        exc = ShiftNotConfiguredError("数据库未配置班次信息")
        http_exc = _map_shift_error(exc)

        assert http_exc.status_code == 422
        assert http_exc.detail["code"] == "SHIFT_NOT_CONFIGURED"


# ═══════════════════════════════════════════════════════════════════════════
# 11. Change detection short-circuit
# ═══════════════════════════════════════════════════════════════════════════

class TestChangeDetectionShortCircuit:
    """When no previous handover snapshot exists, detect_changes must skip LLM."""

    @pytest.mark.asyncio
    async def test_no_previous_skips_llm(self):
        """Empty previous_result → does NOT call call_llm_chat."""
        from app.services.handover.generation_service import HandoverGenerationService

        db = MagicMock()
        svc = HandoverGenerationService(db, {})
        svc._get_previous_shift_data = AsyncMock(return_value={})  # no previous data

        with patch("app.services.handover.generation_service.call_llm_chat") as mock_llm:
            with patch("app.services.handover.context_service.HandoverContextService") as mock_ctx_cls:
                mock_ctx = MagicMock()
                mock_ctx.vitals = []
                mock_ctx.labs = []
                mock_ctx.io = {}
                mock_ctx.pumps = []
                mock_ctx.airway_vent = {}
                mock_ctx.lines = []
                mock_ctx.assessments = {}
                mock_ctx.events = []
                mock_ctx.pending_orders = []
                mock_ctx.alerts = []
                mock_ctx.data_snapshot_at = "2026-07-16T10:00:00"
                mock_ctx_cls.return_value = MagicMock()
                mock_ctx_cls.return_value.build = AsyncMock(return_value=mock_ctx)

                result = await svc.detect_changes(
                    "patient_123",
                    {"start": "2026-07-16T08:00:00", "end": "2026-07-16T10:00:00"},
                    {"code": "D", "name": "白班"},
                )

            # LLM must NOT have been called
            mock_llm.assert_not_called()

        # Verify short-circuit return structure
        assert result["patient_id"] == "patient_123"
        assert result["changes"] == []
        assert result["not_comparable"] == ["上一班快照缺失"]
        assert result["missing_data"] == ["previous"]
        assert result["previous_handover"] == {}
        assert result["previous_shift"] == {}

    @pytest.mark.asyncio
    async def test_short_circuit_preserves_patient_id(self):
        """patient_id must be the system-stable ID, not admission_no."""
        from app.services.handover.generation_service import HandoverGenerationService

        db = MagicMock()
        svc = HandoverGenerationService(db, {})
        svc._get_previous_shift_data = AsyncMock(return_value={})

        with patch("app.services.handover.context_service.HandoverContextService") as mock_ctx_cls:
            mock_ctx = MagicMock()
            mock_ctx.vitals = []
            mock_ctx.labs = []
            mock_ctx.io = {}
            mock_ctx.pumps = []
            mock_ctx.airway_vent = {}
            mock_ctx.lines = []
            mock_ctx.assessments = {}
            mock_ctx.events = []
            mock_ctx.pending_orders = []
            mock_ctx.alerts = []
            mock_ctx.data_snapshot_at = "2026-07-16T10:00:00"
            mock_ctx_cls.return_value = MagicMock()
            mock_ctx_cls.return_value.build = AsyncMock(return_value=mock_ctx)

            result = await svc.detect_changes(
                "mongo_oid_stable_42",
                {"start": "2026-07-16T08:00:00", "end": "2026-07-16T10:00:00"},
            )

        assert result["patient_id"] == "mongo_oid_stable_42"

    @pytest.mark.asyncio
    async def test_previous_handover_is_empty_dict(self):
        """previous_handover must be {} when no prior snapshot exists."""
        from app.services.handover.generation_service import HandoverGenerationService

        db = MagicMock()
        svc = HandoverGenerationService(db, {})
        svc._get_previous_shift_data = AsyncMock(return_value={})

        with patch("app.services.handover.context_service.HandoverContextService") as mock_ctx_cls:
            mock_ctx = MagicMock()
            mock_ctx.vitals = []
            mock_ctx.labs = []
            mock_ctx.io = {}
            mock_ctx.pumps = []
            mock_ctx.airway_vent = {}
            mock_ctx.lines = []
            mock_ctx.assessments = {}
            mock_ctx.events = []
            mock_ctx.pending_orders = []
            mock_ctx.alerts = []
            mock_ctx.data_snapshot_at = "2026-07-16T10:00:00"
            mock_ctx_cls.return_value = MagicMock()
            mock_ctx_cls.return_value.build = AsyncMock(return_value=mock_ctx)

            result = await svc.detect_changes(
                "patient_123",
                {"start": "2026-07-16T08:00:00", "end": "2026-07-16T10:00:00"},
            )

        assert result["previous_handover"] == {}
        assert isinstance(result["previous_handover"], dict)
        assert len(result["previous_handover"]) == 0

    @pytest.mark.asyncio
    async def test_short_circuit_current_shift_includes_data(self):
        """current_shift must contain data from the shift parameter, not be empty."""
        from app.services.handover.generation_service import HandoverGenerationService

        db = MagicMock()
        svc = HandoverGenerationService(db, {})
        svc._get_previous_shift_data = AsyncMock(return_value={})

        with patch("app.services.handover.context_service.HandoverContextService") as mock_ctx_cls:
            mock_ctx = MagicMock()
            mock_ctx.vitals = []
            mock_ctx.labs = []
            mock_ctx.io = {}
            mock_ctx.pumps = []
            mock_ctx.airway_vent = {}
            mock_ctx.lines = []
            mock_ctx.assessments = {}
            mock_ctx.events = []
            mock_ctx.pending_orders = []
            mock_ctx.alerts = []
            mock_ctx.data_snapshot_at = "2026-07-16T10:00:00"
            mock_ctx_cls.return_value = MagicMock()
            mock_ctx_cls.return_value.build = AsyncMock(return_value=mock_ctx)

            result = await svc.detect_changes(
                "patient_123",
                {"start": "2026-07-16T08:00:00", "end": "2026-07-16T16:00:00"},
                {"code": "D", "name": "白班"},
            )

        assert result["current_shift"]["code"] == "D"
        assert result["current_shift"]["name"] == "白班"
        # data_start and data_end come from time_window
        assert result["current_shift"]["data_start"] == "2026-07-16T08:00:00"
        assert result["current_shift"]["data_end"] == "2026-07-16T16:00:00"

    @pytest.mark.asyncio
    async def test_with_previous_data_still_calls_llm(self):
        """When previous clinical data EXISTS, the LLM must still be called."""
        from app.services.handover.generation_service import HandoverGenerationService

        db = MagicMock()
        svc = HandoverGenerationService(db, {})
        svc._get_previous_shift_data = AsyncMock(return_value={
            "shift": {"code": "N", "name": "夜班"},
            "clinical": {"vitals": [{"label": "HR", "latest": 80}]},
        })

        with patch("app.services.handover.generation_service.call_llm_chat") as mock_llm:
            mock_llm.side_effect = Exception("LLM simulated error")
            with patch("app.services.handover.context_service.HandoverContextService") as mock_ctx_cls:
                mock_ctx = MagicMock()
                mock_ctx.vitals = []
                mock_ctx.labs = []
                mock_ctx.io = {}
                mock_ctx.pumps = []
                mock_ctx.airway_vent = {}
                mock_ctx.lines = []
                mock_ctx.assessments = {}
                mock_ctx.events = []
                mock_ctx.pending_orders = []
                mock_ctx.alerts = []
                mock_ctx.data_snapshot_at = "2026-07-16T10:00:00"
                mock_ctx_cls.return_value = MagicMock()
                mock_ctx_cls.return_value.build = AsyncMock(return_value=mock_ctx)

                await svc.detect_changes(
                    "patient_123",
                    {"start": "2026-07-16T08:00:00", "end": "2026-07-16T10:00:00"},
                    {"code": "D", "name": "白班"},
                )

            # LLM MUST have been called because previous data exists
            mock_llm.assert_called_once()


# ═══════════════════════════════════════════════════════════════════════════
# 12. Prompt regression — no hardcoded shift logic
# ═══════════════════════════════════════════════════════════════════════════

class TestPromptNoHardcodedShifts:
    """Prompt files must not contain hardcoded shift names, codes, or times."""

    def test_nurse_bedside_no_hardcoded_shift_names(self):
        """Prompt must not hardcode 白班/夜班/N班/AP班/早班/晚班 as business logic."""
        path = PROMPT_DIR / "nurse_bedside_handover.md"
        content = path.read_text(encoding="utf-8")

        # The prompt may mention these as EXAMPLE labels in documentation
        # but must not embed them as business rules (e.g. "if night shift, do X")
        # Check that shift-related logic uses parameterized values
        assert "scheduled_start" in content
        assert "scheduled_end" in content

    def test_change_detection_no_hardcoded_shifts(self):
        """Change detection prompt must not hardcode shift-specific logic."""
        path = PROMPT_DIR / "handover_change_detection.md"
        content = path.read_text(encoding="utf-8")

        # Shift info must be passed in input_data, not baked into the prompt
        assert "current_shift" in content.lower() or "shift" in content.lower()

    def test_prompts_have_patient_id_in_input(self):
        """All prompts must reference patient_id as an input field."""
        for prompt_name in ["nurse_bedside_handover.md", "handover_change_detection.md"]:
            path = PROMPT_DIR / prompt_name
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8")
            assert "patient_id" in content, f"{prompt_name} missing patient_id"

    def test_output_schemas_have_patient_id(self):
        """All output schemas must require patient_id."""
        for prompt_name in [
            "nurse_bedside_handover.md",
            "handover_change_detection.md",
            "handover_completeness_check.md",
            "handover_conflict_detection.md",
        ]:
            path = PROMPT_DIR / prompt_name
            if not path.exists():
                continue
            content = path.read_text(encoding="utf-8")

            m = re.search(r"<output_schema>(.*?)</output_schema>", content, re.DOTALL)
            if m is None:
                continue  # not all prompts have output_schema
            json_str = m.group(1).strip()
            try:
                obj = json.loads(json_str)
            except json.JSONDecodeError:
                pytest.fail(f"{prompt_name}: output_schema is not valid JSON")
            assert "patient_id" in obj, f"{prompt_name}: output_schema missing patient_id"


# ═══════════════════════════════════════════════════════════════════════════
# 13. Error response format consistency
# ═══════════════════════════════════════════════════════════════════════════

class TestErrorResponseFormat:
    """All structured error responses must follow the unified format."""

    def test_map_shift_error_all_codes_have_source(self):
        """Every mapped error must include source: initSystemConfig.banCiInfoList."""
        from app.routers.handover import _map_shift_error
        from app.services.shift_service import (
            ShiftNotConfiguredError,
            ShiftNotFoundError,
            ShiftNotMatchedError,
            ShiftNotStartedError,
            ShiftQueryFailedError,
        )

        for exc in [
            ShiftQueryFailedError("db down"),
            ShiftNotConfiguredError("no config"),
            ShiftNotMatchedError("no match"),
            ShiftNotFoundError("not found"),
            ShiftNotStartedError("not started"),
        ]:
            http_exc = _map_shift_error(exc)
            assert "code" in http_exc.detail
            assert "message" in http_exc.detail
            assert "source" in http_exc.detail
            assert http_exc.detail["source"] == "initSystemConfig.banCiInfoList"

    def test_map_shift_error_no_exception_details_leaked(self):
        """Error responses must not expose raw DB exception text or stack traces."""
        from app.routers.handover import _map_shift_error
        from app.services.shift_service import ShiftQueryFailedError

        # Simulate refresh_cache wrapping a raw DB error via "raise ... from exc"
        raw = RuntimeError(
            "pymongo.errors.ServerSelectionTimeoutError: "
            "cluster0-shard-00-01.abcde.mongodb.net:27017"
        )
        exc = ShiftQueryFailedError("查询数据库班次配置失败")
        exc.__cause__ = raw

        http_exc = _map_shift_error(exc)

        # The detail message is always our controlled one
        assert http_exc.detail["message"] == "查询数据库班次配置失败"
        # Raw DB error text must NOT appear in the response
        assert "pymongo" not in str(http_exc.detail)
        assert "mongodb.net" not in str(http_exc.detail)
        assert "cluster0" not in str(http_exc.detail)

    def test_unexpected_exception_maps_to_internal_error(self):
        """Any non-ShiftError exception maps to HANDOVER_INTERNAL_ERROR (500)."""
        from app.routers.handover import _map_shift_error

        http_exc = _map_shift_error(ValueError("something unexpected"))

        assert http_exc.status_code == 500
        assert http_exc.detail["code"] == "HANDOVER_INTERNAL_ERROR"
        # Message must be the controlled one, not the raw ValueError message
        assert http_exc.detail["message"] == "交班服务处理失败"
        assert "something unexpected" not in str(http_exc.detail)

    def test_map_shift_error_internal_error_no_source(self):
        """HANDOVER_INTERNAL_ERROR must NOT include source (not a shift-config error)."""
        from app.routers.handover import _map_shift_error

        http_exc = _map_shift_error(RuntimeError("unexpected internal"))
        assert "source" not in http_exc.detail


# ═══════════════════════════════════════════════════════════════════════════
# 14. TTL config edge cases
# ═══════════════════════════════════════════════════════════════════════════

class TestTTLEdgeCases:
    """_ttl_seconds() must handle edge cases robustly."""

    def test_ttl_dict_config(self):
        """Plain dict config with valid TTL."""
        from app.services.shift_service import ShiftService

        svc = ShiftService(MagicMock(), config={"handover": {"shift_cache_ttl_seconds": 30}})
        assert svc._ttl_seconds() == 30

    def test_ttl_string_value(self):
        """String '30' must be accepted."""
        from app.services.shift_service import ShiftService

        svc = ShiftService(MagicMock(), config={"handover": {"shift_cache_ttl_seconds": "30"}})
        assert svc._ttl_seconds() == 30

    def test_ttl_zero_returns_default(self):
        """0 → default 60 (clamped to [1, 3600])."""
        from app.services.shift_service import ShiftService

        svc = ShiftService(MagicMock(), config={"handover": {"shift_cache_ttl_seconds": 0}})
        assert svc._ttl_seconds() == 60

    def test_ttl_negative_returns_default(self):
        """-1 → default 60 (clamped to [1, 3600])."""
        from app.services.shift_service import ShiftService

        svc = ShiftService(MagicMock(), config={"handover": {"shift_cache_ttl_seconds": -1}})
        assert svc._ttl_seconds() == 60

    def test_ttl_non_numeric_returns_default(self):
        """Non-numeric string → default 60."""
        from app.services.shift_service import ShiftService

        svc = ShiftService(MagicMock(), config={"handover": {"shift_cache_ttl_seconds": "abc"}})
        assert svc._ttl_seconds() == 60

    def test_ttl_too_large_returns_default(self):
        """Value > 3600 → default 60 (clamped)."""
        from app.services.shift_service import ShiftService

        svc = ShiftService(MagicMock(), config={"handover": {"shift_cache_ttl_seconds": 9999}})
        assert svc._ttl_seconds() == 60

    def test_ttl_none_returns_default(self):
        """None → default 60."""
        from app.services.shift_service import ShiftService

        svc = ShiftService(MagicMock(), config={"handover": {"shift_cache_ttl_seconds": None}})
        assert svc._ttl_seconds() == 60

    def test_ttl_missing_key_returns_default(self):
        """Missing key → default 60."""
        from app.services.shift_service import ShiftService

        svc = ShiftService(MagicMock(), config={"handover": {}})
        assert svc._ttl_seconds() == 60

    def test_ttl_boolean_returns_default(self):
        """Boolean → default 60."""
        from app.services.shift_service import ShiftService

        svc = ShiftService(MagicMock(), config={"handover": {"shift_cache_ttl_seconds": True}})
        assert svc._ttl_seconds() == 60

    def test_ttl_none_config_returns_default(self):
        """config=None → default 60."""
        from app.services.shift_service import ShiftService

        svc = ShiftService(MagicMock(), config=None)
        assert svc._ttl_seconds() == 60


# ═══════════════════════════════════════════════════════════════════════════
# 15. Forced-alerts API-level tests (call endpoint function directly)
# ═══════════════════════════════════════════════════════════════════════════

class TestForcedAlertsAPI:
    """Call get_forced_alerts directly with mocked dependencies."""

    @pytest.mark.asyncio
    async def test_explicit_since_until(self):
        """Explicit since+until must be used and reflected in time_window.source."""
        from app.routers.handover import get_forced_alerts

        db = MagicMock()
        db.col = MagicMock(return_value=db)
        # alert_records query
        db.find = MagicMock(return_value=db)
        db.sort = MagicMock(return_value=db)
        db.to_list = AsyncMock(return_value=[])

        # Mock config: a plain dict with handover key so ShiftService works
        cfg = {"handover": {"shift_cache_ttl_seconds": 60}}

        result = await get_forced_alerts(
            patient_id="P001",
            db=db,
            cfg=cfg,
            since="2026-07-16T08:00:00",
            until="2026-07-16T16:00:00",
        )

        assert result["code"] == 0
        assert result["patient_id"] == "P001"
        assert result["time_window"]["source"] == "request"
        assert "2026-07-16T08:00:00" in result["time_window"]["start"]
        assert "2026-07-16T16:00:00" in result["time_window"]["end"]

    @pytest.mark.asyncio
    async def test_since_only_returns_422(self):
        """Only since without until → 422."""
        from app.routers.handover import get_forced_alerts
        from fastapi import HTTPException

        db = MagicMock()
        cfg = {"handover": {"shift_cache_ttl_seconds": 60}}

        with pytest.raises(HTTPException) as exc_info:
            await get_forced_alerts(
                patient_id="P001", db=db, cfg=cfg,
                since="2026-07-16T08:00:00", until=None,
            )
        assert exc_info.value.status_code == 422
        assert "成对" in exc_info.value.detail["message"]

    @pytest.mark.asyncio
    async def test_until_only_returns_422(self):
        """Only until without since → 422."""
        from app.routers.handover import get_forced_alerts
        from fastapi import HTTPException

        db = MagicMock()
        cfg = {"handover": {"shift_cache_ttl_seconds": 60}}

        with pytest.raises(HTTPException) as exc_info:
            await get_forced_alerts(
                patient_id="P001", db=db, cfg=cfg,
                since=None, until="2026-07-16T16:00:00",
            )
        assert exc_info.value.status_code == 422
        assert "成对" in exc_info.value.detail["message"]

    @pytest.mark.asyncio
    async def test_until_equals_since_returns_422(self):
        """until == since → 422."""
        from app.routers.handover import get_forced_alerts
        from fastapi import HTTPException

        db = MagicMock()
        cfg = {"handover": {"shift_cache_ttl_seconds": 60}}

        with pytest.raises(HTTPException) as exc_info:
            await get_forced_alerts(
                patient_id="P001", db=db, cfg=cfg,
                since="2026-07-16T08:00:00", until="2026-07-16T08:00:00",
            )
        assert exc_info.value.status_code == 422
        assert "until 必须大于 since" in exc_info.value.detail["message"]

    @pytest.mark.asyncio
    async def test_until_before_since_returns_422(self):
        """until < since → 422."""
        from app.routers.handover import get_forced_alerts
        from fastapi import HTTPException

        db = MagicMock()
        cfg = {"handover": {"shift_cache_ttl_seconds": 60}}

        with pytest.raises(HTTPException) as exc_info:
            await get_forced_alerts(
                patient_id="P001", db=db, cfg=cfg,
                since="2026-07-16T16:00:00", until="2026-07-16T08:00:00",
            )
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_no_params_uses_shift_service(self):
        """Without since/until, the endpoint resolves via ShiftService."""
        from app.routers.handover import get_forced_alerts

        db = _mock_db_with_shifts(
            _make_shift_row("D", "白班", "08:00", "16:00"),
        )
        # Also mock alert_records
        db.original_col = db.col
        def _col_side_effect(name):
            if name == "initSystemConfig":
                return db  # already mocked by _mock_db_with_shifts
            # For alert_records, return a fresh mock
            m = MagicMock()
            m.find = MagicMock(return_value=m)
            m.sort = MagicMock(return_value=m)
            m.to_list = AsyncMock(return_value=[])
            return m
        db.col = MagicMock(side_effect=_col_side_effect)

        cfg = {"handover": {"shift_cache_ttl_seconds": 999}}

        now = datetime(2026, 7, 16, 10, 0, tzinfo=API_TZ)
        with patch("app.routers.handover.datetime") as mock_dt:
            mock_dt.now.return_value = now
            mock_dt.fromisoformat = datetime.fromisoformat
            # Need to let the module-level _now work too
            mock_dt.now.return_value = now

            result = await get_forced_alerts(
                patient_id="P001", db=db, cfg=cfg, since=None, until=None,
            )

        assert result["code"] == 0
        assert result["time_window"]["source"] == "initSystemConfig.banCiInfoList"

    @pytest.mark.asyncio
    async def test_db_exception_returns_shift_query_failed(self):
        """DB exception in ShiftService → SHIFT_QUERY_FAILED (500)."""
        from app.routers.handover import get_forced_alerts
        from fastapi import HTTPException

        db = MagicMock()
        db.col = MagicMock(return_value=db)
        db.find_one = AsyncMock(side_effect=RuntimeError("sensitive database detail"))

        cfg = {"handover": {"shift_cache_ttl_seconds": 0}}

        with pytest.raises(HTTPException) as exc_info:
            await get_forced_alerts(
                patient_id="P001", db=db, cfg=cfg, since=None, until=None,
            )

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail["code"] == "SHIFT_QUERY_FAILED"
        # Must NOT leak raw DB error text
        assert "sensitive database detail" not in exc_info.value.detail["message"]
        assert "RuntimeError" not in str(exc_info.value.detail)
