"""S-AKI 单病种科研中心 API 路由。"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

import os
from app import runtime
from app.utils.serialization import serialize_doc

logger = logging.getLogger("icu-alert")

router = APIRouter(prefix="/api/disease-center/saki", tags=["saki-research"])

# ---- 安全导入 S-AKI 服务 ----
try:
    from app.services.saki import (
        saki_identifier,
        cohort_builder,
        statistics,
        audit_service,
        seed_data,
        disclaimer,
        field_mapping,
        sepsis_phenotype,
        aki_phenotype,
    )
    _saki_ready = True
except ImportError as exc:
    logger.warning("S-AKI 服务加载不完整: %s", exc)
    _saki_ready = False

# ---- 请求模型 ----


class BatchPhenotypeRequest(BaseModel):
    patient_ids: list[str] = Field(default_factory=list)


class CaseReviewRequest(BaseModel):
    reviewer_id: str
    result: str  # confirmed / rejected / modified
    notes: str = ""


class CohortBuildRequest(BaseModel):
    name: str = "未命名S-AKI队列"
    filters: dict[str, Any] = Field(default_factory=dict)


class AnalysisRequest(BaseModel):
    patient_ids: list[str] | None = None
    cohort_id: str | None = None
    group_by: str | None = None
    variables: list[dict[str, Any]] | None = None
    time_field: str = "los_icu_days"
    event_field: str = "icu_mortality"
    outcome: str = "icu_mortality"
    predictors: list[str] | None = None
    max_time: int = 28


class FieldMappingUpdateRequest(BaseModel):
    collection: str
    standard_name: str
    hospital_fields: list[str]
    description: str = ""


def _check_ready():
    if not _saki_ready:
        raise HTTPException(503, "S-AKI 服务未就绪")


def _db():
    return runtime.db


# ==================== 健康检查与配置 ====================

@router.get("/health")
async def saki_health():
    """S-AKI 模块健康检查。"""
    return {
        "status": "ok" if _saki_ready else "degraded",
        "module": "saki-research-center",
        "version": "v1.0.0",
        "disclaimer": "仅用于科研分析与临床决策支持，不替代医生诊断和治疗决策。",
    }


@router.get("/config")
async def saki_config():
    """返回 S-AKI 配置信息。"""
    _check_ready()
    return {
        "phenotype_versions": {
            "sepsis": sepsis_phenotype.VERSION if _saki_ready else "unknown",
            "aki": aki_phenotype.VERSION if _saki_ready else "unknown",
            "saki": saki_identifier.VERSION if _saki_ready else "unknown",
        },
        "temporal_window_hours": saki_identifier.TEMPORAL_WINDOW_HOURS if _saki_ready else 168,
        "rule_sources": {
            "sepsis": sepsis_phenotype.RULE_SOURCE if _saki_ready else "",
            "aki": aki_phenotype.RULE_SOURCE if _saki_ready else "",
        },
    }


# ==================== 表型计算 ====================

@router.post("/phenotype/sepsis/{patient_id}")
async def calculate_sepsis(patient_id: str):
    """计算脓毒症表型。"""
    _check_ready()
    calc = sepsis_phenotype.SepsisPhenotypeCalculator()
    result = await calc.calculate(_db(), patient_id)
    return serialize_doc(result)


@router.post("/phenotype/aki/{patient_id}")
async def calculate_aki(patient_id: str):
    """计算 AKI 表型。"""
    _check_ready()
    calc = aki_phenotype.AKIPhenotypeCalculator()
    result = await calc.calculate(_db(), patient_id)
    return serialize_doc(result)


@router.post("/phenotype/saki/{patient_id}")
async def calculate_saki(patient_id: str):
    """计算 S-AKI 综合表型。"""
    _check_ready()
    identifier = saki_identifier.SAKICaseIdentifier()
    result = await identifier.identify(_db(), patient_id)
    return serialize_doc(result)


@router.post("/phenotype/batch")
async def batch_phenotype(req: BatchPhenotypeRequest):
    """批量计算 S-AKI 表型。"""
    _check_ready()
    identifier = saki_identifier.SAKICaseIdentifier()
    results = await identifier.batch_identify(_db(), req.patient_ids or None)
    return serialize_doc({"cases": results, "total": len(results)})


# ==================== 病例管理 ====================

@router.get("/cases")
async def list_cases(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    aki_stage: Optional[int] = Query(None),
    department: Optional[str] = Query(None),
    is_saki: Optional[bool] = Query(None),
    review_status: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
):
    """分页查询 S-AKI 病例。"""
    _check_ready()
    filters = {}
    if aki_stage is not None:
        filters["aki_stage"] = aki_stage
    if department:
        filters["department"] = department
    if is_saki is not None:
        filters["is_saki"] = is_saki
    if review_status:
        filters["review_status"] = review_status
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to
    identifier = saki_identifier.SAKICaseIdentifier()
    result = await identifier.list_cases(_db(), page, page_size, filters)
    return serialize_doc(result)


@router.get("/cases/{case_id}")
async def get_case(case_id: str):
    """获取病例详情。"""
    _check_ready()
    identifier = saki_identifier.SAKICaseIdentifier()
    case = await identifier.get_case_detail(_db(), case_id)
    if not case:
        raise HTTPException(404, "病例不存在")
    return serialize_doc(case)


@router.post("/cases/{case_id}/review")
async def review_case(case_id: str, req: CaseReviewRequest):
    """提交病例人工复核。"""
    _check_ready()
    if req.result not in ("confirmed", "rejected", "modified"):
        raise HTTPException(400, "审核结果必须是 confirmed/rejected/modified")
    identifier = saki_identifier.SAKICaseIdentifier()
    result = await identifier.review_case(_db(), case_id, req.reviewer_id, req.result, req.notes)
    audit = audit_service.SAKIAuditService()
    await audit.log_event(_db(), "case_reviewed", "saki_case", case_id, req.reviewer_id,
                          {"result": req.result, "notes": req.notes})
    return serialize_doc(result)


@router.get("/cases/statistics")
async def case_statistics():
    """获取病例统计概览。"""
    _check_ready()
    identifier = saki_identifier.SAKICaseIdentifier()
    stats = await identifier.get_statistics(_db())
    return serialize_doc(stats)


@router.post("/cases/identify")
async def identify_cases(req: BatchPhenotypeRequest | None = None):
    """触发批量 S-AKI 识别。"""
    _check_ready()
    identifier = saki_identifier.SAKICaseIdentifier()
    pids = req.patient_ids if req else None
    results = await identifier.batch_identify(_db(), pids or None)
    saki_count = sum(1 for r in results if r.get("is_saki"))
    return serialize_doc({
        "total_identified": len(results),
        "saki_positive": saki_count,
        "cases": results[:50],
    })


# ==================== 队列管理 ====================

@router.post("/cohorts/build")
async def build_cohort(req: CohortBuildRequest):
    """构建科研队列。"""
    _check_ready()
    builder = cohort_builder.SAKICohortBuilder()
    cohort = await builder.build_cohort(_db(), req.filters, req.name)
    audit = audit_service.SAKIAuditService()
    await audit.log_event(_db(), "cohort_created", "saki_cohort", cohort["cohort_id"],
                          details={"name": req.name, "filters": req.filters})
    return serialize_doc(cohort)


@router.get("/cohorts")
async def list_cohorts():
    """列出队列。"""
    _check_ready()
    builder = cohort_builder.SAKICohortBuilder()
    cohorts = await builder.list_cohorts(_db())
    return serialize_doc(cohorts)


@router.get("/cohorts/{cohort_id}")
async def get_cohort(cohort_id: str):
    """获取队列详情。"""
    _check_ready()
    builder = cohort_builder.SAKICohortBuilder()
    patients = await builder.get_cohort_patients(_db(), cohort_id, page=1, page_size=1)
    return serialize_doc({"cohort_id": cohort_id, "patient_count": patients.get("total", 0)})


@router.get("/cohorts/{cohort_id}/patients")
async def cohort_patients(cohort_id: str, page: int = 1, page_size: int = 20):
    """获取队列患者列表。"""
    _check_ready()
    builder = cohort_builder.SAKICohortBuilder()
    result = await builder.get_cohort_patients(_db(), cohort_id, page, page_size)
    return serialize_doc(result)


@router.post("/cohorts/{cohort_id}/snapshot")
async def generate_snapshot(cohort_id: str):
    """生成队列快照。"""
    _check_ready()
    builder = cohort_builder.SAKICohortBuilder()
    snapshot = await builder.generate_snapshot(_db(), cohort_id)
    return serialize_doc(snapshot)


@router.delete("/cohorts/{cohort_id}")
async def delete_cohort(cohort_id: str):
    """删除队列。"""
    _check_ready()
    builder = cohort_builder.SAKICohortBuilder()
    success = await builder.delete_cohort(_db(), cohort_id)
    if not success:
        raise HTTPException(404, "队列不存在")
    return {"success": True}


# ==================== 统计分析 ====================

@router.post("/analysis/table1")
async def analysis_table1(req: AnalysisRequest):
    """Table 1 基线特征分析。"""
    _check_ready()
    stats = statistics.SAKIStatistics()
    result = await stats.table1(_db(), req.patient_ids, req.cohort_id, req.group_by or "aki_stage", req.variables)
    return serialize_doc(result)


@router.post("/analysis/km")
async def analysis_km(req: AnalysisRequest):
    """Kaplan-Meier 生存分析。"""
    _check_ready()
    stats = statistics.SAKIStatistics()
    result = await stats.km_analysis(_db(), req.patient_ids, req.cohort_id,
                                     req.time_field, req.event_field, req.group_by, req.max_time)
    return serialize_doc(result)


@router.post("/analysis/logistic")
async def analysis_logistic(req: AnalysisRequest):
    """Logistic 回归分析。"""
    _check_ready()
    stats = statistics.SAKIStatistics()
    result = await stats.logistic_regression(_db(), req.patient_ids, req.cohort_id,
                                             req.outcome, req.predictors)
    return serialize_doc(result)


@router.post("/analysis/cox")
async def analysis_cox(req: AnalysisRequest):
    """Cox 比例风险回归。"""
    _check_ready()
    stats = statistics.SAKIStatistics()
    result = await stats.cox_regression(_db(), req.patient_ids, req.cohort_id,
                                        req.time_field, req.event_field, req.predictors, req.max_time)
    return serialize_doc(result)


@router.post("/analysis/roc")
async def analysis_roc(req: AnalysisRequest):
    """ROC 曲线分析。"""
    _check_ready()
    stats = statistics.SAKIStatistics()
    result = await stats.roc_analysis(_db(), req.patient_ids, req.cohort_id, req.outcome, req.predictors)
    return serialize_doc(result)


@router.post("/analysis/creatinine-trajectory")
async def analysis_creatinine_trajectory(req: AnalysisRequest):
    """肌酐轨迹分析。"""
    _check_ready()
    stats = statistics.SAKIStatistics()
    result = await stats.creatinine_trajectory(_db(), req.patient_ids, req.cohort_id)
    return serialize_doc(result)


@router.post("/analysis/forest")
async def analysis_forest(req: AnalysisRequest):
    """森林图数据。"""
    _check_ready()
    stats = statistics.SAKIStatistics()
    result = await stats.forest_plot_data(_db(), req.patient_ids, req.cohort_id, req.outcome, req.predictors)
    return serialize_doc(result)


@router.post("/analysis/outcomes")
async def analysis_outcomes(req: AnalysisRequest):
    """住院结局汇总。"""
    _check_ready()
    stats = statistics.SAKIStatistics()
    result = await stats.hospital_outcomes(_db(), req.patient_ids, req.cohort_id)
    return serialize_doc(result)


# ==================== 数据质量与字段映射 ====================

@router.get("/quality/check")
async def quality_check():
    """运行数据质量检查。"""
    _check_ready()
    db = _db()
    total_cases = await db.col("saki_cases").count_documents({})
    with_patient = await db.col("saki_cases").count_documents({"patient_id": {"$exists": True, "$ne": ""}})
    with_sepsis = await db.col("saki_cases").count_documents({"sepsis_phenotype": {"$exists": True}})
    with_aki = await db.col("saki_cases").count_documents({"aki_phenotype": {"$exists": True}})
    completeness = round(
        (with_patient + with_sepsis + with_aki) / max(total_cases * 3, 1) * 100, 1
    )
    return {
        "total_cases": total_cases,
        "completeness_pct": completeness,
        "fields": {
            "patient_id": {"count": with_patient, "pct": round(with_patient / max(total_cases, 1) * 100, 1)},
            "sepsis_phenotype": {"count": with_sepsis, "pct": round(with_sepsis / max(total_cases, 1) * 100, 1)},
            "aki_phenotype": {"count": with_aki, "pct": round(with_aki / max(total_cases, 1) * 100, 1)},
        },
    }


@router.get("/field-mapping")
async def get_field_mappings(collection: Optional[str] = None):
    """获取字段映射。"""
    _check_ready()
    svc = field_mapping.FieldMappingService(_db())
    mappings = await svc.get_all_mappings(collection)
    return serialize_doc(mappings)


@router.put("/field-mapping")
async def update_field_mapping(req: FieldMappingUpdateRequest):
    """更新字段映射。"""
    _check_ready()
    svc = field_mapping.FieldMappingService(_db())
    result = await svc.update_mapping(req.collection, req.standard_name, req.hospital_fields, req.description)
    return serialize_doc(result)


# ==================== 审计日志 ====================

@router.get("/audit")
async def query_audit(
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
):
    """查询审计日志。"""
    _check_ready()
    svc = audit_service.SAKIAuditService()
    events = await svc.query_events(_db(), action, resource_type, resource_id, limit)
    return serialize_doc(events)


# ==================== 演示数据（仅 testing/development） ====================

def _require_demo_env():
    """生产环境禁止访问 demo 接口。"""
    env = os.environ.get("APP_ENV", "production").lower()
    if env not in ("testing", "development", "test", "dev", "ci"):
        raise HTTPException(404, "Not found")


@router.post("/demo/seed")
async def seed_demo(count: int = Query(50, ge=1, le=200), seed: int = Query(42)):
    """生成演示数据。仅 testing/development 可用。"""
    _require_demo_env()
    _check_ready()
    test_run_id = str(__import__("uuid").uuid4())[:8]
    audit = audit_service.SAKIAuditService()
    await audit.log_event(_db(), "demo_seed_started", "system", test_run_id, details={"count": count, "seed": seed})
    result = await seed_data.seed_saki_demo_data(_db(), count, seed=seed)
    await seed_data.ensure_saki_disease_definition(_db())
    await audit.log_event(_db(), "demo_seed_completed", "system", test_run_id, details={"counts": result.get("counts", {})})
    return serialize_doc({"test_run_id": test_run_id, **result})


@router.post("/demo/cleanup")
async def cleanup_demo(test_run_id: str = Query(..., description="必须提供 test_run_id，禁止无条件清理")):
    """清理测试数据。仅 testing/development 可用，必须提供 test_run_id。"""
    _require_demo_env()
    _check_ready()
    audit = audit_service.SAKIAuditService()
    await audit.log_event(_db(), "demo_cleanup_started", "system", test_run_id)
    collections = ["patient", "labResult", "vitalSign", "drug", "crrt",
                    "saki_cases", "saki_cohorts", "saki_snapshots", "saki_audit_log", "diseases"]
    summary: dict[str, Any] = {"counts": {}, "test_run_id": test_run_id}
    for coll_name in collections:
        result = await _db().col(coll_name).delete_many({"test_prefix": {"": test_run_id}})
        summary["counts"][coll_name] = result.deleted_count
    await audit.log_event(_db(), "demo_cleanup_completed", "system", test_run_id, details={"counts": summary["counts"]})
    return serialize_doc(summary)


# ==================== 免责声明 ====================

@router.get("/disclaimer")
async def get_disclaimer():
    """返回免责声明。"""
    return {
        "disclaimer": disclaimer.DISCLAIMER,
        "phenotype_disclaimer": disclaimer.PHENOTYPE_DISCLAIMER,
        "export_disclaimer": disclaimer.EXPORT_DISCLAIMER,
        "analysis_disclaimer": disclaimer.ANALYSIS_DISCLAIMER,
        "llm_disclaimer": disclaimer.LLM_DISCLAIMER,
    }



