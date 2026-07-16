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
from app.services.llm_runtime import call_llm_chat

API_TZ = ZoneInfo("Asia/Shanghai")
logger = logging.getLogger("icu-alert")

PROMPT_DIR = Path(__file__).parent.parent.parent / "prompts"

PROMPT_FILES = {
    "nurse_bedside": "nurse_bedside_handover.md",
    "nurse_ward": "nurse_ward_handover.md",
    "doctor": "doctor_handover.md",
    "change_detection": "handover_change_detection.md",
    "completeness_check": "handover_completeness_check.md",
    "conflict_detection": "handover_conflict_detection.md",
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

        # Build input_data dict matching the prompt's expected structure.
        # Map shift keys: prompt uses scheduled_start/scheduled_end for plan times,
        # time_window for actual data query range.
        shift_dict = context.shift or {}
        input_data: dict[str, Any] = {
            "patient_id": context.patient_id,
            "shift": {
                "code": shift_dict.get("code", ""),
                "name": shift_dict.get("name", ""),
                "scheduled_start": shift_dict.get("scheduled_start", shift_dict.get("start", "")),
                "scheduled_end": shift_dict.get("scheduled_end", shift_dict.get("end", "")),
                "data_start": context.time_window.get("start", ""),
                "data_end": context.time_window.get("end", ""),
                "source": shift_dict.get("source", ""),
            },
            "time_window": context.time_window,
            "data_snapshot_at": context.data_snapshot_at,
            "patient": context.patient,
            "situation": context.situation,
            "background": context.background,
            "vitals": context.vitals,
            "labs": context.labs,
            "io": context.io,
            "pumps": context.pumps,
            "airway_vent": context.airway_vent,
            "lines": context.lines,
            "assessments": context.assessments,
            "events": context.events,
            "pending_orders": context.pending_orders,
            "alerts": context.alerts,
            "shift_changes": context.shift_changes,
            "previous_handover": context.previous_handover,
        }
        input_json = json.dumps(input_data, ensure_ascii=False, default=str)

        user_prompt = (
            f"请基于以下数据生成{handover_type}交班草稿。\n"
            f"<input_data>\n{input_json}\n</input_data>"
        )

        # Call LLM Runtime
        try:
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
        patient_id = context.patient_id

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
            "patient_id": context.patient_id,
            "time_window": context.time_window,
            "data_snapshot_at": context.data_snapshot_at,
            "sections": {},
            "evidence": [],
            "missing_data": ["*"],
            "ai_generated_fields": [],
            "conflicts": [],
            "status": "draft",
        }

    # ── Change Detection ────────────────────────────────────────────

    async def _get_previous_shift_data(
        self, patient_id: str, current_window: dict[str, str]
    ) -> dict[str, Any]:
        """Retrieve the most recent prior handover snapshot for change comparison.

        Returns a dict with:
          - "shift": {code, name, data_start, data_end} for the previous shift
          - "clinical": {vitals, labs, io, pumps, ...} for comparison
          - "handover_snapshot_at": ISO timestamp of the previous snapshot
        """
        try:
            prev_doc = await self.db.col("handover_documents").find_one(
                {
                    "patient_id": patient_id,
                    "time_window.end": {"$lte": current_window["start"]},
                    "status": {"$in": ["submitted", "acknowledged"]},
                },
                sort=[("time_window.end", -1)],
            )
            if prev_doc and prev_doc.get("time_window"):
                from app.services.handover.context_service import HandoverContextService

                context_svc = HandoverContextService(self.db)
                pw = prev_doc["time_window"]
                prev_start = datetime.fromisoformat(pw["start"])
                prev_end = datetime.fromisoformat(pw["end"])
                prev_shift = prev_doc.get("shift", {})
                prev_context = await context_svc.build(
                    patient_id, prev_start, prev_end,
                    shift=prev_shift,
                )
                return {
                    "shift": {
                        "code": prev_shift.get("code", ""),
                        "name": prev_shift.get("name", ""),
                        "data_start": pw.get("start", ""),
                        "data_end": pw.get("end", ""),
                    },
                    "clinical": {
                        "vitals": prev_context.vitals,
                        "labs": prev_context.labs,
                        "io": prev_context.io,
                        "pumps": prev_context.pumps,
                        "airway_vent": prev_context.airway_vent,
                        "lines": prev_context.lines,
                        "assessments": prev_context.assessments,
                        "events": prev_context.events,
                        "pending_orders": prev_context.pending_orders,
                        "alerts": prev_context.alerts,
                    },
                    "handover_snapshot_at": prev_doc.get("data_snapshot_at", ""),
                }
        except Exception as exc:
            logger.warning("Failed to retrieve previous shift data for %s: %s", patient_id, exc)
        return {}

    async def detect_changes(
        self, patient_id: str, time_window: dict[str, str], shift: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Detect meaningful changes between current and previous shift data.

        Reads handover_change_detection.md as the system prompt.
        Input data is aggregated via HandoverContextService ("先查后写").
        """
        from app.services.handover.context_service import HandoverContextService

        context_svc = HandoverContextService(self.db)

        # Parse time window
        time_start = datetime.fromisoformat(time_window["start"])
        time_end = datetime.fromisoformat(time_window["end"])

        # Build current context (query DB first)
        context = await context_svc.build(patient_id, time_start, time_end, shift=shift)

        # Build previous shift data for comparison
        previous_result = await self._get_previous_shift_data(patient_id, time_window)

        # Build input_data matching handover_change_detection.md spec
        current_shift_meta = {
            "code": (shift or {}).get("code", ""),
            "name": (shift or {}).get("name", ""),
            "data_start": time_window.get("start", ""),
            "data_end": time_window.get("end", ""),
        }
        previous_shift_meta = previous_result.get("shift", {}) if previous_result else {}

        input_data: dict[str, Any] = {
            "patient_id": patient_id,
            "current_shift": current_shift_meta,
            "previous_shift": previous_shift_meta,
            "data_snapshot_at": context.data_snapshot_at,
            "current": {
                "vitals": context.vitals,
                "labs": context.labs,
                "io": context.io,
                "pumps": context.pumps,
                "airway_vent": context.airway_vent,
                "lines": context.lines,
                "assessments": context.assessments,
                "events": context.events,
                "pending_orders": context.pending_orders,
                "alerts": context.alerts,
            },
            "previous": previous_result.get("clinical", {}) if previous_result else {},
            "thresholds": self.config.get("handover", {}).get("change_detection", {}).get("thresholds", {}),
        }

        system_prompt = _load_prompt("change_detection")
        user_prompt = (
            f"<input_data>\n{json.dumps(input_data, ensure_ascii=False, default=str)}\n</input_data>"
        )

        try:
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
            return {
                "patient_id": patient_id,
                "current_shift": current_shift_meta,
                "previous_shift": previous_shift_meta,
                "previous_handover": previous_result,
                "time_window": time_window,
                "data_snapshot_at": context.data_snapshot_at,
                "changes": parsed.get("changes", []),
                "not_comparable": parsed.get("not_comparable", []),
                "needs_human": parsed.get("needs_human", []),
                "missing_data": parsed.get("missing_data", []),
            }
        except Exception as exc:
            logger.error("Change detection LLM call failed for %s: %s", patient_id, exc)
            return {
                "patient_id": patient_id,
                "current_shift": current_shift_meta,
                "previous_shift": previous_shift_meta,
                "previous_handover": previous_result,
                "time_window": time_window,
                "data_snapshot_at": context.data_snapshot_at,
                "changes": [],
                "not_comparable": [],
                "needs_human": [],
                "missing_data": ["LLM调用失败"],
            }

    # ── Completeness Check ──────────────────────────────────────────

    async def check_completeness(self, handover_id: str) -> dict[str, Any]:
        """Check handover draft for missing required items before submission.

        Reads handover_completeness_check.md as the system prompt.
        Rebuilds context via HandoverContextService ("先查后写").
        """
        from app.services.handover.context_service import HandoverContextService

        doc = await self.db.col("handover_documents").find_one({"handover_id": handover_id})
        if not doc:
            return {
                "patient_id": "",
                "can_submit": False,
                "blockers": [{"field": "document", "reason": "交班记录不存在"}],
                "warnings": [],
                "info": [],
                "missing_source": [],
                "checked_at": datetime.now().isoformat(),
            }

        handover = HandoverDocument(**doc)
        context_svc = HandoverContextService(self.db)

        # Rebuild context from the document's time window
        tw = handover.time_window
        time_start = datetime.fromisoformat(tw["start"])
        time_end = datetime.fromisoformat(tw["end"])
        context = await context_svc.build(
            handover.patient_id, time_start, time_end, handover.shift
        )

        input_data = {
            "patient_id": handover.patient_id,
            "handover_type": handover.handover_type,
            "time_window": handover.time_window,
            "data_snapshot_at": handover.data_snapshot_at,
            "draft": {
                "sections": handover.sections.model_dump(),
                "forced_confirmations": [
                    fc.model_dump() for fc in handover.forced_confirmations
                ],
            },
            "context": context.model_dump(exclude_none=False),
            "required": {
                "required_fields": [
                    "situation.diagnosis",
                    "recommendation.critical_first",
                    "recommendation.escalation",
                ],
                "forced_items_rules": [
                    "危急值",
                    "未闭环预警",
                    "高危管路",
                    "血管活性药",
                    "特殊隔离",
                    "紧急升级条件",
                ],
            },
        }

        system_prompt = _load_prompt("completeness_check")
        user_prompt = (
            f"<input_data>\n{json.dumps(input_data, ensure_ascii=False, default=str)}\n</input_data>"
        )

        try:
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
            return self._parse_json(raw_text)
        except Exception as exc:
            logger.error(
                "Completeness check LLM call failed for %s: %s", handover_id, exc
            )
            return {
                "patient_id": handover.patient_id,
                "can_submit": True,
                "blockers": [],
                "warnings": [
                    {
                        "field": "_system",
                        "reason": f"完整性检查服务不可用: {exc}",
                        "evidence": [],
                    }
                ],
                "info": [],
                "missing_source": [],
                "checked_at": datetime.now().isoformat(),
            }

    # ── Conflict Detection ──────────────────────────────────────────

    async def detect_conflicts(self, handover_id: str) -> dict[str, Any]:
        """Detect data conflicts between draft, source context, and previous handover.

        Reads handover_conflict_detection.md as the system prompt.
        Rebuilds context via HandoverContextService ("先查后写").
        """
        from app.services.handover.context_service import HandoverContextService

        doc = await self.db.col("handover_documents").find_one({"handover_id": handover_id})
        if not doc:
            return {
                "patient_id": "",
                "conflicts": [],
                "checked_at": datetime.now().isoformat(),
            }

        handover = HandoverDocument(**doc)
        context_svc = HandoverContextService(self.db)

        # Rebuild context from the document's time window
        tw = handover.time_window
        time_start = datetime.fromisoformat(tw["start"])
        time_end = datetime.fromisoformat(tw["end"])
        context = await context_svc.build(
            handover.patient_id, time_start, time_end, handover.shift
        )

        # Get previous shift data for cross-shift conflict detection
        previous_result = await self._get_previous_shift_data(
            handover.patient_id, handover.time_window
        )
        previous = previous_result.get("clinical", previous_result) if previous_result else {}

        input_data = {
            "patient_id": handover.patient_id,
            "time_window": handover.time_window,
            "data_snapshot_at": handover.data_snapshot_at,
            "draft": {"sections": handover.sections.model_dump()},
            "context": context.model_dump(exclude_none=False),
            "previous": previous,
        }

        system_prompt = _load_prompt("conflict_detection")
        user_prompt = (
            f"<input_data>\n{json.dumps(input_data, ensure_ascii=False, default=str)}\n</input_data>"
        )

        try:
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
            return self._parse_json(raw_text)
        except Exception as exc:
            logger.error(
                "Conflict detection LLM call failed for %s: %s", handover_id, exc
            )
            return {
                "patient_id": handover.patient_id,
                "conflicts": [],
                "checked_at": datetime.now().isoformat(),
            }
