from __future__ import annotations

import json
import re
from typing import Any

from app.services.llm_runtime import breaker_snapshot
from app.utils.api_llm import call_api_llm


def _parse_json(text: str) -> dict[str, Any] | None:
    content = str(text or "").strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE)
        content = re.sub(r"\s*```$", "", content)
    match = re.search(r"\{[\s\S]*\}", content)
    if match:
        content = match.group(0)
    try:
        data = json.loads(content)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _best_element_gap(element_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not element_rows:
        return None
    ranked = sorted(
        element_rows,
        key=lambda item: (
            float(item.get("completion_rate") or 0),
            -(int(item.get("required_cases") or 0)),
        ),
    )
    return ranked[0] if ranked else None


def _best_dept_gap(dept_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not dept_rows:
        return None
    ranked = sorted(
        dept_rows,
        key=lambda item: (
            float(item.get("compliance_rate") or 0),
            -(int(item.get("overdue_3h_cases") or 0)),
            -(int(item.get("total_cases") or 0)),
        ),
    )
    return ranked[0] if ranked else None


def _weaning_fallback(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    timeline = payload.get("timeline") if isinstance(payload.get("timeline"), list) else []
    bundle = summary.get("liberation_bundle") if isinstance(summary.get("liberation_bundle"), dict) else {}
    lights = bundle.get("lights") if isinstance(bundle.get("lights"), dict) else {}
    recent_sbt = summary.get("latest_sbt") if isinstance(summary.get("latest_sbt"), dict) else {}
    latest_weaning = summary.get("latest_weaning") if isinstance(summary.get("latest_weaning"), dict) else {}

    red_lights = [key for key, value in lights.items() if str(value) == "red"]
    passed = int(summary.get("sbt_passed_count") or 0)
    failed = int(summary.get("sbt_failed_count") or 0)
    risk_level = str(latest_weaning.get("risk_level") or "unknown")
    recommendation = str(latest_weaning.get("recommendation") or "").strip()

    headline = f"近阶段 SBT 通过 {passed} 次、失败 {failed} 次，当前脱机风险等级 {risk_level}。"
    if red_lights:
        headline += f" Liberation Bundle 薄弱环节主要在 {', '.join(red_lights)}。"

    actions: list[str] = []
    if recent_sbt.get("result") == "failed":
        actions.append("优先按最近一次 SBT 失败指标复盘呼吸负荷、氧合和循环约束。")
    if red_lights:
        actions.append(f"先补齐 Liberation Bundle 红灯项：{', '.join(red_lights)}。")
    if recommendation:
        actions.append(recommendation)
    if not actions:
        actions.append("继续按班次复核 SBT、SAT 与拔管后风险轨迹。")

    risks: list[str] = []
    gate_failures = latest_weaning.get("gate_failures") if isinstance(latest_weaning.get("gate_failures"), list) else []
    for item in gate_failures[:3]:
        text = str(item).strip()
        if text:
            risks.append(text)
    for row in timeline[:3]:
        if str(row.get("event_type") or "") == "post_extubation_failure_risk":
            risks.append("近期存在拔管后失败/再插管风险信号")
            break

    return {
        "summary": headline,
        "key_findings": risks[:4] or ["当前时间线未见新的拔管后失败事件，但仍需连续观察。"],
        "recommended_actions": actions[:4],
        "degraded_mode": True,
    }


def _sepsis_fallback(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    total_cases = int(summary.get("total_cases") or 0)
    compliant = int(summary.get("compliant_1h_cases") or 0)
    overdue_3h = int(summary.get("overdue_3h_cases") or 0)
    dept_rows = summary.get("dept_compare") if isinstance(summary.get("dept_compare"), list) else []
    element_rows = summary.get("element_compliance") if isinstance(summary.get("element_compliance"), list) else []
    recent_cases = summary.get("recent_cases") if isinstance(summary.get("recent_cases"), list) else []

    weakest_element = _best_element_gap(element_rows)
    weakest_dept = _best_dept_gap(dept_rows)
    pending_recent = [row for row in recent_cases if str(row.get("status") or "") in {"pending", "overdue_1h", "overdue_3h"}]

    summary_text = f"本月脓毒症 1h bundle 共 {total_cases} 例，1h 达标 {compliant} 例，超 3h 未完成 {overdue_3h} 例。"
    if weakest_element:
        summary_text += f" 当前最薄弱要素是 {weakest_element.get('element')}。"
    if weakest_dept:
        summary_text += f" 需要优先关注 {weakest_dept.get('dept')}。"

    findings: list[str] = []
    if weakest_element:
        findings.append(
            f"{weakest_element.get('element')} 完成率 {round(float(weakest_element.get('completion_rate') or 0) * 100, 1)}%"
        )
    if weakest_dept:
        findings.append(
            f"{weakest_dept.get('dept')} 1h 达标率 {round(float(weakest_dept.get('compliance_rate') or 0) * 100, 1)}%"
        )
    if pending_recent:
        findings.append(f"最近仍有 {len(pending_recent)} 例处于 pending/overdue 状态")

    actions: list[str] = []
    if weakest_element:
        actions.append(f"围绕 {weakest_element.get('element')} 做流程专项质控和回顾。")
    if weakest_dept:
        actions.append(f"对 {weakest_dept.get('dept')} 做脓毒症首小时执行路径复盘。")
    actions.append("对 recent_cases 中 pending/overdue 个案做逐例追踪，避免由 1h 继续滑到 3h。")

    return {
        "summary": summary_text,
        "key_findings": findings[:4] or ["当前样本量有限，建议继续累计并按周复盘。"],
        "recommended_actions": actions[:4],
        "degraded_mode": True,
    }


async def summarize_weaning_timeline(payload: dict[str, Any]) -> dict[str, Any]:
    system_prompt = (
        "你是ICU脱机管理助手。"
        "只能根据输入时间线和结构化数据总结。"
        "必须返回严格JSON，字段仅包含 summary, key_findings, recommended_actions。"
        "key_findings 和 recommended_actions 均为最多4条中文短句数组。"
    )
    user_prompt = "请总结以下脱机时间线，重点识别SBT趋势、Liberation Bundle短板和下一步动作：\n" + json.dumps(payload, ensure_ascii=False, default=str)
    try:
        raw = await call_api_llm(system_prompt, user_prompt)
        parsed = _parse_json(raw)
        if isinstance(parsed, dict):
            return {
                "summary": str(parsed.get("summary") or "").strip(),
                "key_findings": [str(x).strip() for x in (parsed.get("key_findings") or [])[:4] if str(x).strip()],
                "recommended_actions": [str(x).strip() for x in (parsed.get("recommended_actions") or [])[:4] if str(x).strip()],
                "degraded_mode": False,
            }
    except Exception:
        pass
    fallback = _weaning_fallback(payload)
    fallback["breaker"] = await breaker_snapshot()
    return fallback


async def summarize_sepsis_bundle_analytics(payload: dict[str, Any]) -> dict[str, Any]:
    system_prompt = (
        "你是ICU质控分析助手。"
        "只能根据输入的脓毒症1h bundle统计做总结，不得编造。"
        "必须返回严格JSON，字段仅包含 summary, key_findings, recommended_actions。"
        "key_findings 和 recommended_actions 均为最多4条中文短句数组。"
    )
    user_prompt = "请总结以下脓毒症1h bundle质控统计，指出主要短板、重点科室和改进动作：\n" + json.dumps(payload, ensure_ascii=False, default=str)
    try:
        raw = await call_api_llm(system_prompt, user_prompt)
        parsed = _parse_json(raw)
        if isinstance(parsed, dict):
            return {
                "summary": str(parsed.get("summary") or "").strip(),
                "key_findings": [str(x).strip() for x in (parsed.get("key_findings") or [])[:4] if str(x).strip()],
                "recommended_actions": [str(x).strip() for x in (parsed.get("recommended_actions") or [])[:4] if str(x).strip()],
                "degraded_mode": False,
            }
    except Exception:
        pass
    fallback = _sepsis_fallback(payload)
    fallback["breaker"] = await breaker_snapshot()
    return fallback
