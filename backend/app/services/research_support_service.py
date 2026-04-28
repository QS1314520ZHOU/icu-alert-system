from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from app import runtime
from app.services.ai_prompt_templates import RESEARCH_TOPIC_PROMPT_VERSION, build_research_topic_prompts, extract_json_object
from app.services.audit_service import write_ai_generation_log
from app.services.llm_runtime import call_llm_chat
from app.services.omop_export_service import build_data_quality_report
from app.utils.patient_helpers import research_patient_scope_query
from app.utils.serialization import safe_oid, serialize_doc

logger = logging.getLogger("icu-alert")


async def list_projects() -> dict[str, Any]:
    cursor = runtime.db.col("research_projects").find({}).sort("updated_at", -1).limit(300)
    projects = [serialize_doc(doc) async for doc in cursor]
    return {"projects": projects, "portfolio": build_portfolio_summary(projects)}


def build_portfolio_summary(projects: list[dict[str, Any]]) -> dict[str, Any]:
    by_status: dict[str, int] = {}
    by_type: dict[str, int] = {}
    upcoming: list[dict[str, Any]] = []
    for project in projects:
        status = str(project.get("status") or "计划中")
        ptype = str(project.get("type") or "课题")
        by_status[status] = by_status.get(status, 0) + 1
        by_type[ptype] = by_type.get(ptype, 0) + 1
        for item in project.get("milestones") or []:
            upcoming.append(
                {
                    "project_id": project.get("project_id"),
                    "project_title": project.get("title"),
                    "title": item.get("title") or item.get("name") or "未命名节点",
                    "date": item.get("date") or item.get("due_date") or item.get("time"),
                    "status": item.get("status") or "待完成",
                }
            )
    upcoming = sorted(upcoming, key=lambda row: str(row.get("date") or "9999"))[:8]
    return {
        "by_status": by_status,
        "by_type": by_type,
        "upcoming_milestones": upcoming,
        "active_count": sum(1 for item in projects if item.get("status") in {"计划中", "进行中", "投稿中"}),
        "completed_count": sum(1 for item in projects if item.get("status") in {"已发表", "结题"}),
    }


def build_data_governance_recommendations(report: dict[str, Any]) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []
    missing = report.get("missing_rate") or {}
    high_missing = [field for field, rate in missing.items() if float(rate or 0) >= 0.2]
    if high_missing:
        recs.append({"priority": "high", "title": "优先治理高缺失字段", "detail": "、".join(high_missing[:6])})
    if report.get("time_logic_errors"):
        recs.append({"priority": "high", "title": "修正时间逻辑错误", "detail": f"发现 {len(report.get('time_logic_errors') or [])} 条时间逻辑问题，导出前建议治理。"})
    if report.get("unit_inconsistencies"):
        recs.append({"priority": "medium", "title": "统一单位映射", "detail": "存在单位不一致，建议在 OMOP 映射配置中补充标准单位。"})
    if report.get("outliers"):
        recs.append({"priority": "medium", "title": "复核异常值", "detail": f"发现 {len(report.get('outliers') or [])} 条异常值信号。"})
    if not recs:
        recs.append({"priority": "low", "title": "数据质量可进入初步分析", "detail": "未发现高优先级治理项，仍建议抽样核查。"})
    return recs


async def create_project(payload: dict[str, Any], actor: str) -> dict[str, Any]:
    now = datetime.now()
    doc = {
        "project_id": str(uuid.uuid4()),
        "title": payload.get("title") or "未命名科研项目",
        "type": payload.get("type") or "课题",
        "owner": payload.get("owner") or actor,
        "participants": payload.get("participants") or [],
        "status": payload.get("status") or "计划中",
        "journal_or_funding_source": payload.get("journal_or_funding_source") or "",
        "impact_factor_or_level": payload.get("impact_factor_or_level") or "",
        "milestones": payload.get("milestones") or [],
        "attachments": payload.get("attachments") or [],
        "remarks": payload.get("remarks") or "",
        "created_by": actor,
        "updated_by": actor,
        "created_at": now,
        "updated_at": now,
    }
    await runtime.db.col("research_projects").insert_one(doc)
    return {"project": serialize_doc(doc)}


async def update_project(project_id: str, payload: dict[str, Any], actor: str) -> dict[str, Any]:
    now = datetime.now()
    update = {key: value for key, value in payload.items() if key not in {"_id", "project_id", "created_at", "created_by"}}
    update["updated_by"] = actor
    update["updated_at"] = now
    query = {"project_id": project_id}
    oid = safe_oid(project_id)
    if oid is not None:
        query = {"$or": [{"project_id": project_id}, {"_id": oid}]}
    await runtime.db.col("research_projects").update_one(query, {"$set": update})
    doc = await runtime.db.col("research_projects").find_one(query)
    return {"project": serialize_doc(doc)}


async def delete_project(project_id: str) -> dict[str, Any]:
    query = {"project_id": project_id}
    oid = safe_oid(project_id)
    if oid is not None:
        query = {"$or": [{"project_id": project_id}, {"_id": oid}]}
    result = await runtime.db.col("research_projects").delete_one(query)
    return {"deleted": int(getattr(result, "deleted_count", 0))}


async def _department_snapshot() -> dict[str, Any]:
    patient_count = await runtime.db.col("patient").count_documents(research_patient_scope_query("all"))
    active_count = await runtime.db.col("patient").count_documents(research_patient_scope_query("in_dept"))
    ards_alerts = await runtime.db.col("alert_records").count_documents({"alert_type": {"$regex": "ards|prone|vent", "$options": "i"}})
    sepsis_alerts = await runtime.db.col("alert_records").count_documents({"alert_type": {"$regex": "sepsis|bundle", "$options": "i"}})
    high_dp = await runtime.db.col("alert_records").count_documents({"alert_type": "driving_pressure"})
    return {
        "patient_count": patient_count,
        "active_patient_count": active_count,
        "quality_signals": {
            "ards_or_prone_related_alerts": ards_alerts,
            "sepsis_bundle_related_alerts": sepsis_alerts,
            "high_driving_pressure_alerts": high_dp,
        },
        "data_quality": await build_data_quality_report("all"),
        "limitations": ["当前为院内结构化数据摘要，指南差距指标需与本地质控口径进一步校准。"],
    }


def _fallback_topics(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    signals = snapshot.get("quality_signals") or {}
    quality = snapshot.get("data_quality") or {}
    topics = [
        {
            "title": "ARDS 患者俯卧位治疗比例与氧合改善的质量改进研究",
            "clinical_question": "本科室 ARDS 患者俯卧位启动是否及时，是否与氧合改善和机械通气时间相关？",
            "data_basis": f"系统识别 ARDS/俯卧位/机械通气相关信号 {signals.get('ards_or_prone_related_alerts', 0)} 条，可作为质量差距初筛依据。",
            "study_design": "质量改进项目 / 回顾性队列",
            "inclusion_criteria": ["ICU 住院患者", "ARDS 或急性低氧性呼吸衰竭", "存在氧合与呼吸机参数记录"],
            "exclusion_criteria": ["关键氧合指标缺失", "治疗限制或临终照护患者需单独标记"],
            "primary_outcome": "俯卧位启动率与 P/F Ratio 改善幅度",
            "secondary_outcomes": ["机械通气天数", "ICU住院天数", "28天结局", "压力损伤发生率"],
            "required_data_fields": ["诊断", "PaO2", "FiO2", "PEEP", "俯卧位开始/结束时间", "结局"],
            "estimated_sample_size": "建议先做 3-6 个月病例盘点，再按主要结局估算样本量。",
            "feasibility_score": 82,
            "ethical_risk": "以脱敏质控数据为主，风险较低；涉及干预流程优化时需伦理备案。",
            "multi_center_potential": True,
            "confidence": "medium",
            "limitations": snapshot.get("limitations") or [],
        },
        {
            "title": "机械通气患者高驱动压暴露与预后关系的回顾性队列研究",
            "clinical_question": "高驱动压暴露是否与 ICU 不良结局相关？",
            "data_basis": f"系统记录高驱动压相关预警 {signals.get('high_driving_pressure_alerts', 0)} 条。",
            "study_design": "回顾性队列",
            "inclusion_criteria": ["ICU 机械通气患者", "存在呼吸机参数记录"],
            "exclusion_criteria": ["关键通气参数缺失"],
            "primary_outcome": "ICU死亡或机械通气天数",
            "secondary_outcomes": ["SBT失败", "再插管", "ICU住院天数"],
            "required_data_fields": ["FiO2", "PEEP", "Pplat", "VT", "结局"],
            "estimated_sample_size": "基于当前患者总量需进一步测算",
            "feasibility_score": 72,
            "ethical_risk": "回顾性脱敏数据，伦理风险较低；需伦理备案。",
            "multi_center_potential": True,
            "confidence": "medium",
            "limitations": snapshot.get("limitations") or [],
        },
        {
            "title": "脓毒症 1 小时 Bundle 完成率与流程优化研究",
            "clinical_question": "Bundle 完成情况是否存在可改进环节？",
            "data_basis": f"系统记录脓毒症/Bundle 相关信号 {signals.get('sepsis_bundle_related_alerts', 0)} 条。",
            "study_design": "QI 项目",
            "inclusion_criteria": ["疑似或确诊脓毒症患者"],
            "exclusion_criteria": ["入科前已完成完整处置且无法追踪时间窗"],
            "primary_outcome": "1小时 Bundle 完成率",
            "secondary_outcomes": ["抗菌药物给药时间", "乳酸复查率", "升压药使用"],
            "required_data_fields": ["诊断", "乳酸", "血培养", "抗菌药物", "时间戳"],
            "estimated_sample_size": "按月度病例量滚动评估",
            "feasibility_score": 78,
            "ethical_risk": "流程改进研究需避免影响临床自主决策。",
            "multi_center_potential": True,
            "confidence": "medium",
            "limitations": snapshot.get("limitations") or [],
        },
        {
            "title": "科研数据质量对重症质控指标可信度的影响研究",
            "clinical_question": "人口学字段缺失、时间逻辑错误和单位不一致会如何影响 ARDS、脓毒症 Bundle、驱动压等质量指标？",
            "data_basis": f"当前数据质量报告显示患者数 {quality.get('patient_count', 0)}，时间逻辑错误 {len(quality.get('time_logic_errors') or [])} 条。",
            "study_design": "方法学审计研究",
            "inclusion_criteria": ["进入科研数据仓的 ICU 患者", "存在至少一类结构化临床记录"],
            "exclusion_criteria": ["完全缺失患者主索引", "无法脱敏映射的记录"],
            "primary_outcome": "数据清洗前后关键质控指标差异",
            "secondary_outcomes": ["字段缺失率", "异常值比例", "单位不一致率", "时间逻辑错误率"],
            "required_data_fields": ["患者主索引", "诊断", "时间戳", "实验室指标", "呼吸机参数", "医嘱/用药"],
            "estimated_sample_size": "可覆盖全量科研数据仓记录。",
            "feasibility_score": 90,
            "ethical_risk": "完全脱敏方法学研究，伦理风险较低；需记录数据治理流程。",
            "multi_center_potential": True,
            "confidence": "high",
            "limitations": snapshot.get("limitations") or [],
        },
    ]
    return topics


async def list_topic_suggestions() -> dict[str, Any]:
    cursor = runtime.db.col("research_topic_suggestions").find({}).sort("generated_at", -1).limit(100)
    rows = [serialize_doc(doc) async for doc in cursor]
    if rows:
        return {"topic_suggestions": rows}
    return {"topic_suggestions": _fallback_topics(await _department_snapshot()), "is_mock": True}


async def generate_topic_suggestions(actor: str) -> dict[str, Any]:
    snapshot = await _department_snapshot()
    cfg = runtime.config
    model = str(getattr(cfg, "llm_fast_model", "") or getattr(cfg.settings, "LLM_MODEL", "") or "unknown")
    try:
        system_prompt, user_prompt = build_research_topic_prompts(snapshot)
        llm = await call_llm_chat(cfg=cfg, system_prompt=system_prompt, user_prompt=user_prompt, model=model, temperature=0.1, max_tokens=2200, timeout_seconds=60)
        model = str(llm.get("model") or model)
        parsed = extract_json_object(str(llm.get("text") or ""))
        topics = parsed.get("topic_suggestions") if isinstance(parsed.get("topic_suggestions"), list) else []
        if not topics:
            topics = _fallback_topics(snapshot)
        degraded = False
    except Exception as exc:
        logger.warning("research topic ai fallback: %s", exc)
        topics = _fallback_topics(snapshot)
        degraded = True
    now = datetime.now()
    docs = []
    for item in topics[:5]:
        doc = {**item, "suggestion_id": str(uuid.uuid4()), "generated_at": now, "created_at": now, "created_by": actor, "model": model, "prompt_version": RESEARCH_TOPIC_PROMPT_VERSION, "degraded": degraded, "data_snapshot": snapshot}
        await runtime.db.col("research_topic_suggestions").insert_one(doc)
        docs.append(doc)
    await write_ai_generation_log(runtime.db, module="research_support", action="topic_suggestions", model=model, prompt_version=RESEARCH_TOPIC_PROMPT_VERSION, source_data_summary=snapshot, result=docs, actor=actor, success=not degraded)
    return {"topic_suggestions": serialize_doc(docs), "degraded": degraded}
