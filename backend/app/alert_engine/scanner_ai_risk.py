from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from datetime import datetime, timedelta
from typing import Any
import httpx
from app.services.ai_monitor import AiMonitor
from app.services.llm_runtime import call_llm_chat
from app.services.rag_service import RagService
from .scanners import BaseScanner, ScannerSpec


class AiRiskScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="ai_analysis",
                interval_key="ai_analysis",
                default_interval=1800,
                initial_delay=60,
            ),
        )

    async def scan(self) -> None:
        ai_cfg = self.engine.config.yaml_cfg.get("ai_service", {})
        if not ai_cfg:
            return

        llm_cfg = ai_cfg.get("llm", {}) if isinstance(ai_cfg, dict) else {}
        timeout_sec = float(llm_cfg.get("timeout", 30) or 30)
        max_concurrency = max(1, int(llm_cfg.get("max_concurrency", 4) or 4))
        cache_ttl_sec = max(60, int(llm_cfg.get("cache_ttl_seconds", 1800) or 1800))
        max_patients = max(1, int(ai_cfg.get("max_patients", 20) or 20))
        suppression_sec = max(60, int(ai_cfg.get("suppression_seconds", 3600) or 3600))

        base_url = str(self.engine.config.settings.LLM_BASE_URL or "").lower()
        llm_key = self.engine.config.settings.LLM_API_KEY
        is_ollama = ("ollama" in base_url) or ("11434" in base_url)
        if not is_ollama:
            if not llm_key or llm_key in ("your_api_key", ""):
                return

        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1,
             "clinicalDiagnosis": 1, "admissionDiagnosis": 1, "nursingLevel": 1, "icuAdmissionTime": 1},
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        self.engine._ensure_ai_runtime_state()

        now = datetime.now()
        semaphore = asyncio.Semaphore(max_concurrency)

        try:
            timeout = httpx.Timeout(timeout_sec)
        except Exception:
            timeout = httpx.Timeout(30)

        async with httpx.AsyncClient(timeout=timeout) as client:
            tasks = [
                asyncio.create_task(
                    self.engine._scan_single_patient_ai_risk(
                        patient_doc=patient_doc,
                        now=now,
                        suppression_sec=suppression_sec,
                        cache_ttl_sec=cache_ttl_sec,
                        semaphore=semaphore,
                        client=client,
                    )
                )
                for patient_doc in patients[:max_patients]
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        triggered = 0
        for item in results:
            if item is True:
                triggered += 1

        if triggered > 0:
            self.engine._log_info("AI预警", triggered)

        self.engine._gc_ai_result_cache(cache_ttl_sec)
