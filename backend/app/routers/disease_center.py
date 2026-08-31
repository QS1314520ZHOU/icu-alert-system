"""病种中心 API 路由。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services import (
    disease_service,
    terminology_service,
    phenotype_service,
    offline_service,
    quality_service,
    ai_service,
)
from app.services import case_service
from app.services.clinical_scoring_service import (
    health_check,
    list_scoring_systems,
    get_scoring_rule,
    evaluate_score,
    run_test_case,
)

router = APIRouter(prefix="/api/disease-center", tags=["病种中心"])


# ===== 请求/响应模型 =====


class ConfirmRequest(BaseModel):
    """医生确认请求。"""
    operator_id: str
    operator_name: str = ""
    reason: str = ""
    clinical_note: str = ""


class ExcludeRequest(BaseModel):
    """医生排除请求。"""
    operator_id: str
    operator_name: str = ""
    reason: str = ""
    clinical_note: str = ""


class RecalculateRequest(BaseModel):
    """重新计算请求。"""
    operator_id: str = "system"
    operator_name: str = ""
    reason: str = "手动触发重新计算"


class CompleteTaskRequest(BaseModel):
    """完成任务请求。"""
    operator_id: str
    actual_value: Optional[float] = None
    note: str = ""


class CaseListParams(BaseModel):
    """病例列表查询参数。"""
    disease_id: Optional[str] = None
    status: Optional[str] = None
    patient_id: Optional[str] = None
    dept: Optional[str] = None
    risk_level: Optional[str] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None
    page: int = 1
    page_size: int = 50
    sort_by: str = "last_evaluated_at"
    sort_order: int = -1


# ===== 评分系统 =====


@router.get("/scoring/health")
async def scoring_health():
    """评分系统健康检查。"""
    return await health_check()


@router.get("/scoring/list")
async def scoring_list():
    """获取支持的评分系统列表。"""
    return await list_scoring_systems()


@router.get("/scoring/{score_name}")
async def scoring_get_rule(score_name: str):
    """获取评分规则。"""
    rule = await get_scoring_rule(score_name)
    if rule is None:
        raise HTTPException(404, f"评分系统 {score_name} 不存在")
    return rule


@router.post("/scoring/evaluate")
async def scoring_evaluate(score_name: str, observations: list[dict[str, Any]]):
    """执行评分。"""
    try:
        return await evaluate_score(score_name, observations)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/scoring/test-case")
async def scoring_test_case(score_name: str, test_case: dict[str, Any]):
    """运行测试用例。"""
    try:
        return await run_test_case(score_name, test_case)
    except Exception as e:
        raise HTTPException(400, str(e))


# ===== 仪表盘 =====


@router.get("/dashboard")
async def get_dashboard():
    """获取病种中心总览仪表盘数据。"""
    try:
        return await case_service.get_dashboard_data()
    except Exception as e:
        raise HTTPException(500, f"获取仪表盘数据失败: {e}")


# ===== 病种管理 =====


@router.get("/diseases")
async def list_diseases(
    status: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
):
    """获取病种列表。"""
    return await disease_service.list_diseases(status, category, limit)


@router.get("/diseases/{disease_id}")
async def get_disease(disease_id: str):
    """获取病种详情。"""
    disease = await disease_service.get_disease(disease_id)
    if disease is None:
        raise HTTPException(404, "病种不存在")
    return disease


@router.post("/diseases")
async def create_disease(disease: dict[str, Any]):
    """创建病种。"""
    try:
        from app.models.disease_center import DiseaseDefinition
        disease_model = DiseaseDefinition(**disease)
        return await disease_service.create_disease(disease_model)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.put("/diseases/{disease_id}")
async def update_disease(disease_id: str, updates: dict[str, Any]):
    """更新病种。"""
    try:
        disease = await disease_service.update_disease(disease_id, updates)
        if disease is None:
            raise HTTPException(404, "病种不存在")
        return disease
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.delete("/diseases/{disease_id}")
async def delete_disease(disease_id: str):
    """删除病种。"""
    try:
        success = await disease_service.delete_disease(disease_id)
        if not success:
            raise HTTPException(404, "病种不存在")
        return {"success": True}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/diseases/{disease_id}/submit-review")
async def submit_disease_review(disease_id: str, submitter_id: str):
    """提交病种审核。"""
    try:
        review = await disease_service.submit_review(disease_id, submitter_id)
        return review
    except ValueError as e:
        raise HTTPException(400, str(e))


# ===== 病种关系 =====


@router.get("/diseases/{disease_id}/relations")
async def list_disease_relations(disease_id: str):
    """获取病种关系列表。"""
    return await disease_service.list_relations(disease_id)


@router.post("/relations")
async def create_relation(relation: dict[str, Any]):
    """创建病种关系。"""
    try:
        from app.models.disease_center import DiseaseRelation
        relation_model = DiseaseRelation(**relation)
        return await disease_service.create_relation(relation_model)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.delete("/relations/{relation_id}")
async def delete_relation(relation_id: str):
    """删除病种关系。"""
    success = await disease_service.delete_relation(relation_id)
    if not success:
        raise HTTPException(404, "关系不存在")
    return {"success": True}


# ===== 临床路径 =====


@router.get("/diseases/{disease_id}/pathway")
async def get_pathway(disease_id: str):
    """获取临床路径。"""
    pathway = await disease_service.get_pathway(disease_id)
    if pathway is None:
        raise HTTPException(404, "临床路径不存在")
    return pathway


@router.post("/pathways")
async def create_pathway(pathway: dict[str, Any]):
    """创建临床路径。"""
    try:
        from app.models.disease_center import ClinicalPathway
        pathway_model = ClinicalPathway(**pathway)
        return await disease_service.create_pathway(pathway_model)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.put("/diseases/{disease_id}/pathway")
async def update_pathway(disease_id: str, updates: dict[str, Any]):
    """更新临床路径。"""
    pathway = await disease_service.update_pathway(disease_id, updates)
    if pathway is None:
        raise HTTPException(404, "临床路径不存在")
    return pathway


# ===== 术语管理 =====


@router.get("/terminology")
async def list_terminologies(
    category: Optional[str] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
):
    """获取术语列表。"""
    return await terminology_service.list_terminologies(category, status, keyword, limit)


@router.get("/terminology/categories")
async def get_terminology_categories():
    """获取术语分类。"""
    return await terminology_service.get_categories()


@router.get("/terminology/{term_id}")
async def get_terminology(term_id: str):
    """获取术语详情。"""
    term = await terminology_service.get_terminology(term_id)
    if term is None:
        raise HTTPException(404, "术语不存在")
    return term


@router.post("/terminology")
async def create_terminology(terminology: dict[str, Any]):
    """创建术语。"""
    try:
        from app.models.disease_center import Terminology
        term_model = Terminology(**terminology)
        return await terminology_service.create_terminology(term_model)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.put("/terminology/{term_id}")
async def update_terminology(term_id: str, updates: dict[str, Any]):
    """更新术语。"""
    term = await terminology_service.update_terminology(term_id, updates)
    if term is None:
        raise HTTPException(404, "术语不存在")
    return term


@router.delete("/terminology/{term_id}")
async def delete_terminology(term_id: str):
    """删除术语。"""
    success = await terminology_service.delete_terminology(term_id)
    if not success:
        raise HTTPException(404, "术语不存在")
    return {"success": True}


@router.post("/terminology/import")
async def import_terminology_batch(terms: list[dict[str, Any]]):
    """批量导入术语。"""
    return await terminology_service.import_batch(terms)


# ===== 表型规则 =====


@router.get("/phenotypes")
async def list_phenotypes(
    disease_id: Optional[str] = None,
    status: Optional[str] = None,
    phenotype_type: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
):
    """获取表型规则列表。"""
    return await phenotype_service.list_phenotypes(disease_id, status, phenotype_type, limit)


@router.get("/phenotypes/stats")
async def get_phenotype_stats():
    """获取表型规则统计。"""
    return await phenotype_service.get_phenotype_stats()


@router.get("/phenotypes/{phenotype_id}")
async def get_phenotype(phenotype_id: str):
    """获取表型规则详情。"""
    phenotype = await phenotype_service.get_phenotype(phenotype_id)
    if phenotype is None:
        raise HTTPException(404, "表型规则不存在")
    return phenotype


@router.post("/phenotypes")
async def create_phenotype(phenotype: dict[str, Any]):
    """创建表型规则。"""
    try:
        from app.models.disease_center import PhenotypeRule
        phenotype_model = PhenotypeRule(**phenotype)
        return await phenotype_service.create_phenotype(phenotype_model)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.put("/phenotypes/{phenotype_id}")
async def update_phenotype(phenotype_id: str, updates: dict[str, Any]):
    """更新表型规则。"""
    phenotype = await phenotype_service.update_phenotype(phenotype_id, updates)
    if phenotype is None:
        raise HTTPException(404, "表型规则不存在")
    return phenotype


@router.delete("/phenotypes/{phenotype_id}")
async def delete_phenotype(phenotype_id: str):
    """删除表型规则。"""
    success = await phenotype_service.delete_phenotype(phenotype_id)
    if not success:
        raise HTTPException(404, "表型规则不存在")
    return {"success": True}


@router.post("/phenotypes/validate")
async def validate_phenotype(phenotype: dict[str, Any]):
    """验证表型规则逻辑。"""
    try:
        from app.models.disease_center import PhenotypeRule
        phenotype_model = PhenotypeRule(**phenotype)
        return await phenotype_service.validate_logic(phenotype_model)
    except Exception as e:
        raise HTTPException(400, str(e))


# ===== 审核管理 =====


@router.get("/reviews")
async def list_reviews(status: Optional[str] = None):
    """获取审核列表。"""
    return await disease_service.list_reviews(status)


@router.get("/reviews/{review_id}")
async def get_review(review_id: str):
    """获取审核详情。"""
    review = await disease_service.get_review(review_id)
    if review is None:
        raise HTTPException(404, "审核任务不存在")
    return review


@router.post("/reviews/{review_id}/approve")
async def approve_review(review_id: str, reviewer_id: str):
    """通过审核。"""
    try:
        return await disease_service.approve_review(review_id, reviewer_id)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/reviews/{review_id}/reject")
async def reject_review(review_id: str, reviewer_id: str, comment: str):
    """拒绝审核。"""
    try:
        return await disease_service.reject_review(review_id, reviewer_id, comment)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ===== 离线包管理 =====


@router.get("/offline-packages")
async def list_offline_packages(
    status: Optional[str] = None,
    target_device: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
):
    """获取离线包列表。"""
    return await offline_service.list_packages(status, target_device, limit)


@router.get("/offline-packages/stats")
async def get_offline_package_stats():
    """获取离线包统计。"""
    return await offline_service.get_package_stats()


@router.get("/offline-packages/{package_id}")
async def get_offline_package(package_id: str):
    """获取离线包详情。"""
    package = await offline_service.get_package(package_id)
    if package is None:
        raise HTTPException(404, "离线包不存在")
    return package


@router.post("/offline-packages")
async def create_offline_package(package: dict[str, Any]):
    """创建离线包。"""
    try:
        from app.models.disease_center import OfflinePackage
        package_model = OfflinePackage(**package)
        return await offline_service.create_package(package_model)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/offline-packages/{package_id}/build")
async def build_offline_package(package_id: str):
    """构建离线包。"""
    try:
        package = await offline_service.build_package(package_id)
        if package is None:
            raise HTTPException(404, "离线包不存在")
        return package
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/offline-packages/{package_id}/publish")
async def publish_offline_package(package_id: str):
    """发布离线包。"""
    try:
        package = await offline_service.publish_package(package_id)
        if package is None:
            raise HTTPException(404, "离线包不存在")
        return package
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/offline-packages/{package_id}")
async def delete_offline_package(package_id: str):
    """删除离线包。"""
    success = await offline_service.delete_package(package_id)
    if not success:
        raise HTTPException(404, "离线包不存在")
    return {"success": True}


# ===== 质量监控 =====


@router.get("/quality/snapshots")
async def list_quality_snapshots(
    disease_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
):
    """获取质量快照列表。"""
    return await quality_service.list_snapshots(disease_id, limit)


@router.get("/quality/snapshots/{snapshot_id}")
async def get_quality_snapshot(snapshot_id: str):
    """获取质量快照详情。"""
    snapshot = await quality_service.get_snapshot(snapshot_id)
    if snapshot is None:
        raise HTTPException(404, "质量快照不存在")
    return snapshot


@router.get("/quality/summary/{disease_id}")
async def get_quality_summary(disease_id: str):
    """获取质量摘要。"""
    return await quality_service.get_quality_summary(disease_id)


@router.get("/quality/trend/{disease_id}")
async def get_quality_trend(disease_id: str, days: int = 30):
    """获取质量趋势。"""
    return await quality_service.get_quality_trend(disease_id, days)


@router.post("/quality/check/{disease_id}")
async def run_quality_check(disease_id: str):
    """运行质量检查。"""
    return await quality_service.run_quality_check(disease_id)


# ===== AI 咨询 =====


@router.get("/ai/proposals")
async def list_ai_proposals(
    disease_id: Optional[str] = None,
    proposal_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
):
    """获取 AI 提案列表。"""
    return await ai_service.list_proposals(disease_id, proposal_type, status, limit)


@router.get("/ai/stats")
async def get_ai_stats():
    """获取 AI 咨询统计。"""
    return await ai_service.get_ai_stats()


@router.get("/ai/proposals/{proposal_id}")
async def get_ai_proposal(proposal_id: str):
    """获取 AI 提案详情。"""
    proposal = await ai_service.get_proposal(proposal_id)
    if proposal is None:
        raise HTTPException(404, "AI 提案不存在")
    return proposal


@router.post("/ai/proposals")
async def create_ai_proposal(proposal: dict[str, Any]):
    """创建 AI 提案。"""
    try:
        return await ai_service.create_proposal(**proposal)
    except Exception as e:
        raise HTTPException(400, str(e))


@router.post("/ai/proposals/{proposal_id}/approve")
async def approve_ai_proposal(proposal_id: str, reviewer_id: str):
    """通过 AI 提案。"""
    proposal = await ai_service.approve_proposal(proposal_id, reviewer_id)
    if proposal is None:
        raise HTTPException(404, "AI 提案不存在")
    return proposal


@router.post("/ai/proposals/{proposal_id}/reject")
async def reject_ai_proposal(proposal_id: str, reviewer_id: str, reason: str):
    """拒绝 AI 提案。"""
    proposal = await ai_service.reject_proposal(proposal_id, reviewer_id, reason)
    if proposal is None:
        raise HTTPException(404, "AI 提案不存在")
    return proposal


# ===== 审计日志 =====


@router.get("/audit")
async def list_audit_events(
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
):
    """获取审计事件列表。"""
    return await disease_service.list_audits(resource_type, resource_id, limit)


@router.get("/diseases/{disease_id}/dashboard")
async def get_disease_dashboard(disease_id: str):
    """获取单病种仪表盘数据。"""
    try:
        return await case_service.get_disease_dashboard(disease_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(500, f"获取病种仪表盘失败: {e}")


@router.get("/funnel")
async def get_global_funnel():
    """获取全局筛查漏斗数据。"""
    try:
        return await case_service.get_funnel_data("")
    except Exception as e:
        raise HTTPException(500, f"获取漏斗数据失败: {e}")


@router.get("/diseases/{disease_id}/funnel")
async def get_disease_funnel(disease_id: str):
    """获取筛查漏斗数据。"""
    try:
        return await case_service.get_funnel_data(disease_id)
    except Exception as e:
        raise HTTPException(500, f"获取漏斗数据失败: {e}")


@router.get("/diseases/{disease_id}/outcomes")
async def get_disease_outcomes(disease_id: str):
    """获取结局分析。"""
    # TODO: 实现结局分析
    return {
        "icu_mortality": None,
        "hospital_mortality": None,
        "avg_icu_days": None,
        "avg_hospital_days": None,
        "discharge_recovery_rate": None,
        "followup_30d": None,
        "followup_90d": None,
    }


@router.get("/diseases/{disease_id}/quality/trend")
async def get_disease_quality_trend(disease_id: str, days: int = 30):
    """获取病种质控趋势。"""
    try:
        return await quality_service.get_quality_trend(disease_id, days)
    except Exception as e:
        raise HTTPException(500, f"获取质控趋势失败: {e}")


@router.get("/diseases/{disease_id}/quality/failures")
async def get_disease_quality_failures(disease_id: str):
    """获取未达标原因。"""
    # TODO: 实现未达标原因分析
    return []


# ===== 病例中心 =====


@router.get("/diseases/cases")
async def list_all_cases(
    disease_id: Optional[str] = None,
    status: Optional[str] = None,
    patient_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """获取全部病例列表（跨病种）。"""
    skip = (page - 1) * page_size
    try:
        cases, total = await case_service.list_cases(
            disease_id=disease_id,
            status=status,
            patient_id=patient_id,
            skip=skip,
            limit=page_size,
        )
        return {"items": cases, "total": total, "page": page, "page_size": page_size}
    except Exception as e:
        raise HTTPException(500, f"获取病例列表失败: {e}")


@router.get("/diseases/{disease_id}/cases")
async def list_disease_cases(
    disease_id: str,
    status: Optional[str] = None,
    patient_id: Optional[str] = None,
    dept: Optional[str] = None,
    risk_level: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort_by: str = "last_evaluated_at",
    sort_order: int = -1,
):
    """获取病种病例列表。"""
    skip = (page - 1) * page_size
    cases, total = await case_service.list_cases(
        disease_id=disease_id,
        status=status,
        patient_id=patient_id,
        dept=dept,
        risk_level=risk_level,
        date_from=date_from,
        date_to=date_to,
        skip=skip,
        limit=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return {
        "cases": cases,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/cases/{case_id}")
async def get_case(case_id: str):
    """获取病例详情。"""
    case = await case_service.get_case(case_id)
    if case is None:
        raise HTTPException(404, "病例不存在")
    return case


@router.get("/cases/{case_id}/evidence")
async def get_case_evidence(
    case_id: str,
    evidence_type: Optional[str] = None,
    matched: Optional[bool] = None,
    skip: int = 0,
    limit: int = 200,
):
    """获取病例证据链。"""
    return await case_service.get_case_evidence(
        case_id, evidence_type=evidence_type, matched=matched,
        skip=skip, limit=limit,
    )


@router.get("/cases/{case_id}/evidence/completeness")
async def get_evidence_completeness(case_id: str):
    """获取病例证据完整度。"""
    return await case_service.get_evidence_completeness(case_id)


@router.get("/cases/{case_id}/timeline")
async def get_case_timeline(case_id: str):
    """获取病例时间线。"""
    return await case_service.get_case_timeline(case_id)


@router.get("/cases/{case_id}/pathway")
async def get_case_pathway(case_id: str):
    """获取病例路径实例。"""
    instance = await case_service.get_pathway_instance(case_id)
    if instance is None:
        return None
    tasks = await case_service.get_case_tasks(case_id)
    return {
        "instance": instance,
        "tasks": tasks,
    }


@router.get("/cases/{case_id}/quality")
async def get_case_quality(case_id: str):
    """获取病例质量评估。"""
    case = await case_service.get_case(case_id)
    if case is None:
        raise HTTPException(404, "病例不存在")

    completeness = await case_service.get_evidence_completeness(case_id)
    confirmations = await case_service.get_confirmation_history(case_id)

    return {
        "case_id": case_id,
        "evidence_completeness": completeness,
        "confirmation_count": len(confirmations),
        "risk_level": case.get("risk_level"),
        "confidence": case.get("confidence"),
    }


@router.post("/cases/{case_id}/confirm")
async def confirm_case(case_id: str, req: ConfirmRequest):
    """医生确认病例。"""
    try:
        return await case_service.confirm_case(
            case_id,
            operator_id=req.operator_id,
            operator_name=req.operator_name,
            reason=req.reason,
            clinical_note=req.clinical_note,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"确认失败: {e}")


@router.post("/cases/{case_id}/exclude")
async def exclude_case(case_id: str, req: ExcludeRequest):
    """医生排除病例。"""
    try:
        return await case_service.exclude_case(
            case_id,
            operator_id=req.operator_id,
            operator_name=req.operator_name,
            reason=req.reason,
            clinical_note=req.clinical_note,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"排除失败: {e}")


@router.post("/cases/{case_id}/recalculate")
async def recalculate_case(case_id: str, req: RecalculateRequest):
    """触发病例重新计算。"""
    try:
        return await case_service.recalculate_case(
            case_id,
            operator_id=req.operator_id,
            operator_name=req.operator_name,
            reason=req.reason,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"重新计算失败: {e}")


@router.post("/cases/{case_id}/tasks/{task_id}/complete")
async def complete_case_task(case_id: str, task_id: str, req: CompleteTaskRequest):
    """完成路径任务。"""
    try:
        return await case_service.complete_task(
            task_id,
            operator_id=req.operator_id,
            actual_value=req.actual_value,
            note=req.note,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"完成任务失败: {e}")
