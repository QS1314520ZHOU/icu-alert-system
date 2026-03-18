from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo
import httpx
from app.services.ai_monitor import AiMonitor
from app.services.llm_runtime import call_llm_chat
logger = logging.getLogger("icu-alert")
API_TZ = ZoneInfo("Asia/Shanghai")
from .scanners import BaseScanner, ScannerSpec


class AlertReasoningScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="alert_reasoning",
                interval_key="alert_reasoning",
                default_interval=300,
                initial_delay=75,
            ),
        )

    async def scan(self) -> None:
        cfg = self.engine._alert_reasoning_cfg()
        if not bool(cfg.get("enabled", True)):
            return

        ai_cfg = self.engine.config.yaml_cfg.get("ai_service", {})
        if not ai_cfg:
            return

        llm_cfg = ai_cfg.get("llm", {}) if isinstance(ai_cfg, dict) else {}
        timeout_sec = float(llm_cfg.get("timeout", 30) or 30)
        max_concurrency = max(1, int(cfg.get("max_concurrency", llm_cfg.get("max_concurrency", 2) or 2)))
        max_patients = max(1, int(cfg.get("max_patients", ai_cfg.get("max_patients", 20) or 20)))

        base_url = str(self.engine.config.settings.LLM_BASE_URL or "").lower()
        llm_key = self.engine.config.settings.LLM_API_KEY
        is_ollama = ("ollama" in base_url) or ("11434" in base_url)
        if not is_ollama and (not llm_key or llm_key in ("your_api_key", "")):
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
                "deptCode": 1,
                "clinicalDiagnosis": 1,
                "admissionDiagnosis": 1,
                "nursingLevel": 1,
                "icuAdmissionTime": 1,
            },
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        semaphore = asyncio.Semaphore(max_concurrency)
        now = datetime.now()

        try:
            timeout = httpx.Timeout(timeout_sec)
        except Exception:
            timeout = httpx.Timeout(30)

        async with httpx.AsyncClient(timeout=timeout) as client:
            tasks = [
                asyncio.create_task(
                    self.engine._scan_single_patient_alert_reasoning(
                        patient_doc=patient_doc,
                        now=now,
                        semaphore=semaphore,
                        client=client,
                    )
                )
                for patient_doc in patients[:max_patients]
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        updated = sum(1 for item in results if item is True)
        if updated > 0:
            self.engine._log_info("AI归因摘要", updated)
