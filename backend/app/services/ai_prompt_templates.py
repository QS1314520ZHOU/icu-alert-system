from __future__ import annotations

import json
import re
from typing import Any

from app.services.llm_runtime import sanitize_llm_text

ROUNDING_FOCUS_PROMPT_VERSION = "rounding_focus_points_v1"
RESEARCH_TOPIC_PROMPT_VERSION = "research_topic_suggestions_v1"
CLINICAL_TRIAL_PARSE_PROMPT_VERSION = "clinical_trial_criteria_parse_v1"


def _json_text(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def build_rounding_focus_prompts(summary: dict[str, Any]) -> tuple[str, str]:
    system_prompt = (
        "你是 ICU 智能查房助手。"
        "你的任务是根据结构化 ICU 查房摘要生成 3-5 条临床关注点。"
        "你只能输出严格 JSON，不要输出 markdown，不要输出额外解释。"
        "你必须保守、可追溯、可审计，只能基于输入证据总结。"
        "你不得生成强制医嘱，不得替代医生判断。"
    )
    user_prompt = (
        "请基于以下患者过去 N 小时结构化摘要，输出 JSON：\n"
        "{\n"
        '  "focus_points": [\n'
        "    {\n"
        '      "title": "...",\n'
        '      "risk_level": "low|medium|high",\n'
        '      "evidence": ["..."],\n'
        '      "suggested_attention": "...",\n'
        '      "uncertainty": "..."\n'
        "    }\n"
        "  ],\n"
        '  "disclaimer": "仅供临床决策支持，不替代医生判断"\n'
        "}\n\n"
        "约束：\n"
        "1. focus_points 最多 5 条。\n"
        "2. evidence 必须来自输入中的具体异常或趋势。\n"
        "3. 若证据不足，请明确写 uncertainty。\n"
        "4. 不要凭空补充不存在的数据。\n\n"
        f"输入摘要：\n{_json_text(summary)}"
    )
    return system_prompt, user_prompt


def build_research_topic_prompts(snapshot: dict[str, Any]) -> tuple[str, str]:
    system_prompt = (
        "你是 ICU 科研设计助手。"
        "你需要基于科室聚合数据、质量指标和指南差距，提出潜在科研课题。"
        "你只能输出严格 JSON，不要输出 markdown。"
        "所有建议都必须可追溯到输入数据摘要，不允许凭空编造。"
        "面向中国医院 ICU 科研团队，除必要医学缩写外，所有字段必须使用简体中文。"
    )
    user_prompt = (
        "请根据以下科室聚合数据摘要输出 JSON：\n"
        "{\n"
        '  "topic_suggestions": [\n'
        "    {\n"
        '      "title": "...",\n'
        '      "clinical_question": "...",\n'
        '      "data_basis": "...",\n'
        '      "study_design": "...",\n'
        '      "inclusion_criteria": [],\n'
        '      "exclusion_criteria": [],\n'
        '      "primary_outcome": "...",\n'
        '      "secondary_outcomes": [],\n'
        '      "required_data_fields": [],\n'
        '      "feasibility_score": 0,\n'
        '      "ethical_risk": "...",\n'
        '      "multi_center_potential": true\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "约束：\n"
        "1. 每条建议都要写明 data_basis。\n"
        "2. 若样本量不足或数据缺失，请在 data_basis 或 ethical_risk 中明确限制。\n"
        "3. feasibility_score 为 0-100 的整数。\n"
        "4. 不要输出 5 条以上建议。\n\n"
        "5. title、clinical_question、data_basis、study_design、primary_outcome、ethical_risk、"
        "inclusion_criteria、exclusion_criteria、secondary_outcomes、required_data_fields 均用简体中文；"
        "ARDS、ICU、P/F、PEEP、Bundle 等通用医学缩写可以保留。\n\n"
        f"输入数据摘要：\n{_json_text(snapshot)}"
    )
    return system_prompt, user_prompt


def build_clinical_trial_parse_prompts(
    inclusion_text: str,
    exclusion_text: str,
) -> tuple[str, str]:
    system_prompt = (
        "你是临床试验规则解析助手。"
        "你需要将自然语言入排标准转换为结构化规则草案。"
        "你只能输出严格 JSON，不要输出 markdown。"
        "如果表达不确定，必须保留 warnings，并设置 need_human_review=true。"
    )
    user_prompt = (
        "请把下面的临床试验标准解析为 JSON：\n"
        "{\n"
        '  "inclusion_rules": [\n'
        "    {\n"
        '      "field": "...",\n'
        '      "operator": "...",\n'
        '      "value": "...",\n'
        '      "time_window": "...",\n'
        '      "source_text": "..."\n'
        "    }\n"
        "  ],\n"
        '  "exclusion_rules": [\n'
        "    {\n"
        '      "field": "...",\n'
        '      "operator": "...",\n'
        '      "value": "...",\n'
        '      "time_window": "...",\n'
        '      "source_text": "..."\n'
        "    }\n"
        "  ],\n"
        '  "need_human_review": true,\n'
        '  "warnings": []\n'
        "}\n\n"
        "要求：\n"
        "1. 优先识别年龄、诊断、实验室、生命体征、用药、呼吸机参数、评分、时间窗。\n"
        "2. 无法精确结构化时保留 source_text，并在 warnings 提示。\n"
        "3. 启用前仍需人工审核，因此 need_human_review 保持 true。\n\n"
        f"入组标准原文：\n{inclusion_text or '无'}\n\n"
        f"排除标准原文：\n{exclusion_text or '无'}"
    )
    return system_prompt, user_prompt


def extract_json_object(text: str) -> dict[str, Any]:
    raw = sanitize_llm_text(text)
    if not raw:
        return {}
    fenced = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", raw, flags=re.IGNORECASE)
    if fenced:
        raw = str(fenced.group(1) or "").strip()
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return {}
    try:
        value = json.loads(match.group(0))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}
