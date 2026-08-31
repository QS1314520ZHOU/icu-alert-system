"""病种管理服务 - MongoDB 实现。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.models.disease_center import (
    DiseaseDefinition,
    DiseaseStatus,
    DiseaseRelation,
    RelationType,
    ClinicalPathway,
    ReviewTask,
    ReviewStatus,
    AuditEvent,
)
from app.repositories import (
    DiseaseRepository,
    ReviewRepository,
    AuditRepository,
    DiseaseRelationRepository,
    PathwayRepository,
)


# 仓储实例
_disease_repo = DiseaseRepository()
_review_repo = ReviewRepository()
_audit_repo = AuditRepository()
_relation_repo = DiseaseRelationRepository()
_pathway_repo = PathwayRepository()


def _generate_id() -> str:
    """生成唯一ID。"""
    import uuid
    return str(uuid.uuid4())


async def list_diseases(
    status: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 100,
) -> list[DiseaseDefinition]:
    """获取病种列表。"""
    diseases = await _disease_repo.find_all(status, category, limit)
    return [DiseaseDefinition(**d) for d in diseases]


async def get_disease(disease_id: str) -> Optional[DiseaseDefinition]:
    """获取病种详情。"""
    disease = await _disease_repo.find_by_id(disease_id)
    if disease:
        return DiseaseDefinition(**disease)
    return None


async def create_disease(disease: DiseaseDefinition) -> DiseaseDefinition:
    """创建病种。"""
    disease.id = _generate_id()
    disease.created_at = datetime.utcnow()
    disease.updated_at = datetime.utcnow()
    disease.status = DiseaseStatus.DRAFT
    disease.revision = 1

    await _disease_repo.create(disease.model_dump())

    # 记录审计事件
    await _audit_repo.create({
        "id": _generate_id(),
        "action": "create",
        "resource_type": "disease",
        "resource_id": disease.id,
        "resource_version": disease.version,
        "after": disease.model_dump(),
        "result": "success",
    })

    return disease


async def update_disease(disease_id: str, updates: dict[str, Any]) -> Optional[DiseaseDefinition]:
    """更新病种。"""
    disease = await get_disease(disease_id)
    if not disease:
        return None

    # 检查版本冲突
    if "revision" in updates and updates["revision"] != disease.revision:
        raise ValueError("版本冲突，请刷新后重试")

    # 记录更新前状态
    before = disease.model_dump()

    # 应用更新
    for key, value in updates.items():
        if hasattr(disease, key):
            setattr(disease, key, value)

    disease.updated_at = datetime.utcnow()
    disease.revision += 1

    # 更新数据库
    await _disease_repo.update(disease_id, disease.model_dump())

    # 记录审计事件
    await _audit_repo.create({
        "id": _generate_id(),
        "action": "update",
        "resource_type": "disease",
        "resource_id": disease_id,
        "resource_version": disease.version,
        "before": before,
        "after": disease.model_dump(),
        "result": "success",
    })

    return disease


async def delete_disease(disease_id: str) -> bool:
    """删除病种（软删除）。"""
    disease = await get_disease(disease_id)
    if not disease:
        return False

    # 已发布版本不能直接删除
    if disease.status == DiseaseStatus.PUBLISHED:
        raise ValueError("已发布版本不能直接删除，请先废弃")

    # 更新状态为归档
    await _disease_repo.update(disease_id, {
        "status": DiseaseStatus.ARCHIVED,
        "updated_at": datetime.utcnow(),
    })

    # 记录审计事件
    await _audit_repo.create({
        "id": _generate_id(),
        "action": "archive",
        "resource_type": "disease",
        "resource_id": disease_id,
        "resource_version": disease.version,
        "result": "success",
    })

    return True


async def submit_review(disease_id: str, submitter_id: str) -> ReviewTask:
    """提交审核。"""
    disease = await get_disease(disease_id)
    if not disease:
        raise ValueError("病种不存在")

    # 创建审核任务
    review = ReviewTask(
        id=_generate_id(),
        resource_type="disease",
        resource_id=disease_id,
        resource_version=disease.version,
        status=ReviewStatus.PENDING,
        submitter_id=submitter_id,
        submitted_at=datetime.utcnow(),
        snapshot_after=disease.model_dump(),
    )

    await _review_repo.create(review.model_dump())

    # 更新病种状态
    await _disease_repo.update(disease_id, {
        "status": DiseaseStatus.REVIEW_PENDING,
        "updated_at": datetime.utcnow(),
    })

    return review


async def approve_review(review_id: str, reviewer_id: str) -> ReviewTask:
    """通过审核。"""
    review_data = await _review_repo.find_by_id(review_id)
    if not review_data:
        raise ValueError("审核任务不存在")

    review = ReviewTask(**review_data)
    review.status = ReviewStatus.APPROVED
    review.reviewer_id = reviewer_id
    review.reviewed_at = datetime.utcnow()

    await _review_repo.update(review_id, review.model_dump())

    # 更新病种状态
    await _disease_repo.update(review.resource_id, {
        "status": DiseaseStatus.APPROVED,
        "reviewed_by": reviewer_id,
        "updated_at": datetime.utcnow(),
    })

    return review


async def reject_review(review_id: str, reviewer_id: str, comment: str) -> ReviewTask:
    """拒绝审核。"""
    review_data = await _review_repo.find_by_id(review_id)
    if not review_data:
        raise ValueError("审核任务不存在")

    review = ReviewTask(**review_data)
    review.status = ReviewStatus.REJECTED
    review.reviewer_id = reviewer_id
    review.reviewed_at = datetime.utcnow()
    review.review_comment = comment

    await _review_repo.update(review_id, review.model_dump())

    # 更新病种状态
    await _disease_repo.update(review.resource_id, {
        "status": DiseaseStatus.CHANGES_REQUESTED,
        "updated_at": datetime.utcnow(),
    })

    return review


async def list_relations(disease_id: str) -> list[DiseaseRelation]:
    """获取病种关系列表。"""
    relations = await _relation_repo.find_by_disease(disease_id)
    return [DiseaseRelation(**r) for r in relations]


async def create_relation(relation: DiseaseRelation) -> DiseaseRelation:
    """创建病种关系。"""
    relation.id = _generate_id()
    await _relation_repo.create(relation.model_dump())
    return relation


async def delete_relation(relation_id: str) -> bool:
    """删除病种关系。"""
    return await _relation_repo.delete(relation_id)


async def get_pathway(disease_id: str) -> Optional[ClinicalPathway]:
    """获取临床路径。"""
    pathway = await _pathway_repo.find_by_disease(disease_id)
    if pathway:
        return ClinicalPathway(**pathway)
    return None


async def create_pathway(pathway: ClinicalPathway) -> ClinicalPathway:
    """创建临床路径。"""
    pathway.id = _generate_id()
    pathway.created_at = datetime.utcnow()
    pathway.updated_at = datetime.utcnow()
    await _pathway_repo.create(pathway.model_dump())
    return pathway


async def update_pathway(disease_id: str, updates: dict[str, Any]) -> Optional[ClinicalPathway]:
    """更新临床路径。"""
    existing = await _pathway_repo.find_by_disease(disease_id)
    if not existing:
        return None

    pathway_id = existing.get("id", "")
    await _pathway_repo.update(pathway_id, updates)

    updated = await _pathway_repo.find_by_id(pathway_id)
    if updated:
        return ClinicalPathway(**updated)
    return None


async def list_reviews(status: Optional[str] = None) -> list[ReviewTask]:
    """获取审核列表。"""
    reviews = await _review_repo.find_all(status)
    return [ReviewTask(**r) for r in reviews]


async def get_review(review_id: str) -> Optional[ReviewTask]:
    """获取审核详情。"""
    review = await _review_repo.find_by_id(review_id)
    if review:
        return ReviewTask(**review)
    return None


async def list_audits(
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    limit: int = 100,
) -> list[AuditEvent]:
    """获取审计事件列表。"""
    audits = await _audit_repo.find_all(resource_type, resource_id, limit)
    return [AuditEvent(**a) for a in audits]
