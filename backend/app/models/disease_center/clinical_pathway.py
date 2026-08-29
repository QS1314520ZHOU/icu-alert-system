"""临床路径模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PathwayNode(BaseModel):
    """路径节点。"""
    id: str
    name: str
    node_type: str = ""  # start, decision, action, end
    description: str = ""
    conditions: list[dict] = Field(default_factory=list)
    actions: list[dict] = Field(default_factory=list)
    position: dict = Field(default_factory=dict)  # x, y coordinates


class PathwayEdge(BaseModel):
    """路径边。"""
    id: str
    source_node_id: str
    target_node_id: str
    condition: str = ""
    label: str = ""


class ClinicalPathway(BaseModel):
    """临床路径。"""
    id: str = ""
    disease_id: str
    name: str
    version: str = "v1.0.0"
    nodes: list[PathwayNode] = Field(default_factory=list)
    edges: list[PathwayEdge] = Field(default_factory=list)
    entry_conditions: list[dict] = Field(default_factory=list)
    exit_conditions: list[dict] = Field(default_factory=list)
    status: str = "draft"
    created_by: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_by: str = ""
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    reviewed_by: str = ""
    published_at: Optional[datetime] = None
    revision: int = 1
