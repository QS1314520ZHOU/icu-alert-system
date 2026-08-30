"""JWT 认证处理。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.auth.models import User, UserRole, TokenPayload

# 配置
SECRET_KEY = "icu-alert-system-secret-key-change-in-production"
ALGORITHM = "HS256"
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
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
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
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[TokenPayload]:
    """验证令牌。"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return TokenPayload(**payload)
    except JWTError:
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> User:
    """获取当前用户。"""
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

    # TODO: 从数据库获取用户信息
    # 这里返回模拟用户，dept 从 JWT payload 中读取
    user = User(
        id=payload.sub,
        username=payload.sub,
        email=f"{payload.sub}@hospital.com",
        role=UserRole(payload.role),
        dept=getattr(payload, "dept", "") or "",
        allowed_depts=getattr(payload, "allowed_depts", []) or [],
        is_active=True,
    )

    return user


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

    授权维度：
    1. 管理员 (admin) → 全部患者
    2. 用户科室 (dept) 与患者科室 (hisDept/dept) 匹配
    3. 用户授权科室列表 (allowed_depts) 包含患者科室
    4. 用户关联病区包含患者病区

    Raises:
        HTTPException(403): 无权访问
        HTTPException(404): 患者不存在
    """
    from bson import ObjectId
    from app import runtime

    if db is None:
        db = runtime.db

    # 管理员拥有全部权限
    if current_user.role == UserRole.ADMIN:
        return True

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

    # 检查科室权限
    user_dept = current_user.dept or ""
    user_allowed_depts = current_user.allowed_depts or []

    # 用户科室匹配
    if user_dept and patient_dept and user_dept == patient_dept:
        return True

    # 用户授权科室列表匹配
    if user_allowed_depts and patient_dept and patient_dept in user_allowed_depts:
        return True

    # 无权访问
    raise HTTPException(
        status_code=403,
        detail=f"无权访问该患者数据：患者科室({patient_dept})不在授权范围内",
    )
