from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from app.alert_engine import AlertEngine
from app.config import AppConfig
from app.database import DatabaseManager
from app.services.ai_handoff import AiHandoffService
from app.services.ai_monitor import AiMonitor
from app.services.ai_watching_service import AiWatchingService
from app.services.rag_service import RagService
from app.services.pulse_service import PulseService
from app.ws_manager import WebSocketManager

db: DatabaseManager | None = None
config: AppConfig | None = None
ws_mgr: WebSocketManager | None = None
alert_engine: AlertEngine | None = None
ai_handoff_service: AiHandoffService | None = None
ai_monitor: AiMonitor | None = None
ai_rag_service: RagService | None = None
ai_watching_service: AiWatchingService | None = None
pulse_service: PulseService | None = None
shift_config: dict | None = None
shift_config_loaded_at = None


def set_runtime(
    *,
    db_value: DatabaseManager,
    config_value: AppConfig,
    ws_mgr_value: WebSocketManager,
    alert_engine_value: AlertEngine,
    ai_handoff_service_value: AiHandoffService,
    ai_monitor_value: AiMonitor,
    ai_rag_service_value: RagService,
    ai_watching_service_value: AiWatchingService | None = None,
    pulse_service_value: PulseService | None = None,
) -> None:
    global db, config, ws_mgr, alert_engine, ai_handoff_service, ai_monitor, ai_rag_service, ai_watching_service, pulse_service

    db = db_value
    config = config_value
    ws_mgr = ws_mgr_value
    alert_engine = alert_engine_value
    ai_handoff_service = ai_handoff_service_value
    ai_monitor = ai_monitor_value
    ai_rag_service = ai_rag_service_value
    ai_watching_service = ai_watching_service_value
    pulse_service = pulse_service_value


def _resolve_state_attr(request: Request | None, name: str):
    if request is not None:
        value = getattr(request.app.state, name, None)
        if value is not None:
            return value
    return globals().get(name)


def get_db(request: Request) -> DatabaseManager:
    value = _resolve_state_attr(request, "db")
    if value is None:
        raise HTTPException(status_code=503, detail="Database runtime not ready")
    return value


def get_config_dep(request: Request) -> AppConfig:
    value = _resolve_state_attr(request, "config")
    if value is None:
        raise HTTPException(status_code=503, detail="Config runtime not ready")
    return value


def get_ws_mgr_dep(request: Request) -> WebSocketManager:
    value = _resolve_state_attr(request, "ws_mgr")
    if value is None:
        raise HTTPException(status_code=503, detail="WebSocket runtime not ready")
    return value


def get_alert_engine_dep(request: Request) -> AlertEngine:
    value = _resolve_state_attr(request, "alert_engine")
    if value is None:
        raise HTTPException(status_code=503, detail="Alert engine runtime not ready")
    return value


def get_ai_handoff_service_dep(request: Request) -> AiHandoffService:
    value = _resolve_state_attr(request, "ai_handoff_service")
    if value is None:
        raise HTTPException(status_code=503, detail="AI handoff service not ready")
    return value


def get_ai_monitor_dep(request: Request) -> AiMonitor:
    value = _resolve_state_attr(request, "ai_monitor")
    if value is None:
        raise HTTPException(status_code=503, detail="AI monitor not ready")
    return value


def get_ai_rag_service_dep(request: Request) -> RagService:
    value = _resolve_state_attr(request, "ai_rag_service")
    if value is None:
        raise HTTPException(status_code=503, detail="RAG service not ready")
    return value


def get_ai_watching_service_dep(request: Request) -> AiWatchingService:
    value = _resolve_state_attr(request, "ai_watching_service")
    if value is None:
        raise HTTPException(status_code=503, detail="AI watching service not ready")
    return value


def get_pulse_service_dep(request: Request) -> PulseService:
    value = _resolve_state_attr(request, "pulse_service")
    if value is None:
        raise HTTPException(status_code=503, detail="Pulse service not ready")
    return value


DbDep = Annotated[DatabaseManager, Depends(get_db)]
ConfigDep = Annotated[AppConfig, Depends(get_config_dep)]
WsMgrDep = Annotated[WebSocketManager, Depends(get_ws_mgr_dep)]
AlertEngineDep = Annotated[AlertEngine, Depends(get_alert_engine_dep)]
AiHandoffDep = Annotated[AiHandoffService, Depends(get_ai_handoff_service_dep)]
AiMonitorDep = Annotated[AiMonitor, Depends(get_ai_monitor_dep)]
AiRagDep = Annotated[RagService, Depends(get_ai_rag_service_dep)]
AiWatchingDep = Annotated[AiWatchingService, Depends(get_ai_watching_service_dep)]
PulseDep = Annotated[PulseService, Depends(get_pulse_service_dep)]
