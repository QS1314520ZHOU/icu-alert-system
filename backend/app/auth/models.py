"""认证模型。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Optional

from pydantic import BaseModel, Field


class UserRole(StrEnum):
    """用户角色。"""
    ADMIN = "admin"
    DOCTOR = "doctor"
    NURSE = "nurse"
    HEAD_NURSE = "head_nurse"
    CHARGE_NURSE = "charge_nurse"
    DIRECTOR = "director"
    RESEARCHER = "researcher"
    VIEWER = "viewer"


class User(BaseModel):
    """用户模型。"""
    id: str
    username: str
    email: str
    role: UserRole
    dept: str = ""  # 用户所属科室
    allowed_depts: list[str] = Field(default_factory=list)  # 授权访问的科室列表
    allowed_wards: list[str] = Field(default_factory=list)  # 授权访问的病区列表
    permissions: list[str] = Field(default_factory=list)  # 功能权限列表
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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
    dept: str = ""
    allowed_depts: list[str] = Field(default_factory=list)
    allowed_wards: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
