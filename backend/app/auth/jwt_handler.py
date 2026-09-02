"""JWT 认证处理。"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.auth.models import User, UserRole, TokenPayload

logger = logging.getLogger("icu-auth")

# 配置：从环境变量读取，未配置时延迟报错（允许 import 阶段无 .env）
_SECRET_KEY_RAW = os.environ.get("JWT_SECRET_KEY", "").strip()
ALGORITHM = "HS256"


def _get_secret_key() -> str:
    """延迟校验 JWT_SECRET_KEY，首次使用时才报错。"""
    if not _SECRET_KEY_RAW:
        raise RuntimeError(
            "JWT_SECRET_KEY 环境变量未配置。"
            "请在 .env 文件中设置一个高强度密钥（至少 32 字符）。"
        )
    return _SECRET_KEY_RAW
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

# 密码加密
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Bearer 认证
security = HTTPBearer()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码。"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """获取密码哈希。"""
    return pwd_context.hash(password)


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """创建访问令牌。"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, _get_secret_key(), algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """创建刷新令牌。"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, _get_secret_key(), algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[TokenPayload]:
    """验证令牌。"""
    try:
        payload = jwt.decode(token, _get_secret_key(), algorithms=[ALGORITHM])
        return TokenPayload(**payload)
    except JWTError:
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """获取当前用户。

    从数据库加载用户信息。用户不存在或未激活返回 401，数据库异常返回 503。
    不允许 JWT 降级——所有用户信息必须来自数据库。
    """
    token = credentials.credentials
    payload = verify_token(token)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的令牌类型",
        )

    # 从数据库加载用户——不允许降级
    try:
        from app import runtime
        user_record = await runtime.db.col("users").find_one({
            "username": payload.sub,
        })
    except Exception as exc:
        logger.error("数据库查询用户失败: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="认证服务暂时不可用",
        )

    if not user_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )

    if not user_record.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户账号已停用",
        )

    return User(
        id=str(user_record["_id"]),
        username=user_record["username"],
        email=user_record.get("email", ""),
        role=UserRole(user_record.get("role", payload.role)),
        dept=user_record.get("dept", ""),
        allowed_depts=user_record.get("allowed_depts", []),
        allowed_wards=user_record.get("allowed_wards", []),
        permissions=user_record.get("permissions", []),
        is_active=True,
    )


def require_role(*roles: UserRole):
    """要求特定角色。"""
    async def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足",
            )
        return current_user
    return role_checker


async def require_patient_access(
    current_user: User,
    patient_id: str,
    db=None,
    permission: str = "patient:view",
):
    """检查用户是否有权访问指定患者。

    授权逻辑（按优先级）：
    1. 管理员 (admin) → 全部患者
    2. 功能权限检查：用户必须具有指定 permission
    3. 科室匹配：用户科室 == 患者科室
    4. 授权科室列表：患者科室 ∈ 用户 allowed_depts
    5. 授权病区列表：患者病区 ∈ 用户 allowed_wards

    Raises:
        HTTPException(400): 无效患者ID
        HTTPException(401): 用户未激活
        HTTPException(403): 无权访问
        HTTPException(404): 患者不存在
    """
    from bson import ObjectId
    from app import runtime

    if db is None:
        db = runtime.db

    # 用户未激活
    if not current_user.is_active:
        raise HTTPException(status_code=401, detail="用户账号已停用")

    # 管理员拥有全部权限
    if current_user.role == UserRole.ADMIN:
        return True

    # 功能权限检查
    if permission and permission not in (current_user.permissions or []):
        # 如果用户没有任何权限配置，则跳过权限检查（向后兼容）
        # 如果用户有权限配置但缺少所需权限，则拒绝
        if current_user.permissions:
            raise HTTPException(status_code=403, detail="缺少所需功能权限")

    try:
        pid = ObjectId(patient_id)
    except Exception:
        raise HTTPException(status_code=400, detail="无效患者ID")

    patient = await db.col("patient").find_one(
        {"_id": pid},
        {"hisDept": 1, "dept": 1, "hisWard": 1, "ward": 1},
    )
    if not patient:
        raise HTTPException(status_code=404, detail="患者不存在")

    patient_dept = patient.get("hisDept") or patient.get("dept") or ""
    patient_ward = patient.get("hisWard") or patient.get("ward") or ""

    # 科室匹配：用户科室 == 患者科室
    user_dept = current_user.dept or ""
    if user_dept and patient_dept and user_dept == patient_dept:
        return True

    # 授权科室列表：患者科室 ∈ 用户 allowed_depts
    user_allowed_depts = current_user.allowed_depts or []
    if user_allowed_depts and patient_dept and patient_dept in user_allowed_depts:
        return True

    # 授权病区列表：患者病区 ∈ 用户 allowed_wards
    user_allowed_wards = current_user.allowed_wards or []
    if user_allowed_wards and patient_ward and patient_ward in user_allowed_wards:
        return True

    # 无权访问（不泄漏患者科室信息）
    raise HTTPException(status_code=403, detail="无权访问该患者数据")
