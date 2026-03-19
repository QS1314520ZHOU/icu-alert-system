"""
ICU智能预警系统 - WebSocket 连接管理
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket
from app.alert_engine.task_queue import relay_pubsub_forever

logger = logging.getLogger("icu-alert")


class WebSocketManager:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._client_meta: dict[WebSocket, dict[str, Any]] = {}
        self._lock = asyncio.Lock()
        self._redis_stop = asyncio.Event()
        self._redis_task: asyncio.Task | None = None

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

    async def start_redis_relay(self, redis_client: Any, channel: str) -> None:
        if not redis_client or self._redis_task:
            return
        self._redis_stop.clear()
        self._redis_task = asyncio.create_task(
            relay_pubsub_forever(
                redis_client=redis_client,
                channel=channel,
                stop_event=self._redis_stop,
                handler=self._handle_pubsub_message,
            ),
            name="ws-redis-relay",
        )

    async def stop_redis_relay(self) -> None:
        self._redis_stop.set()
        if self._redis_task:
            self._redis_task.cancel()
            await asyncio.gather(self._redis_task, return_exceptions=True)
            self._redis_task = None

    async def _handle_pubsub_message(self, payload: dict[str, Any]) -> None:
        message_type = str(payload.get("type") or "").strip()
        if not message_type:
            return
        roles = payload.get("roles")
        await self.broadcast(
            {"type": message_type, "data": payload.get("data")},
            roles=roles,
        )
