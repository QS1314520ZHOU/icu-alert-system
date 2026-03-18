"""
ICU智能预警系统 - WebSocket 连接管理
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("icu-alert")


class WebSocketManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._client_meta: dict[WebSocket, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    def _normalize_roles(self, roles: Any) -> list[str]:
        if roles is None:
            return []
        if isinstance(roles, str):
            items = [x.strip().lower() for x in roles.split(",")]
        elif isinstance(roles, (list, tuple, set)):
            items = [str(x).strip().lower() for x in roles]
        else:
            return []
        deduped: list[str] = []
        seen: set[str] = set()
        for item in items:
            if not item or item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return deduped

    async def connect(self, ws: WebSocket, *, accepted: bool = False, roles: Any = None) -> None:
        if not accepted:
            await ws.accept()
        async with self._lock:
            self._clients.add(ws)
            self._client_meta[ws] = {"roles": self._normalize_roles(roles)}
        logger.info(f"WebSocket connected: {len(self._clients)} clients")

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)
            self._client_meta.pop(ws, None)
        logger.info(f"WebSocket disconnected: {len(self._clients)} clients")

    async def subscribe_roles(self, ws: WebSocket, roles: Any) -> None:
        async with self._lock:
            if ws not in self._clients:
                return
            meta = self._client_meta.setdefault(ws, {})
            meta["roles"] = self._normalize_roles(roles)

    async def broadcast(self, message: dict[str, Any], *, roles: Any = None) -> None:
        data = json.dumps(message, ensure_ascii=False, default=str)
        route_roles = set(self._normalize_roles(roles))
        async with self._lock:
            targets = list(self._clients)
        if not targets:
            return
        dead: list[WebSocket] = []
        for ws in targets:
            try:
                if route_roles:
                    client_roles = set(self._normalize_roles((self._client_meta.get(ws) or {}).get("roles")))
                    if client_roles and not (client_roles & route_roles):
                        continue
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)
                    self._client_meta.pop(ws, None)
