"""
ICU rounding workbench generator.

The structured workbench is the source of truth. The note preview is always
rendered from structured cards/goals/tasks unless a signed override is present.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Template

from .schemas import ProgressNoteContext, RoundingWorkbenchDraft

logger = logging.getLogger("icu-alert")

PROMPTS_DIR = Path(__file__).parent / "prompts"
SYSTEM_PROMPT = (PROMPTS_DIR / "progress_note_system.txt").read_text(encoding="utf-8")
USER_TEMPLATE = Template((PROMPTS_DIR / "progress_note_user.j2").read_text(encoding="utf-8"))

SYSTEM_ORDER = [
    ("neuro", "神经"),
    ("resp", "呼吸 / 氧合"),
    ("cv", "循环 / 灌注"),
    ("renal_fluid", "肾脏 / 液体"),
    ("gi_nutrition", "消化 / 营养"),
    ("id", "感染"),
    ("heme", "血液 / 凝血"),
    ("endo", "内分泌 / 代谢"),
    ("lines_devices", "管路 / 装置"),
    ("goals", "今日目标 / 夜间预案"),
]

GOAL_DEFS = [
    ("map", "MAP 目标", "维持 MAP 目标值，需医生确认"),
    ("oxygenation", "氧合目标", "明确 SpO2、PaO2 或 P/F 目标"),
    ("rass", "镇静目标", "记录 RASS 目标"),
    ("fluid_balance", "液体目标", "记录 24h 净平衡目标"),
    ("antibiotics", "抗菌药计划", "确认继续、降阶梯、停用或疗程天数"),
    ("nutrition", "营养目标", "记录热卡和蛋白目标"),
    ("lines", "管路评估", "评估 CVC、尿管、引流管是否可拔除"),
    ("rehab", "康复目标", "记录床边活动或被动运动计划"),
    ("family_communication", "家属沟通", "确认今日沟通状态"),
    ("night_plan", "夜间预案", "记录氧合、循环或出血等恶化处置阈值"),
]


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _safe_text(value: Any, fallback: str = "未提供") -> str:
    text = str(value or "").strip()
    return text or fallback


def _fmt_range(min_val: Any, max_val: Any, unit: str = "") -> str:
    if min_val is None or max_val is None:
        return "未提供"
    if min_val == max_val:
        return f"{min_val}{unit}"
    return f"{min_val}-{max_val}{unit}"


def _trend_text(value: Any) -> str:
    mapping = {
        "up": "上升",
        "down": "下降",
        "stable": "平稳",
        "volatile": "波动",
        "no_data": "无数据",
        "insufficient": "数据不足",
        "涓婂崌": "上升",
        "涓嬮檷": "下降",
        "骞崇ǔ": "平稳",
        "娉㈠姩": "波动",
        "鏃犳暟鎹?": "无数据",
        "鏁版嵁涓嶈冻": "数据不足",
    }
    return mapping.get(str(value or ""), str(value or "未提供"))


def _priority_from_severity(severity: str) -> str:
    value = str(severity or "").lower()
    if value in {"critical", "危急", "high"}:
        return "critical" if value == "critical" or value == "危急" else "high"
    if value in {"medium", "中危", "warning"}:
        return "medium"
    return "low"


def _priority_label(priority: str) -> str:
    return {
        "critical": "危急",
        "high": "高危",
        "medium": "中危",
        "low": "低危",
    }.get(str(priority or "").lower(), "中危")


def _alert_label(alert_type: str) -> str:
    value = str(alert_type or "").strip()
    lowered = value.lower()
    mapping = {
        "ards": "ARDS/低氧性呼吸衰竭风险",
        "prone_position_candidate": "俯卧位评估候选",
        "pupil critical": "瞳孔异常风险",
        "qsofa": "qSOFA 风险",
        "qsofa warning": "qSOFA 风险",
        "lab_threshold": "检验阈值预警",
        "lung_protective_ventilation": "肺保护通气预警",
        "vap_bundle_missing": "VAP 预防清单缺项",
        "hai_vap_bundle_missing": "VAP 预防清单缺项",
        "nurse_reminder": "护理提醒",
        "nutrition_start_delay": "营养启动延迟",
        "delirium_risk": "谵妄风险",
        "pe_wells_high": "Wells 高风险",
        "weaning": "撤机筛查",
        "forecast_threshold_breach": "预测达到预警阈值",
        "pics_risk": "PICS 风险",
        "trajectory_drift": "病情轨迹漂移预警",
        "ventilator_asynchrony": "人机不同步预警",
        "aki": "急性肾损伤风险",
        "sepsis": "感染/脓毒症风险",
        "infection": "感染风险",
        "vap": "呼吸机相关肺炎风险",
        "ventilator": "呼吸机相关风险",
        "trajectory": "病情轨迹变化风险",
        "hypoxemia": "低氧风险",
        "hypotension": "低血压风险",
        "vte": "VTE/血栓风险",
        "dic": "凝血异常风险",
        "bleeding": "出血风险",
        "fibrinolysis": "凝血/溶栓风险",
    }
    for key, label in mapping.items():
        if key in lowered:
            return label
    return value or "风险预警"


def _lab_is_abnormal(flag: str) -> bool:
    value = str(flag or "").lower()
    return any(token in value for token in ["high", "low", "critical", "↑", "↓", "鈫", "危", "高", "低"])


def _hash_structured(draft: dict) -> str:
    payload = {
        "system_ap": draft.get("system_ap", []),
        "daily_goals": draft.get("daily_goals", []),
        "risk_tasks": draft.get("risk_tasks", []),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _is_noninvasive_or_oxygen_mode(mode: Any) -> bool:
    text = str(mode or "").strip().lower()
    return bool(text) and any(
        token in text
        for token in ["hf", "hfnc", "oxygen", "氧", "吸氧", "高流量", "鼻导管", "面罩"]
    )


def _is_antimicrobial_name(name: Any) -> bool:
    text = str(name or "")
    return any(
        token in text
        for token in [
            "抗菌",
            "抗生",
            "头孢",
            "培南",
            "沙星",
            "西林",
            "环素",
            "万古",
            "替加",
            "哌拉",
            "舒巴",
            "霉素",
            "硝唑",
            "卡泊芬净",
        ]
    )


def _line_category_label(category: str) -> str:
    return {
        "airway": "人工气道",
        "vascular": "血管通路",
        "drain": "引流管",
        "enteral": "胃肠/营养管",
        "urinary": "尿管",
        "other": "其他管路",
    }.get(str(category or ""), "其他管路")


def _tube_summary(tube: Any) -> str:
    site = f"（{tube.site}）" if getattr(tube, "site", "") else ""
    days = f"，留置{tube.dwell_days}天" if getattr(tube, "dwell_days", None) is not None else ""
    status = f"，{tube.latest_status}" if getattr(tube, "latest_status", "") else ""
    return f"{tube.name}{site}{days}{status}"


def render_note_preview(draft: dict) -> dict:
    """Render APSO note text from structured content."""
    try:
        from app.clinical_documents.daily_progress_renderer import render_daily_progress_from_workbench

        rendered = render_daily_progress_from_workbench(draft)
        return {
            **rendered,
            "final_text_override": (draft.get("note_preview") or {}).get("final_text_override"),
            "is_overridden": bool((draft.get("note_preview") or {}).get("final_text_override")),
            "generated_from_hash": _hash_structured(draft),
        }
    except Exception:
        logger.exception("daily progress preview render failed; fallback to APSO")
    banner = draft.get("patient_banner") or {}
    lines: list[str] = [
        "A/P：",
    ]
    for idx, card in enumerate(draft.get("system_ap") or [], start=1):
        title = card.get("title") or card.get("system") or f"系统{idx}"
        lines.append(f"{idx}. {title}")
        for label, key in (("评估", "assessment"), ("计划", "plan_items")):
            statements = [s.get("text") for s in card.get(key) or [] if s.get("text")]
            if statements:
                lines.append(f"   {label}：" + "；".join(statements))

    lines.append("")
    lines.append("今日目标：")
    for goal in draft.get("daily_goals") or []:
        lines.append(f"- {goal.get('label')}: {goal.get('target') or '待确认'}")

    lines.append("")
    lines.append("风险任务与待复核项：")
    risk_tasks = draft.get("risk_tasks") or []
    if risk_tasks:
        for task in risk_tasks:
            lines.append(f"- {task.get('title')}（{_priority_label(task.get('priority', 'medium'))}）")
    else:
        lines.append("- 暂无活跃风险任务。")

    lines.append("")
    lines.append("S：床旁症状和主观不适需由医生查房补充。")
    lines.append("")
    lines.append("O：")
    lines.append(
        f"患者 {banner.get('bed_no', '未提供')}床，{banner.get('age', '未提供')}"
        f"{banner.get('sex', '')}，ICU第{banner.get('icu_day', '未提供')}天。"
        f"主要诊断：{banner.get('primary_diagnosis', '未提供')}。"
    )
    for item in draft.get("organ_support") or []:
        lines.append(f"- {item.get('label')}: {item.get('summary')}")
    if draft.get("timeline"):
        lines.append("过去24小时关键事件：" + "；".join(
            f"{ev.get('occurred_at')} {_alert_label(ev.get('title'))}" for ev in draft.get("timeline", [])[:8]
        ))

    return {
        "style": "APSO",
        "generated_text": "\n".join(lines).strip(),
        "final_text_override": (draft.get("note_preview") or {}).get("final_text_override"),
        "is_overridden": bool((draft.get("note_preview") or {}).get("final_text_override")),
        "generated_from_hash": _hash_structured(draft),
    }


class ProgressNoteGenerator:
    """Generate ICU rounding workbench drafts with citation validation."""

    def __init__(self, cfg):
        self.cfg = cfg

    async def generate(self, ctx: ProgressNoteContext) -> dict:
        citations = self._build_citations(ctx)
        base_draft = self._build_skeleton(ctx, citations)
        warnings: list[str] = []
        model = ""
        usage = None

        try:
            patch, model, usage = await self._call_llm_patch(ctx, base_draft, citations)
            draft = self._merge_workbench_patch(base_draft, patch)
        except (asyncio.TimeoutError, TimeoutError) as exc:
            logger.warning("LLM timeout, using deterministic workbench fallback: %s", exc)
            draft = base_draft
            warnings.append("AI生成超时，已返回规则生成的 ICU 查房工作台草稿，请结合床旁查体复核。")
        except Exception as exc:
            logger.warning("LLM workbench generation failed, using fallback: %s", exc)
            draft = base_draft
            warnings.append("AI结构化生成失败，已返回规则生成的 ICU 查房工作台草稿，请重点复核评估和计划。")

        draft = self._validate_and_repair_workbench(draft, citations)
        draft = self._suppress_resolved_missing_data(draft, ctx)
        draft["quality_checks"] = self._run_quality_checks(draft, ctx)
        draft["note_preview"] = render_note_preview(draft)
        validated = RoundingWorkbenchDraft(**draft).model_dump()
        citation_warnings = self._verify_citations(validated, citations)
        warnings.extend(citation_warnings)

        return {
            "draft": validated,
            "citations": citations,
            "hallucination_warnings": warnings,
            "model": model,
            "prompt_version": "workbench_v1",
            "context_snapshot": ctx.model_dump(),
            "usage": usage,
        }

    async def _call_llm_patch(
        self,
        ctx: ProgressNoteContext,
        base_draft: dict,
        citations: list[dict],
    ) -> tuple[dict, str, Any]:
        from app.services.llm_runtime import call_llm_chat

        user_prompt = USER_TEMPLATE.render(
            **ctx.model_dump(),
            base_draft=json.dumps(base_draft, ensure_ascii=False),
            citations=json.dumps(citations, ensure_ascii=False),
        )
        resp = await call_llm_chat(
            cfg=self.cfg,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            model="medical",
            temperature=0.2,
            max_tokens=3500,
            timeout_seconds=25,
            response_format={"type": "json_object"},
        )
        raw_text = resp.get("text", "")
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned.strip())
        patch = self._parse_json(cleaned)
        return patch, resp.get("model", ""), resp.get("usage")

    def _parse_json(self, text: str) -> dict:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            obj_text = self._extract_first_json_object(text)
            if obj_text and obj_text != text:
                return json.loads(obj_text)
            raise

    def _extract_first_json_object(self, text: str) -> str | None:
        start = text.find("{")
        if start < 0:
            return None
        depth = 0
        in_string = False
        escaped = False
        for idx in range(start, len(text)):
            ch = text[idx]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : idx + 1]
        return None

    def _build_citations(self, ctx: ProgressNoteContext) -> list[dict]:
        citations = [
            {
                "id": "V1",
                "source_type": "vital_sign",
                "title": "生命体征",
                "observed_at": ctx.window_end,
                "summary": (
                    f"HR {_fmt_range(ctx.v.hr.min, ctx.v.hr.max)}, "
                    f"MAP {_fmt_range(ctx.v.map.min, ctx.v.map.max)}, "
                    f"SpO2 {_fmt_range(ctx.v.spo2.min, ctx.v.spo2.max, '%')}"
                ),
                "raw_value": {"name": "vitals", "value": ctx.v.model_dump(), "unit": ""},
            }
        ]
        if ctx.vent:
            citations.append({
                "id": "VT0",
                "source_type": "ventilator",
                "title": "呼吸机参数",
                "observed_at": ctx.window_end,
                "summary": (
                    f"{ctx.vent.mode}，吸氧浓度 {ctx.vent.fio2}"
                    f"{'，呼气末正压 ' + str(ctx.vent.peep) if ctx.vent.peep not in (0, None) else ''}，"
                    f"氧合指数 {ctx.vent.pf_ratio if ctx.vent.pf_ratio is not None else '未提供'}"
                ),
                "raw_value": {"name": "ventilator", "value": ctx.vent.model_dump(), "unit": ""},
            })
        if ctx.neuro:
            parts = []
            if ctx.neuro.rass is not None:
                parts.append(f"RASS {ctx.neuro.rass:g}")
            if ctx.neuro.cam_icu:
                parts.append(f"CAM-ICU {ctx.neuro.cam_icu}")
            citations.append({
                "id": "N1",
                "source_type": "bedside",
                "title": "镇静/谵妄评估",
                "observed_at": ctx.neuro.observed_at or ctx.window_end,
                "summary": "，".join(parts) or "镇静/谵妄评估已记录",
                "raw_value": {"name": "neuro_assessment", "value": ctx.neuro.model_dump(), "unit": ""},
            })
        if ctx.scores:
            citations.append({
                "id": "AS1",
                "source_type": "score",
                "title": "评分",
                "observed_at": ctx.window_end,
                "summary": f"GCS {ctx.scores.gcs}, SOFA {ctx.scores.sofa}, APACHE {ctx.scores.apache}",
                "raw_value": {"name": "scores", "value": ctx.scores.model_dump(), "unit": ""},
            })
        if ctx.fluid_balance:
            fb = ctx.fluid_balance
            parts = []
            if fb.intake_24h_ml is not None:
                parts.append(f"24h入量 {fb.intake_24h_ml}mL")
            if fb.output_24h_ml is not None:
                parts.append(f"24h出量 {fb.output_24h_ml}mL")
            if fb.net_24h_ml is not None:
                parts.append(f"净平衡 {fb.net_24h_ml}mL")
            if fb.urine_24h_ml is not None:
                parts.append(f"24h尿量 {fb.urine_24h_ml}mL")
            citations.append({
                "id": "IO1",
                "source_type": "bedside",
                "title": "床旁出入量",
                "observed_at": ctx.window_end,
                "summary": "，".join(parts) or "床旁出入量已记录",
                "raw_value": {"name": "fluid_balance", "value": fb.model_dump(), "unit": "mL"},
            })
        if ctx.line_devices:
            tubes = ctx.line_devices.active_tubes
            parts = [_tube_summary(tube) for tube in tubes[:8]]
            if ctx.line_devices.drainage_24h_ml is not None:
                parts.append(f"24h引流量 {ctx.line_devices.drainage_24h_ml}mL")
            citations.append({
                "id": "LD1",
                "source_type": "tubeExe/bedside",
                "title": "管路/装置",
                "observed_at": ctx.window_end,
                "summary": "；".join(parts) or "管路记录已检索",
                "raw_value": {"name": "line_devices", "value": ctx.line_devices.model_dump(), "unit": ""},
            })
        if ctx.infection_evidence:
            parts = []
            if ctx.infection_evidence.inflammatory_markers:
                parts.append("炎症指标：" + "；".join(
                    f"{item.name} {item.value}{item.unit}" for item in ctx.infection_evidence.inflammatory_markers[:5]
                ))
            if ctx.infection_evidence.culture_results:
                parts.append("培养/病原：" + "；".join(
                    f"{item.name} {item.value}" for item in ctx.infection_evidence.culture_results[:5]
                ))
            citations.append({
                "id": "IE1",
                "source_type": "VI_ICU_EXAM_ITEM",
                "title": "感染相关检验",
                "observed_at": ctx.window_end,
                "summary": "；".join(parts) or "感染相关检验已检索",
                "raw_value": {"name": "infection_evidence", "value": ctx.infection_evidence.model_dump(), "unit": ""},
            })
        for lab in ctx.labs:
            citations.append({
                "id": f"L{lab.id}",
                "source_type": "lab",
                "title": lab.name,
                "observed_at": ctx.window_end,
                "summary": f"{lab.name} {lab.prev}->{lab.curr}{lab.unit} {lab.flag}",
                "raw_value": {"name": lab.name, "value": lab.curr, "unit": lab.unit},
            })
        for drug in ctx.drugs:
            citations.append({
                "id": f"D{drug.id}",
                "source_type": "medication",
                "title": drug.name,
                "observed_at": drug.time_hm,
                "summary": f"{drug.time_hm} {drug.action} {drug.name} {drug.dose_after or ''}".strip(),
                "raw_value": {"name": drug.name, "value": drug.dose_after or drug.action, "unit": ""},
            })
        for alert in ctx.alerts:
            citations.append({
                "id": f"A{alert.id}",
                "source_type": "alert",
                "title": _alert_label(alert.type),
                "observed_at": ctx.window_end,
                "summary": f"{_alert_label(alert.type)} {alert.severity} x{alert.count}",
                "raw_value": {"name": alert.type, "value": alert.count, "unit": ""},
            })
        return citations

    def _build_skeleton(self, ctx: ProgressNoteContext, citations: list[dict]) -> dict:
        generated_at = _now_iso()
        banner = {
            "bed_no": _safe_text(ctx.basics.bed),
            "age": str(ctx.basics.age or "未提供"),
            "sex": _safe_text(ctx.basics.sex),
            "icu_day": str(ctx.basics.day or "未提供"),
            "primary_diagnosis": _safe_text(ctx.basics.diagnosis),
            "current_diagnosis": _safe_text(ctx.basics.diagnosis),
            "allergy_status": "未提供",
            "isolation_status": "未提供",
            "code_status": "未提供",
        }
        draft = {
            "schema_version": "icu_rounding_workbench.v1",
            "content_type": "rounding_workbench",
            "generated_at": generated_at,
            "context_window": {"start": ctx.window_start, "end": ctx.window_end},
            "patient_banner": banner,
            "organ_support": self._build_organ_support(ctx),
            "timeline": self._build_timeline(ctx),
            "system_ap": self._build_system_cards(ctx),
            "daily_goals": self._build_daily_goals(ctx),
            "risk_tasks": self._build_risk_tasks(ctx),
            "note_preview": {
                "style": "APSO",
                "generated_text": "",
                "final_text_override": None,
                "is_overridden": False,
                "generated_from_hash": "",
            },
            "quality_checks": {
                "critical_missing_data": [],
                "stale_data": [],
                "contradictions": [],
                "warnings": [],
            },
            "raw_ai_tags": [str(a.type) for a in ctx.alerts],
        }
        draft["note_preview"] = render_note_preview(draft)
        return draft

    def _build_organ_support(self, ctx: ProgressNoteContext) -> list[dict]:
        vent_missing = []
        if not ctx.vent:
            vent_missing = ["当前呼吸支持方式", "吸氧浓度", "氧合指数"]
            vent_summary = "未提供"
            vent_refs: list[str] = []
            vent_status = "unknown"
        else:
            if ctx.vent.fio2 in (0, None):
                vent_missing.append("吸氧浓度")
            if ctx.vent.peep in (0, None) and not _is_noninvasive_or_oxygen_mode(ctx.vent.mode):
                vent_missing.append("呼气末正压")
            if ctx.vent.pf_ratio is None:
                vent_missing.append("氧合指数")
            peep_text = f" / 呼气末正压 {ctx.vent.peep}" if ctx.vent.peep not in (0, None) else ""
            vent_summary = (
                f"{ctx.vent.mode} / 吸氧浓度 {ctx.vent.fio2}{peep_text} / "
                f"氧合指数 {ctx.vent.pf_ratio if ctx.vent.pf_ratio is not None else '未提供'}"
            )
            vent_refs = ["VT0"]
            vent_status = "active"
        sedation_refs = ["N1"] if ctx.neuro else (["AS1"] if ctx.scores else [])
        sedation_missing = []
        if not ctx.neuro or ctx.neuro.rass is None:
            sedation_missing.append("镇静评分")
        if not ctx.neuro or not ctx.neuro.cam_icu:
            sedation_missing.append("谵妄评估")
        sedation_summary = "未提供镇静/谵妄评估"
        if ctx.neuro:
            parts = []
            if ctx.neuro.rass is not None:
                parts.append(f"RASS {ctx.neuro.rass:g}")
            if ctx.neuro.cam_icu:
                parts.append(f"CAM-ICU {ctx.neuro.cam_icu}")
            sedation_summary = "，".join(parts) or sedation_summary
        infection_refs = [f"A{a.id}" for a in ctx.alerts if any(k in str(a.type).lower() for k in ["sepsis", "infection", "hai", "antibiotic"])]
        antimicrobial_refs = [f"D{d.id}" for d in ctx.drugs if _is_antimicrobial_name(d.name)]
        infection_lab_refs = ["IE1"] if ctx.infection_evidence else []
        has_inflammatory_markers = bool(ctx.infection_evidence and ctx.infection_evidence.inflammatory_markers)
        has_cultures = bool(ctx.infection_evidence and ctx.infection_evidence.culture_results)
        infection_missing = []
        if not has_inflammatory_markers:
            infection_missing.append("WBC/PCT/CRP")
        if not has_cultures:
            infection_missing.append("培养结果")
        if infection_refs or antimicrobial_refs:
            infection_missing.append("抗菌药疗程")
        infection_summary = "有感染相关预警" if infection_refs else ("有当前抗菌药记录" if antimicrobial_refs else "未检索到当前感染预警")
        if ctx.infection_evidence:
            marker_text = "；".join(f"{item.name} {item.value}{item.unit}" for item in ctx.infection_evidence.inflammatory_markers[:3])
            culture_text = "；".join(f"{item.name} {item.value}" for item in ctx.infection_evidence.culture_results[:3])
            details = [text for text in [marker_text, culture_text] if text]
            if details:
                infection_summary = "；".join(details)
        line_refs = ["LD1"] if ctx.line_devices else []
        active_tubes = ctx.line_devices.active_tubes if ctx.line_devices else []
        line_summary = "未检索到当前活动管路"
        line_missing = []
        if active_tubes:
            grouped: dict[str, list[str]] = {}
            for tube in active_tubes:
                grouped.setdefault(tube.category, []).append(_tube_summary(tube))
            parts = [f"{_line_category_label(category)}：{'；'.join(items[:3])}" for category, items in grouped.items()]
            if ctx.line_devices and ctx.line_devices.drainage_24h_ml is not None:
                parts.append(f"24h引流量 {ctx.line_devices.drainage_24h_ml}mL")
            line_summary = "；".join(parts)
            if any(t.category == "drain" for t in active_tubes) and ctx.line_devices and ctx.line_devices.drainage_24h_ml is None:
                line_missing.append("引流量")
        elif ctx.line_devices and ctx.line_devices.drainage_24h_ml is not None:
            line_summary = f"床旁引流量记录：24h {ctx.line_devices.drainage_24h_ml}mL"
        return [
            {"key": "vent", "label": "呼吸机", "status": vent_status, "summary": vent_summary, "missing_data": vent_missing, "evidence_refs": vent_refs},
            {"key": "pressor", "label": "循环支持", "status": "unknown", "summary": "升压药连续剂量待查房确认", "missing_data": [], "evidence_refs": []},
            {"key": "crrt", "label": "肾脏替代", "status": "active" if ctx.fluid_balance else "unknown", "summary": "液体平衡和肾脏替代状态待查房确认", "missing_data": [], "evidence_refs": ["IO1"] if ctx.fluid_balance else []},
            {"key": "sedation", "label": "镇静/神经", "status": "active" if ctx.neuro else "unknown", "summary": sedation_summary, "missing_data": sedation_missing, "evidence_refs": sedation_refs},
            {"key": "lines", "label": "管路", "status": "active" if ctx.line_devices else "unknown", "summary": line_summary, "missing_data": line_missing, "evidence_refs": line_refs},
            {"key": "infection", "label": "感染", "status": "active" if infection_refs or antimicrobial_refs or ctx.infection_evidence else "unknown", "summary": infection_summary, "missing_data": infection_missing, "evidence_refs": infection_refs + antimicrobial_refs + infection_lab_refs},
        ]

    def _build_timeline(self, ctx: ProgressNoteContext) -> list[dict]:
        events: list[dict] = []
        for idx, event in enumerate(ctx.v.events[:6], start=1):
            events.append({
                "id": f"tl_vital_{idx}",
                "occurred_at": event.time_hm,
                "category": "vital",
                "title": event.type,
                "description": f"{event.type}: {event.value}",
                "severity": "high",
                "evidence_refs": ["V1"],
            })
        for lab in ctx.labs[:8]:
            if _lab_is_abnormal(lab.flag):
                events.append({
                    "id": f"tl_lab_{lab.id}",
                    "occurred_at": ctx.window_end,
                    "category": "lab",
                    "title": f"{lab.name}异常/变化",
                    "description": f"{lab.name} {lab.prev}->{lab.curr}{lab.unit} {lab.flag}",
                    "severity": "medium",
                    "evidence_refs": [f"L{lab.id}"],
                })
        for drug in ctx.drugs[:6]:
            events.append({
                "id": f"tl_drug_{drug.id}",
                "occurred_at": drug.time_hm,
                "category": "medication",
                "title": drug.name,
                "description": f"{drug.action} {drug.name} {drug.dose_after or ''}".strip(),
                "severity": "low",
                "evidence_refs": [f"D{drug.id}"],
            })
        for alert in ctx.alerts[:8]:
            events.append({
                "id": f"tl_alert_{alert.id}",
                "occurred_at": ctx.window_end,
                "category": "alert",
                "title": _alert_label(alert.type),
                "description": f"{_alert_label(alert.type)}，触发 {alert.count} 次，状态：{'持续' if alert.active else '已缓解'}",
                "severity": _priority_from_severity(alert.severity),
                "evidence_refs": [f"A{alert.id}"],
            })
        if ctx.vent:
            events.append({
                "id": "tl_vent_current",
                "occurred_at": ctx.window_end,
                "category": "vent",
                "title": "当前呼吸机参数",
                "description": (
                    f"{ctx.vent.mode}，吸氧浓度 {ctx.vent.fio2}"
                    f"{'，呼气末正压 ' + str(ctx.vent.peep) if ctx.vent.peep not in (0, None) else ''}，"
                    f"氧合指数 {ctx.vent.pf_ratio if ctx.vent.pf_ratio is not None else '未提供'}"
                ),
                "severity": "medium",
                "evidence_refs": ["VT0"],
            })
        return events[:20]

    def _build_system_cards(self, ctx: ProgressNoteContext) -> list[dict]:
        cards: list[dict] = []
        alert_refs = [f"A{a.id}" for a in ctx.alerts]
        abnormal_lab_refs = [f"L{lab.id}" for lab in ctx.labs[:8] if _lab_is_abnormal(lab.flag)]
        io_refs = ["IO1"] if ctx.fluid_balance else []
        urine_missing = not (ctx.fluid_balance and ctx.fluid_balance.urine_24h_ml is not None)
        io_missing = not (
            ctx.fluid_balance
            and (ctx.fluid_balance.intake_24h_ml is not None or ctx.fluid_balance.output_24h_ml is not None)
        )
        net_missing = not (ctx.fluid_balance and ctx.fluid_balance.net_24h_ml is not None)
        urine_text = f"24h尿量 {ctx.fluid_balance.urine_24h_ml}mL" if ctx.fluid_balance and ctx.fluid_balance.urine_24h_ml is not None else "24h尿量未提供"
        io_text = "床旁出入量未提供"
        neuro_refs = ["N1"] if ctx.neuro else (["AS1"] if ctx.scores else [])
        rass_missing = not (ctx.neuro and ctx.neuro.rass is not None)
        cam_missing = not (ctx.neuro and ctx.neuro.cam_icu)
        rass_text = f"RASS {ctx.neuro.rass:g}" if ctx.neuro and ctx.neuro.rass is not None else "RASS未提供"
        cam_text = f"CAM-ICU {ctx.neuro.cam_icu}" if ctx.neuro and ctx.neuro.cam_icu else "CAM-ICU未提供"
        antimicrobial_refs = [f"D{d.id}" for d in ctx.drugs if _is_antimicrobial_name(d.name)]
        infection_lab_refs = ["IE1"] if ctx.infection_evidence else []
        has_inflammatory_markers = bool(ctx.infection_evidence and ctx.infection_evidence.inflammatory_markers)
        has_cultures = bool(ctx.infection_evidence and ctx.infection_evidence.culture_results)
        infection_marker_text = "未检索到近72小时炎症指标"
        infection_culture_text = "未检索到近72小时培养/病原学结果"
        if has_inflammatory_markers:
            infection_marker_text = "；".join(
                f"{item.name} {item.value}{item.unit}{(' ' + item.flag) if item.flag else ''}"
                for item in ctx.infection_evidence.inflammatory_markers[:5]
            )
        if has_cultures:
            infection_culture_text = "；".join(
                f"{item.name} {item.value}{(' ' + item.flag) if item.flag else ''}"
                for item in ctx.infection_evidence.culture_results[:5]
            )
        active_tubes = ctx.line_devices.active_tubes if ctx.line_devices else []
        line_refs = ["LD1"] if ctx.line_devices else []
        line_missing = []
        line_text = "未检索到当前活动管路。"
        if active_tubes:
            line_text = "；".join(_tube_summary(tube) for tube in active_tubes[:8]) + "。"
            if ctx.line_devices and ctx.line_devices.drainage_24h_ml is not None:
                line_text = line_text.rstrip("。") + f"；24h引流量 {ctx.line_devices.drainage_24h_ml}mL。"
            if any(tube.category == "drain" for tube in active_tubes) and ctx.line_devices and ctx.line_devices.drainage_24h_ml is None:
                line_missing.append("引流量")
        elif ctx.line_devices and ctx.line_devices.drainage_24h_ml is not None:
            line_text = f"床旁记录24h引流量 {ctx.line_devices.drainage_24h_ml}mL。"
        if ctx.fluid_balance:
            io_parts = []
            if ctx.fluid_balance.intake_24h_ml is not None:
                io_parts.append(f"24h入量 {ctx.fluid_balance.intake_24h_ml}mL")
            if ctx.fluid_balance.output_24h_ml is not None:
                io_parts.append(f"24h出量 {ctx.fluid_balance.output_24h_ml}mL")
            if ctx.fluid_balance.net_24h_ml is not None:
                io_parts.append(f"净平衡 {ctx.fluid_balance.net_24h_ml}mL")
            io_text = "，".join(io_parts) if io_parts else io_text
        for system, title in SYSTEM_ORDER:
            card = {
                "id": f"system_{system}",
                "system": system,
                "title": title,
                "priority": "medium",
                "status": [],
                "trend": [],
                "assessment": [],
                "plan_items": [],
                "missing_data": [],
                "evidence_refs": [],
                "review_status": "unreviewed",
            }
            if system == "resp":
                refs = ["V1"] + (["VT0"] if ctx.vent else [])
                card["priority"] = "high" if ctx.v.spo2.min is not None and ctx.v.spo2.min < 90 else "medium"
                card["status"].append(self._stmt("resp_status_vitals", "fact", f"SpO2 {_fmt_range(ctx.v.spo2.min, ctx.v.spo2.max, '%')}，RR {_fmt_range(ctx.v.rr.min, ctx.v.rr.max)}。", refs[:1]))
                if ctx.vent:
                    peep_part = f"，呼气末正压 {ctx.vent.peep}" if ctx.vent.peep not in (0, None) else ""
                    card["status"].append(self._stmt("resp_status_vent", "fact", f"呼吸支持：{ctx.vent.mode}，吸氧浓度 {ctx.vent.fio2}{peep_part}，氧合指数 {ctx.vent.pf_ratio if ctx.vent.pf_ratio is not None else '未提供'}。", ["VT0"]))
                missing = ["胸部影像"]
                if not ctx.vent:
                    missing.extend(["吸氧浓度", "氧合指数"])
                elif ctx.vent.fio2 in (0, None):
                    missing.append("吸氧浓度")
                if ctx.vent and ctx.vent.peep in (0, None) and not _is_noninvasive_or_oxygen_mode(ctx.vent.mode):
                    missing.append("呼气末正压")
                if ctx.vent and ctx.vent.pf_ratio is None:
                    missing.append("氧合指数")
                card["trend"].append(self._stmt("resp_trend_oxygenation", "inference", f"氧合趋势：SpO2 {_trend_text(ctx.v.spo2.trend)}，需结合呼吸机参数和血气复核。", refs, missing))
                card["assessment"].append(self._stmt("resp_assessment_ards", "inference", "存在低氧/ARDS风险时需结合吸氧浓度、呼气末正压、影像和容量状态复核，证据不足时不直接确诊。", refs, missing, "medium", True))
                card["plan_items"].append(self._stmt("resp_plan_pf", "recommendation", "复核当前呼吸支持参数并确认氧合指数。", refs, missing, review_required=True))
                card["missing_data"] = missing
                card["evidence_refs"] = refs
            elif system == "cv":
                refs = ["V1"] + io_refs
                card["priority"] = "high" if ctx.v.map.min is not None and ctx.v.map.min < 65 else "medium"
                card["status"].append(self._stmt("cv_status_map", "fact", f"MAP {_fmt_range(ctx.v.map.min, ctx.v.map.max)}，HR {_fmt_range(ctx.v.hr.min, ctx.v.hr.max)}。", refs))
                if ctx.fluid_balance and ctx.fluid_balance.urine_24h_ml is not None:
                    card["status"].append(self._stmt("cv_status_urine", "fact", urine_text + "。", io_refs))
                card["trend"].append(self._stmt("cv_trend", "inference", f"循环趋势：MAP {_trend_text(ctx.v.map.trend)}，HR {_trend_text(ctx.v.hr.trend)}。", refs))
                cv_missing = ["乳酸", "升压药剂量"] + (["尿量"] if urine_missing else [])
                card["assessment"].append(self._stmt("cv_assessment", "inference", "需结合乳酸、尿量、升压药剂量和末梢灌注评估循环稳定性。", refs, cv_missing, "medium", True))
                card["plan_items"].append(self._stmt("cv_plan", "recommendation", "明确 MAP 目标并记录升压药名称、剂量和调整计划。", refs, ["MAP目标", "升压药剂量"], review_required=True))
                card["missing_data"] = cv_missing
                card["evidence_refs"] = refs
            elif system == "neuro":
                refs = neuro_refs
                if ctx.scores:
                    card["status"].append(self._stmt("neuro_status_scores", "fact", f"GCS {ctx.scores.gcs}，SOFA {ctx.scores.sofa}，APACHE {ctx.scores.apache}。", refs))
                if ctx.neuro:
                    card["status"].append(self._stmt("neuro_status_sedation", "fact", f"{rass_text}，{cam_text}。", refs))
                else:
                    card["status"].append(self._stmt("neuro_status_missing", "inference", "神经意识和镇静资料未完整提供。", [], ["GCS", "镇静评分", "谵妄评估", "瞳孔"], "low", True))
                neuro_missing = []
                if rass_missing:
                    neuro_missing.append("镇静评分")
                if cam_missing:
                    neuro_missing.append("谵妄评估")
                neuro_missing.append("瞳孔")
                card["assessment"].append(self._stmt("neuro_assessment", "inference", "需床旁确认意识、瞳孔、镇静深度和谵妄状态。", refs, neuro_missing, "medium", True))
                card["plan_items"].append(self._stmt("neuro_plan", "recommendation", "补录镇静评分、谵妄评估、瞳孔和镇痛镇静目标。", refs, neuro_missing, review_required=True))
                card["missing_data"] = neuro_missing
                card["evidence_refs"] = refs
            elif system == "id":
                infection_alert_refs = [f"A{a.id}" for a in ctx.alerts if any(k in str(a.type).lower() for k in ["sepsis", "infection", "hai", "antibiotic"])]
                refs = infection_alert_refs + antimicrobial_refs + infection_lab_refs
                card["priority"] = "high" if refs else "medium"
                id_missing = []
                if not has_inflammatory_markers:
                    id_missing.append("WBC/PCT/CRP")
                if not has_cultures:
                    id_missing.append("培养结果")
                if infection_alert_refs or antimicrobial_refs:
                    id_missing.append("抗菌药疗程")
                status_text = f"炎症指标：{infection_marker_text}。培养/病原：{infection_culture_text}。"
                if infection_alert_refs:
                    status_text += " 同时存在感染相关预警。"
                elif antimicrobial_refs:
                    status_text += " 同时存在当前抗菌药记录。"
                card["assessment"].append(self._stmt("id_assessment", "inference", "感染控制需结合体温、炎症指标、培养结果和抗菌药疗程判断。", refs, id_missing, "medium", True))
                card["status"].append(self._stmt("id_status", "fact" if ctx.infection_evidence else "inference", status_text, refs, id_missing))
                card["plan_items"].append(self._stmt("id_plan", "recommendation", "如存在当前抗菌药或感染线索，确认疗程第几天、是否需降阶梯或复查培养。", refs, id_missing, review_required=True))
                card["missing_data"] = id_missing
                card["evidence_refs"] = refs
            elif system == "heme":
                refs = [f"A{a.id}" for a in ctx.alerts if any(k in str(a.type).lower() for k in ["heme", "vte", "dic", "bleed", "coag", "fibrin", "throm"])] + abnormal_lab_refs[:3]
                card["priority"] = "high" if refs else "medium"
                card["status"].append(self._stmt("heme_status", "fact" if refs else "inference", "有凝血/血栓/出血相关线索需复核。" if refs else "未提供完整凝血与血栓风险资料。", refs, [] if refs else ["血小板", "PT/APTT", "D-dimer", "FIB"]))
                card["assessment"].append(self._stmt("heme_assessment", "inference", "凝血异常、出血和VTE风险需结合活动性出血、抗凝/溶栓用药和凝血指标复核。", refs, ["活动性出血", "抗凝/溶栓用药", "PT/APTT", "D-dimer"], "medium", True))
                card["plan_items"].append(self._stmt("heme_plan", "recommendation", "记录 VTE 预防策略，必要时复查凝血功能或 TEG/ROTEM。", refs, ["VTE预防策略"], review_required=True))
                card["missing_data"] = ["活动性出血", "PT/APTT", "D-dimer", "VTE预防策略"]
                card["evidence_refs"] = refs
            elif system == "renal_fluid":
                refs = abnormal_lab_refs[:3] + io_refs
                renal_missing = ["肌酐", "CRRT状态"]
                if urine_missing:
                    renal_missing.append("尿量")
                if io_missing:
                    renal_missing.append("24h出入量")
                if net_missing:
                    renal_missing.append("24h净平衡")
                card["status"].append(self._stmt("renal_status", "fact" if refs else "inference", f"{io_text}；{urine_text}。" if ctx.fluid_balance else "未提供完整肾功能、尿量和出入量。", refs, [] if ctx.fluid_balance else ["肌酐", "尿量", "24h出入量"]))
                card["assessment"].append(self._stmt("renal_assessment", "inference", "需结合肌酐、尿量、CRRT状态和24h净平衡评估肾功能/容量。", refs, renal_missing, "medium", True))
                plan_missing = ["24h液体目标"] + (["尿量"] if urine_missing else [])
                card["plan_items"].append(self._stmt("renal_plan", "recommendation", "明确24h液体目标并复核尿量、净平衡和CRRT状态。", refs, plan_missing, review_required=True))
                card["missing_data"] = renal_missing
                card["evidence_refs"] = refs
            elif system == "gi_nutrition":
                card["status"].append(self._stmt("gi_status", "inference", "营养、胃肠耐受和应激溃疡/VAP预防资料未完整提供。", [], ["热卡目标", "蛋白目标", "胃肠耐受"]))
                card["assessment"].append(self._stmt("gi_assessment", "inference", "需确认营养达标率、胃肠耐受和误吸风险。", [], ["热卡目标", "蛋白目标"], "low", True))
                card["plan_items"].append(self._stmt("gi_plan", "recommendation", "补录今日热卡、蛋白目标和肠内营养耐受情况。", [], ["热卡目标", "蛋白目标"], review_required=True))
                card["missing_data"] = ["热卡目标", "蛋白目标", "胃肠耐受"]
            elif system == "endo":
                card["status"].append(self._stmt("endo_status", "inference", "血糖和内分泌治疗资料未完整提供。", [], ["血糖范围", "胰岛素方案"]))
                card["assessment"].append(self._stmt("endo_assessment", "inference", "需结合血糖趋势和胰岛素/激素用药评估代谢控制。", [], ["血糖范围", "胰岛素方案"], "low", True))
                card["plan_items"].append(self._stmt("endo_plan", "recommendation", "记录血糖目标和胰岛素调整策略。", [], ["血糖目标"], review_required=True))
                card["missing_data"] = ["血糖范围", "胰岛素方案"]
            elif system == "lines_devices":
                card["status"].append(self._stmt("lines_status", "fact" if ctx.line_devices else "inference", line_text, line_refs, line_missing))
                card["assessment"].append(self._stmt("lines_assessment", "inference", "需每日评估当前管路和装置是否仍有适应证，关注固定、通畅、穿刺点和感染风险。", line_refs, line_missing, "medium", True))
                card["plan_items"].append(self._stmt("lines_plan", "recommendation", "根据当前管路留置天数和适应证评估可拔除管路。", line_refs, line_missing, review_required=True))
                card["missing_data"] = line_missing
                card["evidence_refs"] = line_refs
            elif system == "goals":
                refs = ["V1"] + alert_refs[:3]
                card["status"].append(self._stmt("goals_status", "inference", "今日目标需围绕氧合、循环、液体、感染、镇静、营养、管路和夜间预案确认。", refs, ["MAP目标", "氧合目标", "液体目标"], "medium", True))
                card["plan_items"].append(self._stmt("goals_plan", "recommendation", "完成今日目标单并明确夜间恶化预案。", refs, ["夜间预案"], review_required=True))
                card["missing_data"] = ["MAP目标", "氧合目标", "液体目标", "夜间预案"]
                card["evidence_refs"] = refs
            cards.append(card)
        return cards

    def _stmt(
        self,
        stmt_id: str,
        kind: str,
        text: str,
        refs: list[str] | None = None,
        missing: list[str] | None = None,
        confidence: str | None = None,
        review_required: bool = False,
    ) -> dict:
        stmt = {
            "id": stmt_id,
            "kind": kind,
            "text": text,
            "evidence_refs": refs or [],
            "missing_data": missing or [],
            "review_required": review_required,
        }
        if confidence:
            stmt["confidence"] = confidence
        return stmt

    def _build_daily_goals(self, ctx: ProgressNoteContext) -> list[dict]:
        goals: list[dict] = []
        antimicrobial_refs = [f"D{d.id}" for d in ctx.drugs if _is_antimicrobial_name(d.name)]
        for key, label, target in GOAL_DEFS:
            missing: list[str] = []
            refs: list[str] = []
            if key == "map":
                refs = ["V1"]
                target = "MAP 目标待医生确认，当前 MAP " + _fmt_range(ctx.v.map.min, ctx.v.map.max)
                missing = ["MAP目标"]
            elif key == "oxygenation":
                refs = ["V1"] + (["VT0"] if ctx.vent else [])
                target = "氧合目标待确认，当前 SpO2 " + _fmt_range(ctx.v.spo2.min, ctx.v.spo2.max, "%")
                missing = []
                if not ctx.vent:
                    missing = ["吸氧浓度", "氧合指数"]
                elif ctx.vent.fio2 in (0, None):
                    missing.append("吸氧浓度")
                if ctx.vent and ctx.vent.peep in (0, None) and not _is_noninvasive_or_oxygen_mode(ctx.vent.mode):
                    missing.append("呼气末正压")
                if ctx.vent and ctx.vent.pf_ratio is None:
                    missing.append("氧合指数")
            elif key == "rass":
                refs = ["N1"] if ctx.neuro else []
                if ctx.neuro and ctx.neuro.rass is not None:
                    target = f"镇静目标待确认，当前 RASS {ctx.neuro.rass:g}"
                    missing = []
                else:
                    missing = ["镇静评分"]
            elif key == "fluid_balance":
                refs = ["IO1"] if ctx.fluid_balance else []
                parts = []
                if ctx.fluid_balance:
                    if ctx.fluid_balance.intake_24h_ml is not None:
                        parts.append(f"入量 {ctx.fluid_balance.intake_24h_ml}mL")
                    if ctx.fluid_balance.output_24h_ml is not None:
                        parts.append(f"出量 {ctx.fluid_balance.output_24h_ml}mL")
                    if ctx.fluid_balance.net_24h_ml is not None:
                        parts.append(f"净平衡 {ctx.fluid_balance.net_24h_ml}mL")
                    if ctx.fluid_balance.urine_24h_ml is not None:
                        parts.append(f"尿量 {ctx.fluid_balance.urine_24h_ml}mL")
                target = "液体目标待医生确认" + (f"，当前24h{'，'.join(parts)}" if parts else "")
                missing = ["净平衡目标"]
                if not ctx.fluid_balance or (ctx.fluid_balance.intake_24h_ml is None and ctx.fluid_balance.output_24h_ml is None):
                    missing.append("24h出入量")
                if not ctx.fluid_balance or ctx.fluid_balance.urine_24h_ml is None:
                    missing.append("尿量")
            elif key == "antibiotics":
                refs = antimicrobial_refs
                missing = ["培养结果"]
                if antimicrobial_refs:
                    missing.append("抗菌药疗程")
            goals.append({
                "id": f"goal_{key}",
                "category": key,
                "label": label,
                "target": target,
                "status": "open",
                "evidence_refs": refs,
                "missing_data": missing,
            })
        return goals

    def _build_risk_tasks(self, ctx: ProgressNoteContext) -> list[dict]:
        tasks = []
        for alert in ctx.alerts[:8]:
            ref = f"A{alert.id}"
            label = _alert_label(alert.type)
            category = self._category_from_alert(alert.type)
            tasks.append({
                "id": f"risk_{category}_{alert.id}",
                "priority": _priority_from_severity(alert.severity),
                "category": category,
                "title": f"{label}需复核",
                "why_triggered": [
                    self._stmt(
                        f"risk_{alert.id}_why",
                        "inference",
                        f"系统触发{label}，近窗内 {alert.count} 次，状态：{'持续' if alert.active else '已缓解'}。",
                        [ref],
                        [],
                        "medium",
                        True,
                    )
                ],
                "confirm_items": self._confirm_items_for_category(category),
                "suggested_actions": [
                    {"label": "加入今日计划", "action_type": "add_to_plan"},
                    {"label": "创建医嘱草稿", "action_type": "create_order_draft_placeholder"},
                    {"label": "稍后提醒", "action_type": "snooze"},
                    {"label": "忽略", "action_type": "dismiss"},
                ],
                "status": "open",
            })
        return tasks

    def _category_from_alert(self, alert_type: str) -> str:
        text = str(alert_type or "").lower()
        if any(k in text for k in ["ards", "oxygen", "hypox", "prone", "vent"]):
            return "resp"
        if any(k in text for k in ["aki", "renal", "crrt", "fluid"]):
            return "renal_fluid"
        if any(k in text for k in ["sepsis", "infection", "antibiotic", "hai"]):
            return "id"
        if any(k in text for k in ["vte", "dic", "bleed", "coag", "fibrin", "throm"]):
            return "heme"
        if any(k in text for k in ["shock", "hypotension", "cardiac", "pressor"]):
            return "cv"
        return "general"

    def _confirm_items_for_category(self, category: str) -> list[str]:
        mapping = {
            "resp": ["当前吸氧浓度、呼气末正压、氧合指数是否已记录", "是否需要复查血气", "是否满足俯卧位评估条件", "是否存在禁忌证"],
            "renal_fluid": ["24h尿量是否下降", "净平衡是否超目标", "是否需要CRRT或调整超滤", "肾毒性药物是否复核"],
            "id": ["是否有培养结果", "抗菌药疗程第几天", "是否需要降阶梯或加覆盖", "感染灶控制是否完成"],
            "heme": ["是否存在活动性出血", "是否近期使用抗凝/溶栓药物", "是否需要复查D-dimer、PT/APTT、FIB或TEG/ROTEM", "是否已有VTE预防策略"],
            "cv": ["MAP目标是否明确", "升压药剂量是否变化", "乳酸是否清除", "尿量/末梢灌注是否支持低灌注"],
        }
        return mapping.get(category, ["触发原因是否与床旁情况一致", "是否需要加入今日计划", "是否需要创建医嘱草稿"])

    def _merge_workbench_patch(self, base: dict, patch: dict) -> dict:
        draft = copy.deepcopy(base)
        allowed = {"system_ap", "daily_goals", "risk_tasks", "raw_ai_tags"}
        for key in allowed:
            value = patch.get(key)
            if isinstance(value, list):
                draft[key] = value
        return draft

    def _validate_and_repair_workbench(self, draft: dict, citations: list[dict]) -> dict:
        valid_refs = {c["id"] for c in citations}
        existing_systems = {card.get("system") for card in draft.get("system_ap") or []}
        base_cards = {card["system"]: card for card in self._build_system_cards_from_draft(draft)}
        for system, _ in SYSTEM_ORDER:
            if system not in existing_systems and system in base_cards:
                draft.setdefault("system_ap", []).append(base_cards[system])

        for card in draft.get("system_ap") or []:
            card["evidence_refs"] = [r for r in card.get("evidence_refs", []) if r in valid_refs]
            for key in ("status", "trend", "assessment", "plan_items"):
                repaired = []
                for stmt in card.get(key) or []:
                    stmt.setdefault("id", f"{card.get('system', 'system')}_{key}_{len(repaired) + 1}")
                    stmt.setdefault("kind", "inference")
                    stmt.setdefault("text", "")
                    stmt["evidence_refs"] = [r for r in stmt.get("evidence_refs", []) if r in valid_refs]
                    stmt.setdefault("missing_data", [])
                    stmt.setdefault("review_required", False)
                    if stmt["kind"] == "fact" and not stmt["evidence_refs"]:
                        stmt["kind"] = "inference"
                        stmt["review_required"] = True
                        stmt["missing_data"] = sorted(set(stmt["missing_data"] + ["事实依据"]))
                    if stmt["kind"] == "recommendation" and not stmt["evidence_refs"] and not stmt["missing_data"]:
                        stmt["review_required"] = True
                        stmt["missing_data"] = ["执行依据"]
                    if stmt["text"]:
                        repaired.append(stmt)
                card[key] = repaired
        for goal in draft.get("daily_goals") or []:
            goal["evidence_refs"] = [r for r in goal.get("evidence_refs", []) if r in valid_refs]
            goal.setdefault("missing_data", [])
        for task in draft.get("risk_tasks") or []:
            for stmt in task.get("why_triggered") or []:
                stmt["evidence_refs"] = [r for r in stmt.get("evidence_refs", []) if r in valid_refs]
                stmt.setdefault("missing_data", [])
                stmt.setdefault("review_required", True)
        return draft

    def _suppress_resolved_missing_data(self, draft: dict, ctx: ProgressNoteContext) -> dict:
        """Keep missing chips evidence-driven instead of template-driven."""
        resolved: set[str] = set()
        suppress: set[str] = {
            "当前呼吸机模式",
            "当前呼吸支持方式",
            "当前呼吸模式",
            "胸部影像",
            "乳酸",
            "升压药名称及剂量",
            "升压药剂量",
            "MAP目标",
            "氧合目标",
            "液体目标",
            "24h液体目标",
            "夜间预案",
            "GCS",
            "镇静评分",
            "谵妄评估",
            "镇痛镇静用药",
            "瞳孔",
            "活动性出血",
            "抗凝/溶栓用药",
            "PT/APTT",
            "D-dimer",
            "VTE预防策略",
            "热卡目标",
            "蛋白目标",
            "胃肠耐受",
            "血糖范围",
            "胰岛素方案",
            "血糖目标",
            "CRRT状态",
            "CVC天数",
            "尿管天数",
            "24h尿量",
            "尿量",
            "24h出入量",
            "24h液体平衡",
            "抗菌药疗程",
            "肌酐",
            "培养结果",
            "管路留置天数",
            "床旁查体",
            "事实依据",
            "执行依据",
        }

        if ctx.vent:
            resolved.update({"当前呼吸支持方式", "当前呼吸机模式"})
            if ctx.vent.fio2 not in (0, None):
                resolved.update({"FiO2", "吸氧浓度"})
            if ctx.vent.peep not in (0, None) or _is_noninvasive_or_oxygen_mode(ctx.vent.mode):
                resolved.update({"PEEP", "呼气末正压"})
            if ctx.vent.pf_ratio is not None:
                resolved.update({"P/F ratio", "氧合指数"})
        if ctx.fluid_balance:
            if ctx.fluid_balance.urine_24h_ml is not None:
                resolved.update({"尿量", "24h尿量"})
            if ctx.fluid_balance.intake_24h_ml is not None:
                resolved.update({"24h入量", "入量"})
            if ctx.fluid_balance.output_24h_ml is not None:
                resolved.update({"24h出量", "出量"})
            if ctx.fluid_balance.intake_24h_ml is not None or ctx.fluid_balance.output_24h_ml is not None:
                resolved.update({"24h出入量", "24h液体平衡"})
            if ctx.fluid_balance.net_24h_ml is not None:
                resolved.update({"24h净平衡", "净平衡"})
        if ctx.scores:
            resolved.update({"GCS", "SOFA", "APACHE"})
        if ctx.neuro:
            if ctx.neuro.rass is not None:
                resolved.update({"RASS", "镇静评分"})
            if ctx.neuro.cam_icu:
                resolved.update({"CAM-ICU", "谵妄评估"})
        if ctx.line_devices and ctx.line_devices.active_tubes:
            resolved.update({"管路留置天数", "CVC天数", "尿管天数", "引流管"})
            categories = {tube.category for tube in ctx.line_devices.active_tubes}
            if "vascular" in categories:
                resolved.update({"中心静脉导管"})
            if "urinary" in categories:
                resolved.update({"尿管"})
            if "drain" in categories:
                resolved.update({"引流管"})
            if ctx.line_devices.drainage_24h_ml is not None:
                resolved.update({"引流量"})
        if ctx.infection_evidence and ctx.infection_evidence.inflammatory_markers:
            resolved.update({"WBC/PCT/CRP", "炎症指标", "体温峰值"})
        if ctx.infection_evidence and ctx.infection_evidence.culture_results:
            resolved.update({"培养结果"})

        for item in draft.get("organ_support") or []:
            key = str(item.get("key") or "")
            summary = str(item.get("summary") or "")
            refs = item.get("evidence_refs") or []
            if key == "vent" and (refs or any(token in summary for token in ["吸氧浓度", "氧合指数", "FiO2", "HF", "高流量", "呼吸支持"])):
                resolved.update({"FiO2", "吸氧浓度", "PEEP", "呼气末正压", "P/F ratio", "氧合指数", "当前呼吸机模式", "当前呼吸支持方式"})
            if key == "sedation" and (refs or "RASS" in summary or "CAM-ICU" in summary):
                resolved.update({"RASS", "镇静评分", "CAM-ICU", "谵妄评估"})
            if key == "lines" and (refs or summary):
                resolved.update({"管路留置天数", "CVC天数", "尿管天数", "引流管"})
                if "引流" in summary:
                    resolved.update({"引流量"})
            if key == "infection" and (refs or summary):
                resolved.update({"WBC/PCT/CRP", "炎症指标", "培养结果", "抗菌药疗程", "抗菌药疗程天数"})

        for card in draft.get("system_ap") or []:
            system = str(card.get("system") or "").lower()
            refs = card.get("evidence_refs") or []
            texts: list[str] = []
            for group in ("status", "trend", "assessment", "plan_items"):
                texts.extend(str(stmt.get("text") or "") for stmt in card.get(group) or [])
            joined_text = " ".join(texts)
            if system == "resp" and (refs or any(token in joined_text for token in ["吸氧浓度", "氧合指数", "FiO2", "HF", "高流量", "呼吸支持"])):
                resolved.update({"FiO2", "吸氧浓度", "PEEP", "呼气末正压", "P/F ratio", "氧合指数"})

        allowed_critical = {"吸氧浓度", "呼气末正压", "氧合指数", "24h出入量", "尿量", "镇静评分", "抗菌药疗程"}

        def clean(items: list[str] | None, critical_only: bool = False) -> list[str]:
            output: list[str] = []
            for item in items or []:
                name = str(item or "").strip()
                if not name or name in resolved or name in suppress:
                    continue
                if critical_only and name not in allowed_critical:
                    continue
                if name not in output:
                    output.append(name)
            return output

        for item in draft.get("organ_support") or []:
            item["missing_data"] = clean(item.get("missing_data"), critical_only=True)
        for card in draft.get("system_ap") or []:
            card["missing_data"] = clean(card.get("missing_data"))
            for group in ("status", "trend", "assessment", "plan_items"):
                for stmt in card.get(group) or []:
                    stmt["missing_data"] = clean(stmt.get("missing_data"))
        for goal in draft.get("daily_goals") or []:
            goal["missing_data"] = clean(goal.get("missing_data"), critical_only=True)
        return draft

    def _build_system_cards_from_draft(self, draft: dict) -> list[dict]:
        cards = []
        for system, title in SYSTEM_ORDER:
            cards.append({
                "id": f"system_{system}",
                "system": system,
                "title": title,
                "priority": "medium",
                "status": [{"id": f"{system}_status_missing", "kind": "inference", "text": "该系统资料需查房复核。", "evidence_refs": [], "missing_data": ["床旁查体"], "review_required": True}],
                "trend": [],
                "assessment": [],
                "plan_items": [{"id": f"{system}_plan_review", "kind": "recommendation", "text": "查房时补充该系统评估和今日计划。", "evidence_refs": [], "missing_data": ["床旁查体"], "review_required": True}],
                "missing_data": ["床旁查体"],
                "evidence_refs": [],
                "review_status": "unreviewed",
            })
        return cards

    def _run_quality_checks(self, draft: dict, ctx: ProgressNoteContext) -> dict:
        missing: list[str] = []
        for item in draft.get("organ_support") or []:
            missing.extend(item.get("missing_data") or [])
        for card in draft.get("system_ap") or []:
            missing.extend(card.get("missing_data") or [])
        for goal in draft.get("daily_goals") or []:
            missing.extend(goal.get("missing_data") or [])
        aliases = {
            "FiO2": "吸氧浓度",
            "PEEP": "呼气末正压",
            "P/F ratio": "氧合指数",
            "RASS": "镇静评分",
            "抗菌药疗程天数": "抗菌药疗程",
        }
        normalized_missing = {aliases.get(name, name) for name in missing}
        critical_order = ["吸氧浓度", "呼气末正压", "氧合指数", "24h出入量", "尿量", "镇静评分", "抗菌药疗程"]
        critical_missing = [name for name in critical_order if name in normalized_missing]
        warnings = []
        if draft.get("raw_ai_tags") and not ctx.alerts:
            warnings.append("部分AI风险标签缺少对应结构化原始数据，已作为待复核项展示。")
        if not ctx.vent:
            warnings.append("未检索到当前呼吸机参数，呼吸系统判断需床旁复核。")
        return {
            "critical_missing_data": critical_missing,
            "stale_data": [],
            "contradictions": [],
            "warnings": warnings,
        }

    def _verify_citations(self, draft: dict, citations: list[dict]) -> list[str]:
        valid_refs = {c["id"] for c in citations}
        refs = set(re.findall(r'"evidence_refs"\s*:\s*\[(.*?)\]', json.dumps(draft, ensure_ascii=False)))
        warnings: list[str] = []
        for ref in self._iter_evidence_refs(draft):
            if ref not in valid_refs:
                warnings.append(f"可疑引用：{ref} 不存在于原始数据")
        return warnings

    def _iter_evidence_refs(self, value: Any):
        if isinstance(value, dict):
            for key, inner in value.items():
                if key == "evidence_refs" and isinstance(inner, list):
                    for ref in inner:
                        yield ref
                else:
                    yield from self._iter_evidence_refs(inner)
        elif isinstance(value, list):
            for item in value:
                yield from self._iter_evidence_refs(item)

    def _collect_valid_ids(self, ctx: ProgressNoteContext) -> dict[str, str]:
        """Backward-compatible helper used by older tests."""
        citations = self._build_citations(ctx)
        return {c["id"]: c["source_type"] if c["source_type"] in {"vital_sign", "ventilator", "score"} else f"{c['source_type']}:{c['title']}" for c in citations}
