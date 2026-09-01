"""Evidence 幂等性和历史测试。

验证：
- 同记录重复扫描只更新同一 Evidence
- 不同时间的记录生成不同 Evidence
- 业务 ID 创建后不变
- created_at 稳定
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_same_record_same_hash(mongodb):
    """相同源记录、相同规则产生相同 hash。"""
    from app.models.disease_center import compute_evidence_hash

    hash1 = compute_evidence_hash("case-1", "lab_report", "cr-001", "AKI_STAGE_2", "KDIGO_v2012")
    hash2 = compute_evidence_hash("case-1", "lab_report", "cr-001", "AKI_STAGE_2", "KDIGO_v2012")

    assert hash1 == hash2


@pytest.mark.asyncio
async def test_different_time_different_record(mongodb):
    """不同时间的肌酐产生不同 Evidence。"""
    from app.services.disease_case_bridge import upsert_case_from_scanner, add_or_update_evidence
    from app.repositories import EvidenceRepository

    case = await upsert_case_from_scanner(
        patient_id="p1", disease_code="AKI", encounter_id="e1",
    )

    # 第一次肌酐
    id1 = await add_or_update_evidence(
        case_id=case["id"],
        patient_id="p1",
        evidence_type="lab_value",
        feature_name="creatinine",
        raw_value=180.0,
        raw_unit="μmol/L",
        observed_at=datetime(2025, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
        source_collection="lab_report",
        source_record_id="cr-20250101",
        rule_id="AKI_STAGE_2",
        rule_version="KDIGO_v2012",
    )

    # 第二次肌酐（不同时间）
    id2 = await add_or_update_evidence(
        case_id=case["id"],
        patient_id="p1",
        evidence_type="lab_value",
        feature_name="creatinine",
        raw_value=200.0,
        raw_unit="μmol/L",
        observed_at=datetime(2025, 1, 2, 10, 0, 0, tzinfo=timezone.utc),
        source_collection="lab_report",
        source_record_id="cr-20250102",
        rule_id="AKI_STAGE_2",
        rule_version="KDIGO_v2012",
    )

    assert id1 != id2

    # 验证两条证据都存在
    repo = EvidenceRepository()
    e1 = await repo.find_by_id(id1)
    e2 = await repo.find_by_id(id2)

    assert e1 is not None
    assert e2 is not None
    assert e1["raw_value"] == 180.0
    assert e2["raw_value"] == 200.0


@pytest.mark.asyncio
async def test_same_record_different_rule_different_evidence(mongodb):
    """相同源记录、不同规则产生不同 Evidence。"""
    from app.services.disease_case_bridge import upsert_case_from_scanner, add_or_update_evidence

    case = await upsert_case_from_scanner(
        patient_id="p1", disease_code="AKI", encounter_id="e1",
    )

    id1 = await add_or_update_evidence(
        case_id=case["id"],
        patient_id="p1",
        evidence_type="lab_value",
        feature_name="creatinine",
        raw_value=180.0,
        raw_unit="μmol/L",
        observed_at=datetime.now(timezone.utc),
        source_collection="lab_report",
        source_record_id="cr-001",
        rule_id="AKI_STAGE_1",
        rule_version="KDIGO_v2012",
    )

    id2 = await add_or_update_evidence(
        case_id=case["id"],
        patient_id="p1",
        evidence_type="lab_value",
        feature_name="creatinine",
        raw_value=180.0,
        raw_unit="μmol/L",
        observed_at=datetime.now(timezone.utc),
        source_collection="lab_report",
        source_record_id="cr-001",
        rule_id="AKI_STAGE_2",
        rule_version="KDIGO_v2012",
    )

    assert id1 != id2


@pytest.mark.asyncio
async def test_evidence_id_stable_after_update(mongodb):
    """Evidence 业务 ID 创建后不变。"""
    from app.services.disease_case_bridge import upsert_case_from_scanner, add_or_update_evidence
    from app.repositories import EvidenceRepository

    case = await upsert_case_from_scanner(
        patient_id="p1", disease_code="AKI", encounter_id="e1",
    )

    # 第一次写入
    id1 = await add_or_update_evidence(
        case_id=case["id"],
        patient_id="p1",
        evidence_type="lab_value",
        feature_name="creatinine",
        raw_value=180.0,
        raw_unit="μmol/L",
        observed_at=datetime.now(timezone.utc),
        source_collection="lab_report",
        source_record_id="cr-001",
        rule_id="AKI_STAGE_2",
        rule_version="KDIGO_v2012",
    )

    # 第二次写入（更新值）
    id2 = await add_or_update_evidence(
        case_id=case["id"],
        patient_id="p1",
        evidence_type="lab_value",
        feature_name="creatinine",
        raw_value=200.0,
        raw_unit="μmol/L",
        observed_at=datetime.now(timezone.utc),
        source_collection="lab_report",
        source_record_id="cr-001",
        rule_id="AKI_STAGE_2",
        rule_version="KDIGO_v2012",
    )

    # ID 应该相同
    assert id1 == id2

    # 验证值已更新
    repo = EvidenceRepository()
    evidence = await repo.find_by_id(id1)
    assert evidence["raw_value"] == 200.0


@pytest.mark.asyncio
async def test_evidence_created_at_stable(mongodb):
    """created_at 在更新时不变。"""
    from app.services.disease_case_bridge import upsert_case_from_scanner, add_or_update_evidence
    from app.repositories import EvidenceRepository

    case = await upsert_case_from_scanner(
        patient_id="p1", disease_code="AKI", encounter_id="e1",
    )

    # 第一次写入
    id1 = await add_or_update_evidence(
        case_id=case["id"],
        patient_id="p1",
        evidence_type="lab_value",
        feature_name="creatinine",
        raw_value=180.0,
        raw_unit="μmol/L",
        observed_at=datetime.now(timezone.utc),
        source_collection="lab_report",
        source_record_id="cr-001",
        rule_id="AKI_STAGE_2",
        rule_version="KDIGO_v2012",
    )

    repo = EvidenceRepository()
    e1 = await repo.find_by_id(id1)
    created_at_1 = e1["created_at"]

    # 第二次写入（更新）
    import asyncio
    await asyncio.sleep(0.01)  # 确保时间差

    await add_or_update_evidence(
        case_id=case["id"],
        patient_id="p1",
        evidence_type="lab_value",
        feature_name="creatinine",
        raw_value=200.0,
        raw_unit="μmol/L",
        observed_at=datetime.now(timezone.utc),
        source_collection="lab_report",
        source_record_id="cr-001",
        rule_id="AKI_STAGE_2",
        rule_version="KDIGO_v2012",
    )

    e2 = await repo.find_by_id(id1)

    # created_at 应该不变
    assert e2["created_at"] == created_at_1


@pytest.mark.asyncio
async def test_evidence_preserves_raw_and_normalized(mongodb):
    """Evidence 保留原始值和标准化值。"""
    from app.services.disease_case_bridge import upsert_case_from_scanner, add_or_update_evidence
    from app.repositories import EvidenceRepository

    case = await upsert_case_from_scanner(
        patient_id="p1", disease_code="AKI", encounter_id="e1",
    )

    evidence_id = await add_or_update_evidence(
        case_id=case["id"],
        patient_id="p1",
        evidence_type="lab_value",
        feature_name="creatinine",
        raw_value=180.0,
        raw_unit="μmol/L",
        normalized_value=2.03,
        normalized_unit="mg/dL",
        observed_at=datetime.now(timezone.utc),
        source_collection="lab_report",
        source_record_id="cr-001",
        rule_id="AKI_STAGE_2",
        rule_version="KDIGO_v2012",
        baseline_value=90.0,
        baseline_source="historical",
        aggregation_method="latest",
        time_window={"hours": 48},
    )

    repo = EvidenceRepository()
    evidence = await repo.find_by_id(evidence_id)

    assert evidence["raw_value"] == 180.0
    assert evidence["raw_unit"] == "μmol/L"
    assert evidence["normalized_value"] == 2.03
    assert evidence["normalized_unit"] == "mg/dL"
    assert evidence["baseline_value"] == 90.0
    assert evidence["baseline_source"] == "historical"
    assert evidence["aggregation_method"] == "latest"
    assert evidence["time_window"] == {"hours": 48}
