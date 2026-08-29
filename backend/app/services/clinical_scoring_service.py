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

    quality_str = d.get("data_quality", "measured")
    try:
        data_quality = DataQuality(quality_str)
    except ValueError:
        data_quality = DataQuality.MEASURED

    return Observation(
        category=category,
        code=d.get("code", ""),
        display_name=d.get("display_name", d.get("code", "")),
        value_number=d.get("value_number"),
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

    systems: dict[str, dict[str, Any]] = {}
    for name in registry.available_scores():
        calc = registry.get(name)
        score_name = calc.score_name
        if score_name not in systems:
            systems[score_name] = {
                "name": score_name,
                "variants": [],
            }
        systems[score_name]["variants"].append({
            "id": name,
            "name": name,
            "version": calc.rulepack_version,
        })

    return list(systems.values())


async def get_scoring_rule(rule_id: str) -> dict[str, Any]:
    """获取评分规则详情。"""
    service = get_scoring_service()
    registry = service.registry

    try:
        calc = registry.get(rule_id)
        return {
            "id": rule_id,
            "name": calc.score_name,
            "version": calc.rulepack_version,
            "score_system": calc.score_name,
            "score_variant": rule_id,
        }
    except KeyError:
        raise ValueError(f"未找到评分规则: {rule_id}")


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
            "score_system": result.score_system,
            "score_variant": result.score_variant,
            "rule_id": result.rule_id,
            "rule_version": result.rule_version,
            "total_score": result.total_score,
            "component_scores": {c.name: c.score_points for c in result.components},
            "missing_inputs": result.missing_items,
            "evidence": [
                {
                    "input": c.name,
                    "value": c.value,
                    "source": c.source,
                }
                for c in result.components
                if c.value is not None
            ],
            "input_snapshot_hash": result.content_hash,
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
