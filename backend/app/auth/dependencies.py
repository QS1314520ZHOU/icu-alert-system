"""认证与授权依赖注入。

所有写操作接口必须使用 get_current_user 依赖。
后端不信任任何前端传入的操作者身份。

支持两种认证方式：
1. 宿主签发的 JWT（后端验证签名）
2. 一次性授权码交换
3. 开发模式 Mock（仅 development/test）
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.models import User, UserRole
from app.auth.iframe_auth import (
    CurrentUser,
    IframeAuthConfig,
    verify_host_jwt,
    exchange_authorization_code,
    get_mock_user,
    _load_config,
)

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> CurrentUser:
    """从 JWT 令牌获取当前用户。

    所有需要认证的接口使用此依赖。
    后端验证宿主签发的 Token，不信任前端传入的身份信息。
    """
    config = _load_config()

    # 开发模式 Mock
    mock_user = get_mock_user(config)
    if mock_user:
        logger.info(f"[DEV] Using mock user: {mock_user.user_id}")
        return mock_user

    # 检查是否为授权码交换请求
    if request.url.path == "/api/auth/iframe/exchange":
        # 交换请求在路由中处理
        raise HTTPException(status_code=400, detail="请使用 /api/auth/iframe/exchange 接口")

    # 从 Bearer Token 验证
    if credentials is None:
        raise HTTPException(status_code=401, detail="未提供认证令牌")

    token = credentials.credentials

    # 优先验证宿主 JWT
    user = await verify_host_jwt(token, config)
    if user:
        return user

    # 回退：尝试本地 JWT（兼容旧系统）
    try:
        from app.routers.auth import _decode_token
        payload = _decode_token(token)
        user_id = payload.get("sub")
        if user_id:
            return CurrentUser(
                user_id=user_id,
                user_name=payload.get("username", ""),
                roles=[payload.get("role", "viewer")],
                department_ids=payload.get("dept", "").split(",") if payload.get("dept") else [],
                expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc) if "exp" in payload else None,
            )
    except Exception:
        pass

    raise HTTPException(status_code=401, detail="无效的认证令牌")


async def require_role(*roles: str):
    """要求用户具有指定角色之一。"""
    async def checker(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        user_roles = set(current_user.roles)
        if not user_roles.intersection(set(roles)):
            raise HTTPException(
                status_code=403,
                detail=f"需要角色 {', '.join(roles)}，当前角色: {', '.join(current_user.roles)}"
            )
        return current_user
    return checker


async def require_permission(permission: str):
    """要求用户具有指定权限。"""
    async def checker(
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if permission not in current_user.permissions and "admin" not in current_user.roles:
            raise HTTPException(
                status_code=403,
                detail=f"缺少权限: {permission}"
            )
        return current_user
    return checker


def check_patient_access(user: CurrentUser, patient_dept: str, encounter_id: str = "") -> bool:
    """检查用户是否有权访问指定科室的患者。"""
    if "admin" in user.roles:
        return True
    if "researcher" in user.roles:
        return True  # 研究人员可访问脱敏数据
    if not user.department_ids:
        return True  # 未配置科室限制则允许
    return patient_dept in user.department_ids


def check_case_operation_permission(user: CurrentUser, operation: str) -> bool:
    """检查用户是否有权执行病例操作。"""
    from app.services.case_state_service import check_permission
    return check_permission(user.role, operation)


# ===== 兼容层：将 CurrentUser 转换为旧 User 模型 =====

def current_user_to_user(current_user: CurrentUser) -> User:
    """将 CurrentUser 转换为旧 User 模型（兼容旧接口）。"""
    return User(
        id=current_user.user_id,
        username=current_user.user_name or current_user.user_id,
        email="",
        role=UserRole(current_user.role) if current_user.role in UserRole.__members__.values() else UserRole.VIEWER,
        dept=current_user.dept,
        allowed_depts=current_user.department_ids,
        allowed_wards=[],
        permissions=current_user.permissions,
    )
