"""扫描器到病种病例的统一适配层。

禁止在每个 Scanner 中复制病例管理代码。
所有 Scanner 通过此 Bridge 创建/更新 DiseaseCase 和 CaseEvidence。
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from app.models.disease_center import (
    DiseaseCaseStatus,
    EvidenceType,
    ConfirmationAction,
    compute_evidence_hash,
)
from app.models.disease_center.clinical_conclusion import ClinicalConclusion, ConclusionLevel
from app.repositories import (
    CaseRepository,
    EvidenceRepository,
    ConclusionRepository,
    PathwayInstanceRepository,
    PathwayTaskRepository,
)

logger = logging.getLogger(__name__)

_case_repo = CaseRepository()
_evidence_repo = EvidenceRepository()
_conclusion_repo = ConclusionRepository()
_pathway_repo = PathwayInstanceRepository()
_task_repo = PathwayTaskRepository()


def _gen_id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def upsert_case_from_scanner(
    patient_id: str,
    disease_code: str,
    encounter_id: str = "",
    episode_no: int = 1,
    disease_id: str = "",
    disease_name: str = "",
    scanner_id: str = "",
    rule_id: str = "",
    rule_version: str = "",
    patient_name: str = "",
    bed: str = "",
    dept: str = "",
    risk_level: str = "",
    screening_score: Optional[float] = None,
    confidence: Optional[float] = None,
    clinical_summary: Optional[dict[str, Any]] = None,
    source_alert_id: str = "",
) -> dict[str, Any]:
    """从扫描器创建或更新病种病例。

    使用 MongoDB 原子 upsert 防止并发重复。
    去重维度：patient_id + encounter_id + disease_code + episode_no

    Returns:
        病例字典，包含 id 字段
    """
    now = _now()

    create_fields = {
        "id": _gen_id(),
        "status": DiseaseCaseStatus.SCREENING,
        "disease_id": disease_id,
        "disease_name": disease_name,
        "scanner_id": scanner_id,
        "rule_id": rule_id,
        "rule_version": rule_version,
        "patient_name": patient_name,
        "bed": bed,
        "dept": dept,
        "created_by": "scanner",
    }

    update_fields: dict[str, Any] = {
        "last_evaluated_at": now,
    }
    if scanner_id:
        update_fields["scanner_id"] = scanner_id
    if rule_id:
        update_fields["rule_id"] = rule_id
    if rule_version:
        update_fields["rule_version"] = rule_version
    if risk_level:
        update_fields["risk_level"] = risk_level
    if screening_score is not None:
        update_fields["screening_score"] = screening_score
    if confidence is not None:
        update_fields["confidence"] = confidence
    if clinical_summary:
        update_fields["clinical_summary"] = clinical_summary
    if patient_name:
        update_fields["patient_name"] = patient_name
    if bed:
        update_fields["bed"] = bed
    if dept:
        update_fields["dept"] = dept

    # 如果没有 encounter_id，使用兼容旧逻辑的 upsert
    if not encounter_id:
        existing = await _case_repo.find_active_by_patient_disease(
            patient_id, disease_code
        )
        if existing:
            await _case_repo.update(existing["id"], update_fields)
            if source_alert_id and source_alert_id not in existing.get("source_alert_ids", []):
                await _case_repo.update(existing["id"], {
                    "source_alert_ids": existing.get("source_alert_ids", []) + [source_alert_id]
                })
            existing.update(update_fields)
            return existing
        else:
            case_data = {**create_fields, **update_fields}
            case_data["patient_id"] = patient_id
            case_data["disease_code"] = disease_code
            case_data["first_detected_at"] = now
            case_data["source_alert_ids"] = [source_alert_id] if source_alert_id else []
            await _case_repo.create(case_data)
            return case_data

    # 使用原子 upsert
    result = await _case_repo.upsert_case(
        patient_id=patient_id,
        encounter_id=encounter_id,
        disease_code=disease_code,
        episode_no=episode_no,
        create_fields=create_fields,
        update_fields=update_fields,
    )

    # 关联 Alert ID
    if source_alert_id:
        alert_ids = result.get("source_alert_ids", [])
        if source_alert_id not in alert_ids:
            await _case_repo.update(result["id"], {
                "source_alert_ids": alert_ids + [source_alert_id]
            })
            result["source_alert_ids"] = alert_ids + [source_alert_id]

    return result


async def add_or_update_evidence(
    case_id: str,
    patient_id: str,
    evidence_type: str,
    raw_value: Any,
    observed_at: datetime,
    source_collection: str = "",
    source_record_id: str = "",
    source_field: str = "",
    raw_unit: str = "",
    normalized_value: Optional[float] = None,
    normalized_unit: str = "",
    rule_id: str = "",
    rule_version: str = "",
    threshold: Optional[float] = None,
    threshold_operator: str = "",
    matched: bool = False,
    confidence: float = 1.0,
    quality_flags: Optional[list[str]] = None,
    explanation: str = "",
    disease_code: str = "",
    feature_name: str = "",
    criterion: Optional[dict[str, Any]] = None,
    guideline_source: str = "",
    guideline_version: str = "",
    guideline_reference: str = "",
    baseline_value: Any = None,
    baseline_source: str = "",
    baseline_confidence: Optional[float] = None,
    aggregation_method: str = "",
    time_window: Optional[dict[str, Any]] = None,
) -> str:
    """添加或更新病例证据（幂等）。

    使用 evidence_hash 实现幂等写入。
    """
    evidence_hash = compute_evidence_hash(
        case_id, source_collection, source_record_id, rule_id, rule_version
    )

    evidence_data = {
        "id": _gen_id(),
        "patient_id": patient_id,
        "case_id": case_id,
        "disease_code": disease_code,
        "evidence_type": evidence_type,
        "source_collection": source_collection,
        "source_record_id": source_record_id,
        "source_field": source_field,
        "raw_value": raw_value,
        "raw_unit": raw_unit,
        "normalized_value": normalized_value,
        "normalized_unit": normalized_unit,
        "observed_at": observed_at,
        "rule_id": rule_id,
        "rule_version": rule_version,
        "threshold": threshold,
        "threshold_operator": threshold_operator,
        "matched": matched,
        "confidence": confidence,
        "quality_flags": quality_flags or [],
        "explanation": explanation,
        "evidence_hash": evidence_hash,
        "feature_name": feature_name,
        "criterion": criterion or {},
        "guideline_source": guideline_source,
        "guideline_version": guideline_version,
        "guideline_reference": guideline_reference,
        "baseline_value": baseline_value,
        "baseline_source": baseline_source,
        "baseline_confidence": baseline_confidence,
        "aggregation_method": aggregation_method,
        "time_window": time_window or {},
    }

    return await _evidence_repo.upsert_by_hash(evidence_data)


async def mark_screen_positive(
    case_id: str,
    screening_score: Optional[float] = None,
    confidence: Optional[float] = None,
    risk_level: str = "warning",
    clinical_summary: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """标记病例为筛查阳性。

    仅当病例处于 screening 状态时转换。
    """
    case = await _case_repo.find_by_id(case_id)
    if not case:
        raise ValueError(f"病例不存在: {case_id}")

    current = case.get("status", "")
    if current == DiseaseCaseStatus.SCREENING:
        now = _now()
        updates = {
            "status": DiseaseCaseStatus.SCREEN_POSITIVE,
            "screen_positive_at": now,
            "updated_at": now,
        }
        if screening_score is not None:
            updates["screening_score"] = screening_score
        if confidence is not None:
            updates["confidence"] = confidence
        if risk_level:
            updates["risk_level"] = risk_level
        if clinical_summary:
            updates["clinical_summary"] = clinical_summary

        await _case_repo.update(case_id, updates)
        case.update(updates)

    return case


async def move_to_pending_review(case_id: str) -> dict[str, Any]:
    """将筛查阳性病例移至待临床确认。"""
    case = await _case_repo.find_by_id(case_id)
    if not case:
        raise ValueError(f"病例不存在: {case_id}")

    current = case.get("status", "")
    if current == DiseaseCaseStatus.SCREEN_POSITIVE:
        now = _now()
        updates = {
            "status": DiseaseCaseStatus.PENDING_REVIEW,
            "updated_at": now,
        }
        await _case_repo.update(case_id, updates)
        case.update(updates)

    return case


async def sync_alert_reference(case_id: str, alert_id: str) -> None:
    """将旧 Alert ID 关联到 DiseaseCase。"""
    case = await _case_repo.find_by_id(case_id)
    if not case:
        return

    alert_ids = case.get("source_alert_ids", [])
    if alert_id not in alert_ids:
        alert_ids.append(alert_id)
        await _case_repo.update(case_id, {"source_alert_ids": alert_ids})


async def reopen_on_new_evidence(
    case_id: str,
    new_evidence_hash: str,
    reason: str = "新证据触发重开",
) -> dict[str, Any]:
    """在新证据出现时重开已完成或已排除的病例。

    保留原排除记录。
    """
    case = await _case_repo.find_by_id(case_id)
    if not case:
        raise ValueError(f"病例不存在: {case_id}")

    current = case.get("status", "")
    if current not in (
        DiseaseCaseStatus.COMPLETED,
        DiseaseCaseStatus.EXCLUDED,
    ):
        return case

    # 检查是否为实质性新证据
    old_hash = case.get("last_evidence_hash", "")
    if new_evidence_hash == old_hash:
        return case

    now = _now()
    updates = {
        "status": DiseaseCaseStatus.REOPENED,
        "reopened_at": now,
        "last_evidence_hash": new_evidence_hash,
        "last_material_change_at": now,
        "updated_at": now,
    }

    await _case_repo.update(case_id, updates)
    case.update(updates)

    # 记录重开事件
    from app.repositories import ConfirmationRepository
    confirm_repo = ConfirmationRepository()
    await confirm_repo.create({
        "id": _gen_id(),
        "case_id": case_id,
        "patient_id": case.get("patient_id", ""),
        "action": ConfirmationAction.STATUS_CHANGE,
        "previous_status": current,
        "new_status": DiseaseCaseStatus.REOPENED,
        "operator_id": "system",
        "operator_name": "扫描器",
        "reason": reason,
        "created_at": now,
    })

    return case


async def sync_pathway_from_bundle(
    case_id: str,
    patient_id: str,
    disease_id: str,
    disease_code: str,
    bundle_elements: list[dict[str, Any]],
    deadline_1h: Optional[datetime] = None,
    deadline_3h: Optional[datetime] = None,
) -> dict[str, Any]:
    """将 Sepsis Bundle Tracker 同步为 PathwayInstance 和 PathwayTask。

    如果已有活动路径实例，更新任务状态；
    否则创建新实例。
    """
    now = _now()

    # 查找或创建路径实例
    instance = await _pathway_repo.find_by_case(case_id)
    if not instance:
        instance_id = _gen_id()
        instance_data = {
            "id": instance_id,
            "case_id": case_id,
            "patient_id": patient_id,
            "pathway_id": f"sepsis_hour1_bundle",
            "disease_id": disease_id,
            "disease_code": disease_code,
            "status": "active",
            "started_at": now,
            "deadline_1h": deadline_1h,
            "deadline_3h": deadline_3h,
        }
        await _pathway_repo.create(instance_data)
        instance = instance_data

        # 更新病例的路径关联
        await _case_repo.update(case_id, {
            "pathway_instance_id": instance_id,
        })

    instance_id = instance["id"]

    # 同步任务
    for element in bundle_elements:
        task_key = element.get("key", "")
        if not task_key:
            continue

        # 查找现有任务
        existing_tasks = await _task_repo.find_by_instance(instance_id)
        existing_task = next(
            (t for t in existing_tasks if t.get("task_key") == task_key),
            None
        )

        task_data = {
            "task_key": task_key,
            "name": element.get("label", task_key),
            "description": element.get("description", ""),
            "applicability": element.get("applicability", "review_pending"),
            "execution_status": element.get("execution_status", "pending"),
            "evidence_ids": element.get("evidence_ids", []),
            "target_value": element.get("target_value"),
            "target_unit": element.get("target_unit", ""),
            "actual_value": element.get("actual_value"),
            "actual_unit": element.get("actual_unit", ""),
        }

        if existing_task:
            await _task_repo.update(existing_task["id"], task_data)
        else:
            task_data.update({
                "id": _gen_id(),
                "instance_id": instance_id,
                "case_id": case_id,
                "patient_id": patient_id,
                "task_type": "bundle_item",
                "due_at": deadline_1h,
            })
            await _task_repo.create(task_data)

    return instance


async def add_conclusion(
    case_id: str,
    patient_id: str,
    conclusion_code: str,
    conclusion_label: str,
    conclusion_level: str = "screening",
    supporting_evidence_ids: Optional[list[str]] = None,
    contradicting_evidence_ids: Optional[list[str]] = None,
    missing_evidence: Optional[list[str]] = None,
    rule_id: str = "",
    rule_version: str = "",
    confidence: float = 0.0,
    detail: Optional[dict[str, Any]] = None,
) -> str:
    """添加临床结论。

    如果已有同 code 的当前结论，标记为 superseded 后创建新结论。
    """
    # 查找现有同 code 结论
    existing = await _conclusion_repo.find_by_case(case_id, current_only=True)
    for c in existing:
        if c.get("conclusion_code") == conclusion_code:
            await _conclusion_repo.supersede(c["id"], "")

    conclusion_id = _gen_id()
    conclusion_data = {
        "id": conclusion_id,
        "case_id": case_id,
        "patient_id": patient_id,
        "conclusion_code": conclusion_code,
        "conclusion_label": conclusion_label,
        "conclusion_level": conclusion_level,
        "supporting_evidence_ids": supporting_evidence_ids or [],
        "contradicting_evidence_ids": contradicting_evidence_ids or [],
        "missing_evidence": missing_evidence or [],
        "rule_id": rule_id,
        "rule_version": rule_version,
        "confidence": confidence,
        "requires_clinician_confirmation": True,
        "detail": detail or {},
        "generated_at": _now(),
    }

    await _conclusion_repo.create(conclusion_data)

    # 更新 superseded_by
    for c in existing:
        if c.get("conclusion_code") == conclusion_code:
            await _conclusion_repo.update(c["id"], {"superseded_by": conclusion_id})

    return conclusion_id
