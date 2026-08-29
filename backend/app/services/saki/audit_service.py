"""S-AKI 审计追踪服务。"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("icu-alert")


class SAKIAuditService:
    """审计追踪 - 记录所有 S-AKI 数据操作。"""

    async def log_event(
        self,
        db: Any,
        action: str,
        resource_type: str,
        resource_id: str,
        actor: str = "system",
        details: dict[str, Any] | None = None,
    ) -> str:
        """记录审计事件。"""
        event_id = str(uuid.uuid4())
        doc = {
            "event_id": event_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "actor": actor,
            "details": details or {},
            "timestamp": datetime.now(timezone.utc),
        }
        try:
            await db.col("saki_audit_log").insert_one(doc)
        except Exception as exc:
            logger.warning("审计事件记录失败: %s", exc)
        return event_id

    async def query_events(
        self,
        db: Any,
        action: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """查询审计事件。"""
        query: dict[str, Any] = {}
        if action:
            query["action"] = action
        if resource_type:
            query["resource_type"] = resource_type
        if resource_id:
            query["resource_id"] = resource_id

        cursor = db.col("saki_audit_log").find(query).sort("timestamp", -1).limit(limit)
        result = []
        async for doc in cursor:
            doc.pop("_id", None)
            result.append(doc)
        return result
