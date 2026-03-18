from __future__ import annotations

import secrets

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


def ws_origin_allowed(origin: str | None) -> bool:
    if not origin:
        return False
    return origin in set(_config().cors_allowed_origins)


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
    if origin and not ws_origin_allowed(origin):
        return False
    if not ws_token_required():
        return ws_origin_allowed(origin)

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
