"""
Handover — Brief Renderer.

Deterministic rendering of handover briefs from confirmed ISBAR content.
No LLM involved — purely rule-based: fields with content are shown,
empty fields are hidden, empty sections are omitted entirely.

Three view modes:
  - "full": Complete bedside handover view
  - "compact": Only abnormalities and pending tasks
  - "ward": One-liner summary + key points for ward-level overview
"""
from __future__ import annotations

from typing import Any

from app.services.handover.schemas import (
    AssessmentSection,
    ISbarSections,
    RecommendationSection,
)


class HandoverBriefRenderer:
    """Renders handover briefs deterministically from ISBAR sections."""

    # ── Public API ─────────────────────────────────────────────────

    def render(
        self,
        sections: ISbarSections,
        mode: str = "full",
        handover_type: str = "nurse_bedside",
    ) -> dict[str, Any]:
        """Render a brief from ISBAR sections.

        Args:
            sections: The ISBAR content sections
            mode: "full" | "compact" | "ward"
            handover_type: "nurse_bedside" | "doctor"

        Returns:
            A dict with "blocks": list of rendered content blocks
        """
        if mode == "ward":
            return self._render_ward(sections)
        if mode == "compact":
            return self._render_compact(sections)
        return self._render_full(sections)

    # ── Full Mode ──────────────────────────────────────────────────

    def _render_full(self, sections: ISbarSections) -> dict[str, Any]:
        blocks: list[dict[str, Any]] = []

        # I — Identity (always shown, even if sparse)
        ident = self._render_identify(sections)
        if ident.get("lines"):
            blocks.append({"section": "I 身份", "icon": "👤", "lines": ident["lines"], "tags": ident.get("tags", [])})

        # S — Situation
        sit = self._render_situation(sections)
        if sit.get("lines"):
            blocks.append({"section": "S 现况", "icon": "📋", "lines": sit["lines"]})

        # B — Background
        bg = self._render_background(sections)
        if bg.get("lines"):
            blocks.append({"section": "B 背景", "icon": "📖", "lines": bg["lines"]})

        # A — Assessment (by organ system)
        assessment_blocks = self._render_assessment(sections)
        blocks.extend(assessment_blocks)

        # R — Recommendation (critical first!)
        rec_blocks = self._render_recommendation(sections)
        blocks.extend(rec_blocks)

        return {"mode": "full", "blocks": blocks}

    # ── Compact Mode ───────────────────────────────────────────────

    def _render_compact(self, sections: ISbarSections) -> dict[str, Any]:
        """Only show abnormalities and pending tasks."""
        blocks: list[dict[str, Any]] = []
        rec = sections.recommendation

        # Critical alerts — always shown in compact
        if rec.critical_first:
            blocks.append({
                "section": "⚠️ 危急值与未闭环预警",
                "icon": "🚨",
                "lines": [self._format_alert(a) for a in rec.critical_first],
            })

        # Tasks
        if rec.tasks:
            blocks.append({
                "section": "📝 下一班任务",
                "icon": "✅",
                "lines": [f"• {t}" for t in rec.tasks if t],
            })

        # Pending
        if rec.pending:
            blocks.append({
                "section": "⏳ 待完成事项",
                "icon": "⏰",
                "lines": [f"• {p}" for p in rec.pending if p],
            })

        # Escalation
        if rec.escalation:
            blocks.append({
                "section": "🆘 紧急升级条件",
                "icon": "🔴",
                "lines": [f"• {e}" for e in rec.escalation if e],
            })

        # Assessment changes only
        a = sections.assessment
        changes = {
            "神经": a.neuro.changes,
            "呼吸": a.resp.changes,
            "循环": a.circ.changes,
            "体温": a.temp.changes,
            "消化": a.gi.changes,
            "血液": a.heme.changes,
        }
        change_lines = [f"{k}: {v}" for k, v in changes.items() if v]
        if change_lines:
            blocks.append({"section": "🔄 本班变化", "icon": "📊", "lines": change_lines})

        return {"mode": "compact", "blocks": blocks}

    # ── Ward Mode ──────────────────────────────────────────────────

    def _render_ward(self, sections: ISbarSections) -> dict[str, Any]:
        """One-liner summary for ward-level overview."""
        ident = sections.identify
        sit = sections.situation
        rec = sections.recommendation

        one_liner = f"{ident.bed or '?'}床 {ident.name or '—'} · {sit.diagnosis or '诊断待填'}"
        if sit.main_problems:
            one_liner += f" · {sit.main_problems}"

        key_points = []
        if rec.critical_first:
            key_points.append(f"⚠️ {len(rec.critical_first)}条危急值需确认")
        if rec.tasks:
            key_points.append(f"📝 {len(rec.tasks)}项待办")
        if rec.pending:
            key_points.append(f"⏳ {len(rec.pending)}项待完成")

        return {
            "mode": "ward",
            "patient_id": ident.admission_no,
            "bed": ident.bed,
            "name": ident.name,
            "one_liner": one_liner,
            "key_points": key_points,
            "has_critical": len(rec.critical_first) > 0,
        }

    # ── Section Renderers ──────────────────────────────────────────

    def _render_identify(self, sections: ISbarSections) -> dict[str, Any]:
        i = sections.identify
        lines = []
        if i.name:
            lines.append(f"姓名: {i.name}")
        if i.bed:
            lines.append(f"床号: {i.bed}")
        if i.sex:
            lines.append(f"性别: {i.sex}")
        if i.age:
            lines.append(f"年龄: {i.age}")
        if i.admission_no:
            lines.append(f"住院号: {i.admission_no}")
        if i.medical_group:
            lines.append(f"医疗分组: {i.medical_group}")
        tags = [t for t in i.special_tags if t]
        return {"lines": lines, "tags": tags}

    def _render_situation(self, sections: ISbarSections) -> dict[str, Any]:
        s = sections.situation
        lines = []
        if s.diagnosis:
            lines.append(f"诊断: {s.diagnosis}")
        if s.surgery:
            lines.append(f"手术: {s.surgery}")
        if s.post_op_day:
            lines.append(f"术后: {s.post_op_day}")
        if s.icu_day:
            lines.append(f"入科: {s.icu_day}")
        if s.main_problems:
            lines.append(f"主要问题: {s.main_problems}")
        if s.life_support_level:
            lines.append(f"生命支持: {s.life_support_level}")
        if s.life_support_changes:
            lines.append(f"本班变化: {s.life_support_changes}")
        return {"lines": lines}

    def _render_background(self, sections: ISbarSections) -> dict[str, Any]:
        b = sections.background
        lines = []
        if b.admission_course:
            lines.append(f"诊疗经过: {b.admission_course}")
        if b.past_history:
            lines.append(f"既往史: {b.past_history}")
        if b.isolation:
            lines.append(f"隔离: {b.isolation}")
        if b.allergies:
            lines.append(f"过敏: {b.allergies}")
        return {"lines": lines}

    def _render_assessment(self, sections: ISbarSections) -> list[dict[str, Any]]:
        a = sections.assessment
        systems = [
            ("神经", "🧠", a.neuro),
            ("呼吸", "🫁", a.resp),
            ("循环", "❤️", a.circ),
            ("体温", "🌡️", a.temp),
            ("消化", "🫄", a.gi),
            ("血液", "🩸", a.heme),
            ("专科要点", "🔬", a.specialty),
            ("护理要点", "💊", a.nursing),
            ("管路", "🪡", a.lines),
            ("皮肤", "🖐️", a.skin),
            ("物品交接", "📦", a.items),
        ]
        blocks: list[dict[str, Any]] = []
        for name, icon, obj in systems:
            content = getattr(obj, "content", "")
            changes = getattr(obj, "changes", "")
            if isinstance(obj, dict):
                content = obj.get("content", "")
                changes = obj.get("changes", "")
            if not content and not changes:
                continue
            lines = []
            if content:
                lines.append(content)
            if changes:
                lines.append(f"[变化] {changes}")
            if lines:
                blocks.append({"section": f"{name}", "icon": icon, "lines": lines})
        return blocks

    def _render_recommendation(self, sections: ISbarSections) -> list[dict[str, Any]]:
        r = sections.recommendation
        blocks: list[dict[str, Any]] = []

        # Critical alerts — always first, with red styling hint
        if r.critical_first:
            blocks.append({
                "section": "⚠️ 危急值与未闭环预警",
                "icon": "🚨",
                "urgent": True,
                "lines": [self._format_alert(a) for a in r.critical_first],
            })

        if r.tasks:
            blocks.append({
                "section": "📝 下一班任务",
                "icon": "✅",
                "lines": [f"• {t}" for t in r.tasks if t],
            })

        if r.pending:
            blocks.append({
                "section": "⏳ 待回报结果 / 未完成医嘱",
                "icon": "⏰",
                "lines": [f"• {p}" for p in r.pending if p],
            })

        if r.escalation:
            blocks.append({
                "section": "🆘 紧急升级条件",
                "icon": "🔴",
                "urgent": True,
                "lines": [f"• {e}" for e in r.escalation if e],
            })

        return blocks

    # ── Helpers ────────────────────────────────────────────────────

    def _format_alert(self, alert: dict[str, Any]) -> str:
        """Format a critical alert dict into a display line."""
        if isinstance(alert, str):
            return f"🚨 {alert}"
        alert_type = alert.get("type", alert.get("alert_type", "?"))
        value = alert.get("value", alert.get("alert_value", ""))
        time = alert.get("time", "")
        priority = alert.get("priority", "")
        parts = [f"[{priority.upper()}]" if priority else "", alert_type, str(value) if value else "", f"— {time}" if time else ""]
        return " ".join(p for p in parts if p)

    def is_empty(self, sections: ISbarSections) -> bool:
        """Check if all sections are effectively empty."""
        blocks = self._render_full(sections)
        return len(blocks.get("blocks", [])) == 0
