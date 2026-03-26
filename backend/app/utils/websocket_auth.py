from __future__ import annotations

import secrets
from urllib.parse import urlparse

from fastapi import WebSocket
from jose import JWTError, jwt

from app import runtime
from app.config import get_config


_bootstrap_config = get_config()


def _config():
    return runtime.config or _bootstrap_config


def get_valid_ws_tokens() -> list[str]:
    return _config().websocket_tokens


def ws_token_required() -> bool:
    return _config().websocket_require_token


def ws_origin_allowed(origin: str | None, request_host: str | None = None) -> bool:
    if not origin:
        return False
    allowed = set(_config().cors_allowed_origins)
    if origin in allowed:
        return True

    try:
        parsed = urlparse(origin)
        origin_host = str(parsed.netloc or "").strip().lower()
    except Exception:
        origin_host = ""

    normalized_request_host = str(request_host or "").strip().lower()
    if origin_host and normalized_request_host and origin_host == normalized_request_host:
        return True
    return False


def extract_ws_token(ws: WebSocket) -> str:
    auth = ws.headers.get("authorization") or ws.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    for key in ("token", "access_token", "ws_token"):
        value = ws.query_params.get(key)
        if value:
            return str(value).strip()
    header_token = ws.headers.get("x-ws-token") or ws.headers.get("x-access-token")
    return str(header_token or "").strip()


def extract_ws_roles(ws: WebSocket) -> list[str]:
    raw = ws.query_params.get("roles") or ws.query_params.get("role") or ""
    if not raw:
        return []
    roles: list[str] = []
    seen: set[str] = set()
    for item in str(raw).split(","):
        role = item.strip().lower()
        if not role or role in seen:
            continue
        seen.add(role)
        roles.append(role)
    return roles


def is_ws_authorized(ws: WebSocket) -> bool:
    origin = ws.headers.get("origin") or ws.headers.get("Origin")
    request_host = ws.headers.get("host") or ws.headers.get("Host")
    if origin and not ws_origin_allowed(origin, request_host=request_host):
        return False
    if not ws_token_required():
        return ws_origin_allowed(origin, request_host=request_host)

    token = extract_ws_token(ws)
    if not token:
        return False

    cfg = _config()
    jwt_secret = cfg.ws_token_secret
    jwt_algorithm = cfg.ws_token_algorithm
    if jwt_secret and "." in token:
        try:
            jwt.decode(token, jwt_secret, algorithms=[jwt_algorithm])
            return True
        except JWTError:
            return False

    for valid in get_valid_ws_tokens():
        if valid and secrets.compare_digest(token, valid):
            return True
    return False
