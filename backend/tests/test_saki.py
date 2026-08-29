"""S-AKI 单病种科研中心 - 单元测试。"""
from __future__ import annotations

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock


def _mock_cursor(to_list_result=None):
    """创建一个模拟 MongoDB cursor，支持 .sort().to_list() 和 .limit().to_list() 链式调用。"""
    to_list_result = to_list_result or []
    cursor = MagicMock()
    cursor.to_list = AsyncMock(return_value=to_list_result)
    cursor.sort.return_value = cursor
    cursor.limit.return_value = cursor
    cursor.skip.return_value = cursor
    return cursor


def _make_mock_db(patient_doc=None, lab_docs=None, drug_docs=None, crrt_docs=None, vital_docs=None):
    """构建符合 DatabaseManager 接口的 mock。db.col() 是同步的。"""
    lab_docs = lab_docs or []
    drug_docs = drug_docs or []
    crrt_docs = crrt_docs or []
    vital_docs = vital_docs or []

    def _col(name):
        mock = MagicMock()
        mock.find_one = AsyncMock(return_value=patient_doc if name == "patient" else None)
        mock.count_documents = AsyncMock(return_value=0)
        mock.insert_one = AsyncMock()
        mock.delete_one = AsyncMock(return_value=MagicMock(deleted_count=0))
        mock.delete_many = MagicMock(deleted_count=0)

        if name == "labResult":
            mock.find.return_value = _mock_cursor(lab_docs)
        elif name == "drug":
            mock.find.return_value = _mock_cursor(drug_docs)
        elif name == "crrt":
            mock.find.return_value = _mock_cursor(crrt_docs)
        elif name == "vitalSign":
            mock.find.return_value = _mock_cursor(vital_docs)
        elif name == "saki_cohorts":
            mock.find.return_value = _mock_cursor([])
        elif name == "saki_audit_log":
            mock.find.return_value = _mock_cursor([])
        else:
            mock.find.return_value = _mock_cursor([])
        return mock

    db = MagicMock()
    db.col = _col
    return db


# ---- 免责声明 ----
class TestDisclaimer:
    def test_texts(self):
        from app.services.saki.disclaimer import DISCLAIMER, PHENOTYPE_DISCLAIMER, EXPORT_DISCLAIMER, ANALYSIS_DISCLAIMER, LLM_DISCLAIMER
        assert "科研" in DISCLAIMER
        assert "不替代医生" in DISCLAIMER
        assert "规则引擎" in PHENOTYPE_DISCLAIMER
        assert "脱敏" in EXPORT_DISCLAIMER
        assert "因果推断" in ANALYSIS_DISCLAIMER
        assert "不使用大语言模型" in LLM_DISCLAIMER


# ---- 字段映射 ----
class TestFieldMapping:
    def test_defaults_loaded(self):
        from app.services.saki.field_mapping import DEFAULT_ENTRIES
        assert len(DEFAULT_ENTRIES) > 0
        assert {e.collection for e in DEFAULT_ENTRIES} >= {"patient", "labResult", "vitalSign"}

    @pytest.mark.asyncio
    async def test_resolve_patient_field(self):
        from app.services.saki.field_mapping import FieldMappingService
        fields = await FieldMappingService(None).resolve_field("patient", "patient_id")
        assert "hisPid" in fields

    @pytest.mark.asyncio
    async def test_resolve_lab_field(self):
        from app.services.saki.field_mapping import FieldMappingService
        fields = await FieldMappingService(None).resolve_field("labResult", "creatinine")
        assert "cr" in fields

    @pytest.mark.asyncio
    async def test_all_mappings(self):
        from app.services.saki.field_mapping import FieldMappingService
        mappings = await FieldMappingService(None).get_all_mappings()
        assert len(mappings) > 20


# ---- 脓毒症表型 ----
class TestSepsisPhenotype:
    def test_version(self):
        from app.services.saki.sepsis_phenotype import VERSION, RULE_SOURCE
        assert "v2" in VERSION
        assert "Sepsis" in RULE_SOURCE

    @pytest.mark.asyncio
    async def test_missing_patient(self):
        from app.services.saki.sepsis_phenotype import SepsisPhenotypeCalculator
        result = await SepsisPhenotypeCalculator().calculate(_make_mock_db(), "x")
        assert result["is_sepsis"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_with_patient_no_labs(self):
        from app.services.saki.sepsis_phenotype import SepsisPhenotypeCalculator
        db = _make_mock_db(patient_doc={"_id": "p1", "clinicalDiagnosis": "脓毒症"})
        result = await SepsisPhenotypeCalculator().calculate(db, "p1")
        assert "is_sepsis" in result and "sofa_score" in result and "disclaimer" in result


# ---- AKI 表型 ----
class TestAKIPhenotype:
    def test_version(self):
        from app.services.saki.aki_phenotype import VERSION, RULE_SOURCE
        assert "v1" in VERSION and "KDIGO" in RULE_SOURCE

    def test_unit_conversion(self):
        from app.services.saki.aki_phenotype import _to_umol_l
        assert _to_umol_l(1.0, "mg/dL") == pytest.approx(88.4)
        assert _to_umol_l(100, "umol/L") == 100
        assert _to_umol_l(1.5, "") == pytest.approx(1.5 * 88.4)

    @pytest.mark.asyncio
    async def test_missing_patient(self):
        from app.services.saki.aki_phenotype import AKIPhenotypeCalculator
        result = await AKIPhenotypeCalculator().calculate(_make_mock_db(), "x")
        assert result["aki_stage"] == 0 and "error" in result

    @pytest.mark.asyncio
    async def test_no_cr_data(self):
        from app.services.saki.aki_phenotype import AKIPhenotypeCalculator
        db = _make_mock_db(patient_doc={"_id": "p1"})
        result = await AKIPhenotypeCalculator().calculate(db, "p1")
        assert result["aki_stage"] == 0


# ---- S-AKI 标识器 ----
class TestSAKICaseIdentifier:
    def test_version(self):
        from app.services.saki.saki_identifier import VERSION, TEMPORAL_WINDOW_HOURS
        assert "v1" in VERSION and TEMPORAL_WINDOW_HOURS == 168

    @pytest.mark.asyncio
    async def test_missing_patient(self):
        from app.services.saki.saki_identifier import SAKICaseIdentifier
        db = _make_mock_db(patient_doc=None)
        result = await SAKICaseIdentifier().identify(db, "missing")
        assert "error" in result

    def test_temporal_in_window(self):
        from app.services.saki.saki_identifier import SAKICaseIdentifier
        r = SAKICaseIdentifier()._assess_temporal_association(
            {"calc_time": datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)},
            {"calc_time": datetime(2024, 1, 2, 12, 0, tzinfo=timezone.utc)},
        )
        assert r["associated"] is True and r["time_delta_hours"] == 24.0

    def test_temporal_out_of_window(self):
        from app.services.saki.saki_identifier import SAKICaseIdentifier
        r = SAKICaseIdentifier()._assess_temporal_association(
            {"calc_time": datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)},
            {"calc_time": datetime(2024, 2, 1, 0, 0, tzinfo=timezone.utc)},
        )
        assert r["associated"] is False

    @pytest.mark.asyncio
    async def test_statistics_empty(self):
        from app.services.saki.saki_identifier import SAKICaseIdentifier
        stats = await SAKICaseIdentifier().get_statistics(_make_mock_db())
        assert stats["total_cases"] == 0


# ---- 队列 ----
class TestCohortBuilder:
    @pytest.mark.asyncio
    async def test_build(self):
        from app.services.saki.cohort_builder import SAKICohortBuilder
        r = await SAKICohortBuilder().build_cohort(_make_mock_db(), {"is_saki": True}, "Test")
        assert r["name"] == "Test" and "cohort_id" in r

    @pytest.mark.asyncio
    async def test_delete(self):
        from app.services.saki.cohort_builder import SAKICohortBuilder
        r = await SAKICohortBuilder().delete_cohort(_make_mock_db(), "x")
        assert isinstance(r, bool)


# ---- 审计 ----
class TestAuditService:
    @pytest.mark.asyncio
    async def test_log(self):
        from app.services.saki.audit_service import SAKIAuditService
        eid = await SAKIAuditService().log_event(_make_mock_db(), "act", "res", "r1", "u1")
        assert eid


# ---- 路由 ----
class TestRouter:
    def test_prefix(self):
        from app.routers.saki import router
        assert router.prefix == "/api/disease-center/saki"

    def test_routes_count(self):
        from app.routers.saki import router
        assert len(router.routes) >= 25

    def test_key_endpoints(self):
        from app.routers.saki import router
        paths = [r.path for r in router.routes]
        assert any("health" in p for p in paths)
        assert any("disclaimer" in p for p in paths)
        assert any("analysis/table1" in p for p in paths)


# ---- 种子数据 ----
class TestSeedData:
    def test_diagnosis(self):
        from app.services.saki.seed_data import _gen_diagnosis
        assert len(_gen_diagnosis(True, True)) > 0

    def test_trajectory_aki(self):
        from app.services.saki.seed_data import _gen_creatinine_trajectory
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        traj = _gen_creatinine_trajectory(80.0, True, True, now - timedelta(days=3), now)
        assert len(traj) > 0 and max(v for _, v in traj) > 80.0

    def test_trajectory_no_aki(self):
        from app.services.saki.seed_data import _gen_creatinine_trajectory
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        traj = _gen_creatinine_trajectory(80.0, False, False, now - timedelta(days=3), now)
        assert len(traj) > 0 and max(v for _, v in traj) < 120.0

