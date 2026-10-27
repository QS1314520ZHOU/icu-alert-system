"""临床评分服务。

使用内部 Clinical Core 替代外部 RuleCoreClient。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.clinical_core import (
    ClinicalScoringService,
    create_default_registry,
    Observation,
    ObservationCategory,
    DataQuality,
)


# 全局服务实例
_scoring_service: ClinicalScoringService | None = None


def get_scoring_service() -> ClinicalScoringService:
    """获取评分服务单例。"""
    global _scoring_service
    if _scoring_service is None:
        _scoring_service = ClinicalScoringService(create_default_registry())
    return _scoring_service


# 前端短码 → 计算器内部码
_CODE_ALIASES = {
    "platelet": "PLT",
    "plt": "PLT",
    "tbil": "TBIL",
    "cr": "CREA",
    "gcs_total": "GCS",
    "map": "MAP",
    "mean_arterial_pressure": "MAP",
    "pao2": "PaO2",
    "fio2": "FiO2",
    "resp_rate": "RR",
    "respiratory_rate": "RR",
    "systolic_bp": "SBP",
    "pulse": "HR",
    "heart_rate": "HR",
    "temperature": "TEMP",
    "spo2": "SpO2",
}


def _observation_from_dict(d: dict[str, Any]) -> Observation:
    """从字典构建 Observation。"""
    category_str = d.get("category", "vital_sign")
    try:
        category = ObservationCategory(category_str)
    except ValueError:
        category = ObservationCategory.VITAL_SIGN

    observed_at_raw = d.get("observed_at", datetime.now(timezone.utc))
    if isinstance(observed_at_raw, str):
        observed_at = datetime.fromisoformat(observed_at_raw)
    elif isinstance(observed_at_raw, datetime):
        observed_at = observed_at_raw
    else:
        observed_at = datetime.now(timezone.utc)

    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)

    quality_str = d.get("data_quality", "valid")
    try:
        data_quality = DataQuality(quality_str)
    except ValueError:
        data_quality = DataQuality.VALID

    # 前端 evaluateScore 传 value，Observation 需要 value_number
    value_number = d.get("value_number")
    if value_number is None and d.get("value") is not None:
        try:
            value_number = float(d["value"])
        except (TypeError, ValueError):
            value_number = None

    raw_code = str(d.get("code", "")).strip()
    code = _CODE_ALIASES.get(raw_code.lower(), raw_code)

    return Observation(
        category=category,
        code=code,
        display_name=d.get("display_name", raw_code),
        value_number=value_number,
        value_text=d.get("value_text"),
        unit=d.get("unit", ""),
        observed_at=observed_at,
        data_quality=data_quality,
    )


async def health_check() -> dict[str, Any]:
    """健康检查。"""
    service = get_scoring_service()
    return {
        "clinical_core": {
            "status": "healthy",
            "registered_scores": service.health_check(),
        }
    }


async def list_scoring_systems() -> list[dict[str, Any]]:
    """列出所有评分系统。"""
    service = get_scoring_service()
    registry = service.registry

    systems: list[dict[str, Any]] = []
    for name in registry.available_scores():
        calc = registry.get(name)
        systems.append({
            "name": calc.score_name,
            "score_name": name,
            "rulepack_version": calc.rulepack_version,
            "status": "active",
        })

    return systems


# 各评分体系的输入项（供前端运行评分表单）
_SCORE_INPUTS: dict[str, list[dict[str, Any]]] = {
    "SOFA": [
        {"name": "pao2", "label": "PaO2", "type": "number", "unit": "mmHg", "required": True},
        {"name": "fio2", "label": "FiO2", "type": "number", "unit": "ratio", "required": True},
        {"name": "platelet", "label": "血小板", "type": "number", "unit": "×10^9/L", "required": True},
        {"name": "bilirubin", "label": "胆红素", "type": "number", "unit": "mg/dL", "required": True},
        {"name": "map", "label": "平均动脉压", "type": "number", "unit": "mmHg", "required": True},
        {"name": "dopamine", "label": "多巴胺", "type": "number", "unit": "μg/kg/min", "required": False},
        {"name": "dobutamine", "label": "多巴酚丁胺", "type": "number", "unit": "μg/kg/min", "required": False},
        {"name": "norepinephrine", "label": "去甲肾上腺素", "type": "number", "unit": "μg/kg/min", "required": False},
        {"name": "gcs", "label": "GCS 评分", "type": "number", "unit": "", "required": True},
        {"name": "creatinine", "label": "肌酐", "type": "number", "unit": "mg/dL", "required": True},
    ],
    "SOFA2": [
        {"name": "pao2", "label": "PaO2", "type": "number", "unit": "mmHg", "required": True},
        {"name": "fio2", "label": "FiO2", "type": "number", "unit": "ratio", "required": True},
        {"name": "platelet", "label": "血小板", "type": "number", "unit": "×10^9/L", "required": True},
        {"name": "bilirubin", "label": "胆红素", "type": "number", "unit": "mg/dL", "required": True},
        {"name": "map", "label": "平均动脉压", "type": "number", "unit": "mmHg", "required": True},
        {"name": "gcs", "label": "GCS 评分", "type": "number", "unit": "", "required": True},
        {"name": "creatinine", "label": "肌酐", "type": "number", "unit": "mg/dL", "required": True},
    ],
    "NEWS2": [
        {"name": "resp_rate", "label": "呼吸频率", "type": "number", "unit": "次/分", "required": True},
        {"name": "spo2", "label": "SpO2", "type": "number", "unit": "%", "required": True},
        {"name": "air_or_oxygen", "label": "吸氧(0/1)", "type": "number", "unit": "", "required": True},
        {"name": "systolic_bp", "label": "收缩压", "type": "number", "unit": "mmHg", "required": True},
        {"name": "pulse", "label": "心率", "type": "number", "unit": "次/分", "required": True},
        {"name": "consciousness", "label": "意识(0=警觉/3=昏迷)", "type": "number", "unit": "", "required": True},
        {"name": "temperature", "label": "体温", "type": "number", "unit": "°C", "required": True},
    ],
    "qSOFA": [
        {"name": "resp_rate", "label": "呼吸频率", "type": "number", "unit": "次/分", "required": True},
        {"name": "systolic_bp", "label": "收缩压", "type": "number", "unit": "mmHg", "required": True},
        {"name": "gcs", "label": "GCS 评分", "type": "number", "unit": "", "required": True},
    ],
    "MEWS": [
        {"name": "resp_rate", "label": "呼吸频率", "type": "number", "unit": "次/分", "required": True},
        {"name": "systolic_bp", "label": "收缩压", "type": "number", "unit": "mmHg", "required": True},
        {"name": "pulse", "label": "心率", "type": "number", "unit": "次/分", "required": True},
        {"name": "temperature", "label": "体温", "type": "number", "unit": "°C", "required": True},
        {"name": "avpu", "label": "AVPU(0=清醒)", "type": "number", "unit": "", "required": True},
    ],
    "GCS": [
        {"name": "eye", "label": "睁眼反应(1-4)", "type": "number", "unit": "", "required": True},
        {"name": "verbal", "label": "语言反应(1-5)", "type": "number", "unit": "", "required": True},
        {"name": "motor", "label": "运动反应(1-6)", "type": "number", "unit": "", "required": True},
    ],
    "KDIGO_AKI": [
        {"name": "creatinine", "label": "肌酐", "type": "number", "unit": "mg/dL", "required": True},
        {"name": "urine_output_ml_kg_h", "label": "尿量", "type": "number", "unit": "mL/kg/h", "required": False},
    ],
}


async def get_scoring_rule(rule_id: str) -> dict[str, Any] | None:
    """获取评分规则详情。"""
    service = get_scoring_service()
    registry = service.registry

    try:
        calc = registry.get(rule_id)
    except KeyError:
        return None

    inputs = _SCORE_INPUTS.get(rule_id) or _SCORE_INPUTS.get(calc.score_name) or []
    return {
        "id": rule_id,
        "name": calc.score_name,
        "version": calc.rulepack_version,
        "score_system": calc.score_name,
        "score_variant": rule_id,
        "description": f"{calc.score_name} 评分（规则包 {calc.rulepack_version}）",
        "inputs": inputs,
        "thresholds": [],
        "missing_policy": "treat_as_normal",
        "time_window": "24h",
    }


async def evaluate_score(
    patient_id: str,
    score_system: str,
    score_variant: str | None = None,
    inputs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """执行评分计算。"""
    service = get_scoring_service()

    # 确定评分名称
    score_name = score_variant or score_system

    # 构建观测数据
    observations = []
    if inputs:
        for inp in inputs:
            obs = _observation_from_dict(inp)
            observations.append(obs)

    # 计算评分
    try:
        result = service.compute_score(score_name, observations)
        return {
            "score_system": result.score_name,
            "score_variant": result.score_variant or score_name,
            "rule_id": result.rulepack_id or score_name,
            "rule_version": result.rulepack_version,
            "total_score": result.total_score if result.total_score is not None else 0,
            "component_scores": {c.name: c.score_points for c in result.components},
            "missing_inputs": result.missing_items,
            "evidence": [
                {
                    "input": c.name,
                    "value": c.raw_value if c.raw_value is not None else c.canonical_value,
                    "source": c.name,
                }
                for c in result.components
                if c.raw_value is not None or c.canonical_value is not None
            ],
            "input_snapshot_hash": result.content_hash or result.rulepack_content_hash,
            "evaluation_time": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise ValueError(f"评分计算失败: {e}")


async def run_test_case(
    rule_id: str,
    test_case: dict[str, Any],
) -> dict[str, Any]:
    """执行测试病例。"""
    # 构建观测数据
    inputs = test_case.get("inputs", [])
    observations = []
    for inp in inputs:
        obs = _observation_from_dict(inp)
        observations.append(obs)

    # 计算评分
    service = get_scoring_service()
    try:
        result = service.compute_score(rule_id, observations)
        return {
            "rule_id": rule_id,
            "total_score": result.total_score,
            "component_scores": {c.name: c.score_points for c in result.components},
            "missing_inputs": result.missing_items,
            "passed": True,
        }
    except Exception as e:
        return {
            "rule_id": rule_id,
            "passed": False,
            "error": str(e),
        }
