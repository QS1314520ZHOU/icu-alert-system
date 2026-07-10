from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Any
import httpx
import numpy as np
from app.services.llm_runtime import call_llm_chat
logger = logging.getLogger("icu-alert")
POPULATION_DEFAULTS: dict[str, dict[str, float | None]] = {
    "map": {"low_critical": 55, "low_warning": 65, "high_warning": 110, "high_critical": 130},
    "hr": {"low_critical": 40, "low_warning": 50, "high_warning": 120, "high_critical": 150},
    "spo2": {"low_critical": 85, "low_warning": 90, "high_warning": None, "high_critical": None},
    "sbp": {"low_critical": 70, "low_warning": 90, "high_warning": 180, "high_critical": 200},
    "rr": {"low_critical": 6, "low_warning": 10, "high_warning": 30, "high_critical": 40},
    "temperature": {"low_critical": 34.0, "low_warning": 35.5, "high_warning": 38.5, "high_critical": 39.5},
}
def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except Exception:
        return None
from .scanners import BaseScanner, ScannerSpec


class AdaptiveThresholdsScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="adaptive_threshold_advisor",
                interval_key="adaptive_threshold_advisor",
                default_interval=7200,
                initial_delay=70,
            ),
        )

    async def scan(self) -> None:
        cfg = self.engine._threshold_advisor_cfg()
        if not bool(cfg.get("enabled", True)):
            return

        base_url = str(self.engine.config.settings.LLM_BASE_URL or "").lower()
        llm_key = self.engine.config.settings.LLM_API_KEY
        is_ollama = ("ollama" in base_url) or ("11434" in base_url)
        if not is_ollama and (not llm_key or llm_key in {"", "your_api_key"}):
            return

        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {
                "_id": 1,
                "name": 1,
                "hisPid": 1,
                "hisBed": 1,
                "dept": 1,
                "hisDept": 1,
                "age": 1,
                "gender": 1,
                "hisSex": 1,
                "clinicalDiagnosis": 1,
                "admissionDiagnosis": 1,
                "diagnosis": 1,
                "remark": 1,
                "icuAdmissionTime": 1,
                "admissionTime": 1,
                "admitTime": 1,
                "inTime": 1,
                "createTime": 1,
            },
        )
        patients = [row async for row in patient_cursor]
        if not patients:
            return

        suppression = self.engine._cfg("alert_engine", "suppression", default={}) or {}
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        cache_ttl_sec = int(cfg.get("cache_ttl_seconds", 3600))
        max_concurrent = max(1, int(cfg.get("max_concurrent", 3)))
        semaphore = asyncio.Semaphore(max_concurrent)
        now = datetime.now()

        try:
            timeout = httpx.Timeout(float(cfg.get("llm_timeout", 45) or 45))
        except Exception:
            timeout = httpx.Timeout(45)

        async with httpx.AsyncClient(timeout=timeout) as client:
            tasks = [
                asyncio.create_task(
                    self.engine._scan_single_patient_adaptive_thresholds(
                        patient_doc=patient_doc,
                        now=now,
                        semaphore=semaphore,
                        cache_ttl_sec=cache_ttl_sec,
                        same_rule_sec=same_rule_sec,
                        max_per_hour=max_per_hour,
                        client=client,
                    )
                )
                for patient_doc in patients
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        triggered = 0
        for item in results:
            if item is True:
                triggered += 1
        if triggered > 0:
            self.engine._log_info("个性化阈值建议", triggered)
        self.engine._gc_threshold_cache(cache_ttl_sec)
