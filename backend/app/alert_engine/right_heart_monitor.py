"""右心功能恶化早期预警。"""
from __future__ import annotations

from datetime import datetime, timedelta

from .scanner_right_heart_monitor import RightHeartMonitorScanner


class RightHeartMonitorMixin:
    def _right_heart_cfg(self) -> dict:
        cfg = self._cfg("alert_engine", "right_heart_monitor", default={}) or {}
        return cfg if isinstance(cfg, dict) else {}

    async def _get_cvp_trend(self, pid, since: datetime) -> dict:
        codes = ["param_cvp", "cvp", "CVP"]
        series = []
        for code in codes:
            rows = await self._get_param_series_by_pid(pid, code, since, prefer_device_types=["monitor"], limit=200)
            if rows:
                series = rows
                break
        values = [float(row.get("value")) for row in series if row.get("value") is not None]
        if len(values) < 2:
            return {"latest": None, "baseline": None, "delta": None, "series": []}
        baseline = sum(values[: min(3, len(values))]) / min(3, len(values))
        latest = sum(values[-min(3, len(values)) :]) / min(3, len(values))
        return {
            "latest": round(latest, 2),
            "baseline": round(baseline, 2),
            "delta": round(latest - baseline, 2),
            "series": values[-6:],
        }

    async def _liver_kidney_worsening(self, patient_doc: dict, pid, his_pid: str | None) -> dict:
        result = {"aki_stage": None, "bilirubin_latest": None, "bilirubin_ratio": None, "worsening": False}
        aki = await self._calc_aki_stage(patient_doc, pid, his_pid) if his_pid else None
        if aki:
            result["aki_stage"] = aki.get("stage")
            if (aki.get("stage") or 0) >= 2:
                result["worsening"] = True
        if his_pid:
            bil_series = await self._get_lab_series(his_pid, "bil", datetime.now() - timedelta(hours=72), limit=60)
            if bil_series:
                latest = bil_series[-1].get("value")
                baseline = min(float(row.get("value")) for row in bil_series if row.get("value") is not None)
                ratio = round(float(latest) / float(baseline), 2) if latest is not None and baseline not in (None, 0) else None
                result["bilirubin_latest"] = latest
                result["bilirubin_ratio"] = ratio
                if ratio is not None and ratio >= 1.5:
                    result["worsening"] = True
        return result

    async def scan_right_heart_monitor(self) -> None:
        await RightHeartMonitorScanner(self).scan()

