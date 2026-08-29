"""通知路由。"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends

from app.auth import get_current_user, verify_token
from app.auth.models import User
from app.ws import notification_manager

router = APIRouter(prefix="/notifications", tags=["通知"])


@router.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    """WebSocket 连接端点。"""
    # 验证令牌（从查询参数获取）
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="缺少认证令牌")
        return

    payload = verify_token(token)
    if not payload:
        await websocket.close(code=4001, reason="无效的认证令牌")
        return

    # 连接
    await notification_manager.connect(user_id, websocket)

    try:
        while True:
            # 接收消息
            data = await websocket.receive_json()

            # 处理消息
            message_type = data.get("type")

            if message_type == "join_room":
                room_id = data.get("room_id")
                if room_id:
                    await notification_manager.join_room(user_id, room_id)

            elif message_type == "leave_room":
                room_id = data.get("room_id")
                if room_id:
                    await notification_manager.leave_room(user_id, room_id)

            elif message_type == "ping":
                await notification_manager.send_to_user(user_id, {
                    "type": "pong",
                    "timestamp": data.get("timestamp"),
                })

    except WebSocketDisconnect:
        await notification_manager.disconnect(user_id)
    except Exception as e:
        await notification_manager.disconnect(user_id)


@router.get("/online-users")
async def get_online_users(current_user: User = Depends(get_current_user)):
    """获取在线用户列表。"""
    return {
        "users": notification_manager.get_online_users(),
        "count": len(notification_manager.get_online_users()),
    }


@router.get("/room/{room_id}/users")
async def get_room_users(room_id: str, current_user: User = Depends(get_current_user)):
    """获取房间内用户列表。"""
    return {
        "room_id": room_id,
        "users": notification_manager.get_room_users(room_id),
        "count": len(notification_manager.get_room_users(room_id)),
    }


@router.post("/send/{user_id}")
async def send_notification(
    user_id: str,
    message: dict,
    current_user: User = Depends(get_current_user)
):
    """发送通知给指定用户。"""
    await notification_manager.send_to_user(user_id, {
        "type": "notification",
        "data": message,
        "from": current_user.id,
    })
    return {"success": True}


@router.post("/broadcast")
async def broadcast_notification(
    message: dict,
    current_user: User = Depends(get_current_user)
):
    """广播通知。"""
    if current_user.role != "admin":
        return {"error": "权限不足"}

    await notification_manager.broadcast({
        "type": "broadcast",
        "data": message,
        "from": current_user.id,
    })
    return {"success": True}
