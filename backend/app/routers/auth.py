"""认证路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import (
    create_access_token,
    create_refresh_token,
    get_current_user,
    verify_password,
    get_password_hash,
    verify_token,
)
from app.auth.models import (
    User,
    UserCreate,
    UserLogin,
    TokenResponse,
    UserRole,
)

router = APIRouter(prefix="/api/auth", tags=["认证"])

# 模拟用户数据库（生产环境应使用 MongoDB）
_users: dict[str, dict] = {
    "admin": {
        "id": "admin",
        "username": "admin",
        "email": "admin@hospital.com",
        "password_hash": get_password_hash("admin123"),
        "role": UserRole.ADMIN,
        "is_active": True,
    },
    "doctor": {
        "id": "doctor",
        "username": "doctor",
        "email": "doctor@hospital.com",
        "password_hash": get_password_hash("doctor123"),
        "role": UserRole.DOCTOR,
        "is_active": True,
    },
    "nurse": {
        "id": "nurse",
        "username": "nurse",
        "email": "nurse@hospital.com",
        "password_hash": get_password_hash("nurse123"),
        "role": UserRole.NURSE,
        "is_active": True,
    },
}


@router.post("/login", response_model=TokenResponse)
async def login(request: UserLogin):
    """用户登录。"""
    user = _users.get(request.username)

    if not user or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用",
        )

    # 创建令牌
    token_data = {
        "sub": user["id"],
        "role": user["role"],
    }

    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=30 * 60,  # 30 分钟
    )


@router.post("/register", response_model=User)
async def register(request: UserCreate):
    """用户注册。"""
    # 检查用户名是否已存在
    if request.username in _users:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在",
        )

    # 创建用户
    user_id = f"user_{len(_users) + 1}"
    user = {
        "id": user_id,
        "username": request.username,
        "email": request.email,
        "password_hash": get_password_hash(request.password),
        "role": request.role,
        "is_active": True,
    }

    _users[request.username] = user

    return User(
        id=user_id,
        username=request.username,
        email=request.email,
        role=request.role,
        is_active=True,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(refresh_token: str):
    """刷新令牌。"""
    payload = verify_token(refresh_token)

    if not payload or payload.type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的刷新令牌",
        )

    # 创建新令牌
    token_data = {
        "sub": payload.sub,
        "role": payload.role,
    }

    new_access_token = create_access_token(token_data)
    new_refresh_token = create_refresh_token(token_data)

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        expires_in=30 * 60,
    )


@router.get("/me", response_model=User)
async def get_me(current_user: User = Depends(get_current_user)):
    """获取当前用户信息。"""
    return current_user


@router.get("/users", response_model=list[User])
async def list_users(current_user: User = Depends(get_current_user)):
    """获取用户列表（仅管理员）。"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足",
        )

    return [
        User(
            id=user["id"],
            username=user["username"],
            email=user["email"],
            role=user["role"],
            is_active=user["is_active"],
        )
        for user in _users.values()
    ]
