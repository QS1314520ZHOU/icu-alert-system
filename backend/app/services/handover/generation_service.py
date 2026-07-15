"""
Handover — Generation Service.

Calls LLM Runtime to produce a structured ISBAR handover draft from
pre-aggregated patient context data ("先查库再写").
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.services.handover.schemas import (
    HandoverContext,
    HandoverDocument,
    HandoverStatus,
    ISbarSections,
)

API_TZ = ZoneInfo("Asia/Shanghai")
logger = logging.getLogger("icu-alert")

PROMPT_DIR = Path(__file__).parent.parent.parent / "prompts"

PROMPT_FILES = {
    "nurse_bedside": "nurse_bedside_handover.md",
    "nurse_ward": "nurse_ward_handover.md",
    "doctor": "doctor_handover.md",
}


def _load_prompt(handover_type: str) -> str:
    """Load the system prompt markdown file for the given handover type."""
    filename = PROMPT_FILES.get(handover_type, "nurse_bedside_handover.md")
    path = PROMPT_DIR / filename
    if path.exists():
        return path.read_text(encoding="utf-8")
    logger.warning("Prompt file not found: %s, using embedded fallback", path)
    return _fallback_prompt(handover_type)


def _fallback_prompt(handover_type: str) -> str:
    """Minimal fallback system prompt if the markdown file is missing."""
    return (
        "你是ICU交班助手。只能使用传入的数据，不得编造。"
        "无数据字段留空并写入missing_data。"
        "危急值与未闭环预警必须置顶纳入R部分。"
        "严格输出JSON，不加Markdown代码围栏。"
    )


class HandoverGenerationService:
    """Generates structured ISBAR handover drafts via LLM Runtime."""

    def __init__(self, db, config) -> None:
        self.db = db
        self.config = config

    async def generate(
        self,
        context: HandoverContext,
        handover_type: str = "nurse_bedside",
    ) -> HandoverDocument:
        """Generate an AI-drafted handover document from patient context.

        Args:
            context: Pre-aggregated HandoverContext (from HandoverContextService)
            handover_type: "nurse_bedside" | "nurse_ward" | "doctor"

        Returns:
            HandoverDocument with AI-generated sections in draft status.
        """
        system_prompt = _load_prompt(handover_type)
        context_json = context.model_dump_json(exclude_none=False)

        user_prompt = (
            f"请基于以下数据生成{handover_type}交班草稿。\n"
            f"<input_data>\n{context_json}\n</input_data>"
        )

        # Call LLM Runtime
        try:
            from app.services.llm_runtime import call_llm_chat

            result = await call_llm_chat(
                cfg=self.config,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model="medical",
                temperature=0.1,
                max_tokens=4096,
                timeout_seconds=60,
                response_format={"type": "json_object"},
            )
            raw_text = str(result.get("text") or "")
            parsed = self._parse_json(raw_text)
        except Exception as exc:
            logger.error("LLM call failed for handover generation: %s", exc)
            parsed = self._build_empty_draft(handover_type, context)

        # Build document
        return self._build_document(parsed, context, handover_type)

    def _parse_json(self, raw: str) -> dict[str, Any]:
        """Parse LLM output, stripping markdown fences if present."""
        text = raw.strip()
        # Strip ```json / ``` fences
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object boundaries
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    pass
            logger.warning("Failed to parse LLM JSON output, using empty draft")
            return {}

    def _build_document(
        self,
        parsed: dict[str, Any],
        context: HandoverContext,
        handover_type: str,
    ) -> HandoverDocument:
        """Construct a HandoverDocument from parsed LLM output."""
        now = datetime.now(API_TZ).isoformat()
        patient_id = str(context.patient.get("admission_no") or context.patient.get("name", ""))

        sections_data = parsed.get("sections", {})
        try:
            sections = ISbarSections(**sections_data)
        except Exception:
            sections = ISbarSections()

        return HandoverDocument(
            handover_id=str(uuid.uuid4()),
            patient_id=patient_id,
            handover_type=handover_type,
            shift=context.shift,
            time_window=context.time_window,
            data_snapshot_at=context.data_snapshot_at,
            sections=sections,
            evidence=parsed.get("evidence", []),
            missing_data=parsed.get("missing_data", []),
            ai_generated_fields=parsed.get("ai_generated_fields", []),
            content_sources=self._init_content_sources(parsed.get("ai_generated_fields", [])),
            status=HandoverStatus.DRAFT,
            versions=[],
            created_at=now,
            updated_at=now,
        )

    def _init_content_sources(self, ai_fields: list[str]) -> dict[str, str]:
        """Initialize content_sources dict from ai_generated_fields list."""
        sources: dict[str, str] = {}
        for field in ai_fields:
            sources[field] = "ai_generated"
        return sources

    def _build_empty_draft(self, handover_type: str, context: HandoverContext) -> dict[str, Any]:
        """Return a minimal empty draft when LLM is unavailable."""
        return {
            "handover_type": handover_type,
            "patient_id": context.patient.get("admission_no", ""),
            "time_window": context.time_window,
            "data_snapshot_at": context.data_snapshot_at,
            "sections": {},
            "evidence": [],
            "missing_data": ["*"],
            "ai_generated_fields": [],
            "conflicts": [],
            "status": "draft",
        }
