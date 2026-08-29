"""审计事件模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    """审计事件。"""
    id: str = ""
    actor_id: str = ""
    actor_role: str = ""
    action: str = ""  # create, update, delete, approve, reject, publish, etc.
    resource_type: str = ""  # disease, terminology, phenotype_rule, etc.
    resource_id: str = ""
    resource_version: str = ""
    before: Optional[dict] = None
    after: Optional[dict] = None
    reason: str = ""
    request_id: str = ""
    ip: str = ""
    user_agent: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    result: str = ""  # success, failure, error
