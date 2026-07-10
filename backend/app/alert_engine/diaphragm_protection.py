"""膈肌保护性通气监测。"""
from __future__ import annotations

from datetime import datetime


class DiaphragmProtectionMixin:
    def _diaphragm_cfg(self) -> dict:
        cfg = self._cfg("alert_engine", "diaphragm_protection", default={}) or {}
        return cfg if isinstance(cfg, dict) else {}

    async def _latest_diaphragm_drive(self, pid, device_id: str | None) -> dict:
        codes = ["param_edi", "edi", "Edi", "param_pdi", "pdi", "Pdi", "param_p0_1", "p0.1", "P0.1"]
        cap = await self._get_latest_param_snapshot_by_pid(pid, codes=codes)
        if not cap and device_id:
            cap = await self._get_latest_device_cap(device_id, codes=codes)
        params = (cap or {}).get("params") or {}
        edi = None
        pdi = None
        p01 = None
        for key in ["param_edi", "edi", "Edi"]:
            if params.get(key) is not None:
                edi = float(params.get(key))
                break
        for key in ["param_pdi", "pdi", "Pdi"]:
            if params.get(key) is not None:
                pdi = float(params.get(key))
                break
        for key in ["param_p0_1", "p0.1", "P0.1"]:
            if params.get(key) is not None:
                p01 = float(params.get(key))
                break
        return {"time": (cap or {}).get("time"), "edi": edi, "pdi": pdi, "p0_1": p01}

    async def scan_diaphragm_protection(self) -> None:
        from .scanner_diaphragm_protection import DiaphragmProtectionScanner

        await DiaphragmProtectionScanner(self).scan()
