"""已加载的不可变规则包。

从 critical-care-alert-platform 迁移。
"""

from __future__ import annotations

from typing import Any

from .. import RulepackConfig
from .threshold_lookup import ThresholdLookup, build_lookup


class LoadedRulepack:
    def __init__(self, config: RulepackConfig) -> None:
        self._config = config
        self._lookups: dict[str, ThresholdLookup] = {}
        for comp in config.components:
            if comp.thresholds:
                self._lookups[comp.name] = build_lookup(comp.thresholds)

    @property
    def config(self) -> RulepackConfig:
        return self._config

    @property
    def score_name(self) -> str:
        return self._config.score_name

    @property
    def rulepack_version(self) -> str:
        return self._config.rulepack_version

    @property
    def content_hash(self) -> str:
        return self._config.content_hash

    def get_threshold_lookup(self, component_name: str) -> ThresholdLookup | None:
        return self._lookups.get(component_name)

    def get_component_codes(self, component_name: str) -> list[str]:
        for comp in self._config.components:
            if comp.name == component_name:
                return list(comp.codes)
        return []

    def get_component(self, component_name: str) -> Any | None:
        for comp in self._config.components:
            if comp.name == component_name:
                return comp
        return None

    @property
    def component_names(self) -> list[str]:
        return [c.name for c in self._config.components]


def load_and_validate(config_dict: dict[str, Any], *, mode: str = "experimental") -> LoadedRulepack:
    from .. import load_rulepack
    config = load_rulepack(config_dict, mode=mode)
    return LoadedRulepack(config)
