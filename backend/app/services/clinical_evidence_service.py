"""临床证据链统一查询服务。

从 MongoDB 聚合多数据源，为前端证据抽屉提供完整证据链。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app import runtime
from app.services.audit_service import write_audit_log
from app.utils.serialization import serialize_doc

logger = logging.getLogger("icu-alert")

# 数据源到集合的映射
_COLLECTION_MAP = {
    "vitals": "bedside",
    "labs": "labResult",
    "alerts": "alert_records",
    "scores": "score",
    "drugs": "drugExe",
    "nursing": "nursing_records",
    "orders": "order_records",
    "clinical_events": "clinical_events",
}

_TIME_RANGE_HOURS = {
    "1h": 1,
    "6h": 6,
    "12h": 12,
    "24h": 24,
    "48h": 48,
    "72h": 72,
    "7d": 168,
}

# 器官系统到指标代码的映射
_ORGAN_SYSTEM_CODES: dict[str, dict[str, Any]] = {
    "respiratory": {
        "label": "呼吸系统",
        "codes": ["SpO2", "PaO2", "PaCO2", "FiO2", "P/F_ratio", "RR", "TV", "PEEP", "Pplat", "driving_pressure", "mechanical_power"],
        "score_types": ["ards", "respiratory"],
    },
    "circulatory": {
        "label": "循环系统",
        "codes": ["HR", "MAP", "SBP", "DBP", "CVP", "Lactate", "NE_dose", "DOSE_norepinephrine", "ScvO2", "CI"],
        "score_types": ["sepsis", "septic_shock", "sofa_cardiovascular"],
    },
    "renal": {
        "label": "肾脏系统",
        "codes": ["Cr", "BUN", "Urine_output_24h", "Urine_output_6h", "K", "Na", "pH", "HCO3"],
        "score_types": ["aki", "sofa_renal"],
    },
    "hepatic": {
        "label": "肝脏系统",
        "codes": ["TBIL", "DBIL", "ALT", "AST", "ALB", "PT", "INR", "NH3"],
        "score_types": ["sofa_hepatic"],
    },
    "neurologic": {
        "label": "神经系统",
        "codes": ["GCS", "RASS", "CAM_ICU", "RASS_target", "pupil_left", "pupil_right"],
        "score_types": ["deliric", "pre_deliric", "sofa_neurologic"],
    },
    "coagulation": {
        "label": "凝血系统",
        "codes": ["PLT", "PT", "APTT", "Fib", "D_dimer", "INR"],
        "score_types": ["sofa_coagulation"],
    },
    "infection": {
        "label": "感染",
        "codes": ["WBC", "PCT", "CRP", "temperature", "blood_culture", "sputum_culture"],
        "score_types": ["sepsis", "qsofa"],
    },
    "nutrition": {
        "label": "营养",
        "codes": ["prealbumin", "albumin", "BMI", "NRS2002", "energy_intake", "protein_intake"],
        "score_types": ["nutrition"],
    },
}


async def get_evidence(
    patient_id: str,
    context_type: str,
    context_id: str | None = None,
    organ_system: str | None = None,
    time_range: str = "24h",
    include_raw: bool = False,
    include_ai: bool = False,
    actor: str = "anonymous",
) -> dict[str, Any]:
    """统一证据查询入口。"""

    db = runtime.db
    if db is None:
        return _error_response("数据库未连接")

    hours = _TIME_RANGE_HOURS.get(time_range, 24)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    now = datetime.now(timezone.utc)

    # 验证患者存在
    patient = await db.col("patient").find_one(
        {"_id": patient_id}, {"_name": 1, "hisBed": 1, "hisDept": 1}
    )
    if not patient:
        return _error_response(f"患者 {patient_id} 不存在")

    # 根据 context_type 分发
    if context_type == "organ_system":
        result = await _build_organ_evidence(db, patient_id, organ_system or "respiratory", since, hours)
    elif context_type == "risk":
        result = await _build_risk_evidence(db, patient_id, context_id, since, hours)
    elif context_type == "order":
        result = await _build_order_evidence(db, patient_id, context_id, since, hours)
    elif context_type == "nursing":
        result = await _build_nursing_evidence(db, patient_id, context_id, since, hours)
    elif context_type == "weaning":
        result = await _build_weaning_evidence(db, patient_id, since, hours)
    elif context_type == "discharge":
        result = await _build_discharge_evidence(db, patient_id, since, hours)
    elif context_type == "rule_noise":
        result = await _build_rule_noise_evidence(db, patient_id, context_id, since, hours)
    elif context_type == "vitals":
        result = await _build_vitals_evidence(db, patient_id, since, hours)
    elif context_type == "unclosed":
        result = await _build_unclosed_evidence(db, patient_id, since, hours)
    else:
        result = await _build_general_evidence(db, patient_id, since, hours)

    # 附加通用字段
    result["generated_at"] = now.isoformat()
    result["data_cutoff_at"] = now.isoformat()
    result["provenance"] = {
        "patient_id": patient_id,
        "context_type": context_type,
        "context_id": context_id,
        "time_range": time_range,
        "query_since": since.isoformat(),
        "data_sources": list(_COLLECTION_MAP.values()),
    }
    result["model_version"] = "icu-evidence-v1.0"
    result["rule_version"] = "clinical-core-v1.0"

    # AI 分析
    if include_ai:
        result["ai_analysis"] = await _build_ai_analysis(db, patient_id, context_type, organ_system, since)
    else:
        result["ai_analysis"] = None

    # 如果不需要原始数据，裁剪 evidence_rows
    if not include_raw:
        for row in result.get("evidence_rows", []):
            row.pop("source_system", None)
            row.pop("collection_name", None)

    # 审计日志
    try:
        await write_audit_log(
            db,
            action="view_evidence",
            module="clinical_evidence",
            actor=actor,
            target_type="patient",
            target_id=patient_id,
            detail={"context_type": context_type, "context_id": context_id, "organ_system": organ_system},
        )
    except Exception as exc:
        logger.warning("审计日志写入失败: %s", exc)

    return serialize_doc(result)


# ── 器官系统证据 ──────────────────────────────────────

async def _build_organ_evidence(db, patient_id: str, organ_system: str, since: datetime, hours: int) -> dict:
    organ_cfg = _ORGAN_SYSTEM_CODES.get(organ_system, _ORGAN_SYSTEM_CODES["respiratory"])
    codes = organ_cfg["codes"]
    score_types = organ_cfg["score_types"]

    # 指标数据
    metrics = await _query_metrics(db, patient_id, codes, since)
    trends = await _query_trends(db, patient_id, codes, since)
    evidence_rows = await _query_evidence_rows(db, patient_id, codes, since)

    # 评分计算
    rule_calc = await _query_scores(db, patient_id, score_types, since)

    # 时间线
    timeline = await _query_timeline(db, patient_id, since)

    # 缺失数据
    missing = _detect_missing_data(codes, metrics)

    severity = _compute_severity(metrics, evidence_rows)
    conclusion = _build_conclusion(organ_cfg["label"], severity, metrics, missing)

    return {
        "conclusion": conclusion,
        "severity": severity,
        "confidence": _compute_confidence(metrics, missing),
        "metrics": metrics,
        "trends": trends,
        "evidence_rows": evidence_rows,
        "rule_calculation": rule_calc,
        "timeline": timeline,
        "missing_data": missing,
    }


# ── 风险证据 ──────────────────────────────────────────

async def _build_risk_evidence(db, patient_id: str, alert_id: str | None, since: datetime, hours: int) -> dict:
    query: dict[str, Any] = {"patient_id": patient_id, "created_at": {"$gte": since}}
    if alert_id:
        query["_id"] = alert_id

    alerts = []
    cursor = db.col("alert_records").find(query).sort("created_at", -1).limit(50)
    async for doc in cursor:
        alerts.append(doc)

    evidence_rows = []
    for alert in alerts:
        evidence_rows.append({
            "record_id": str(alert.get("_id", "")),
            "patient_id": patient_id,
            "observed_at": alert.get("created_at"),
            "category": "alert",
            "code": alert.get("alert_type", ""),
            "name": alert.get("name", alert.get("alert_type", "")),
            "value": alert.get("trigger_value", ""),
            "unit": alert.get("unit", ""),
            "reference_range": alert.get("threshold_description", ""),
            "abnormal_flag": _severity_to_flag(alert.get("severity", "info")),
            "source_system": "alert_engine",
            "collection_name": "alert_records",
            "data_quality": "complete",
        })

    # 关联指标
    trigger_codes = list({a.get("trigger_code", "") for a in alerts if a.get("trigger_code")})
    metrics = await _query_metrics(db, patient_id, trigger_codes, since) if trigger_codes else []
    trends = await _query_trends(db, patient_id, trigger_codes, since) if trigger_codes else []

    scores = await _query_scores(db, patient_id, [], since)
    timeline = await _query_timeline(db, patient_id, since)

    severity = "critical" if any(a.get("severity") == "critical" for a in alerts) else (
        "high" if any(a.get("severity") == "high" for a in alerts) else "warning"
    )

    return {
        "conclusion": f"过去{hours}小时共 {len(alerts)} 条风险告警",
        "severity": severity,
        "confidence": 0.95 if alerts else 0.0,
        "metrics": metrics,
        "trends": trends,
        "evidence_rows": evidence_rows,
        "rule_calculation": scores,
        "timeline": timeline,
        "missing_data": [],
    }


# ── 医嘱闭环证据 ──────────────────────────────────────

async def _build_order_evidence(db, patient_id: str, order_id: str | None, since: datetime, hours: int) -> dict:
    # 告警 → 医嘱 → 执行 → 复查 → 结果
    alerts = []
    cursor = db.col("alert_records").find(
        {"patient_id": patient_id, "created_at": {"$gte": since}}
    ).sort("created_at", -1).limit(30)
    async for doc in cursor:
        alerts.append(doc)

    drugs = []
    cursor = db.col("drugExe").find(
        {"patient_id": patient_id, "time": {"$gte": since}}
    ).sort("time", -1).limit(50)
    async for doc in cursor:
        drugs.append(doc)

    evidence_rows = []
    for alert in alerts:
        evidence_rows.append({
            "record_id": str(alert.get("_id", "")),
            "patient_id": patient_id,
            "observed_at": alert.get("created_at"),
            "category": "alert",
            "code": alert.get("alert_type", ""),
            "name": alert.get("name", ""),
            "value": alert.get("trigger_value", ""),
            "unit": "",
            "reference_range": "",
            "abnormal_flag": _severity_to_flag(alert.get("severity", "info")),
            "source_system": "alert_engine",
            "collection_name": "alert_records",
            "data_quality": "complete",
        })

    for drug in drugs:
        evidence_rows.append({
            "record_id": str(drug.get("_id", "")),
            "patient_id": patient_id,
            "observed_at": drug.get("time"),
            "category": "medication",
            "code": drug.get("drug_code", ""),
            "name": drug.get("drug_name", ""),
            "value": drug.get("dose", ""),
            "unit": drug.get("unit", ""),
            "reference_range": "",
            "abnormal_flag": "normal",
            "source_system": "his",
            "collection_name": "drugExe",
            "data_quality": "complete",
        })

    timeline = await _query_timeline(db, patient_id, since)

    return {
        "conclusion": f"过去{hours}小时：{len(alerts)} 条告警，{len(drugs)} 条用药执行",
        "severity": "warning" if alerts else "stable",
        "confidence": 0.9,
        "metrics": [],
        "trends": [],
        "evidence_rows": evidence_rows,
        "rule_calculation": None,
        "timeline": timeline,
        "missing_data": [],
    }


# ── 护理证据 ──────────────────────────────────────────

async def _build_nursing_evidence(db, patient_id: str, nursing_key: str | None, since: datetime, hours: int) -> dict:
    evidence_rows = []

    # 尝试查询护理记录集合
    try:
        cursor = db.col("nursing_records").find(
            {"patient_id": patient_id, "created_at": {"$gte": since}}
        ).sort("created_at", -1).limit(50)
        async for doc in cursor:
            evidence_rows.append({
                "record_id": str(doc.get("_id", "")),
                "patient_id": patient_id,
                "observed_at": doc.get("created_at"),
                "category": "nursing",
                "code": doc.get("task_type", ""),
                "name": doc.get("task_name", doc.get("title", "")),
                "value": doc.get("status", ""),
                "unit": "",
                "reference_range": doc.get("scheduled_time", ""),
                "abnormal_flag": "normal" if doc.get("status") == "completed" else "high",
                "source_system": "nursing",
                "collection_name": "nursing_records",
                "data_quality": "complete",
            })
    except Exception:
        pass

    # 补充用药执行记录
    cursor = db.col("drugExe").find(
        {"patient_id": patient_id, "time": {"$gte": since}}
    ).sort("time", -1).limit(30)
    async for doc in cursor:
        evidence_rows.append({
            "record_id": str(doc.get("_id", "")),
            "patient_id": patient_id,
            "observed_at": doc.get("time"),
            "category": "medication_execution",
            "code": doc.get("drug_code", ""),
            "name": doc.get("drug_name", ""),
            "value": doc.get("status", ""),
            "unit": "",
            "reference_range": "",
            "abnormal_flag": "normal",
            "source_system": "his",
            "collection_name": "drugExe",
            "data_quality": "complete",
        })

    timeline = await _query_timeline(db, patient_id, since)

    return {
        "conclusion": f"过去{hours}小时护理相关记录 {len(evidence_rows)} 条",
        "severity": "info",
        "confidence": 0.85,
        "metrics": [],
        "trends": [],
        "evidence_rows": evidence_rows,
        "rule_calculation": None,
        "timeline": timeline,
        "missing_data": [],
    }


# ── 撤机证据 ──────────────────────────────────────────

async def _build_weaning_evidence(db, patient_id: str, since: datetime, hours: int) -> dict:
    # SBT 评分记录
    sbt_scores = []
    cursor = db.col("score").find(
        {"patient_id": patient_id, "score_type": "sbt_assessment", "calc_time": {"$gte": since}}
    ).sort("calc_time", -1).limit(10)
    async for doc in cursor:
        sbt_scores.append(doc)

    # 呼吸相关指标
    vent_codes = ["SpO2", "RR", "TV", "PEEP", "FiO2", "Pplat", "RSBI", "P/F_ratio"]
    metrics = await _query_metrics(db, patient_id, vent_codes, since)
    trends = await _query_trends(db, patient_id, vent_codes, since)

    evidence_rows = []
    for score in sbt_scores:
        evidence_rows.append({
            "record_id": str(score.get("_id", "")),
            "patient_id": patient_id,
            "observed_at": score.get("calc_time"),
            "category": "clinical_score",
            "code": "sbt_assessment",
            "name": "SBT 自主呼吸试验",
            "value": score.get("total_score", score.get("result", "")),
            "unit": "",
            "reference_range": "通过/未通过",
            "abnormal_flag": "normal" if score.get("result") == "pass" else "high",
            "source_system": "clinical_core",
            "collection_name": "score",
            "data_quality": "complete",
        })

    # 构建灯号状态
    lights = _build_weaning_lights(metrics, sbt_scores)
    passed = sum(1 for l in lights if l["ok"])
    total = len(lights)

    timeline = await _query_timeline(db, patient_id, since)
    rule_calc = await _query_scores(db, patient_id, ["weaning", "respiratory"], since)

    return {
        "conclusion": f"撤机评估：{passed}/{total} 项通过" if total > 0 else "暂无撤机评估数据",
        "severity": "stable" if passed == total else "warning",
        "confidence": 0.9 if total > 0 else 0.0,
        "metrics": metrics,
        "trends": trends,
        "evidence_rows": evidence_rows,
        "rule_calculation": {**rule_calc, "lights": lights} if rule_calc else {"lights": lights},
        "timeline": timeline,
        "missing_data": _detect_missing_data(vent_codes, metrics),
    }


# ── 转出证据 ──────────────────────────────────────────

async def _build_discharge_evidence(db, patient_id: str, since: datetime, hours: int) -> dict:
    # 转出评估指标
    discharge_codes = ["HR", "MAP", "SpO2", "FiO2", "GCS", "Urine_output_24h", "Lactate", "P/F_ratio"]
    metrics = await _query_metrics(db, patient_id, discharge_codes, since)
    trends = await _query_trends(db, patient_id, discharge_codes, since)

    # SOFA 评分
    scores = await _query_scores(db, patient_id, ["sofa"], since)

    # 构建灯号和百分比
    lights = _build_discharge_lights(metrics, scores)
    passed = sum(1 for l in lights if l["ok"])
    total = len(lights)
    percent = round(passed / total * 100) if total > 0 else 0

    evidence_rows = []
    for m in metrics:
        evidence_rows.append({
            "record_id": m.get("code", ""),
            "patient_id": patient_id,
            "observed_at": m.get("observed_at"),
            "category": "vital_sign",
            "code": m.get("code", ""),
            "name": m.get("name", m.get("code", "")),
            "value": m.get("value"),
            "unit": m.get("unit", ""),
            "reference_range": m.get("reference_range", ""),
            "abnormal_flag": m.get("abnormal_flag", "normal"),
            "source_system": "bedside",
            "collection_name": "bedside",
            "data_quality": "complete",
        })

    timeline = await _query_timeline(db, patient_id, since)
    missing = _detect_missing_data(discharge_codes, metrics)

    return {
        "conclusion": f"转出评估：{percent}% 达标（{passed}/{total} 项通过）",
        "severity": "stable" if percent >= 80 else "warning",
        "confidence": _compute_confidence(metrics, missing),
        "metrics": metrics,
        "trends": trends,
        "evidence_rows": evidence_rows,
        "rule_calculation": {
            "score_type": "discharge_readiness",
            "total_score": percent,
            "items": lights,
            "description": "转出就绪度评估",
        },
        "timeline": timeline,
        "missing_data": missing,
    }


# ── 规则噪声证据 ──────────────────────────────────────

async def _build_rule_noise_evidence(db, patient_id: str, rule_id: str | None, since: datetime, hours: int) -> dict:
    # 查询规则触发统计
    pipeline = [
        {"$match": {"created_at": {"$gte": since}}},
        {"$group": {
            "_id": "$alert_type",
            "count": {"$sum": 1},
            "confirmed": {"$sum": {"$cond": [{"$eq": ["$acknowledged", True]}, 1, 0]}},
            "overridden": {"$sum": {"$cond": [{"$eq": ["$overridden", True]}, 1, 0]}},
        }},
        {"$sort": {"count": -1}},
        {"$limit": 20},
    ]

    rule_stats = []
    async for doc in db.col("alert_records").aggregate(pipeline):
        total = doc.get("count", 0)
        confirmed = doc.get("confirmed", 0)
        overridden = doc.get("overridden", 0)
        ppv = confirmed / total if total > 0 else 0
        override_rate = overridden / total if total > 0 else 0
        rule_stats.append({
            "rule_id": doc.get("_id", ""),
            "rule_name": doc.get("_id", ""),
            "trigger_count": total,
            "confirmed_count": confirmed,
            "overridden_count": overridden,
            "ppv": round(ppv, 3),
            "override_rate": round(override_rate, 3),
        })

    evidence_rows = []
    for stat in rule_stats:
        evidence_rows.append({
            "record_id": stat["rule_id"],
            "patient_id": patient_id,
            "observed_at": since,
            "category": "rule_stat",
            "code": stat["rule_id"],
            "name": stat["rule_name"],
            "value": stat["trigger_count"],
            "unit": "次",
            "reference_range": "",
            "abnormal_flag": "high" if stat["override_rate"] > 0.3 else "normal",
            "source_system": "alert_engine",
            "collection_name": "alert_records",
            "data_quality": "complete",
        })

    return {
        "conclusion": f"过去{hours}小时 {len(rule_stats)} 条规则触发统计",
        "severity": "warning" if any(s["override_rate"] > 0.3 for s in rule_stats) else "info",
        "confidence": 0.85,
        "metrics": [],
        "trends": [],
        "evidence_rows": evidence_rows,
        "rule_calculation": {
            "score_type": "rule_noise",
            "items": rule_stats,
            "description": "规则触发统计与噪声分析",
            "statistical_scope": f"过去{hours}小时全部告警记录",
        },
        "timeline": [],
        "missing_data": [],
    }


# ── 生命体征证据 ──────────────────────────────────────

async def _build_vitals_evidence(db, patient_id: str, since: datetime, hours: int) -> dict:
    vital_codes = ["HR", "MAP", "SBP", "DBP", "SpO2", "RR", "T", "CVP"]
    metrics = await _query_metrics(db, patient_id, vital_codes, since)
    trends = await _query_trends(db, patient_id, vital_codes, since)
    evidence_rows = await _query_evidence_rows(db, patient_id, vital_codes, since)
    timeline = await _query_timeline(db, patient_id, since)
    missing = _detect_missing_data(vital_codes, metrics)

    return {
        "conclusion": f"过去{hours}小时生命体征数据 {len(evidence_rows)} 条",
        "severity": _compute_severity(metrics, evidence_rows),
        "confidence": _compute_confidence(metrics, missing),
        "metrics": metrics,
        "trends": trends,
        "evidence_rows": evidence_rows,
        "rule_calculation": None,
        "timeline": timeline,
        "missing_data": missing,
    }


# ── 未闭环证据 ──────────────────────────────────────

async def _build_unclosed_evidence(db, patient_id: str, since: datetime, hours: int) -> dict:
    alerts = []
    cursor = db.col("alert_records").find(
        {"patient_id": patient_id, "acknowledged": {"$ne": True}, "created_at": {"$gte": since}}
    ).sort("created_at", -1).limit(30)
    async for doc in cursor:
        alerts.append(doc)

    evidence_rows = []
    for alert in alerts:
        evidence_rows.append({
            "record_id": str(alert.get("_id", "")),
            "patient_id": patient_id,
            "observed_at": alert.get("created_at"),
            "category": "unclosed_alert",
            "code": alert.get("alert_type", ""),
            "name": alert.get("name", ""),
            "value": alert.get("trigger_value", ""),
            "unit": "",
            "reference_range": "",
            "abnormal_flag": _severity_to_flag(alert.get("severity", "info")),
            "source_system": "alert_engine",
            "collection_name": "alert_records",
            "data_quality": "complete",
        })

    timeline = await _query_timeline(db, patient_id, since)

    return {
        "conclusion": f"未闭环告警 {len(alerts)} 条",
        "severity": "high" if len(alerts) > 5 else "warning",
        "confidence": 0.95,
        "metrics": [],
        "trends": [],
        "evidence_rows": evidence_rows,
        "rule_calculation": None,
        "timeline": timeline,
        "missing_data": [],
    }


# ── 通用证据 ──────────────────────────────────────────

async def _build_general_evidence(db, patient_id: str, since: datetime, hours: int) -> dict:
    return {
        "conclusion": f"过去{hours}小时综合证据",
        "severity": "info",
        "confidence": 0.5,
        "metrics": [],
        "trends": [],
        "evidence_rows": [],
        "rule_calculation": None,
        "timeline": await _query_timeline(db, patient_id, since),
        "missing_data": [],
    }


# ── 共享查询工具 ──────────────────────────────────────

async def _query_metrics(db, patient_id: str, codes: list[str], since: datetime) -> list[dict]:
    """查询最新指标值。"""
    if not codes:
        return []

    metrics = []
    # 从 bedside 集合查询生命体征
    pipeline = [
        {"$match": {
            "patient_id": patient_id,
            "time": {"$gte": since},
            "code": {"$in": codes},
        }},
        {"$sort": {"time": -1}},
        {"$group": {
            "_id": "$code",
            "latest_value": {"$first": "$value"},
            "latest_time": {"$first": "$time"},
            "unit": {"$first": "$unit"},
            "min": {"$min": "$value"},
            "max": {"$max": "$value"},
            "count": {"$sum": 1},
        }},
    ]

    try:
        async for doc in db.col("bedside").aggregate(pipeline):
            code = doc.get("_id", "")
            value = doc.get("latest_value")
            metrics.append({
                "code": code,
                "name": _code_to_name(code),
                "value": value,
                "unit": doc.get("unit", ""),
                "observed_at": doc.get("latest_time"),
                "min": doc.get("min"),
                "max": doc.get("max"),
                "count": doc.get("count", 0),
                "reference_range": _get_reference_range(code),
                "abnormal_flag": _check_abnormal(code, value),
            })
    except Exception as exc:
        logger.warning("指标查询失败: %s", exc)

    # 从 labResult 查询检验指标
    lab_codes = [c for c in codes if c not in _VITAL_CODES]
    if lab_codes:
        try:
            pipeline[1]["$match"]["code"] = {"$in": lab_codes}
            async for doc in db.col("labResult").aggregate(pipeline):
                code = doc.get("_id", "")
                value = doc.get("latest_value")
                metrics.append({
                    "code": code,
                    "name": _code_to_name(code),
                    "value": value,
                    "unit": doc.get("unit", ""),
                    "observed_at": doc.get("latest_time"),
                    "min": doc.get("min"),
                    "max": doc.get("max"),
                    "count": doc.get("count", 0),
                    "reference_range": _get_reference_range(code),
                    "abnormal_flag": _check_abnormal(code, value),
                })
        except Exception as exc:
            logger.warning("检验指标查询失败: %s", exc)

    return metrics


async def _query_trends(db, patient_id: str, codes: list[str], since: datetime) -> list[dict]:
    """查询趋势数据点。"""
    if not codes:
        return []

    trends = []
    for code in codes[:8]:  # 限制最多8个指标的趋势
        points = []
        try:
            cursor = db.col("bedside").find(
                {"patient_id": patient_id, "code": code, "time": {"$gte": since}},
                {"value": 1, "time": 1, "_id": 0},
            ).sort("time", 1).limit(200)
            async for doc in cursor:
                points.append({"time": doc.get("time"), "value": doc.get("value")})
        except Exception:
            pass

        if not points:
            try:
                cursor = db.col("labResult").find(
                    {"patient_id": patient_id, "code": code, "time": {"$gte": since}},
                    {"value": 1, "time": 1, "_id": 0},
                ).sort("time", 1).limit(100)
                async for doc in cursor:
                    points.append({"time": doc.get("time"), "value": doc.get("value")})
            except Exception:
                pass

        if points:
            trends.append({
                "code": code,
                "name": _code_to_name(code),
                "points": points,
                "reference_range": _get_reference_range(code),
            })

    return trends


async def _query_evidence_rows(db, patient_id: str, codes: list[str], since: datetime) -> list[dict]:
    """查询原始证据行。"""
    if not codes:
        return []

    rows = []
    try:
        cursor = db.col("bedside").find(
            {"patient_id": patient_id, "code": {"$in": codes}, "time": {"$gte": since}}
        ).sort("time", -1).limit(200)
        async for doc in cursor:
            rows.append({
                "record_id": str(doc.get("_id", "")),
                "patient_id": patient_id,
                "observed_at": doc.get("time"),
                "category": "vital_sign",
                "code": doc.get("code", ""),
                "name": _code_to_name(doc.get("code", "")),
                "value": doc.get("value"),
                "unit": doc.get("unit", ""),
                "reference_range": _get_reference_range(doc.get("code", "")),
                "abnormal_flag": _check_abnormal(doc.get("code", ""), doc.get("value")),
                "source_system": "bedside_monitor",
                "collection_name": "bedside",
                "data_quality": "complete",
            })
    except Exception as exc:
        logger.warning("证据行查询失败: %s", exc)

    return rows


async def _query_scores(db, patient_id: str, score_types: list[str], since: datetime) -> dict | None:
    """查询评分记录。"""
    if not score_types:
        # 查询最近的任何评分
        score = await db.col("score").find_one(
            {"patient_id": patient_id, "calc_time": {"$gte": since}},
            sort=[("calc_time", -1)],
        )
    else:
        score = await db.col("score").find_one(
            {"patient_id": patient_id, "score_type": {"$in": score_types}, "calc_time": {"$gte": since}},
            sort=[("calc_time", -1)],
        )

    if not score:
        return None

    return {
        "score_type": score.get("score_type", ""),
        "total_score": score.get("total_score"),
        "items": score.get("items", []),
        "calc_time": score.get("calc_time"),
        "description": score.get("description", ""),
    }


async def _query_timeline(db, patient_id: str, since: datetime) -> list[dict]:
    """查询临床事件时间线。"""
    events = []

    # 告警事件
    try:
        cursor = db.col("alert_records").find(
            {"patient_id": patient_id, "created_at": {"$gte": since}}
        ).sort("created_at", -1).limit(30)
        async for doc in cursor:
            events.append({
                "time": doc.get("created_at"),
                "event_type": "alert",
                "title": doc.get("name", doc.get("alert_type", "")),
                "severity": doc.get("severity", "info"),
                "detail": doc.get("description", ""),
            })
    except Exception:
        pass

    # 用药事件
    try:
        cursor = db.col("drugExe").find(
            {"patient_id": patient_id, "time": {"$gte": since}}
        ).sort("time", -1).limit(30)
        async for doc in cursor:
            events.append({
                "time": doc.get("time"),
                "event_type": "medication",
                "title": doc.get("drug_name", ""),
                "severity": "info",
                "detail": f"{doc.get('dose', '')} {doc.get('unit', '')}",
            })
    except Exception:
        pass

    # 按时间排序
    events.sort(key=lambda e: str(e.get("time", "")), reverse=True)
    return events[:50]


async def _build_ai_analysis(db, patient_id: str, context_type: str, organ_system: str | None, since: datetime) -> dict | None:
    """构建 AI 分析结果。"""
    try:
        # 查询最近的 AI 分析记录
        ai_doc = await db.col("ai_analysis").find_one(
            {"patient_id": patient_id, "context_type": context_type},
            sort=[("created_at", -1)],
        )
        if ai_doc:
            return {
                "supporting_evidence": ai_doc.get("supporting", []),
                "opposing_evidence": ai_doc.get("opposing", []),
                "uncertainties": ai_doc.get("uncertainties", []),
                "disclaimer": "AI生成，待临床确认",
                "model": ai_doc.get("model", "unknown"),
                "generated_at": ai_doc.get("created_at"),
            }
    except Exception:
        pass

    return {
        "supporting_evidence": [],
        "opposing_evidence": [],
        "uncertainties": [],
        "disclaimer": "AI生成，待临床确认",
        "model": "pending",
        "generated_at": None,
    }


# ── 辅助函数 ──────────────────────────────────────────

_VITAL_CODES = {"HR", "MAP", "SBP", "DBP", "SpO2", "RR", "T", "CVP", "FiO2", "PEEP", "TV", "Pplat"}

_CODE_NAME_MAP = {
    "HR": "心率", "MAP": "平均动脉压", "SBP": "收缩压", "DBP": "舒张压",
    "SpO2": "血氧饱和度", "RR": "呼吸频率", "T": "体温", "CVP": "中心静脉压",
    "FiO2": "吸入氧浓度", "PEEP": "呼气末正压", "TV": "潮气量", "Pplat": "平台压",
    "PaO2": "动脉氧分压", "PaCO2": "动脉二氧化碳分压", "P/F_ratio": "氧合指数",
    "RSBI": "浅快呼吸指数", "driving_pressure": "驱动压", "mechanical_power": "机械功率",
    "Cr": "肌酐", "BUN": "尿素氮", "Urine_output_24h": "24小时尿量", "Urine_output_6h": "6小时尿量",
    "K": "钾", "Na": "钠", "pH": "pH值", "HCO3": "碳酸氢根",
    "TBIL": "总胆红素", "DBIL": "直接胆红素", "ALT": "谷丙转氨酶", "AST": "谷草转氨酶",
    "ALB": "白蛋白", "PT": "凝血酶原时间", "INR": "国际标准化比值", "NH3": "血氨",
    "GCS": "格拉斯哥昏迷评分", "RASS": "Richmond躁动镇静评分", "CAM_ICU": "CAM-ICU谵妄评估",
    "PLT": "血小板", "APTT": "活化部分凝血活酶时间", "Fib": "纤维蛋白原", "D_dimer": "D-二聚体",
    "WBC": "白细胞", "PCT": "降钙素原", "CRP": "C反应蛋白", "temperature": "体温",
    "Lactate": "乳酸", "NE_dose": "去甲肾上腺素剂量", "ScvO2": "中心静脉血氧饱和度",
    "prealbumin": "前白蛋白", "BMI": "体重指数", "NRS2002": "NRS2002营养评分",
}

_REFERENCE_RANGES = {
    "HR": "60-100 bpm", "MAP": "70-105 mmHg", "SBP": "90-140 mmHg", "DBP": "60-90 mmHg",
    "SpO2": "≥95%", "RR": "12-20 次/min", "T": "36.0-37.5°C", "CVP": "5-12 cmH2O",
    "Cr": "44-133 μmol/L", "BUN": "2.9-8.2 mmol/L", "K": "3.5-5.5 mmol/L", "Na": "135-145 mmol/L",
    "pH": "7.35-7.45", "PLT": "100-300 ×10⁹/L", "WBC": "4-10 ×10⁹/L",
    "Lactate": "<2 mmol/L", "GCS": "15分", "P/F_ratio": "≥300 mmHg",
}

_ABNORMAL_THRESHOLDS = {
    "HR": {"low": 50, "high": 120, "critical_low": 40, "critical_high": 150},
    "MAP": {"low": 65, "high": 110, "critical_low": 55, "critical_high": 130},
    "SpO2": {"low": 90, "high": None, "critical_low": 85, "critical_high": None},
    "RR": {"low": 8, "high": 25, "critical_low": 6, "critical_high": 35},
    "T": {"low": 36.0, "high": 38.0, "critical_low": 35.0, "critical_high": 39.5},
    "Lactate": {"low": None, "high": 2.0, "critical_low": None, "critical_high": 4.0},
    "Cr": {"low": None, "high": 133, "critical_low": None, "critical_high": 300},
    "K": {"low": 3.5, "high": 5.5, "critical_low": 3.0, "critical_high": 6.0},
    "PLT": {"low": 100, "high": None, "critical_low": 50, "critical_high": None},
    "GCS": {"low": 13, "high": None, "critical_low": 8, "critical_high": None},
}


def _code_to_name(code: str) -> str:
    return _CODE_NAME_MAP.get(code, code)


def _get_reference_range(code: str) -> str:
    return _REFERENCE_RANGES.get(code, "")


def _check_abnormal(code: str, value: Any) -> str:
    if value is None:
        return "missing"
    try:
        num = float(value)
    except (ValueError, TypeError):
        return "normal"

    thresholds = _ABNORMAL_THRESHOLDS.get(code)
    if not thresholds:
        return "normal"

    if thresholds.get("critical_low") is not None and num < thresholds["critical_low"]:
        return "critical"
    if thresholds.get("critical_high") is not None and num > thresholds["critical_high"]:
        return "critical"
    if thresholds.get("low") is not None and num < thresholds["low"]:
        return "low"
    if thresholds.get("high") is not None and num > thresholds["high"]:
        return "high"
    return "normal"


def _severity_to_flag(severity: str) -> str:
    return {"critical": "critical", "high": "high", "warning": "high", "info": "normal", "stable": "normal"}.get(severity, "normal")


def _compute_severity(metrics: list[dict], evidence_rows: list[dict]) -> str:
    flags = [m.get("abnormal_flag", "normal") for m in metrics]
    if "critical" in flags:
        return "critical"
    if "high" in flags or "low" in flags:
        return "high"
    if evidence_rows:
        return "warning"
    return "stable"


def _compute_confidence(metrics: list[dict], missing: list[dict]) -> float:
    if not metrics:
        return 0.0
    total = len(metrics) + len(missing)
    complete = len(metrics)
    return round(complete / total, 2) if total > 0 else 0.0


def _detect_missing_data(expected_codes: list[str], metrics: list[dict]) -> list[dict]:
    found = {m["code"] for m in metrics}
    missing = []
    for code in expected_codes:
        if code not in found:
            missing.append({
                "code": code,
                "name": _code_to_name(code),
                "reason": "数据不可用",
                "impact": "该指标的评估结果为不可计算",
            })
    return missing


def _build_conclusion(system_label: str, severity: str, metrics: list[dict], missing: list[dict]) -> str:
    severity_text = {"critical": "危急", "high": "高风险", "warning": "预警", "info": "一般", "stable": "稳定"}.get(severity, "未知")
    metric_count = len(metrics)
    missing_count = len(missing)
    parts = [f"{system_label}：{severity_text}"]
    if metric_count:
        parts.append(f"共 {metric_count} 项指标")
    if missing_count:
        parts.append(f"{missing_count} 项数据缺失（不可计算）")
    return "，".join(parts)


def _build_weaning_lights(metrics: list[dict], sbt_scores: list[dict]) -> list[dict]:
    lights = []
    metric_map = {m["code"]: m for m in metrics}

    # RSBI < 105
    rsbi = metric_map.get("RSBI")
    lights.append({"label": "RSBI < 105", "ok": rsbi and rsbi.get("value") is not None and float(rsbi["value"]) < 105 if rsbi else False})
    # SpO2 > 90%
    spo2 = metric_map.get("SpO2")
    lights.append({"label": "SpO2 > 90%", "ok": spo2 and spo2.get("value") is not None and float(spo2["value"]) > 90 if spo2 else False})
    # PEEP ≤ 8
    peep = metric_map.get("PEEP")
    lights.append({"label": "PEEP ≤ 8", "ok": peep and peep.get("value") is not None and float(peep["value"]) <= 8 if peep else False})
    # FiO2 ≤ 0.4
    fio2 = metric_map.get("FiO2")
    lights.append({"label": "FiO2 ≤ 40%", "ok": fio2 and fio2.get("value") is not None and float(fio2["value"]) <= 40 if fio2 else False})
    # SBT 通过
    sbt_pass = any(s.get("result") == "pass" for s in sbt_scores)
    lights.append({"label": "SBT 通过", "ok": sbt_pass})

    return lights


def _build_discharge_lights(metrics: list[dict], scores: dict | None) -> list[dict]:
    lights = []
    metric_map = {m["code"]: m for m in metrics}

    # 循环稳定
    hr = metric_map.get("HR")
    map_val = metric_map.get("MAP")
    lights.append({"label": "循环稳定", "ok": (
        hr and hr.get("value") is not None and 60 <= float(hr["value"]) <= 100 and
        map_val and map_val.get("value") is not None and 65 <= float(map_val["value"]) <= 105
    ) if hr and map_val else False})

    # 氧合达标
    spo2 = metric_map.get("SpO2")
    pf = metric_map.get("P/F_ratio")
    lights.append({"label": "氧合达标", "ok": (
        spo2 and spo2.get("value") is not None and float(spo2["value"]) >= 92
    ) if spo2 else False})

    # 意识清楚
    gcs = metric_map.get("GCS")
    lights.append({"label": "意识清楚", "ok": gcs and gcs.get("value") is not None and float(gcs["value"]) >= 13 if gcs else False})

    # 尿量充足
    urine = metric_map.get("Urine_output_24h")
    lights.append({"label": "尿量充足", "ok": urine and urine.get("value") is not None and float(urine["value"]) >= 500 if urine else False})

    # 乳酸正常
    lactate = metric_map.get("Lactate")
    lights.append({"label": "乳酸正常", "ok": lactate and lactate.get("value") is not None and float(lactate["value"]) < 2.0 if lactate else False})

    # SOFA ≤ 6
    if scores and scores.get("total_score") is not None:
        lights.append({"label": "SOFA ≤ 6", "ok": float(scores["total_score"]) <= 6})
    else:
        lights.append({"label": "SOFA ≤ 6", "ok": False})

    return lights


def _error_response(message: str) -> dict:
    return {
        "conclusion": message,
        "severity": "info",
        "confidence": 0.0,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data_cutoff_at": datetime.now(timezone.utc).isoformat(),
        "metrics": [],
        "trends": [],
        "evidence_rows": [],
        "rule_calculation": None,
        "ai_analysis": None,
        "timeline": [],
        "missing_data": [],
        "provenance": {},
        "model_version": "icu-evidence-v1.0",
        "rule_version": "clinical-core-v1.0",
    }
