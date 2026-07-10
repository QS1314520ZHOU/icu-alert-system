"""血流动力学建议模块。"""
from __future__ import annotations

from datetime import datetime

from .scanner_hemodynamic_advisor import HemodynamicAdvisorScanner


class HemodynamicAdvisorMixin:
    async def scan_hemodynamic_advisor(self) -> None:
        await HemodynamicAdvisorScanner(self).scan()
