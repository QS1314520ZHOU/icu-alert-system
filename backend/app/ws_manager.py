"""
ICU智能协同工作台 - WebSocket 连接管理（内部系统路由上下文，不依赖JWT）

路由上下文来源：连接参数 / 页面URL参数 / 前端页面上下文。
- routing_roles: 页面身份（nurse/doctor/pharmacist/head_nurse），由前端传入
- dept_code: 科室代码，由页面URL或当前登录科室决定
- patient_ids: 授权患者列表；空列表 = 接收本科室全部患者告警

安全原则：
  - 客户端 subscribe 只能缩小订阅范围
  - 广播按 routing_roles + dept_code + patient_ids 过滤
  - 浏览器语音仅辅助提示，记录投递结果
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
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

    def _normalize_str_list(self, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            items = [x.strip().lower() for x in value.split(",") if x.strip()]
        elif isinstance(value, (list, tuple, set)):
            items = [str(x).strip().lower() for x in value if str(x).strip()]
        else:
            return []
        deduped: list[str] = []
        seen: set[str] = set()
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return deduped

    # ═══════════════════════════════════════════════════════════════════════
    # 连接管理
    # ═══════════════════════════════════════════════════════════════════════

    async def connect(
        self,
        ws: WebSocket,
        *,
        accepted: bool = False,
        roles: Any = None,
        dept: str = "",
        dept_code: str = "",
        patient_ids: Any = None,
    ) -> None:
        """
        建立 WebSocket 连接。

        参数均从现有页面上下文获取（无JWT）：
          - roles: 页面角色，如 "nurse" / "doctor" / "pharmacist" / "head_nurse"
          - dept_code: 科室代码
          - patient_ids: 授权患者列表；空列表 = 接收本科室全部患者告警
        """
        if not accepted:
            await ws.accept()
        async with self._lock:
            self._clients.add(ws)
            self._client_meta[ws] = {
                "routing_roles": self._normalize_str_list(roles),
                "dept": str(dept or "").strip(),
                "dept_code": str(dept_code or "").strip(),
                "patient_ids": self._normalize_str_list(patient_ids),
                "connected_at": datetime.now(),
            }
        logger.info(f"WebSocket connected: {len(self._clients)} clients")

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)
            self._client_meta.pop(ws, None)
        logger.info(f"WebSocket disconnected: {len(self._clients)} clients")

    # ═══════════════════════════════════════════════════════════════════════
    # 订阅管理（仅缩小，不扩大）
    # ═══════════════════════════════════════════════════════════════════════

    async def subscribe_roles(self, ws: WebSocket, roles: Any) -> None:
        """客户端订阅角色：只能缩小已连接时的 routing_roles。"""
        async with self._lock:
            if ws not in self._clients:
                return
            meta = self._client_meta.setdefault(ws, {})
            current = set(self._normalize_str_list(meta.get("routing_roles")))
            requested = set(self._normalize_str_list(roles))
            # 如果当前无角色则接受请求的角色；否则只能缩小
            if not current:
                meta["routing_roles"] = sorted(requested)
            else:
                meta["routing_roles"] = sorted(current & requested)

    async def update_viewer_context(self, ws: WebSocket, context: dict[str, Any]) -> None:
        async with self._lock:
            if ws not in self._clients:
                return
            meta = self._client_meta.setdefault(ws, {})
            viewer = meta.setdefault("viewer_context", {})
            viewer.update({k: v for k, v in (context or {}).items() if v is not None})

    async def online_viewers(self) -> list[tuple[WebSocket, dict[str, Any]]]:
        async with self._lock:
            rows: list[tuple[WebSocket, dict[str, Any]]] = []
            for ws in self._clients:
                meta = dict(self._client_meta.get(ws) or {})
                meta["routing_roles"] = self._normalize_str_list(meta.get("routing_roles"))
                meta["viewer_context"] = dict(meta.get("viewer_context") or {})
                rows.append((ws, meta))
            return rows

    async def get_meta(self, ws: WebSocket) -> dict[str, Any]:
        async with self._lock:
            meta = dict(self._client_meta.get(ws) or {})
            meta["routing_roles"] = self._normalize_str_list(meta.get("routing_roles"))
            meta["viewer_context"] = dict(meta.get("viewer_context") or {})
            return meta

    # ═══════════════════════════════════════════════════════════════════════
    # 路由上下文解析
    # ═══════════════════════════════════════════════════════════════════════

    def _routing_roles(self, meta: dict[str, Any]) -> set[str]:
        return set(self._normalize_str_list(meta.get("routing_roles")))

    def _has_access_to_patient(self, meta: dict[str, Any], patient_id: str | None) -> bool:
        """patient_ids 为空 → 接收本科室全部患者。"""
        if not patient_id:
            return True
        allowed = self._normalize_str_list(meta.get("patient_ids"))
        if not allowed:
            return True  # 空 = 本科室全部
        return str(patient_id) in allowed

    def _matches_dept(self, meta: dict[str, Any], dept: str | None, dept_code: str | None) -> bool:
        if not dept and not dept_code:
            return True
        conn_dept = str(meta.get("dept", "")).strip()
        conn_code = str(meta.get("dept_code", "")).strip()
        if not conn_dept and not conn_code:
            return True  # 未设置科室上下文 → 全部可见
        if dept and conn_dept and dept == conn_dept:
            return True
        if dept_code and conn_code and dept_code == conn_code:
            return True
        return False

    # ═══════════════════════════════════════════════════════════════════════
    # 消息发送
    # ═══════════════════════════════════════════════════════════════════════

    async def send_to(self, ws: WebSocket, message: dict[str, Any]) -> bool:
        data = json.dumps(message, ensure_ascii=False, default=str)
        try:
            await ws.send_text(data)
            return True
        except Exception:
            async with self._lock:
                self._clients.discard(ws)
                self._client_meta.pop(ws, None)
            return False

    async def broadcast(
        self,
        message: dict[str, Any],
        *,
        roles: Any = None,
        dept: str = "",
        dept_code: str = "",
        patient_id: str = "",
        alert_domain: str = "",
    ) -> dict[str, int]:
        """
        按 routing_roles + dept_code + patient_ids 过滤广播。

        无 routing_roles 的连接不接收角色定向消息（除非未指定 route_roles）。
        返回投递统计。
        """
        route_roles = set(self._normalize_str_list(roles))
        data = json.dumps(message, ensure_ascii=False, default=str)

        stats: dict[str, int] = {
            "attempted": 0, "delivered": 0, "failed": 0,
            "skipped_role": 0, "skipped_dept": 0, "skipped_patient": 0,
        }

        async with self._lock:
            targets = list(self._clients)

        if not targets:
            return stats

        dead: list[WebSocket] = []
        for ws in targets:
            stats["attempted"] += 1
            meta = self._client_meta.get(ws, {})
            client_roles = self._routing_roles(meta)

            # 角色过滤：仅当指定了 route_roles 时才过滤
            if route_roles and client_roles and not (route_roles & client_roles):
                stats["skipped_role"] += 1
                continue

            # 科室过滤
            if not self._matches_dept(meta, dept, dept_code):
                stats["skipped_dept"] += 1
                continue

            # 患者权限过滤
            if not self._has_access_to_patient(meta, patient_id):
                stats["skipped_patient"] += 1
                continue

            try:
                await ws.send_text(data)
                stats["delivered"] += 1
            except Exception:
                dead.append(ws)
                stats["failed"] += 1

        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)
                    self._client_meta.pop(ws, None)

        return stats

    # ═══════════════════════════════════════════════════════════════════════
    # WebSocket 端点上下文辅助
    # ═══════════════════════════════════════════════════════════════════════

    @staticmethod
    def extract_context(
        headers: dict[str, str] | None = None,
        query_params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        从 WebSocket 连接参数中提取路由上下文（内部系统，无JWT）。

        返回：
          {
            "routing_roles": [...],
            "dept": "",
            "dept_code": "",
            "patient_ids": [...],
          }
        """
        headers = headers or {}
        query_params = query_params or {}

        # 角色：header 或 query param
        role_src = headers.get("x-routing-roles") or query_params.get("roles") or query_params.get("role") or ""
        routing_roles = [r.strip().lower() for r in role_src.split(",") if r.strip()]

        dept = headers.get("x-dept") or query_params.get("dept") or ""
        dept_code = headers.get("x-dept-code") or query_params.get("dept_code") or query_params.get("deptCode") or ""

        patient_src = headers.get("x-patient-ids") or query_params.get("patient_ids") or ""
        patient_ids = [p.strip() for p in patient_src.split(",") if p.strip()]

        return {
            "routing_roles": routing_roles,
            "dept": dept,
            "dept_code": dept_code,
            "patient_ids": patient_ids,
        }

    # ═══════════════════════════════════════════════════════════════════════
    # Redis PubSub 中继
    # ═══════════════════════════════════════════════════════════════════════

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
        await self.broadcast(
            {
                "type": message_type,
                "data": payload.get("data"),
                "alert_domain": payload.get("alert_domain", ""),
                "priority": payload.get("priority", ""),
            },
            roles=payload.get("roles"),
            dept=payload.get("dept", ""),
            dept_code=payload.get("deptCode", ""),
            patient_id=payload.get("patient_id", ""),
            alert_domain=payload.get("alert_domain", ""),
        )
