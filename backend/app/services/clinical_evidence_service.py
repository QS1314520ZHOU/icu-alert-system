"""临床证据链统一查询服务。

P0 修复版：
- 所有查询必须包含 patient_id 过滤
- rule_noise 仅查询当前患者数据
- bedside 和 labResult 使用独立聚合管道
- 置信度拆分为 evidence_completeness / rule_reliability / model_probability
- 缺失值不回退为 0，使用 null + calculable=false
- context_id 必须真实生效，找不到返回 None（路由层返回 404）
- 证据行始终返回 source_system（临床来源名称）
- AI 分析无真实结果时不渲染
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app import runtime
from app.services.audit_service import write_audit_log
from app.utils.serialization import serialize_doc

logger = logging.getLogger("icu-alert")

_COLLECTION_MAP = {
    "vitals": "bedside",
    "labs": "labResult",
    "alerts": "alert_records",
    "scores": "score",
    "drugs": "drugExe",
    "nursing": "nursing_records",
    "orders": "order_records",
}

_TIME_RANGE_HOURS = {
    "1h": 1, "6h": 6, "12h": 12, "24h": 24,
    "48h": 48, "72h": 72, "7d": 168,
}

_ORGAN_SYSTEM_CODES: dict[str, dict[str, Any]] = {
    "respiratory": {
        "label": "呼吸系统",
        "codes": ["SpO2", "PaO2", "PaCO2", "FiO2", "P/F_ratio", "RR", "TV", "PEEP", "Pplat"],
        "score_types": ["ards", "respiratory"],
    },
    "circulatory": {
        "label": "循环系统",
        "codes": ["HR", "MAP", "SBP", "DBP", "CVP", "Lactate", "ScvO2"],
        "score_types": ["sepsis", "septic_shock"],
    },
    "renal": {
        "label": "肾脏系统",
        "codes": ["Cr", "BUN", "Urine_output_24h", "K", "Na", "pH"],
        "score_types": ["aki"],
    },
    "hepatic": {
        "label": "肝脏系统",
        "codes": ["TBIL", "DBIL", "ALT", "AST", "ALB", "PT", "INR"],
        "score_types": [],
    },
    "neurologic": {
        "label": "神经系统",
        "codes": ["GCS", "RASS", "CAM_ICU"],
        "score_types": ["deliric", "pre_deliric"],
    },
    "coagulation": {
        "label": "凝血系统",
        "codes": ["PLT", "PT", "APTT", "Fib", "D_dimer", "INR"],
        "score_types": [],
    },
    "infection": {
        "label": "感染",
        "codes": ["WBC", "PCT", "CRP", "temperature"],
        "score_types": ["sepsis", "qsofa"],
    },
    "nutrition": {
        "label": "营养",
        "codes": ["prealbumin", "albumin", "NRS2002"],
        "score_types": [],
    },
}

# 临床来源名称映射（面向用户展示）
_SOURCE_DISPLAY_MAP = {
    "bedside": "监护仪",
    "bedside_monitor": "监护仪",
    "labResult": "LIS检验系统",
    "lis": "LIS检验系统",
    "alert_records": "预警引擎",
    "alert_engine": "预警引擎",
    "score": "临床评分引擎",
    "clinical_core": "临床评分引擎",
    "drugExe": "HIS医嘱系统",
    "his": "HIS医嘱系统",
    "nursing_records": "护理信息系统",
    "nursing": "护理信息系统",
    "order_records": "HIS医嘱系统",
    "ai_analysis": "AI分析引擎",
}

_VITAL_CODES = {"HR", "MAP", "SBP", "DBP", "SpO2", "RR", "T", "CVP", "FiO2", "PEEP", "TV", "Pplat"}

_CODE_NAME_MAP = {
    "HR": "心率", "MAP": "平均动脉压", "SBP": "收缩压", "DBP": "舒张压",
    "SpO2": "血氧饱和度", "RR": "呼吸频率", "T": "体温", "temperature": "体温",
    "CVP": "中心静脉压", "FiO2": "吸入氧浓度", "PEEP": "呼气末正压",
    "TV": "潮气量", "Pplat": "平台压", "PaO2": "动脉氧分压", "PaCO2": "动脉二氧化碳分压",
    "P/F_ratio": "氧合指数", "RSBI": "浅快呼吸指数",
    "Cr": "肌酐", "BUN": "尿素氮", "Urine_output_24h": "24小时尿量",
    "K": "钾", "Na": "钠", "pH": "pH值", "HCO3": "碳酸氢根",
    "TBIL": "总胆红素", "DBIL": "直接胆红素", "ALT": "谷丙转氨酶", "AST": "谷草转氨酶",
    "ALB": "白蛋白", "PT": "凝血酶原时间", "INR": "国际标准化比值",
    "GCS": "格拉斯哥昏迷评分", "RASS": "Richmond躁动镇静评分", "CAM_ICU": "CAM-ICU",
    "PLT": "血小板", "APTT": "活化部分凝血活酶时间", "Fib": "纤维蛋白原", "D_dimer": "D-二聚体",
    "WBC": "白细胞", "PCT": "降钙素原", "CRP": "C反应蛋白",
    "Lactate": "乳酸", "ScvO2": "中心静脉血氧饱和度",
    "prealbumin": "前白蛋白", "albumin": "白蛋白", "NRS2002": "NRS2002营养评分",
    "NE_dose": "去甲肾上腺素剂量",
}

_REFERENCE_RANGES = {
    "HR": "60-100 bpm", "MAP": "70-105 mmHg", "SBP": "90-140 mmHg", "DBP": "60-90 mmHg",
    "SpO2": "≥95%", "RR": "12-20 次/min", "T": "36.0-37.5°C", "temperature": "36.0-37.5°C",
    "CVP": "5-12 cmH2O", "Cr": "44-133 μmol/L", "BUN": "2.9-8.2 mmol/L",
    "K": "3.5-5.5 mmol/L", "Na": "135-145 mmol/L", "pH": "7.35-7.45",
    "PLT": "100-300 ×10⁹/L", "WBC": "4-10 ×10⁹/L", "CRP": "<10 mg/L", "PCT": "<0.05 ng/mL",
    "Lactate": "<2 mmol/L", "GCS": "15分", "P/F_ratio": "≥300 mmHg",
    "TBIL": "0-26 μmol/L", "ALT": "0-40 U/L", "AST": "0-40 U/L", "ALB": "35-55 g/L",
    "PT": "11-14 s", "INR": "0.8-1.2", "APTT": "25-35 s",
}

_ABNORMAL_THRESHOLDS = {
    "HR": {"low": 50, "high": 120, "critical_low": 40, "critical_high": 150},
    "MAP": {"low": 65, "high": 110, "critical_low": 55, "critical_high": 130},
    "SpO2": {"low": 90, "high": None, "critical_low": 85, "critical_high": None},
    "RR": {"low": 8, "high": 25, "critical_low": 6, "critical_high": 35},
    "T": {"low": 36.0, "high": 38.0, "critical_low": 35.0, "critical_high": 39.5},
    "temperature": {"low": 36.0, "high": 38.0, "critical_low": 35.0, "critical_high": 39.5},
    "Lactate": {"low": None, "high": 2.0, "critical_low": None, "critical_high": 4.0},
    "Cr": {"low": None, "high": 133, "critical_low": None, "critical_high": 300},
    "K": {"low": 3.5, "high": 5.5, "critical_low": 3.0, "critical_high": 6.0},
    "PLT": {"low": 100, "high": None, "critical_low": 50, "critical_high": None},
    "GCS": {"low": 13, "high": None, "critical_low": 8, "critical_high": None},
    "WBC": {"low": 4.0, "high": 10.0, "critical_low": 2.0, "critical_high": 20.0},
    "CRP": {"low": None, "high": 10.0, "critical_low": None, "critical_high": 100.0},
    "PCT": {"low": None, "high": 0.05, "critical_low": None, "critical_high": 2.0},
}


# ── 主入口 ──────────────────────────────────────────

async def get_evidence(
    db,
    patient_id: str,
    context_type: str,
    current_user: dict[str, Any],
    context_id: str | None = None,
    organ_system: str | None = None,
    time_range: str = "24h",
    include_raw: bool = False,
    include_ai: bool = False,
) -> dict[str, Any] | None:
    """统一证据查询入口。

    返回 None 表示患者不存在（路由层返回 404）。
    返回 dict 但含 "calculable": false 表示数据不足（路由层返回 200）。
    """
    if db is None:
        raise ServiceUnavailable("数据库不可用")

    hours = _TIME_RANGE_HOURS.get(time_range, 24)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    now = datetime.now(timezone.utc)

    # 验证患者存在
    patient = await db.col("patient").find_one(
        {"_id": patient_id}, {"_id": 1, "_name": 1, "hisBed": 1, "hisDept": 1}
    )
    if not patient:
        return None

    actor = current_user.get("username", "unknown")

    # 根据 context_type 分发，context_id 必须真实生效
    if context_type == "organ_system":
        result = await _build_organ_evidence(db, patient_id, organ_system or "respiratory", since, hours)
    elif context_type == "risk":
        result = await _build_risk_evidence(db, patient_id, context_id, since, hours)
        if context_id and result is _NOT_FOUND:
            return None
    elif context_type == "order":
        result = await _build_order_evidence(db, patient_id, context_id, since, hours)
        if context_id and result is _NOT_FOUND:
            return None
    elif context_type == "nursing":
        result = await _build_nursing_evidence(db, patient_id, context_id, since, hours)
        if context_id and result is _NOT_FOUND:
            return None
    elif context_type == "weaning":
        result = await _build_weaning_evidence(db, patient_id, since, hours)
    elif context_type == "discharge":
        result = await _build_discharge_evidence(db, patient_id, since, hours)
    elif context_type == "rule_noise":
        result = await _build_rule_noise_evidence(db, patient_id, context_id, since, hours)
        if context_id and result is _NOT_FOUND:
            return None
    elif context_type == "vitals":
        result = await _build_vitals_evidence(db, patient_id, since, hours)
    elif context_type == "unclosed":
        result = await _build_unclosed_evidence(db, patient_id, since, hours)
    else:
        result = await _build_general_evidence(db, patient_id, since, hours)

    if result is _NOT_FOUND:
        return None

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

    # AI 分析：无真实结果时返回 None
    if include_ai:
        ai_result = await _build_ai_analysis(db, patient_id, context_type, context_id, organ_system, since)
        result["ai_analysis"] = ai_result
    else:
        result["ai_analysis"] = None

    # source_system 始终返回临床来源名称，collection_name 仅 include_raw 时返回
    for row in result.get("evidence_rows", []):
        raw_source = row.get("source_system", "")
        row["source_system"] = _SOURCE_DISPLAY_MAP.get(raw_source, raw_source)
        if not include_raw:
            row.pop("collection_name", None)
            row.pop("source_record_id", None)

    # 审计日志（actor 来自信可信会话）
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


class ServiceUnavailable(Exception):
    pass


_NOT_FOUND = object()  # 哨兵值：context_id 对应的记录不存在


# ── 器官系统证据 ──────────────────────────────────────

async def _build_organ_evidence(db, patient_id: str, organ_system: str, since: datetime, hours: int) -> dict:
    organ_cfg = _ORGAN_SYSTEM_CODES.get(organ_system, _ORGAN_SYSTEM_CODES["respiratory"])
    codes = organ_cfg["codes"]
    score_types = organ_cfg["score_types"]

    metrics = await _query_metrics(db, patient_id, codes, since)
    trends = await _query_trends(db, patient_id, codes, since)
    evidence_rows = await _query_evidence_rows(db, patient_id, codes, since)
    rule_calc = await _query_scores(db, patient_id, score_types, since)
    timeline = await _query_timeline(db, patient_id, since)
    missing = _detect_missing_data(codes, metrics)

    completeness = _compute_evidence_completeness(metrics, missing)
    severity = _compute_severity(metrics, evidence_rows)
    conclusion = _build_conclusion(organ_cfg["label"], severity, metrics, missing)

    return {
        "conclusion": conclusion,
        "severity": severity,
        "calculable": completeness > 0,
        "confidence": {
            "evidence_completeness": completeness,
            "rule_reliability": 1.0 if rule_calc else None,
            "model_probability": None,
        },
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

    # 如果指定了 alert_id 但未找到，返回 _NOT_FOUND
    if alert_id and not alerts:
        return _NOT_FOUND  # type: ignore[return-value]

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
            "source_record_id": str(alert.get("_id", "")),
            "data_quality": "complete",
        })

    trigger_codes = list({a.get("trigger_code", "") for a in alerts if a.get("trigger_code")})
    metrics = await _query_metrics(db, patient_id, trigger_codes, since) if trigger_codes else []
    trends = await _query_trends(db, patient_id, trigger_codes, since) if trigger_codes else []
    timeline = await _query_timeline(db, patient_id, since)
    missing = _detect_missing_data(trigger_codes, metrics)

    severity = "critical" if any(a.get("severity") == "critical" for a in alerts) else (
        "high" if any(a.get("severity") == "high" for a in alerts) else "warning"
    )

    return {
        "conclusion": f"过去{hours}小时共 {len(alerts)} 条风险告警",
        "severity": severity,
        "calculable": True,
        "confidence": {
            "evidence_completeness": _compute_evidence_completeness(metrics, missing),
            "rule_reliability": None,
            "model_probability": None,
        },
        "metrics": metrics,
        "trends": trends,
        "evidence_rows": evidence_rows,
        "rule_calculation": None,
        "timeline": timeline,
        "missing_data": missing,
    }


# ── 医嘱闭环证据 ──────────────────────────────────────

async def _build_order_evidence(db, patient_id: str, order_id: str | None, since: datetime, hours: int) -> dict:
    alert_query: dict[str, Any] = {"patient_id": patient_id, "created_at": {"$gte": since}}
    drug_query: dict[str, Any] = {"patient_id": patient_id, "time": {"$gte": since}}

    if order_id:
        # context_id 生效：只查对应记录
        alert_query["_id"] = order_id
        drug_query["_id"] = order_id

    alerts = []
    cursor = db.col("alert_records").find(alert_query).sort("created_at", -1).limit(30)
    async for doc in cursor:
        alerts.append(doc)

    drugs = []
    cursor = db.col("drugExe").find(drug_query).sort("time", -1).limit(50)
    async for doc in cursor:
        drugs.append(doc)

    if order_id and not alerts and not drugs:
        return _NOT_FOUND  # type: ignore[return-value]

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
            "source_record_id": str(alert.get("_id", "")),
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
            "source_record_id": str(drug.get("_id", "")),
            "data_quality": "complete",
        })

    timeline = await _query_timeline(db, patient_id, since)

    return {
        "conclusion": f"过去{hours}小时：{len(alerts)} 条告警，{len(drugs)} 条用药执行",
        "severity": "warning" if alerts else "stable",
        "calculable": True,
        "confidence": {
            "evidence_completeness": 1.0,
            "rule_reliability": None,
            "model_probability": None,
        },
        "metrics": [],
        "trends": [],
        "evidence_rows": evidence_rows,
        "rule_calculation": None,
        "timeline": timeline,
        "missing_data": [],
    }


# ── 护理证据 ──────────────────────────────────────────

async def _build_nursing_evidence(db, patient_id: str, nursing_key: str | None, since: datetime, hours: int) -> dict:
    nursing_query: dict[str, Any] = {"patient_id": patient_id, "created_at": {"$gte": since}}
    if nursing_key:
        nursing_query["$or"] = [
            {"task_type": nursing_key},
            {"task_key": nursing_key},
            {"key": nursing_key},
        ]

    evidence_rows = []
    try:
        cursor = db.col("nursing_records").find(nursing_query).sort("created_at", -1).limit(50)
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
                "source_record_id": str(doc.get("_id", "")),
                "data_quality": "complete",
            })
    except Exception:
        pass

    if nursing_key and not evidence_rows:
        return _NOT_FOUND  # type: ignore[return-value]

    timeline = await _query_timeline(db, patient_id, since)

    return {
        "conclusion": f"过去{hours}小时护理相关记录 {len(evidence_rows)} 条",
        "severity": "info",
        "calculable": True,
        "confidence": {
            "evidence_completeness": 1.0 if evidence_rows else 0.0,
            "rule_reliability": None,
            "model_probability": None,
        },
        "metrics": [],
        "trends": [],
        "evidence_rows": evidence_rows,
        "rule_calculation": None,
        "timeline": timeline,
        "missing_data": [],
    }


# ── 撤机证据 ──────────────────────────────────────────

async def _build_weaning_evidence(db, patient_id: str, since: datetime, hours: int) -> dict:
    sbt_scores = []
    cursor = db.col("score").find(
        {"patient_id": patient_id, "score_type": "sbt_assessment", "calc_time": {"$gte": since}}
    ).sort("calc_time", -1).limit(10)
    async for doc in cursor:
        sbt_scores.append(doc)

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
            "source_record_id": str(score.get("_id", "")),
            "data_quality": "complete",
        })

    lights = _build_weaning_lights(metrics, sbt_scores)
    passed = sum(1 for l in lights if l["status"] == "pass")
    total = len(lights)
    missing = _detect_missing_data(vent_codes, metrics)

    # 计算性：有数据的灯号占比
    available = sum(1 for l in lights if l["status"] != "unavailable")
    calculable = available >= 3  # 至少3项有数据才可计算

    rule_calc = await _query_scores(db, patient_id, ["weaning", "respiratory"], since)

    return {
        "conclusion": f"撤机评估：{passed}/{available} 项通过" if available > 0 else "撤机评估：数据不足，不可计算",
        "severity": "stable" if calculable and passed == available else ("warning" if calculable else "info"),
        "calculable": calculable,
        "confidence": {
            "evidence_completeness": _compute_evidence_completeness(metrics, missing),
            "rule_reliability": 1.0 if rule_calc else None,
            "model_probability": None,
        },
        "metrics": metrics,
        "trends": trends,
        "evidence_rows": evidence_rows,
        "rule_calculation": {**(rule_calc or {}), "lights": lights},
        "timeline": await _query_timeline(db, patient_id, since),
        "missing_data": missing,
    }


# ── 转出证据 ──────────────────────────────────────────

async def _build_discharge_evidence(db, patient_id: str, since: datetime, hours: int) -> dict:
    discharge_codes = ["HR", "MAP", "SpO2", "FiO2", "GCS", "Urine_output_24h", "Lactate", "P/F_ratio"]
    metrics = await _query_metrics(db, patient_id, discharge_codes, since)
    trends = await _query_trends(db, patient_id, discharge_codes, since)
    scores = await _query_scores(db, patient_id, ["sofa"], since)

    lights = _build_discharge_lights(metrics, scores)
    passed = sum(1 for l in lights if l["status"] == "pass")
    available = sum(1 for l in lights if l["status"] != "unavailable")
    total = len(lights)

    calculable = available >= 4
    percent = round(passed / available * 100) if available > 0 else None

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
            "source_record_id": m.get("code", ""),
            "data_quality": "complete",
        })

    timeline = await _query_timeline(db, patient_id, since)
    missing = _detect_missing_data(discharge_codes, metrics)

    return {
        "conclusion": f"转出评估：{percent}% 达标（{passed}/{available} 项通过）" if calculable else "转出评估：数据不足，不可计算",
        "severity": "stable" if calculable and percent is not None and percent >= 80 else ("warning" if calculable else "info"),
        "calculable": calculable,
        "confidence": {
            "evidence_completeness": _compute_evidence_completeness(metrics, missing),
            "rule_reliability": 1.0 if scores else None,
            "model_probability": None,
        },
        "metrics": metrics,
        "trends": trends,
        "evidence_rows": evidence_rows,
        "rule_calculation": {
            "score_type": "discharge_readiness",
            "total_score": percent,
            "calculable": calculable,
            "items": lights,
            "description": "转出就绪度评估",
        },
        "timeline": timeline,
        "missing_data": missing,
    }


# ── 规则噪声证据（仅当前患者） ────────────────────────

async def _build_rule_noise_evidence(db, patient_id: str, rule_id: str | None, since: datetime, hours: int) -> dict:
    # P0修复：必须包含 patient_id 过滤
    match_stage: dict[str, Any] = {
        "patient_id": patient_id,
        "created_at": {"$gte": since},
    }
    if rule_id:
        match_stage["alert_type"] = rule_id

    pipeline = [
        {"$match": match_stage},
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

    if rule_id and not rule_stats:
        return _NOT_FOUND  # type: ignore[return-value]

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
            "source_record_id": stat["rule_id"],
            "data_quality": "complete",
        })

    return {
        "conclusion": f"过去{hours}小时当前患者 {len(rule_stats)} 条规则触发统计",
        "severity": "warning" if any(s["override_rate"] > 0.3 for s in rule_stats) else "info",
        "calculable": True,
        "confidence": {
            "evidence_completeness": 1.0,
            "rule_reliability": None,
            "model_probability": None,
        },
        "metrics": [],
        "trends": [],
        "evidence_rows": evidence_rows,
        "rule_calculation": {
            "score_type": "rule_noise",
            "items": rule_stats,
            "description": "规则触发统计与噪声分析（仅当前患者）",
            "statistical_scope": f"过去{hours}小时患者 {patient_id} 的告警记录",
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
        "calculable": len(metrics) > 0,
        "confidence": {
            "evidence_completeness": _compute_evidence_completeness(metrics, missing),
            "rule_reliability": None,
            "model_probability": None,
        },
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
            "source_record_id": str(alert.get("_id", "")),
            "data_quality": "complete",
        })

    return {
        "conclusion": f"未闭环告警 {len(alerts)} 条",
        "severity": "high" if len(alerts) > 5 else "warning",
        "calculable": True,
        "confidence": {
            "evidence_completeness": 1.0,
            "rule_reliability": None,
            "model_probability": None,
        },
        "metrics": [],
        "trends": [],
        "evidence_rows": evidence_rows,
        "rule_calculation": None,
        "timeline": await _query_timeline(db, patient_id, since),
        "missing_data": [],
    }


# ── 通用证据 ──────────────────────────────────────────

async def _build_general_evidence(db, patient_id: str, since: datetime, hours: int) -> dict:
    return {
        "conclusion": f"过去{hours}小时综合证据",
        "severity": "info",
        "calculable": False,
        "confidence": {
            "evidence_completeness": 0.0,
            "rule_reliability": None,
            "model_probability": None,
        },
        "metrics": [],
        "trends": [],
        "evidence_rows": [],
        "rule_calculation": None,
        "timeline": await _query_timeline(db, patient_id, since),
        "missing_data": [],
    }


# ── 共享查询工具 ──────────────────────────────────────

async def _query_metrics(db, patient_id: str, codes: list[str], since: datetime) -> list[dict]:
    """查询最新指标值。bedside 和 labResult 使用独立聚合管道。"""
    if not codes:
        return []

    metrics = []
    vital_codes = [c for c in codes if c in _VITAL_CODES]
    lab_codes = [c for c in codes if c not in _VITAL_CODES]

    # 独立管道：bedside（生命体征）
    if vital_codes:
        pipeline_vital = [
            {"$match": {
                "patient_id": patient_id,
                "time": {"$gte": since},
                "code": {"$in": vital_codes},
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
            async for doc in db.col("bedside").aggregate(pipeline_vital):
                code = doc.get("_id", "")
                value = doc.get("latest_value")
                metrics.append(_build_metric_entry(code, value, doc))
        except Exception as exc:
            logger.warning("bedside 指标查询失败: %s", exc)

    # 独立管道：labResult（检验指标）
    if lab_codes:
        pipeline_lab = [
            {"$match": {
                "patient_id": patient_id,
                "time": {"$gte": since},
                "code": {"$in": lab_codes},
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
            async for doc in db.col("labResult").aggregate(pipeline_lab):
                code = doc.get("_id", "")
                value = doc.get("latest_value")
                metrics.append(_build_metric_entry(code, value, doc))
        except Exception as exc:
            logger.warning("labResult 指标查询失败: %s", exc)

    return metrics


def _build_metric_entry(code: str, value: Any, doc: dict) -> dict:
    return {
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
    }


async def _query_trends(db, patient_id: str, codes: list[str], since: datetime) -> list[dict]:
    if not codes:
        return []

    trends = []
    for code in codes[:8]:
        points = []
        collection = "bedside" if code in _VITAL_CODES else "labResult"
        try:
            cursor = db.col(collection).find(
                {"patient_id": patient_id, "code": code, "time": {"$gte": since}},
                {"value": 1, "time": 1, "_id": 0},
            ).sort("time", 1).limit(200)
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
    if not codes:
        return []

    rows = []
    vital_codes = [c for c in codes if c in _VITAL_CODES]
    lab_codes = [c for c in codes if c not in _VITAL_CODES]

    # bedside 证据行
    if vital_codes:
        try:
            cursor = db.col("bedside").find(
                {"patient_id": patient_id, "code": {"$in": vital_codes}, "time": {"$gte": since}}
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
                    "source_system": "bedside",
                    "source_record_id": str(doc.get("_id", "")),
                    "data_quality": "complete",
                })
        except Exception as exc:
            logger.warning("bedside 证据行查询失败: %s", exc)

    # labResult 证据行
    if lab_codes:
        try:
            cursor = db.col("labResult").find(
                {"patient_id": patient_id, "code": {"$in": lab_codes}, "time": {"$gte": since}}
            ).sort("time", -1).limit(200)
            async for doc in cursor:
                rows.append({
                    "record_id": str(doc.get("_id", "")),
                    "patient_id": patient_id,
                    "observed_at": doc.get("time"),
                    "category": "lab_result",
                    "code": doc.get("code", ""),
                    "name": _code_to_name(doc.get("code", "")),
                    "value": doc.get("value"),
                    "unit": doc.get("unit", ""),
                    "reference_range": _get_reference_range(doc.get("code", "")),
                    "abnormal_flag": _check_abnormal(doc.get("code", ""), doc.get("value")),
                    "source_system": "lis",
                    "source_record_id": str(doc.get("_id", "")),
                    "data_quality": "complete",
                })
        except Exception as exc:
            logger.warning("labResult 证据行查询失败: %s", exc)

    return rows


async def _query_scores(db, patient_id: str, score_types: list[str], since: datetime) -> dict | None:
    if not score_types:
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
    events = []

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

    events.sort(key=lambda e: str(e.get("time", "")), reverse=True)
    return events[:50]


async def _build_ai_analysis(db, patient_id: str, context_type: str, context_id: str | None, organ_system: str | None, since: datetime) -> dict | None:
    """查询真实 AI 分析结果。无结果返回 None。"""
    try:
        query: dict[str, Any] = {
            "patient_id": patient_id,
            "context_type": context_type,
        }
        if context_id:
            query["context_id"] = context_id

        ai_doc = await db.col("ai_analysis").find_one(query, sort=[("created_at", -1)])
        if not ai_doc:
            return None

        # 校验患者 ID
        if ai_doc.get("patient_id") != patient_id:
            return None

        supporting = ai_doc.get("supporting", [])
        opposing = ai_doc.get("opposing", [])
        uncertainties = ai_doc.get("uncertainties", [])

        # 三个列表都为空时不渲染
        if not supporting and not opposing and not uncertainties:
            return None

        return {
            "supporting_evidence": supporting,
            "opposing_evidence": opposing,
            "uncertainties": uncertainties,
            "disclaimer": "AI生成，待临床确认",
            "model": ai_doc.get("model", "unknown"),
            "generated_at": ai_doc.get("created_at"),
            "data_cutoff_at": ai_doc.get("data_cutoff_at"),
            "patient_id": patient_id,
            "context_type": context_type,
            "context_id": context_id,
        }
    except Exception:
        return None


# ── 辅助函数 ──────────────────────────────────────────

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


def _compute_evidence_completeness(metrics: list[dict], missing: list[dict]) -> float:
    """数据完整率 = 已获取指标数 / (已获取 + 缺失数)。"""
    total = len(metrics) + len(missing)
    if total == 0:
        return 0.0
    return round(len(metrics) / total, 2)


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
    parts = [f"{system_label}：{severity_text}"]
    if metrics:
        parts.append(f"共 {len(metrics)} 项指标")
    if missing:
        parts.append(f"{len(missing)} 项数据缺失（不可计算）")
    return "，".join(parts)


def _build_weaning_lights(metrics: list[dict], sbt_scores: list[dict]) -> list[dict]:
    """灯号三态：pass / fail / unavailable。"""
    metric_map = {m["code"]: m for m in metrics}

    def _light(code: str, label: str, check) -> dict:
        m = metric_map.get(code)
        if m is None or m.get("value") is None:
            return {"label": label, "status": "unavailable", "ok": None}
        try:
            return {"label": label, "status": "pass" if check(float(m["value"])) else "fail", "ok": check(float(m["value"]))}
        except (ValueError, TypeError):
            return {"label": label, "status": "unavailable", "ok": None}

    lights = [
        _light("RSBI", "RSBI < 105", lambda v: v < 105),
        _light("SpO2", "SpO2 > 90%", lambda v: v > 90),
        _light("PEEP", "PEEP ≤ 8", lambda v: v <= 8),
        _light("FiO2", "FiO2 ≤ 40%", lambda v: v <= 40),
    ]

    sbt_pass = any(s.get("result") == "pass" for s in sbt_scores)
    sbt_any = len(sbt_scores) > 0
    lights.append({
        "label": "SBT 通过",
        "status": "pass" if sbt_pass else ("fail" if sbt_any else "unavailable"),
        "ok": sbt_pass if sbt_any else None,
    })

    return lights


def _build_discharge_lights(metrics: list[dict], scores: dict | None) -> list[dict]:
    """灯号三态：pass / fail / unavailable。"""
    metric_map = {m["code"]: m for m in metrics}

    def _light(code: str, label: str, check) -> dict:
        m = metric_map.get(code)
        if m is None or m.get("value") is None:
            return {"label": label, "status": "unavailable", "ok": None}
        try:
            ok = check(float(m["value"]))
            return {"label": label, "status": "pass" if ok else "fail", "ok": ok}
        except (ValueError, TypeError):
            return {"label": label, "status": "unavailable", "ok": None}

    hr = metric_map.get("HR")
    map_val = metric_map.get("MAP")
    circ_ok = (
        hr and hr.get("value") is not None and map_val and map_val.get("value") is not None
        and 60 <= float(hr["value"]) <= 100 and 65 <= float(map_val["value"]) <= 105
    )
    if hr is None or map_val is None or hr.get("value") is None or map_val.get("value") is None:
        lights_circ = {"label": "循环稳定", "status": "unavailable", "ok": None}
    else:
        lights_circ = {"label": "循环稳定", "status": "pass" if circ_ok else "fail", "ok": circ_ok}

    lights = [
        lights_circ,
        _light("SpO2", "氧合达标", lambda v: v >= 92),
        _light("GCS", "意识清楚", lambda v: v >= 13),
        _light("Urine_output_24h", "尿量充足", lambda v: v >= 500),
        _light("Lactate", "乳酸正常", lambda v: v < 2.0),
    ]

    if scores and scores.get("total_score") is not None:
        sofa_ok = float(scores["total_score"]) <= 6
        lights.append({"label": "SOFA ≤ 6", "status": "pass" if sofa_ok else "fail", "ok": sofa_ok})
    else:
        lights.append({"label": "SOFA ≤ 6", "status": "unavailable", "ok": None})

    return lights


def _error_response(message: str) -> dict:
    return {
        "conclusion": message,
        "severity": "info",
        "calculable": False,
        "confidence": {
            "evidence_completeness": 0.0,
            "rule_reliability": None,
            "model_probability": None,
        },
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
