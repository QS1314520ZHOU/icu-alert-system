"""认证模型。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class UserRole(StrEnum):
    """用户角色。"""
    ADMIN = "admin"
    DOCTOR = "doctor"
    NURSE = "nurse"
    RESEARCHER = "researcher"
    VIEWER = "viewer"


class User(BaseModel):
    """用户模型。"""
    id: str
    username: str
    email: str
    role: UserRole
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class UserCreate(BaseModel):
    """创建用户请求。"""
    username: str
    email: str
    password: str
    role: UserRole = UserRole.VIEWER


class UserLogin(BaseModel):
    """用户登录请求。"""
    username: str
    password: str


class TokenResponse(BaseModel):
    """令牌响应。"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TokenPayload(BaseModel):
    """令牌载荷。"""
    sub: str
    role: str
    type: str
    exp: datetime
