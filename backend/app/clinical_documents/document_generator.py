"""
Clinical Documents — Progress Note Generator.

Renders the Jinja2 user prompt, calls the LLM, parses the JSON response,
and verifies citation integrity (hallucination detection).
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from jinja2 import Template

from .schemas import DraftOutput, ProgressNoteContext

logger = logging.getLogger("icu-alert")

PROMPTS_DIR = Path(__file__).parent / "prompts"
SYSTEM_PROMPT = (PROMPTS_DIR / "progress_note_system.txt").read_text(encoding="utf-8")
USER_TEMPLATE = Template(
    (PROMPTS_DIR / "progress_note_user.j2").read_text(encoding="utf-8")
)


class ProgressNoteGenerator:
    """Generate SOAP progress notes via LLM with citation verification."""

    def __init__(self, cfg):
        self.cfg = cfg

    async def generate(self, ctx: ProgressNoteContext) -> dict:
        from app.services.llm_runtime import call_llm_chat

        user_prompt = USER_TEMPLATE.render(**ctx.model_dump())

        resp = await call_llm_chat(
            cfg=self.cfg,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model="medical",
            temperature=0.2,
            max_tokens=1500,
            timeout_seconds=60,
            response_format={"type": "json_object"},
        )

        raw_text = resp.get("text", "")
        # Strip potential markdown code fences
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned.strip())

        try:
            raw = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.error("LLM 返回非法 JSON: %s — %s", exc, raw_text[:300])
            raise ValueError(f"LLM 返回 JSON 解析失败: {exc}") from exc

        draft = DraftOutput(**raw)
        citations, warnings = self._verify_citations(raw, ctx)

        return {
            "draft": draft.model_dump(),
            "citations": citations,
            "hallucination_warnings": warnings,
            "model": resp.get("model", ""),
            "prompt_version": "v1",
            "context_snapshot": ctx.model_dump(),
            "usage": resp.get("usage"),
        }

    # ── Citation verification ─────────────────────────────────────────

    def _verify_citations(
        self, draft: dict, ctx: ProgressNoteContext
    ) -> tuple[list[dict], list[str]]:
        text = json.dumps(draft, ensure_ascii=False)
        refs = re.findall(r"\[([A-Z]+\d*)\]", text)
        valid_ids = self._collect_valid_ids(ctx)
        citations: list[dict] = []
        warnings: list[str] = []
        seen: set[str] = set()
        for ref in refs:
            if ref in seen:
                continue
            seen.add(ref)
            if ref in valid_ids:
                citations.append({"ref": ref, "source": valid_ids[ref]})
            else:
                warnings.append(f"幻觉引用：{ref} 不存在于原始数据")
        return citations, warnings

    def _collect_valid_ids(self, ctx: ProgressNoteContext) -> dict[str, str]:
        ids: dict[str, str] = {"V": "vitals", "VT0": "ventilator_current"}
        for lab in ctx.labs:
            ids[f"L{lab.id}"] = f"lab:{lab.name}"
        for drug in ctx.drugs:
            ids[f"D{drug.id}"] = f"drug:{drug.name}"
        for alert in ctx.alerts:
            ids[f"A{alert.id}"] = f"alert:{alert.type}"
        if ctx.vent:
            for change in ctx.vent.changes:
                ids[f"VT{change.id}"] = "vent_change"
        if ctx.scores:
            ids["AS1"] = "scores"
        return ids
