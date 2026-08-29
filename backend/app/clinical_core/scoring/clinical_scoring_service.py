"""评分应用服务。

接收患者上下文，构建 Observation 列表，选择计算器，返回 ScoreResult + 业务解释。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..enums import DataQuality, ObservationCategory
from ..observation import Observation
from .score_result import ScoreResult
from .registry import ScoreCalculatorRegistry, create_default_registry


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
        value_number=d.get("value_number"),
        value_text=d.get("value_text"),
        unit=d.get("unit", ""),
        observed_at=observed_at,
        data_quality=data_quality,
    )


class ClinicalScoringService:
    """评分应用服务。

    接收患者上下文，构建 Observation 列表，计算评分，返回业务解释。
    """

    def __init__(self, registry: ScoreCalculatorRegistry | None = None) -> None:
        self.registry = registry or create_default_registry()

    def compute_score(
        self,
        score_name: str,
        observations: list[Observation] | list[dict[str, Any]],
    ) -> ScoreResult:
        """计算指定评分。

        Parameters
        ----------
        score_name : str
            评分名称，如 "SOFA", "NEWS2" 等。
        observations : list[Observation] | list[dict]
            观测数据列表，可以是 Observation 对象或字典。

        Returns
        -------
        ScoreResult
            包含总分、分项、缺失项、业务解释。
        """
        if observations and isinstance(observations[0], dict):
            obs_list = [_observation_from_dict(d) for d in observations]
        else:
            obs_list = observations  # type: ignore

        result = self.registry.calculate(score_name, obs_list)
        return result

    def compute_sofa(
        self,
        observations: list[Observation] | list[dict[str, Any]],
        version: str = "classic",
    ) -> ScoreResult:
        """计算 SOFA 评分（自动路由到 Classic 或 SOFA-2）。

        Parameters
        ----------
        observations : list
            观测数据。
        version : str
            "classic" 或 "sofa2"。
        """
        from .sofa_router import calculate_sofa

        if observations and isinstance(observations[0], dict):
            obs_list = [_observation_from_dict(d) for d in observations]
        else:
            obs_list = observations  # type: ignore

        return calculate_sofa(obs_list, version=version)

    def compute_all(
        self,
        observations: list[Observation] | list[dict[str, Any]],
    ) -> dict[str, ScoreResult]:
        """计算所有已注册评分。

        Parameters
        ----------
        observations : list
            观测数据。

        Returns
        -------
        dict[str, ScoreResult]
            评分名称 -> 评分结果。
        """
        if observations and isinstance(observations[0], dict):
            obs_list = [_observation_from_dict(d) for d in observations]
        else:
            obs_list = observations  # type: ignore

        results: dict[str, ScoreResult] = {}
        for name in self.registry.available_scores():
            try:
                results[name] = self.registry.calculate(name, obs_list)
            except Exception:
                pass
        return results

    def health_check(self) -> dict[str, Any]:
        """健康检查。"""
        return self.registry.health_check()
