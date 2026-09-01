"""Bridge 接口契约测试。

验证 DiseaseCaseBridge 的所有函数签名和基本功能。
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_upsert_case_from_scanner_creates_case(mongodb):
    """测试 upsert_case_from_scanner 创建新病例。"""
    from app.services.disease_case_bridge import upsert_case_from_scanner

    case = await upsert_case_from_scanner(
        patient_id="patient-001",
        disease_code="AKI",
        disease_name="急性肾损伤",
        encounter_id="enc-001",
        patient_name="张三",
        bed="5",
        dept="ICU",
        scanner_id="aki",
        rule_id="AKI_STAGE_2",
        rule_version="KDIGO_v2012",
        risk_level="high",
        source_alert_id="alert-001",
    )

    assert case is not None
    assert "id" in case
    assert case["patient_id"] == "patient-001"
    assert case["disease_code"] == "AKI"
    assert case["status"] == "screening"
    assert "alert-001" in case.get("source_alert_ids", [])


@pytest.mark.asyncio
async def test_upsert_case_from_scanner_upserts_existing(mongodb):
    """测试 upsert_case_from_scanner 更新已有病例。"""
    from app.services.disease_case_bridge import upsert_case_from_scanner

    # 第一次创建
    case1 = await upsert_case_from_scanner(
        patient_id="patient-001",
        disease_code="AKI",
        encounter_id="enc-001",
    )

    # 第二次更新
    case2 = await upsert_case_from_scanner(
        patient_id="patient-001",
        disease_code="AKI",
        encounter_id="enc-001",
        source_alert_id="alert-002",
    )

    assert case1["id"] == case2["id"]
    assert "alert-002" in case2.get("source_alert_ids", [])


@pytest.mark.asyncio
async def test_add_or_update_evidence_creates_evidence(mongodb):
    """测试 add_or_update_evidence 创建证据。"""
    from app.services.disease_case_bridge import upsert_case_from_scanner, add_or_update_evidence

    case = await upsert_case_from_scanner(
        patient_id="patient-001",
        disease_code="AKI",
        encounter_id="enc-001",
    )

    evidence_id = await add_or_update_evidence(
        case_id=case["id"],
        patient_id="patient-001",
        disease_code="AKI",
        evidence_type="lab_value",
        feature_name="creatinine",
        raw_value=180.5,
        raw_unit="μmol/L",
        observed_at=datetime.now(timezone.utc),
        source_collection="lab_report",
        source_record_id="cr-001",
        rule_id="AKI_STAGE_2",
        rule_version="KDIGO_v2012",
        matched=True,
    )

    assert evidence_id is not None
    assert isinstance(evidence_id, str)
    assert len(evidence_id) > 0


@pytest.mark.asyncio
async def test_add_or_update_evidence_is_idempotent(mongodb):
    """测试 add_or_update_evidence 幂等写入。"""
    from app.services.disease_case_bridge import upsert_case_from_scanner, add_or_update_evidence

    case = await upsert_case_from_scanner(
        patient_id="patient-001",
        disease_code="AKI",
        encounter_id="enc-001",
    )

    # 第一次写入
    id1 = await add_or_update_evidence(
        case_id=case["id"],
        patient_id="patient-001",
        evidence_type="lab_value",
        feature_name="creatinine",
        raw_value=180.5,
        raw_unit="μmol/L",
        observed_at=datetime.now(timezone.utc),
        source_collection="lab_report",
        source_record_id="cr-001",
        rule_id="AKI_STAGE_2",
        rule_version="KDIGO_v2012",
    )

    # 第二次写入（相同 hash）
    id2 = await add_or_update_evidence(
        case_id=case["id"],
        patient_id="patient-001",
        evidence_type="lab_value",
        feature_name="creatinine",
        raw_value=200.0,  # 更新值
        raw_unit="μmol/L",
        observed_at=datetime.now(timezone.utc),
        source_collection="lab_report",
        source_record_id="cr-001",
        rule_id="AKI_STAGE_2",
        rule_version="KDIGO_v2012",
    )

    # 应该返回相同的 ID（幂等）
    assert id1 == id2


@pytest.mark.asyncio
async def test_mark_screen_positive_transitions_to_pending_review(mongodb):
    """测试 mark_screen_positive 将病例从 screening 转到 pending_review。"""
    from app.services.disease_case_bridge import (
        upsert_case_from_scanner,
        mark_screen_positive,
    )
    from app.repositories import CaseRepository

    case = await upsert_case_from_scanner(
        patient_id="patient-001",
        disease_code="AKI",
        encounter_id="enc-001",
    )

    result = await mark_screen_positive(
        case_id=case["id"],
        risk_level="high",
    )

    # 验证状态已转到 pending_review
    repo = CaseRepository()
    updated = await repo.find_by_id(case["id"])
    assert updated["status"] == "pending_review"
    assert updated["risk_level"] == "high"


@pytest.mark.asyncio
async def test_add_conclusion_creates_conclusion(mongodb):
    """测试 add_conclusion 创建临床结论。"""
    from app.services.disease_case_bridge import upsert_case_from_scanner, add_conclusion

    case = await upsert_case_from_scanner(
        patient_id="patient-001",
        disease_code="AKI",
        encounter_id="enc-001",
    )

    conclusion_id = await add_conclusion(
        case_id=case["id"],
        patient_id="patient-001",
        conclusion_code="AKI_STAGE_2",
        conclusion_label="急性肾损伤KDIGO 2期",
        conclusion_level="screening",
        rule_id="AKI_STAGE_2",
        rule_version="KDIGO_v2012",
        confidence=0.8,
    )

    assert conclusion_id is not None
    assert isinstance(conclusion_id, str)


@pytest.mark.asyncio
async def test_sync_pathway_from_bundle_creates_instance(mongodb):
    """测试 sync_pathway_from_bundle 创建路径实例。"""
    from app.services.disease_case_bridge import upsert_case_from_scanner, sync_pathway_from_bundle

    case = await upsert_case_from_scanner(
        patient_id="patient-001",
        disease_code="SEPSIS",
        encounter_id="enc-001",
    )

    bundle_elements = [
        {"key": "blood_culture", "label": "血培养", "execution_status": "pending"},
        {"key": "lactate", "label": "乳酸检测", "execution_status": "pending"},
        {"key": "antibiotics", "label": "抗菌药物", "execution_status": "pending"},
    ]

    instance = await sync_pathway_from_bundle(
        case_id=case["id"],
        patient_id="patient-001",
        disease_id="",
        disease_code="SEPSIS",
        bundle_elements=bundle_elements,
    )

    assert instance is not None
    assert "id" in instance
    assert instance["case_id"] == case["id"]

    # 第二次同步不应创建新实例
    instance2 = await sync_pathway_from_bundle(
        case_id=case["id"],
        patient_id="patient-001",
        disease_id="",
        disease_code="SEPSIS",
        bundle_elements=bundle_elements,
    )

    assert instance["id"] == instance2["id"]


@pytest.mark.asyncio
async def test_alert_to_case_risk_mapping():
    """测试 ALERT_TO_CASE_RISK 映射。"""
    from app.services.disease_case_bridge import ALERT_TO_CASE_RISK

    assert ALERT_TO_CASE_RISK["info"] == "low"
    assert ALERT_TO_CASE_RISK["warning"] == "warning"
    assert ALERT_TO_CASE_RISK["high"] == "high"
    assert ALERT_TO_CASE_RISK["critical"] == "critical"
