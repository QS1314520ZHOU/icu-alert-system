from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app import runtime
from app.utils.websocket_auth import extract_ws_roles, is_ws_authorized
from app.utils.serialization import serialize_doc

router = APIRouter()


def resolve_ws_actor_identity(ws: WebSocket, raw_actor: str | None, source: str = "") -> str:
    candidates = [
        raw_actor,
        ws.headers.get("x-user-id"),
        ws.headers.get("x-actor-id"),
        ws.headers.get("x-operator-id"),
        ws.headers.get("x-forwarded-user"),
        ws.headers.get("x-user-name"),
        ws.headers.get("remote-user"),
    ]
    for item in candidates:
        value = runtime.alert_engine._normalize_lifecycle_actor(str(item or "").strip(), source=source)
        if value:
            return value
    return ""


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
            elif msg.get("type") == "alert_viewed":
                alert_ids = msg.get("alert_ids") if isinstance(msg.get("alert_ids"), list) else []
                source = str(msg.get("source") or "websocket").strip() or "websocket"
                modified = await runtime.alert_engine.mark_alerts_viewed(
                    [str(item) for item in alert_ids if str(item or "").strip()],
                    actor=resolve_ws_actor_identity(ws, str(msg.get("actor") or "").strip(), source=source),
                    source=source,
                )
                await ws.send_json({"type": "alert_viewed_ack", "modified": modified})
            elif msg.get("type") == "alert_acknowledge":
                alert_id = str(msg.get("alert_id") or "").strip()
                record = await runtime.alert_engine.acknowledge_alert(
                    alert_id,
                    actor=resolve_ws_actor_identity(ws, str(msg.get("actor") or "").strip()),
                    note=str(msg.get("note") or "").strip(),
                )
                await ws.send_json({"type": "alert_acknowledged", "record": serialize_doc(record) if record else None})
    except WebSocketDisconnect:
        await runtime.ws_mgr.disconnect(ws)
    except Exception:
        await runtime.ws_mgr.disconnect(ws)
