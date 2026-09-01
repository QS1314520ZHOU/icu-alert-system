"""病例级AI服务 - 使用项目已有LLM配置生成病例分析摘要。"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.config import get_config
from app.services.llm_runtime import call_llm_chat

logger = logging.getLogger("icu-alert")


CASE_AI_SYSTEM_PROMPT = """你是一位ICU重症医学专家AI助手。请根据提供的病例信息和证据链，生成简洁的病例分析摘要。

要求：
1. 只依据输入数据推理，严禁编造未提供的信息
2. 明确区分"已知事实"和"推断建议"
3. 摘要应包含：核心问题、风险评估、建议关注点
4. 输出格式为JSON，不要输出额外文本

JSON结构：
{
  "summary": "病例摘要（100字以内）",
  "core_problems": ["核心问题1", "核心问题2"],
  "risk_assessment": "风险评估（low/medium/high/critical）",
  "key_evidence": ["关键证据1", "关键证据2"],
  "recommendations": ["建议1", "建议2"],
  "confidence": 0.85
}"""


async def generate_case_ai_summary(
    case_data: dict[str, Any],
    evidence_list: list[dict[str, Any]],
    conclusions: list[dict[str, Any]],
) -> dict[str, Any]:
    """生成病例AI摘要。

    Args:
        case_data: 病例基本信息
        evidence_list: 证据列表
        conclusions: 临床结论列表

    Returns:
        AI生成的病例分析摘要
    """
    config = get_config()

    # 构建用户提示词
    evidence_text = "\n".join(
        f"- {e.get('evidence_type', '未知')}: {e.get('raw_value', 'N/A')}{e.get('raw_unit', '')}"
        f" (观察时间: {e.get('observed_at', '未知')})"
        for e in evidence_list[:20]  # 限制证据数量
    )

    conclusions_text = "\n".join(
        f"- {c.get('conclusion_type', '未知')}: {c.get('summary', '无摘要')}"
        for c in conclusions[:5]
    )

    user_prompt = f"""病例信息：
- 患者ID: {case_data.get('patient_id', '未知')}
- 疾病: {case_data.get('disease_name', '未知')} ({case_data.get('disease_code', '')})
- 状态: {case_data.get('status', '未知')}
- 风险等级: {case_data.get('risk_level', '未知')}
- 筛查评分: {case_data.get('screening_score', 'N/A')}
- 置信度: {case_data.get('confidence', 'N/A')}
- 首次检测时间: {case_data.get('first_detected_at', '未知')}
- 最后评估时间: {case_data.get('last_evaluated_at', '未知')}

证据链：
{evidence_text or '暂无证据'}

临床结论：
{conclusions_text or '暂无结论'}

请生成病例分析摘要。"""

    try:
        # 使用项目已有的LLM配置
        result = await call_llm_chat(
            cfg=config,
            system_prompt=CASE_AI_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.1,
            max_tokens=1024,
            timeout_seconds=30,
        )

        # 解析LLM响应
        content = result.get("content", "")
        if not content:
            return {
                "success": False,
                "error": "LLM返回空内容",
                "summary": "无法生成AI摘要",
            }

        # 尝试解析JSON
        import json
        try:
            # 提取JSON部分（可能被markdown代码块包裹）
            json_str = content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0]

            ai_result = json.loads(json_str.strip())
            return {
                "success": True,
                "data": ai_result,
                "model": result.get("model", ""),
                "usage": result.get("usage", {}),
            }
        except json.JSONDecodeError:
            # JSON解析失败，返回原始文本
            return {
                "success": True,
                "data": {
                    "summary": content[:500],
                    "core_problems": [],
                    "risk_assessment": "unknown",
                    "key_evidence": [],
                    "recommendations": [],
                    "confidence": 0.5,
                },
                "model": result.get("model", ""),
                "usage": result.get("usage", {}),
            }

    except Exception as e:
        logger.error(f"病例AI摘要生成失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "summary": f"AI摘要生成失败: {str(e)[:100]}",
        }
