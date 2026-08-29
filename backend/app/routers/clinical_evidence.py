"""临床证据链统一查询 API。

P0 修复版：
- 使用 session-based JWT 认证（Depends(get_current_user)）
- 正确 HTTP 状态码：401/403/404/503
- data insufficient = 200 + calculable=false
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app import runtime
from app.auth import get_current_user
from app.services.clinical_evidence_service import ServiceUnavailable, get_evidence

logger = logging.getLogger("icu-alert")

router = APIRouter(prefix="/api/patients", tags=["clinical-evidence"])


def _serialize(data):
    if not data:
        return data
    from app.utils.json_utils import sanitize_for_json
    return sanitize_for_json(data)


@router.get("/{patient_id}/evidence")
async def get_patient_evidence(
    patient_id: str,
    current_user: dict = Depends(get_current_user),
    context_type: str = Query("organ_system", description="上下文类型"),
    context_id: Optional[str] = Query(None, description="具体记录 ID（order_id / nursing_key / alert_id / rule_id）"),
    organ_system: Optional[str] = Query(None, description="器官系统"),
    time_range: str = Query("24h", description="时间范围"),
    include_raw: bool = Query(False, description="是否包含原始数据"),
    include_ai: bool = Query(False, description="是否包含 AI 分析"),
):
    """查询患者临床证据链。

    认证与授权：
    - 匿名请求 → 401 Unauthorized
    - 已认证但无权访问患者 → 403 Forbidden
    - 患者不存在 → 404 Not Found
    - 数据不足 → 200 + calculable=false
    - 数据库不可用 → 503 Service Unavailable
    """
    # 验证当前用户存在（get_current_user 已处理 401）
    if not current_user or not current_user.get("username"):
        raise HTTPException(status_code=401, detail="未认证")

    db = runtime.db

    try:
        result = await get_evidence(
            db=db,
            patient_id=patient_id,
            context_type=context_type,
            current_user=current_user,
            context_id=context_id,
            organ_system=organ_system,
            time_range=time_range,
            include_raw=include_raw,
            include_ai=include_ai,
        )
    except ServiceUnavailable:
        raise HTTPException(status_code=503, detail="数据库不可用")

    if result is None:
        raise HTTPException(status_code=404, detail="未找到对应数据")

    return {"code": 0, "data": result}
