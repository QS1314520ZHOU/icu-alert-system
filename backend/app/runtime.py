from __future__ import annotations

from app.alert_engine import AlertEngine
from app.config import AppConfig
from app.database import DatabaseManager
from app.services.ai_handoff import AiHandoffService
from app.services.ai_monitor import AiMonitor
from app.services.rag_service import RagService
from app.ws_manager import WebSocketManager

db: DatabaseManager | None = None
config: AppConfig | None = None
ws_mgr: WebSocketManager | None = None
alert_engine: AlertEngine | None = None
ai_handoff_service: AiHandoffService | None = None
ai_monitor: AiMonitor | None = None
ai_rag_service: RagService | None = None


def set_runtime(
    *,
    db_value: DatabaseManager,
    config_value: AppConfig,
    ws_mgr_value: WebSocketManager,
    alert_engine_value: AlertEngine,
    ai_handoff_service_value: AiHandoffService,
    ai_monitor_value: AiMonitor,
    ai_rag_service_value: RagService,
) -> None:
    global db, config, ws_mgr, alert_engine, ai_handoff_service, ai_monitor, ai_rag_service

    db = db_value
    config = config_value
    ws_mgr = ws_mgr_value
    alert_engine = alert_engine_value
    ai_handoff_service = ai_handoff_service_value
    ai_monitor = ai_monitor_value
    ai_rag_service = ai_rag_service_value
