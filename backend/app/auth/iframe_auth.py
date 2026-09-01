"""宿主 iframe 认证模块。

支持两种认证方式：
1. 宿主签发的 JWT（后端验证签名）
2. 一次性授权码交换（向宿主后端校验）

后端不信任任何前端传入的操作者身份。
操作者身份最终从验证通过的宿主认证上下文中取得。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from jose import JWTError, jwt
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class CurrentUser(BaseModel):
    """当前认证用户。

    从验证通过的宿主认证上下文中取得。
    """
    user_id: str
    user_name: str | None = None
    tenant_id: str = ""
    hospital_id: str | None = None
    department_ids: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    session_id: str | None = None
    token_id: str | None = None
    issued_at: datetime | None = None
    expires_at: datetime | None = None

    @property
    def role(self) -> str:
        """获取主角色（兼容旧接口）。"""
        return self.roles[0] if self.roles else "viewer"

    @property
    def dept(self) -> str:
        """获取主科室（兼容旧接口）。"""
        return self.department_ids[0] if self.department_ids else ""


class IframeAuthConfig(BaseModel):
    """iframe 认证配置。"""
    # JWT 验证
    jwt_secret_key: str = ""
    jwt_algorithms: list[str] = Field(default=["HS256"])
    jwt_issuer: str = ""
    jwt_audience: str = ""

    # JWKS（用于宿主公钥验证）
    jwks_url: str = ""

    # 授权码交换
    exchange_url: str = ""  # 宿主后端授权码校验 URL
    exchange_secret: str = ""

    # 允许的宿主 origin
    allowed_origins: list[str] = Field(default_factory=list)

    # 开发模式
    dev_mode: bool = False
    mock_user_id: str = ""
    mock_user_name: str = ""
    mock_role: str = "doctor"

    class Config:
        env_prefix = "IFRAME_AUTH_"


def _load_config() -> IframeAuthConfig:
    """加载 iframe 认证配置。"""
    from app.config import get_config
    cfg = get_config()

    # 从 YAML 配置读取
    iframe_cfg = cfg.yaml_cfg.get("iframe_auth", {})

    return IframeAuthConfig(
        jwt_secret_key=iframe_cfg.get("jwt_secret_key", cfg.settings.SECRET_KEY),
        jwt_algorithms=iframe_cfg.get("jwt_algorithms", ["HS256"]),
        jwt_issuer=iframe_cfg.get("jwt_issuer", ""),
        jwt_audience=iframe_cfg.get("jwt_audience", ""),
        jwks_url=iframe_cfg.get("jwks_url", ""),
        exchange_url=iframe_cfg.get("exchange_url", ""),
        exchange_secret=iframe_cfg.get("exchange_secret", ""),
        allowed_origins=iframe_cfg.get("allowed_origins", []),
        dev_mode=iframe_cfg.get("dev_mode", False),
        mock_user_id=iframe_cfg.get("mock_user_id", ""),
        mock_user_name=iframe_cfg.get("mock_user_name", ""),
        mock_role=iframe_cfg.get("mock_role", "doctor"),
    )


# JWKS 缓存
_jwks_cache: dict[str, Any] = {}
_jwks_cache_time: float = 0
_JWKS_CACHE_TTL = 3600  # 1 hour


async def _get_jwks(jwks_url: str) -> dict[str, Any]:
    """获取 JWKS（带缓存）。"""
    global _jwks_cache, _jwks_cache_time

    now = time.time()
    if _jwks_cache and (now - _jwks_cache_time) < _JWKS_CACHE_TTL:
        return _jwks_cache

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(jwks_url)
        resp.raise_for_status()
        _jwks_cache = resp.json()
        _jwks_cache_time = now
        return _jwks_cache


def _find_key(jwks: dict[str, Any], kid: str) -> Optional[str]:
    """从 JWKS 中找到对应的公钥。"""
    for key in jwks.get("keys", []):
        if key.get("kid") == kid:
            # 返回 PEM 格式的公钥
            from jose.utils import long_to_base64
            import base64

            n = key.get("n", "")
            e = key.get("e", "")

            if n and e:
                # 构建 RSA 公钥
                try:
                    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicNumbers
                    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

                    n_bytes = base64.urlsafe_b64decode(n + "==")
                    e_bytes = base64.urlsafe_b64decode(e + "==")

                    n_int = int.from_bytes(n_bytes, "big")
                    e_int = int.from_bytes(e_bytes, "big")

                    public_numbers = RSAPublicNumbers(e_int, n_int)
                    public_key = public_numbers.public_key()
                    pem = public_key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
                    return pem.decode()
                except Exception as e:
                    logger.warning(f"Failed to construct RSA public key: {e}")

    return None


async def verify_host_jwt(token: str, config: IframeAuthConfig) -> Optional[CurrentUser]:
    """验证宿主签发的 JWT。

    Returns:
        CurrentUser if valid, None otherwise.
    """
    try:
        # 先解析 header 获取 kid
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid", "")

        # 确定验证密钥
        key = config.jwt_secret_key

        if config.jwks_url and kid:
            # 使用 JWKS
            jwks = await _get_jwks(config.jwks_url)
            key = _find_key(jwks, kid) or key

        # 禁止 alg=none
        algorithms = [a for a in config.jwt_algorithms if a.upper() != "NONE"]
        if not algorithms:
            algorithms = ["HS256"]

        # 验证 JWT
        payload = jwt.decode(
            token,
            key,
            algorithms=algorithms,
            issuer=config.jwt_issuer or None,
            audience=config.jwt_audience or None,
            options={
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iat": True,
                "verify_iss": bool(config.jwt_issuer),
                "verify_aud": bool(config.jwt_audience),
            },
        )

        # 构建 CurrentUser
        user_id = payload.get("sub") or payload.get("user_id") or ""
        if not user_id:
            logger.warning("JWT missing 'sub' or 'user_id' claim")
            return None

        return CurrentUser(
            user_id=user_id,
            user_name=payload.get("user_name") or payload.get("name"),
            tenant_id=payload.get("tenant_id", ""),
            hospital_id=payload.get("hospital_id"),
            department_ids=payload.get("department_ids") or payload.get("dept_ids", []),
            roles=payload.get("roles") or [payload.get("role", "viewer")],
            permissions=payload.get("permissions", []),
            session_id=payload.get("session_id"),
            token_id=payload.get("jti"),
            issued_at=datetime.fromtimestamp(payload["iat"], tz=timezone.utc) if "iat" in payload else None,
            expires_at=datetime.fromtimestamp(payload["exp"], tz=timezone.utc) if "exp" in payload else None,
        )

    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during JWT verification: {e}")
        return None


async def exchange_authorization_code(
    code: str,
    nonce: str,
    config: IframeAuthConfig,
) -> Optional[CurrentUser]:
    """向宿主后端校验一次性授权码。

    Returns:
        CurrentUser if valid, None otherwise.
    """
    if not config.exchange_url:
        logger.error("Exchange URL not configured")
        return None

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                config.exchange_url,
                json={
                    "authorization_code": code,
                    "nonce": nonce,
                },
                headers={
                    "Content-Type": "application/json",
                    "X-Exchange-Secret": config.exchange_secret,
                },
            )

            if resp.status_code != 200:
                logger.warning(f"Authorization code exchange failed: {resp.status_code}")
                return None

            data = resp.json()

            user_id = data.get("user_id") or data.get("sub") or ""
            if not user_id:
                logger.warning("Exchange response missing user_id")
                return None

            return CurrentUser(
                user_id=user_id,
                user_name=data.get("user_name") or data.get("name"),
                tenant_id=data.get("tenant_id", ""),
                hospital_id=data.get("hospital_id"),
                department_ids=data.get("department_ids") or data.get("dept_ids", []),
                roles=data.get("roles") or [data.get("role", "viewer")],
                permissions=data.get("permissions", []),
                session_id=data.get("session_id"),
                token_id=data.get("token_id"),
                expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            )

    except Exception as e:
        logger.error(f"Authorization code exchange error: {e}")
        return None


def get_mock_user(config: IframeAuthConfig) -> Optional[CurrentUser]:
    """获取开发模式的模拟用户。

    仅在 dev_mode=True 时返回。
    production 环境禁止使用。
    """
    if not config.dev_mode:
        return None

    import os
    env = os.getenv("APP_ENV", "development")
    if env == "production":
        logger.error("Mock auth is NOT allowed in production!")
        return None

    if not config.mock_user_id:
        return None

    return CurrentUser(
        user_id=config.mock_user_id,
        user_name=config.mock_user_name,
        roles=[config.mock_role],
        permissions=[],
        expires_at=datetime.now(timezone.utc).replace(hour=23, minute=59, second=59),
    )
