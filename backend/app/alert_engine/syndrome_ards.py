"""ARDS 自动识别"""
from __future__ import annotations


class ArdsMixin:
    async def scan_ards(self) -> None:
        from .scanner_ards import ArdsScanner

        await ArdsScanner(self).scan()
