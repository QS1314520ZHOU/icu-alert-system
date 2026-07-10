"""颅脑损伤/颅高压"""
from __future__ import annotations

from app.utils.clinical import _extract_param


class TbiMixin:
    async def scan_tbi(self) -> None:
        from .scanner_tbi import TbiScanner

        await TbiScanner(self).scan()
