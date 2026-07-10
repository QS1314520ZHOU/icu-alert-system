"""DIC ISTH"""
from __future__ import annotations

from datetime import datetime, timedelta


class DicMixin:
    async def scan_dic(self) -> None:
        from .scanner_dic import DicScanner

        await DicScanner(self).scan()
