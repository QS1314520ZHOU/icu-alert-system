"""消化道出血识别"""
from __future__ import annotations


class BleedingMixin:
    async def scan_bleeding(self) -> None:
        from .scanner_bleeding import BleedingScanner

        await BleedingScanner(self).scan()
