"""VoiceRoundingStreamService — orchestrates one streaming voice-rounding session.

Owns the lifecycle of a single 2pass streaming session:
- start()  opens a StreamingASRSession and registers callbacks
- send_pcm()  forwards audio chunks to FunASR
- stop()  sends stop marker, awaits final results, runs LLM correction + summary,
  and writes a draft to MongoDB

Key invariants:
- LLM is NEVER called on partial results
- LLM correction is called ONCE after all final segments are collected
- If wait_final times out, the session is degraded (needs_human_review=True)
  but existing full_text is still processed through LLM
- If there is no full_text and only partial, a degraded draft is created
  without LLM processing
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from app.services.asr_client import (
    ASREmptyTranscriptionError,
    ASRRuntimeUnavailableError,
    _asr_config,
)
from app.services.streaming_asr import (
    StreamingASRSession,
    OnPartial,
    OnFinalSegment,
    OnError,
)
from app.utils.runtime_paths import package_root

logger = logging.getLogger("icu-alert")

# ── Suspicious term types (mirror voice_rounding.py) ───────────────────────
SUSPECT_TYPE_DRUG = "drug_confusable"
SUSPECT_TYPE_NUMBER = "number_override"
SUSPECT_TYPE_DIALECT = "dialect_uncertain"
SUSPECT_TYPE_OTHER = "other"

# ── Default stream config ──────────────────────────────────────────────────
DEFAULT_MAX_SESSION_SEC = 600
DEFAULT_FINAL_WAIT_TIMEOUT = 30.0


class VoiceRoundingStreamService:
    """Manages one streaming voice-rounding session from start to completed draft."""

    def __init__(self, db: Any, config: Any, patient_id: str) -> None:
        self._db = db
        self._config = config
        self._patient_id = patient_id
        self._session_id = uuid.uuid4().hex[:12]
        self._cfg = self._load_stream_cfg()

        # Accumulated state
        self._partial_text = ""                     # current live partial (replaced each update)
        self._final_segments: list[dict] = []       # accumulated final segments
        self._full_text = ""                        # accumulated full final text
        self._stopped = False
        self._total_audio_bytes = 0
        self._chunk_count = 0
        self._events: list[str] = []

        self._session: StreamingASRSession | None = None

        # These are set to asyncio.Event when waiting for backend push to frontend
        self._partial_updated = asyncio.Event()
        self._final_updated = asyncio.Event()
        self._error_occurred = asyncio.Event()
        self._error_message = ""

        # Load voice-rounding service for its pipeline methods (strip_fillers, llm_correct)
        from app.services.voice_rounding import VoiceRoundingService
        self._vr_svc = VoiceRoundingService(db, config)

    # ── Public API ──────────────────────────────────────────────────────

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def partial_text(self) -> str:
        return self._partial_text

    @property
    def full_text(self) -> str:
        return self._full_text

    @property
    def final_segments(self) -> list[dict]:
        return list(self._final_segments)

    @property
    def is_stopped(self) -> bool:
        return self._stopped

    @property
    def error_message(self) -> str:
        return self._error_message

    async def start(self, hotwords: list[str] | None = None) -> str:
        """Open StreamingASRSession and register callbacks.  Returns session_id."""
        base_url, _ = _asr_config()
        if not base_url:
            raise ASRRuntimeUnavailableError("ASR_BASE_URL 未配置")

        # Generate hotwords from patient context if not provided
        if hotwords is None:
            hotwords = await self._generate_hotwords()

        self._session = StreamingASRSession(
            base_url=base_url,
            hotwords=hotwords,
            language=self._cfg.get("language", "zh"),
        )
        self._session.on_partial = self._on_partial
        self._session.on_final_segment = self._on_final
        self._session.on_error = self._on_error

        await self._session.open()
        self._events.append("ready")
        logger.info("VoiceRoundingStreamService started: session=%s patient=%s",
                     self._session_id, self._patient_id)
        return self._session_id

    async def send_pcm(self, chunk: bytes) -> None:
        """Forward a PCM chunk from browser to FunASR."""
        if self._stopped:
            logger.warning("stop 后拒绝接收 PCM: session=%s", self._session_id)
            return
        if self._session is None:
            return
        self._chunk_count += 1
        self._total_audio_bytes += len(chunk)
        await self._session.send_pcm(chunk)

    async def stop(self) -> dict[str, Any]:
        """Stop the session: send stop marker, wait for finals, run pipeline.

        Returns the completed draft dict.
        """
        if self._stopped:
            raise ASRRuntimeUnavailableError("stop() 已调用过")
        self._stopped = True
        self._events.append("stop")

        if self._session is None:
            raise ASRRuntimeUnavailableError("session 未启动")

        await self._session.send_stop()

        # Wait for stop_final_future
        final_complete = False
        try:
            timeout = float(self._cfg.get("final_wait_timeout", DEFAULT_FINAL_WAIT_TIMEOUT))
            await self._session.wait_final(timeout=timeout)
            final_complete = True
        except asyncio.TimeoutError:
            logger.warning("stop_final_future 超时: session=%s", self._session_id)

        # Clean up FunASR connection
        await self._session.close()

        # ── Text selection ──────────────────────────────────────────
        degraded = not final_complete
        needs_human_review = degraded

        if self._full_text.strip():
            final_text = self._full_text.strip()
        elif self._partial_text.strip():
            final_text = self._partial_text.strip()
            needs_human_review = True
        else:
            raise ASREmptyTranscriptionError("最终文本和 partial 均为空")

        # ── Degraded: no final completion ───────────────────────────
        if degraded and not self._full_text.strip():
            # Only partial — skip LLM, create minimal degraded draft
            cleaned = self._vr_svc._strip_fillers(final_text)
            return await self._write_draft(
                raw_text=final_text,
                cleaned_text=cleaned,
                corrected_text=cleaned,
                summary_text=None,
                summary_sections=None,
                degraded=True,
                needs_human_review=True,
                processing={
                    "asr_mode": "2pass",
                    "asr_final_complete": False,
                    "llm_correction": False,
                    "llm_summary": False,
                },
            )

        # ── Normal / degraded-with-full_text flow ───────────────────
        cleaned = self._vr_svc._strip_fillers(final_text)
        try:
            corrected = await self._vr_svc._llm_correct(cleaned, self._patient_id)
        except Exception:
            logger.exception("LLM 纠错失败，降级使用清洗文本")
            corrected = {"text": cleaned, "corrected": False, "suspect": [],
                         "suspect_terms": [], "needs_human_review": True, "degraded": True}
            degraded = True
            needs_human_review = True
        summary = await self._generate_summary(corrected["text"])

        return await self._write_draft(
            raw_text=final_text,
            cleaned_text=cleaned,
            corrected_text=corrected.get("text", cleaned),
            summary_text=summary.get("text"),
            summary_sections=summary.get("sections"),
            suspect=corrected.get("suspect", []),
            suspect_terms=corrected.get("suspect_terms", []),
            needs_human_review=needs_human_review or corrected.get("needs_human_review", False),
            degraded=degraded,
            summary_degraded=summary.get("degraded", False),
            hints_hit=self._collect_hints_hit(cleaned, corrected.get("suspect", [])),
            processing={
                "asr_mode": "2pass",
                "asr_final_complete": final_complete,
                "llm_correction": not degraded or bool(self._full_text.strip()),
                "llm_summary": summary.get("text") is not None,
            },
        )

    async def cancel(self) -> None:
        """Abort the session — no draft written."""
        self._stopped = True
        self._events.append("cancel")
        if self._session:
            await self._session.close()
            self._session = None

    # ── ASR callbacks ──────────────────────────────────────────────────

    async def _on_partial(self, text: str, start_ms: int | None, end_ms: int | None) -> None:
        """Called for every 2pass-online message.  NEVER call LLM here."""
        self._partial_text = text  # replace, not append
        self._partial_updated.set()
        self._partial_updated.clear()

    async def _on_final(
        self,
        text: str,
        segments: list[dict],
        start_ms: int | None,
        end_ms: int | None,
    ) -> None:
        """Called for every 2pass-offline message (stop-before and stop-after)."""
        seg_entry = {
            "text": text,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "timestamp": datetime.now().isoformat(),
        }
        self._final_segments.append(seg_entry)
        if self._full_text:
            self._full_text += "。"
        self._full_text += text
        self._events.append("final_segment")
        self._final_updated.set()
        self._final_updated.clear()

    async def _on_error(self, message: str) -> None:
        """Called when StreamingASRSession encounters a fatal error."""
        self._error_message = message
        self._error_occurred.set()

    # ── Internal helpers ────────────────────────────────────────────────

    def _load_stream_cfg(self) -> dict[str, Any]:
        """Load voice_rounding.stream config section."""
        try:
            cfg = self._config.yaml_cfg.get("voice_rounding", {})
        except Exception:
            cfg = {}
        return (cfg.get("stream") or {}) if isinstance(cfg, dict) else {}

    async def _generate_hotwords(self) -> list[str]:
        """Generate hotwords from patient context."""
        try:
            return list(getattr(self._vr_svc.asr, "hotwords", []) or [])
        except Exception:
            return []

    async def _generate_summary(self, corrected_text: str) -> dict[str, Any]:
        """Generate a structured summary from the corrected transcript.

        Uses a lightweight prompt focused on extracting what the doctor
        actually said — no fabricated content.
        """
        from app.services.llm_runtime import call_llm_chat

        system_prompt = (
            "你是 ICU 查房记录助手。请将医生的口述整理为结构化记录。"
            "只提取口述中实际包含的信息。未提及的内容不要输出，不要生成'未提及'正文。"
        )
        user_prompt = f"医生口述查房内容：\n{corrected_text}\n\n请输出 JSON。"

        try:
            result = await call_llm_chat(
                cfg=self._config,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=getattr(self._config, "llm_fast_model", None),
                temperature=0.1,
                max_tokens=2048,
                timeout_seconds=30.0,
            )
            raw = result.get("text") if isinstance(result, dict) else str(result)
            data = self._parse_summary_json(raw)
            return {"text": data.get("text"), "sections": data.get("sections") or [], "degraded": False}
        except Exception:
            logger.exception("结构化总结生成失败")
            return {"text": None, "sections": None, "degraded": True}

    @staticmethod
    def _parse_summary_json(raw: str) -> dict[str, Any]:
        """Parse the summary LLM JSON response with markdown tolerance."""
        import re
        text = str(raw or "").strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            text = m.group(0)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": None, "sections": None}

    async def _write_draft(self, **overrides: Any) -> dict[str, Any]:
        """Build and insert the draft document into voice_rounding_drafts."""
        draft: dict[str, Any] = {
            "patient_id": str(self._patient_id),
            "status": "draft",
            "raw_text": overrides.get("raw_text", ""),
            "cleaned_text": overrides.get("cleaned_text", ""),
            "corrected_text": overrides.get("corrected_text", ""),
            "summary_text": overrides.get("summary_text"),
            "summary_sections": overrides.get("summary_sections"),
            "suspect": overrides.get("suspect", []),
            "suspect_terms": overrides.get("suspect_terms", []),
            "hints_hit": overrides.get("hints_hit", {}),
            "needs_human_review": overrides.get("needs_human_review", False),
            "degraded": overrides.get("degraded", False),
            "summary_degraded": overrides.get("summary_degraded", False),
            "duration_seconds": self._total_audio_bytes / (16000 * 2) if self._total_audio_bytes > 0 else 0.0,
            "segments": self._final_segments,
            "dropped_chunks": 0,
            "processing": overrides.get("processing", {}),
            "session_id": self._session_id,
            "events": self._events,
            "created_at": datetime.now(),
        }

        result = await self._db.col("voice_rounding_drafts").insert_one(draft)
        draft["_id"] = str(result.inserted_id)
        self._events.append("completed")
        logger.info("流式查房 draft 已创建: session=%s draft=%s",
                     self._session_id, draft["_id"])
        return draft

    def _collect_hints_hit(
        self, cleaned_text: str, suspects: list[dict[str, str]]
    ) -> dict[str, list[str]]:
        """Collect correction hints that were triggered — mirrors VoiceRoundingService."""
        hints = self._vr_svc.correction_hints
        hit: dict[str, list[str]] = {"accent": [], "dialect": [], "drug_confusable": []}

        for entry in hints.get("accent_errors") or []:
            for w in entry.get("wrong") or []:
                if w in cleaned_text:
                    hit["accent"].append(f"{w}→{entry.get('right', '')}")

        for entry in hints.get("dialect_phrases") or []:
            for w in entry.get("wrong") or []:
                if w in cleaned_text:
                    hit["dialect"].append(f"{w}→{entry.get('right', '')}")

        for s in suspects:
            if s.get("type") == SUSPECT_TYPE_DRUG:
                hit["drug_confusable"].append(s.get("term", ""))

        return {k: v for k, v in hit.items() if v}
