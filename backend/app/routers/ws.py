from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app import runtime
from app.utils.websocket_auth import extract_ws_roles, is_ws_authorized

router = APIRouter()


@router.websocket("/ws/alerts")
async def ws_alerts(ws: WebSocket):
    if not is_ws_authorized(ws):
        await ws.close(code=4001, reason="Unauthorized")
        return
    await runtime.ws_mgr.connect(ws, roles=extract_ws_roles(ws))
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data) if data else {}
            if msg.get("type") == "ping":
                await ws.send_json({"type": "pong"})
            elif msg.get("type") == "subscribe":
                await runtime.ws_mgr.subscribe_roles(ws, msg.get("roles") or msg.get("role"))
                await ws.send_json({"type": "subscribed", "roles": msg.get("roles") or msg.get("role") or []})
    except WebSocketDisconnect:
        await runtime.ws_mgr.disconnect(ws)
    except Exception:
        await runtime.ws_mgr.disconnect(ws)
