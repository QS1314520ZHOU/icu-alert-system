"""评分引擎协议。

从 critical-care-alert-platform 迁移，导入路径已调整。
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from ..observation import Observation
from .score_result import ScoreResult
from .window_spec import ScoreWindowSpec


@runtime_checkable
class ScoreCalculator(Protocol):
    """评分计算器。

    必须是纯函数：相同输入必定得到相同输出。
    不得访问数据库，不得调用 now()。
    """

    @property
    def score_name(self) -> str: ...

    @property
    def rulepack_version(self) -> str: ...

    def calculate(
        self,
        observations: list[Observation],
        *,
        evaluation_time: datetime,
        window_spec: ScoreWindowSpec,
        patient_weight_kg: float | None = None,
    ) -> ScoreResult: ...
