from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import AlertEngine


@dataclass(frozen=True)
class ScannerSpec:
    name: str
    interval_key: str
    default_interval: int
    initial_delay: int


class BaseScanner(ABC):
    def __init__(self, engine: AlertEngine, spec: ScannerSpec) -> None:
        self.engine = engine
        self.spec = spec

    @property
    def name(self) -> str:
        return self.spec.name

    def interval_seconds(self) -> int:
        intervals = self.engine.config.yaml_cfg.get("alert_engine", {}).get("scan_intervals", {})
        return int(intervals.get(self.spec.interval_key, self.spec.default_interval))

    @property
    def initial_delay(self) -> int:
        return int(self.spec.initial_delay)

    def is_enabled(self) -> bool:
        cfg = self.engine.config.yaml_cfg.get("alert_engine", {})
        disabled = cfg.get("disabled_scanners", []) if isinstance(cfg, dict) else []
        disabled_names = {str(name).strip() for name in disabled if str(name).strip()}
        return self.name not in disabled_names

    @abstractmethod
    async def scan(self) -> None:
        raise NotImplementedError
