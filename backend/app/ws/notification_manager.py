"""WebSocket 通知管理器。"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class NotificationManager:
    """WebSocket 通知管理器。"""

    def __init__(self):
        # 用户连接: {user_id: WebSocket}
        self._connections: dict[str, WebSocket] = {}
        # 房间: {room_id: set(user_id)}
        self._rooms: dict[str, set[str]] = {}
        # 消息队列
        self._message_queue: asyncio.Queue = asyncio.Queue()

    async def connect(self, user_id: str, websocket: WebSocket):
        """用户连接。"""
        await websocket.accept()
        self._connections[user_id] = websocket
        logger.info(f"用户 {user_id} 已连接")

        # 发送欢迎消息
        await self.send_to_user(user_id, {
            "type": "connected",
            "message": "连接成功",
            "timestamp": datetime.utcnow().isoformat(),
        })

    async def disconnect(self, user_id: str):
        """用户断开连接。"""
        if user_id in self._connections:
            del self._connections[user_id]

        # 从所有房间移除
        for room_id in list(self._rooms.keys()):
            self._rooms[room_id].discard(user_id)
            if not self._rooms[room_id]:
                del self._rooms[room_id]

        logger.info(f"用户 {user_id} 已断开连接")

    async def join_room(self, user_id: str, room_id: str):
        """加入房间。"""
        if room_id not in self._rooms:
            self._rooms[room_id] = set()
        self._rooms[room_id].add(user_id)
        logger.info(f"用户 {user_id} 加入房间 {room_id}")

    async def leave_room(self, user_id: str, room_id: str):
        """离开房间。"""
        if room_id in self._rooms:
            self._rooms[room_id].discard(user_id)
            if not self._rooms[room_id]:
                del self._rooms[room_id]
        logger.info(f"用户 {user_id} 离开房间 {room_id}")

    async def send_to_user(self, user_id: str, message: dict[str, Any]):
        """发送消息给指定用户。"""
        websocket = self._connections.get(user_id)
        if websocket:
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.error(f"发送消息给用户 {user_id} 失败: {e}")
                await self.disconnect(user_id)

    async def send_to_room(self, room_id: str, message: dict[str, Any]):
        """发送消息给房间内所有用户。"""
        user_ids = self._rooms.get(room_id, set())
        for user_id in user_ids:
            await self.send_to_user(user_id, message)

    async def broadcast(self, message: dict[str, Any]):
        """广播消息给所有用户。"""
        for user_id in list(self._connections.keys()):
            await self.send_to_user(user_id, message)

    async def notify_alert(self, alert: dict[str, Any]):
        """发送告警通知。"""
        message = {
            "type": "alert",
            "data": alert,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # 发送给相关科室
        department_id = alert.get("department_id")
        if department_id:
            await self.send_to_room(f"department:{department_id}", message)

        # 广播给管理员
        await self.send_to_room("admin", message)

    async def notify_disease_update(self, disease: dict[str, Any]):
        """发送病种更新通知。"""
        message = {
            "type": "disease_update",
            "data": disease,
            "timestamp": datetime.utcnow().isoformat(),
        }
        await self.broadcast(message)

    async def notify_review_status(self, review: dict[str, Any]):
        """发送审核状态通知。"""
        message = {
            "type": "review_status",
            "data": review,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # 发送给提交者
        submitter_id = review.get("submitter_id")
        if submitter_id:
            await self.send_to_user(submitter_id, message)

        # 发送给审核者
        reviewer_id = review.get("reviewer_id")
        if reviewer_id:
            await self.send_to_user(reviewer_id, message)

    def get_online_users(self) -> list[str]:
        """获取在线用户列表。"""
        return list(self._connections.keys())

    def get_room_users(self, room_id: str) -> list[str]:
        """获取房间内用户列表。"""
        return list(self._rooms.get(room_id, set()))

    def is_user_online(self, user_id: str) -> bool:
        """检查用户是否在线。"""
        return user_id in self._connections


# 全局通知管理器实例
notification_manager = NotificationManager()
