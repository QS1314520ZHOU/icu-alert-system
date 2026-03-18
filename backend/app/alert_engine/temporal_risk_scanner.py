"""时序恶化风险扫描器。"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

import numpy as np


class TemporalRiskScannerMixin:
    def _temporal_scanner_cfg(self) -> dict:
        cfg = self._cfg("alert_engine", "temporal_risk_scanner", default={}) or {}
        return cfg if isinstance(cfg, dict) else {}

    def _temporal_population_medians(self) -> dict[str, float]:
        cfg = self._temporal_scanner_cfg()
        medians = cfg.get("population_medians", {}) if isinstance(cfg.get("population_medians"), dict) else {}
        defaults = {
            "hr": 88.0,
            "map": 75.0,
            "spo2": 97.0,
            "rr": 19.0,
            "temp": 36.8,
            "lactate": 1.6,
            "sofa": 5.0,
        }
        for key, value in defaults.items():
            if medians.get(key) is None:
                medians[key] = value
        return {str(k): float(v) for k, v in medians.items() if v is not None}

    def _align_series_to_grid(
        self,
        *,
        grid_times: list[datetime],
        series: list[dict],
        median: float,
    ) -> list[float]:
        sorted_series = [row for row in series if isinstance(row.get("time"), datetime) and row.get("value") is not None]
        sorted_series.sort(key=lambda x: x["time"])
        aligned: list[float | None] = []
        cursor = 0
        last_value: float | None = None
        for point_time in grid_times:
            while cursor < len(sorted_series) and sorted_series[cursor]["time"] <= point_time:
                last_value = float(sorted_series[cursor]["value"])
                cursor += 1
            aligned.append(last_value)
        filled: list[float] = []
        carry = None
        for value in aligned:
            if value is not None:
                carry = float(value)
                filled.append(float(value))
            elif carry is not None:
                filled.append(float(carry))
            else:
                filled.append(float(median))
        return filled

    async def _prepare_temporal_input(
        self,
        *,
        patient_doc: dict,
        pid,
        lookback_hours: int,
        grid_minutes: int,
    ) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
        now = datetime.now().replace(second=0, microsecond=0)
        total_steps = max(2, int((lookback_hours * 60) / max(grid_minutes, 1)) + 1)
        start = now - timedelta(minutes=(total_steps - 1) * grid_minutes)
        grid_times = [start + timedelta(minutes=grid_minutes * idx) for idx in range(total_steps)]
        medians = self._temporal_population_medians()

        code_map = {
            "hr": "param_HR",
            "map": "param_ibp_m",
            "spo2": "param_spo2",
            "rr": "param_resp",
            "temp": str(self._cfg("vital_signs", "temperature", "code", default="param_T")),
        }
        hr_series = await self._get_param_series_by_pid(pid, code_map["hr"], start, prefer_device_types=["monitor"], limit=4000)
        map_series = await self._get_param_series_by_pid(pid, code_map["map"], start, prefer_device_types=["monitor"], limit=4000)
        if not map_series:
            map_series = await self._get_param_series_by_pid(pid, "param_nibp_m", start, prefer_device_types=["monitor"], limit=4000)
        spo2_series = await self._get_param_series_by_pid(pid, code_map["spo2"], start, prefer_device_types=["monitor"], limit=4000)
        rr_series = await self._get_param_series_by_pid(pid, code_map["rr"], start, prefer_device_types=["monitor"], limit=4000)
        temp_series = await self._get_param_series_by_pid(pid, code_map["temp"], start, prefer_device_types=["monitor"], limit=4000)

        if hasattr(self, "_filter_series_quality"):
            hr_series = self._filter_series_quality(code_map["hr"], hr_series)
            map_series = self._filter_series_quality("param_ibp_m", map_series)
            spo2_series = self._filter_series_quality(code_map["spo2"], spo2_series)
            rr_series = self._filter_series_quality(code_map["rr"], rr_series)
            temp_series = self._filter_series_quality(code_map["temp"], temp_series)

        feature_order = ["hr", "map", "spo2", "rr", "temp"]
        aligned = {
            "hr": self._align_series_to_grid(grid_times=grid_times, series=hr_series, median=medians["hr"]),
            "map": self._align_series_to_grid(grid_times=grid_times, series=map_series, median=medians["map"]),
            "spo2": self._align_series_to_grid(grid_times=grid_times, series=spo2_series, median=medians["spo2"]),
            "rr": self._align_series_to_grid(grid_times=grid_times, series=rr_series, median=medians["rr"]),
            "temp": self._align_series_to_grid(grid_times=grid_times, series=temp_series, median=medians["temp"]),
        }

        matrix = np.asarray([[aligned[key][idx] for key in feature_order] for idx in range(len(grid_times))], dtype=np.float32)
        sequence = matrix.reshape(1, matrix.shape[0], matrix.shape[1])

        pid_str = self._pid_str(pid)
        his_pid = (patient_doc or {}).get("hisPid")
        age = self._parse_age_years(patient_doc) if hasattr(self, "_parse_age_years") else None
        gender_text = str((patient_doc or {}).get("gender") or "").lower()
        female = 1.0 if any(x in gender_text for x in ["女", "female", "f"]) else 0.0
        icu_start = self._patient_icu_start_time(patient_doc)
        icu_days = ((datetime.now() - icu_start).total_seconds() / 86400.0) if isinstance(icu_start, datetime) else 0.0
        vent_device = await self._get_device_id_for_patient(patient_doc, ["vent"])
        on_vent = 1.0 if vent_device else 0.0
        sofa = await self._calc_sofa(patient_doc, pid, vent_device, his_pid) if his_pid else None
        sofa_score = float((sofa or {}).get("score")) if isinstance(sofa, dict) and (sofa or {}).get("score") is not None else medians["sofa"]
        lac_series = await self._get_lab_series(his_pid, "lac", datetime.now() - timedelta(hours=max(lookback_hours, 24)), limit=80) if his_pid else []
        lactate = float(lac_series[-1]["value"]) if lac_series and lac_series[-1].get("value") is not None else medians["lactate"]

        meta_features = np.asarray(
            [[
                float(age if age is not None else 65.0),
                female,
                float(max(icu_days, 0.0)),
                on_vent,
                sofa_score,
                lactate,
            ]],
            dtype=np.float32,
        )
        context = {
            "grid_minutes": grid_minutes,
            "lookback_hours": lookback_hours,
            "feature_order": feature_order,
            "grid_start": start,
            "grid_end": now,
            "steps": len(grid_times),
            "meta_features": {
                "age": float(age if age is not None else 65.0),
                "female": female,
                "icu_days": round(float(max(icu_days, 0.0)), 2),
                "mechanical_ventilation": bool(on_vent),
                "sofa": sofa_score,
                "lactate": lactate,
            },
            "latest_values": {key: aligned[key][-1] if aligned.get(key) else None for key in feature_order},
        }
        return sequence, meta_features, context

    async def _latest_temporal_risk_record(self, pid_str: str, hours: int = 6) -> dict | None:
        since = datetime.now() - timedelta(hours=max(hours, 1))
        return await self.db.col("score_records").find_one(
            {
                "patient_id": pid_str,
                "score_type": "temporal_risk_scanner",
                "calc_time": {"$gte": since},
            },
            sort=[("calc_time", -1)],
        )

    async def scan_temporal_risk(self) -> None:
        from .scanner_temporal_risk import TemporalRiskScanner

        await TemporalRiskScanner(self).scan()
