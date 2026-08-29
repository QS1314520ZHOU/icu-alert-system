"""临床证据链 API 路由。

提供统一的证据查询接口，支持按上下文类型、器官系统、时间范围等维度查询。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.services.clinical_evidence_service import get_evidence

router = APIRouter(prefix="/api/patients", tags=["clinical-evidence"])


@router.get("/{patient_id}/evidence")
async def get_patient_evidence(
    patient_id: str,
    context_type: str = Query(..., description="上下文类型: organ_system|risk|order|nursing|weaning|discharge|rule_noise|vitals|unclosed"),
    context_id: str | None = Query(None, description="上下文ID，如告警ID、规则ID等"),
    organ_system: str | None = Query(None, description="器官系统: respiratory|circulatory|renal|hepatic|neurologic|coagulation|infection|nutrition"),
    time_range: str = Query("24h", description="时间范围: 1h|6h|12h|24h|48h|72h|7d"),
    include_raw: bool = Query(False, description="是否包含原始数据来源信息"),
    include_ai: bool = Query(False, description="是否包含AI分析"),
    request: Request = None,
):
    """获取患者临床证据链。

    返回完整的证据结构，包括：
    - conclusion: 结论摘要
    - severity: 严重程度
    - confidence: 置信度（来自后端模型/规则引擎）
    - metrics: 关键指标
    - trends: 趋势数据
    - evidence_rows: 原始证据行
    - rule_calculation: 规则/评分计算明细
    - ai_analysis: AI分析（可选）
    - timeline: 临床事件时间线
    - missing_data: 缺失数据提示
    - provenance: 数据来源
    """
    # 提取操作者身份
    actor = (
        request.headers.get("X-User-Id")
        or request.headers.get("x-operator-id")
        or "anonymous"
    ) if request else "anonymous"

    # 验证 context_type
    valid_context_types = {
        "organ_system", "risk", "order", "nursing", "weaning",
        "discharge", "rule_noise", "vitals", "unclosed",
    }
    if context_type not in valid_context_types:
        raise HTTPException(
            status_code=400,
            detail=f"无效的 context_type: {context_type}，有效值: {', '.join(sorted(valid_context_types))}",
        )

    # 验证 organ_system
    valid_organ_systems = {
        "respiratory", "circulatory", "renal", "hepatic",
        "neurologic", "coagulation", "infection", "nutrition",
    }
    if organ_system and organ_system not in valid_organ_systems:
        raise HTTPException(
            status_code=400,
            detail=f"无效的 organ_system: {organ_system}，有效值: {', '.join(sorted(valid_organ_systems))}",
        )

    # 验证 time_range
    valid_time_ranges = {"1h", "6h", "12h", "24h", "48h", "72h", "7d"}
    if time_range not in valid_time_ranges:
        raise HTTPException(
            status_code=400,
            detail=f"无效的 time_range: {time_range}，有效值: {', '.join(sorted(valid_time_ranges))}",
        )

    result = await get_evidence(
        patient_id=patient_id,
        context_type=context_type,
        context_id=context_id,
        organ_system=organ_system,
        time_range=time_range,
        include_raw=include_raw,
        include_ai=include_ai,
        actor=actor,
    )

    return {"code": 0, "data": result}
