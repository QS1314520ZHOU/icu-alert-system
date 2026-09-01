"""病例级AI服务 - 结构化可追溯AI证据归纳。

使用项目已有LLM配置生成病例分析，输出结构化AICaseInsight。
每条Claim必须关联Evidence ID，不构成诊断或医嘱。
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.config import get_config
from app.services.llm_runtime import call_llm_chat

logger = logging.getLogger("icu-alert")


# ===== 结构化输出模型 =====


class AIClaim(BaseModel):
    """AI声明，必须关联Evidence ID。"""
    claim: str
    evidence_ids: list[str] = []
    knowledge_reference_ids: list[str] = []
    confidence_level: Literal["low", "moderate", "high"] = "moderate"


class AIMissingItem(BaseModel):
    """缺失信息项。"""
    item: str
    reason: str
    related_rule_id: str | None = None


class AISuggestedAssessment(BaseModel):
    """建议评估事项（非诊断建议）。"""
    title: str
    reason: str
    evidence_ids: list[str] = []
    pathway_task_id: str | None = None
    priority: Literal["low", "medium", "high"] = "medium"
    requires_clinician_review: bool = True


class AICaseInsight(BaseModel):
    """病例级AI结构化输出。"""
    case_id: str = ""
    summary: str = ""
    core_problems: list[AIClaim] = []
    supporting_evidence: list[AIClaim] = []
    contradicting_evidence: list[AIClaim] = []
    missing_information: list[AIMissingItem] = []
    suggested_assessments: list[AISuggestedAssessment] = []
    risk_level: Literal["low", "medium", "high", "critical", "unknown"] = "unknown"
    uncertainty: Literal["low", "moderate", "high"] = "high"
    safety_notes: list[str] = Field(default_factory=lambda: [
        "AI仅归纳当前可用证据，不构成诊断或医嘱。",
        "请结合完整病历和临床评估进行判断。",
    ])
    model_name: str = ""
    prompt_version: str = "v1.0"
    rule_versions: list[str] = []
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data_cutoff_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    stale: bool = False
    generation_mode: Literal["llm", "rule_fallback"] = "llm"


# ===== Prompt =====


CASE_AI_SYSTEM_PROMPT = """你是一位ICU重症医学专家AI助手。请根据提供的病例信息和证据链，生成结构化的病例证据归纳。

重要安全规则：
1. 只依据输入数据推理，严禁编造未提供的信息
2. 不得自动确诊、排除或改变病例状态
3. 不得建议自动下医嘱
4. 每条声明必须关联提供的Evidence ID
5. 无法确认的事项必须列入缺失信息

输出格式为JSON，不要输出额外文本。

JSON结构：
{
  "summary": "病例摘要（100字以内）",
  "core_problems": [
    {"claim": "核心问题描述", "evidence_ids": ["ev_id_1"], "confidence_level": "high|moderate|low"}
  ],
  "supporting_evidence": [
    {"claim": "支持证据描述", "evidence_ids": ["ev_id_2"], "confidence_level": "high|moderate|low"}
  ],
  "contradicting_evidence": [
    {"claim": "反对/冲突证据描述", "evidence_ids": ["ev_id_3"], "confidence_level": "moderate"}
  ],
  "missing_information": [
    {"item": "缺失项", "reason": "为什么需要", "related_rule_id": "规则ID或null"}
  ],
  "suggested_assessments": [
    {"title": "建议评估事项", "reason": "原因", "evidence_ids": [], "priority": "high|medium|low", "requires_clinician_review": true}
  ],
  "risk_level": "low|medium|high|critical|unknown",
  "uncertainty": "low|moderate|high"
}"""


def _validate_evidence_ids(
    ai_result: dict[str, Any],
    valid_evidence_ids: set[str],
) -> tuple[dict[str, Any], list[str]]:
    """验证AI输出中的Evidence ID是否属于当前病例。

    Returns:
        (清理后的结果, 质量告警列表)
    """
    warnings: list[str] = []
    claim_fields = ["core_problems", "supporting_evidence", "contradicting_evidence"]

    for field_name in claim_fields:
        claims = ai_result.get(field_name, [])
        if not isinstance(claims, list):
            continue
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            original_ids = claim.get("evidence_ids", [])
            if not isinstance(original_ids, list):
                claim["evidence_ids"] = []
                continue
            valid_ids = [eid for eid in original_ids if eid in valid_evidence_ids]
            removed = [eid for eid in original_ids if eid not in valid_evidence_ids]
            if removed:
                warnings.append(
                    f"{field_name}: 移除无效Evidence ID {removed}"
                )
            claim["evidence_ids"] = valid_ids

    # 检查是否有至少一条有效Evidence ID
    has_any_valid = False
    for field_name in claim_fields:
        claims = ai_result.get(field_name, [])
        if isinstance(claims, list):
            for claim in claims:
                if isinstance(claim, dict) and claim.get("evidence_ids"):
                    has_any_valid = True
                    break
        if has_any_valid:
            break

    if not has_any_valid and ai_result.get("core_problems"):
        warnings.append("所有核心结论均无有效Evidence ID")

    return ai_result, warnings


def _build_rule_fallback(
    case_data: dict[str, Any],
    evidence_list: list[dict[str, Any]],
    conclusions: list[dict[str, Any]],
) -> AICaseInsight:
    """当LLM失败时，使用规则模板生成摘要。"""
    disease_name = case_data.get("disease_name", "未知")
    risk_level = case_data.get("risk_level", "unknown")
    status = case_data.get("status", "unknown")

    core_problems: list[AIClaim] = []
    for c in conclusions:
        label = c.get("conclusion_label", "")
        if not label:
            continue
        core_problems.append(AIClaim(
            claim=label,
            evidence_ids=c.get("supporting_evidence_ids", []),
            confidence_level="moderate",
        ))

    supporting: list[AIClaim] = []
    for ev in evidence_list[:10]:
        if ev.get("matched"):
            supporting.append(AIClaim(
                claim=f"{ev.get('feature_name', ev.get('evidence_type', ''))}: "
                      f"{ev.get('raw_value', 'N/A')}{ev.get('raw_unit', '')}",
                evidence_ids=[ev.get("id", "")],
                confidence_level="moderate",
            ))

    return AICaseInsight(
        case_id=case_data.get("id", ""),
        summary=f"{disease_name}病例，当前状态{status}，风险等级{risk_level}。",
        core_problems=core_problems,
        supporting_evidence=supporting,
        risk_level=risk_level if risk_level in ("low", "medium", "high", "critical") else "unknown",
        uncertainty="high",
        generation_mode="rule_fallback",
    )


async def generate_case_ai_summary(
    case_data: dict[str, Any],
    evidence_list: list[dict[str, Any]],
    conclusions: list[dict[str, Any]],
) -> dict[str, Any]:
    """生成病例AI摘要（结构化输出）。

    Args:
        case_data: 病例基本信息
        evidence_list: 证据列表
        conclusions: 临床结论列表

    Returns:
        结构化AI病例洞察
    """
    config = get_config()
    case_id = case_data.get("id", "")
    valid_evidence_ids = {str(e.get("id", "")) for e in evidence_list if e.get("id")}

    # 构建用户提示词
    evidence_text = "\n".join(
        f"- [Evidence ID: {e.get('id', '')}] "
        f"{e.get('evidence_type', '未知')}: {e.get('feature_name', '')}="
        f"{e.get('raw_value', 'N/A')}{e.get('raw_unit', '')}"
        f" (观察时间: {e.get('observed_at', '未知')}, matched={e.get('matched', False)})"
        for e in evidence_list[:30]
    )

    conclusions_text = "\n".join(
        f"- [{c.get('conclusion_code', '')}] {c.get('conclusion_label', '无标签')}"
        f" (level={c.get('conclusion_level', '未知')}, "
        f"supporting_evidence={c.get('supporting_evidence_ids', [])})"
        for c in conclusions[:10]
    )

    user_prompt = f"""病例信息：
- 病例ID: {case_id}
- 疾病: {case_data.get('disease_name', '未知')} ({case_data.get('disease_code', '')})
- 状态: {case_data.get('status', '未知')}
- 风险等级: {case_data.get('risk_level', '未知')}
- 首次检测时间: {case_data.get('first_detected_at', '未知')}
- 最后评估时间: {case_data.get('last_evaluated_at', '未知')}

证据链（请使用Evidence ID引用）：
{evidence_text or '暂无证据'}

临床结论：
{conclusions_text or '暂无结论'}

请生成结构化病例证据归纳。"""

    try:
        result = await call_llm_chat(
            cfg=config,
            system_prompt=CASE_AI_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.1,
            max_tokens=2048,
            timeout_seconds=30,
        )

        content = result.get("content", "")
        if not content:
            logger.warning("LLM returned empty content for case %s", case_id)
            fallback = _build_rule_fallback(case_data, evidence_list, conclusions)
            return {
                "success": True,
                "data": fallback.model_dump(mode="json"),
                "generation_mode": "rule_fallback",
                "warnings": ["LLM返回空内容，使用规则回退"],
            }

        # 解析JSON
        json_str = content
        if "```json" in content:
            json_str = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            json_str = content.split("```")[1].split("```")[0]

        try:
            ai_raw = json.loads(json_str.strip())
        except json.JSONDecodeError:
            # 尝试格式修复：有时LLM输出的JSON有多余逗号等
            try:
                import re
                fixed = re.sub(r',\s*([}\]])', r'\1', json_str.strip())
                ai_raw = json.loads(fixed)
            except (json.JSONDecodeError, Exception):
                # 第二次失败，回退到规则模板
                logger.warning("JSON parse failed for case %s, using rule fallback", case_id)
                fallback = _build_rule_fallback(case_data, evidence_list, conclusions)
                return {
                    "success": True,
                    "data": fallback.model_dump(mode="json"),
                    "generation_mode": "rule_fallback",
                    "warnings": ["JSON解析失败，使用规则回退"],
                }

        # 验证Evidence ID
        ai_raw, evidence_warnings = _validate_evidence_ids(ai_raw, valid_evidence_ids)

        # 构建结构化输出
        insight = AICaseInsight(
            case_id=case_id,
            summary=ai_raw.get("summary", ""),
            core_problems=[AIClaim(**c) for c in ai_raw.get("core_problems", []) if isinstance(c, dict)],
            supporting_evidence=[AIClaim(**c) for c in ai_raw.get("supporting_evidence", []) if isinstance(c, dict)],
            contradicting_evidence=[AIClaim(**c) for c in ai_raw.get("contradicting_evidence", []) if isinstance(c, dict)],
            missing_information=[AIMissingItem(**m) for m in ai_raw.get("missing_information", []) if isinstance(m, dict)],
            suggested_assessments=[AISuggestedAssessment(**s) for s in ai_raw.get("suggested_assessments", []) if isinstance(s, dict)],
            risk_level=ai_raw.get("risk_level", "unknown") if ai_raw.get("risk_level") in ("low", "medium", "high", "critical", "unknown") else "unknown",
            uncertainty=ai_raw.get("uncertainty", "high") if ai_raw.get("uncertainty") in ("low", "moderate", "high") else "high",
            model_name=result.get("model", ""),
            generated_at=datetime.now(timezone.utc),
            data_cutoff_at=datetime.now(timezone.utc),
            generation_mode="llm",
        )

        return {
            "success": True,
            "data": insight.model_dump(mode="json"),
            "generation_mode": "llm",
            "warnings": evidence_warnings,
        }

    except Exception as e:
        logger.error("病例AI摘要生成失败: %s", e, exc_info=True)
        fallback = _build_rule_fallback(case_data, evidence_list, conclusions)
        return {
            "success": True,
            "data": fallback.model_dump(mode="json"),
            "generation_mode": "rule_fallback",
            "warnings": [f"LLM调用失败({str(e)[:50]})，使用规则回退"],
        }
