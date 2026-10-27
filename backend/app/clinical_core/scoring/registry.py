"""评分计算器注册表。

按名称注册/获取评分计算器，支持健康检查和规则包验证。
"""

from __future__ import annotations

from typing import Protocol

from .protocols import ScoreCalculator
from .score_result import ScoreResult
from ..observation import Observation


class ScoreCalculatorRegistry:
    """评分计算器注册表。

    注册所有可用评分计算器，按名称获取。
    支持 health check 和规则包一致性验证。
    """

    def __init__(self) -> None:
        self._calculators: dict[str, ScoreCalculator] = {}

    def register(self, calculator: ScoreCalculator, name: str | None = None) -> None:
        """注册评分计算器。

        Parameters
        ----------
        calculator : ScoreCalculator
            评分计算器实例。
        name : str | None
            注册名称，默认使用 calculator.score_name。
            用于注册同名评分的不同版本（如 SOFA Classic 和 SOFA-2）。
        """
        reg_name = name or calculator.score_name
        if reg_name in self._calculators:
            raise ValueError(f"Calculator already registered: {reg_name}")
        self._calculators[reg_name] = calculator

    def get(self, name: str) -> ScoreCalculator:
        """获取评分计算器。"""
        if name not in self._calculators:
            raise KeyError(f"No calculator registered for: {name}")
        return self._calculators[name]

    def available_scores(self) -> list[str]:
        """列出所有已注册评分名称。"""
        return list(self._calculators.keys())

    def calculate(self, name: str, observations: list[Observation]) -> ScoreResult:
        """计算指定评分（自动补 evaluation_time / window_spec）。"""
        from datetime import UTC, datetime, timedelta
        from .window_spec import ScoreWindowSpec, WindowSpec

        calc = self.get(name)
        evaluation_time = datetime.now(UTC)

        # 各评分默认 24h 窗口；分项名按计算器约定
        component_names = {
            "SOFA": [
                "respiratory", "coagulation", "liver",
                "cardiovascular", "central_nervous_system", "renal",
            ],
            "SOFA2": ["brain", "respiratory", "hemostasis", "liver", "kidney", "cardiovascular"],
            "NEWS2": [
                "respiratory_rate", "spo2", "air_or_oxygen",
                "systolic_bp", "pulse", "consciousness", "temperature",
            ],
            "qSOFA": ["respiratory_rate", "systolic_bp", "gcs"],
            "MEWS": ["respiratory_rate", "systolic_bp", "pulse", "temperature", "avpu"],
            "GCS": ["eye", "verbal", "motor"],
            "KDIGO_AKI": ["creatinine", "urine_output"],
        }.get(name, ["respiratory", "coagulation", "liver", "cardiovascular", "cns", "renal"])

        window_spec = ScoreWindowSpec(
            spec_id=f"{name.lower()}-default-window",
            score_name=calc.score_name,
            rulepack_version=calc.rulepack_version,
            components=[
                WindowSpec(
                    component_name=cn,
                    lookback_window=timedelta(hours=24),
                    max_staleness=timedelta(hours=12),
                    aggregation="worst",
                )
                for cn in component_names
            ],
        )
        return calc.calculate(
            observations,
            evaluation_time=evaluation_time,
            window_spec=window_spec,
        )

    def health_check(self) -> dict[str, dict]:
        """健康检查：检查所有已注册计算器。"""
        results: dict[str, dict] = {}
        for name, calc in self._calculators.items():
            try:
                results[name] = {
                    "registered": True,
                    "score_name": calc.score_name,
                    "version": calc.rulepack_version,
                }
            except Exception as exc:
                results[name] = {"registered": True, "error": str(exc)}
        return results


def create_default_registry() -> ScoreCalculatorRegistry:
    """创建默认注册表，注册所有已迁移的计算器。"""
    from .calculators.sofa import SOFACalculator
    from .calculators.sofa2 import SOFA2Calculator
    from .calculators.news2 import NEWS2Calculator
    from .calculators.qsofa import qSOFACalculator
    from .calculators.mews import MEWSCalculator
    from .calculators.gcs import GCSCalculator
    from .calculators.aki import AKICalculator

    registry = ScoreCalculatorRegistry()
    registry.register(SOFACalculator())       # "SOFA" - Classic SOFA 1996
    registry.register(SOFA2Calculator(), name="SOFA2")  # SOFA-2 2025
    registry.register(NEWS2Calculator())
    registry.register(qSOFACalculator())
    registry.register(MEWSCalculator())
    registry.register(GCSCalculator())
    registry.register(AKICalculator())
    return registry
