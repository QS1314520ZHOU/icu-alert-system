"""AKI KDIGO"""
from __future__ import annotations


class AkiMixin:
    async def scan_aki(self) -> None:
        from .aki_scanner import AkiScanner

        await AkiScanner(self).scan()

