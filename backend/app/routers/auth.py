"""认证路由。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

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

_auth_logger = logging.getLogger("icu-auth")

router = APIRouter(prefix="/api/auth", tags=["认证"])


async def _find_user(http_request: Request, username: str) -> dict | None:
    """查找用户：先内存，再 MongoDB。"""
    # 内存用户
    _memory_users: dict[str, dict] = {
        "admin": {
            "id": "admin", "username": "admin", "email": "admin@hospital.com",
            "password_hash": get_password_hash("admin123"),
            "role": UserRole.ADMIN, "is_active": True,
        },
        "doctor": {
            "id": "doctor", "username": "doctor", "email": "doctor@hospital.com",
            "password_hash": get_password_hash("doctor123"),
            "role": UserRole.DOCTOR, "is_active": True,
        },
        "nurse": {
            "id": "nurse", "username": "nurse", "email": "nurse@hospital.com",
            "password_hash": get_password_hash("nurse123"),
            "role": UserRole.NURSE, "is_active": True,
        },
    }
    user = _memory_users.get(username)
    if user:
        return user

    # MongoDB 用户
    try:
        db = getattr(http_request.app.state, "db", None)
        if db is not None:
            db_record = await db.col("users").find_one({"username": username})
            if db_record:
                return {
                    "id": str(db_record["_id"]),
                    "username": db_record["username"],
                    "email": db_record.get("email", ""),
                    "password_hash": db_record["password_hash"],
                    "role": db_record.get("role", "doctor"),
                    "is_active": db_record.get("is_active", True),
                }
    except Exception as exc:
        _auth_logger.warning("MongoDB login lookup failed: %s", exc, exc_info=True)

    return None


@router.post("/login", response_model=TokenResponse)
async def login(login_req: UserLogin, http_request: Request):
    """用户登录。"""
    user = await _find_user(http_request, login_req.username)

    if not user or not verify_password(login_req.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用",
        )

    token_data = {"sub": user["username"], "role": user["role"]}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=30 * 60,
    )


@router.post("/register", response_model=User)
async def register(request: UserCreate, http_request: Request):
    """用户注册。"""
    existing = await _find_user(http_request, request.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在",
        )

    user_id = f"user_{request.username}"
    user_doc = {
        "username": request.username,
        "email": request.email,
        "password_hash": get_password_hash(request.password),
        "role": request.role.value if hasattr(request.role, "value") else request.role,
        "is_active": True,
    }

    # 保存到 MongoDB
    try:
        db = getattr(http_request.app.state, "db", None)
        if db is not None:
            result = await db.col("users").insert_one(user_doc)
            user_id = str(result.inserted_id)
    except Exception as exc:
        _auth_logger.warning("MongoDB register failed: %s", exc)

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

    token_data = {"sub": payload.sub, "role": payload.role}
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
async def list_users(http_request: Request, current_user: User = Depends(get_current_user)):
    """获取用户列表（仅管理员）。"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="权限不足",
        )

    results = []
    # 内存用户
    results.append(User(id="admin", username="admin", email="admin@hospital.com", role=UserRole.ADMIN, is_active=True))
    results.append(User(id="doctor", username="doctor", email="doctor@hospital.com", role=UserRole.DOCTOR, is_active=True))
    results.append(User(id="nurse", username="nurse", email="nurse@hospital.com", role=UserRole.NURSE, is_active=True))

    # MongoDB 用户
    try:
        db = getattr(http_request.app.state, "db", None)
        if db is not None:
            async for doc in db.col("users").find({}):
                results.append(User(
                    id=str(doc["_id"]),
                    username=doc["username"],
                    email=doc.get("email", ""),
                    role=UserRole(doc.get("role", "doctor")),
                    is_active=doc.get("is_active", True),
                ))
    except Exception as exc:
        _auth_logger.warning("MongoDB list users failed: %s", exc)

    return results


# ===== 宿主 iframe 认证 =====


class IframeExchangeRequest(BaseModel):
    """iframe 授权码交换请求。"""
    authorization_code: str
    nonce: str


@router.post("/iframe/exchange")
async def iframe_exchange(req: IframeExchangeRequest):
    """向宿主后端校验一次性授权码，签发 ICU 访问令牌。

    流程：
    1. 宿主后端生成一次性授权码
    2. 宿主页面通过 postMessage 发送给 iframe
    3. iframe 调用此接口交换
    4. ICU 后端向宿主后端校验授权码
    5. ICU 后端签发短期访问 Token
    """
    from app.auth.iframe_auth import _load_config, exchange_authorization_code

    config = _load_config()

    if not config.exchange_url:
        raise HTTPException(
            status_code=501,
            detail="授权码交换功能未配置",
        )

    user = await exchange_authorization_code(
        code=req.authorization_code,
        nonce=req.nonce,
        config=config,
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="授权码验证失败",
        )

    # 签发 ICU 访问令牌
    token_data = {
        "sub": user.user_id,
        "role": user.role,
        "dept": ",".join(user.department_ids),
    }
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": 30 * 60,
        "user_id": user.user_id,
        "user_name": user.user_name,
        "role": user.role,
        "department_ids": user.department_ids,
    }


@router.get("/iframe/status")
async def iframe_status():
    """获取 iframe 认证配置状态。"""
    from app.auth.iframe_auth import _load_config

    config = _load_config()

    return {
        "jwt_configured": bool(config.jwt_secret_key),
        "jwks_configured": bool(config.jwks_url),
        "exchange_configured": bool(config.exchange_url),
        "dev_mode": config.dev_mode,
        "allowed_origins": config.allowed_origins,
    }
