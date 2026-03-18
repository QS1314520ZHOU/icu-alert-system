"""
ICU智能预警系统 - FastAPI 主应用
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import runtime
from app.alert_engine import AlertEngine
from app.config import AppConfig, get_config
from app.database import DatabaseManager
from app.routers.ai import router as ai_router
from app.routers.alerts import router as alerts_router
from app.routers.analytics import router as analytics_router
from app.routers.knowledge import router as knowledge_router
from app.routers.patient_data import router as patient_data_router
from app.routers.patients import router as patients_router
from app.routers.system import router as system_router
from app.routers.ws import router as ws_router
from app.services.ai_handoff import AiHandoffService
from app.services.ai_monitor import AiMonitor
from app.services.rag_service import RagService
from app.ws_manager import WebSocketManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("icu-alert")

db: DatabaseManager = None  # type: ignore[assignment]
config: AppConfig = None  # type: ignore[assignment]
ws_mgr: WebSocketManager = None  # type: ignore[assignment]
alert_engine: AlertEngine = None  # type: ignore[assignment]
ai_handoff_service: AiHandoffService = None  # type: ignore[assignment]
ai_monitor: AiMonitor = None  # type: ignore[assignment]
ai_rag_service: RagService = None  # type: ignore[assignment]
bootstrap_config = get_config()


@asynccontextmanager
async def lifespan(application: FastAPI):
    global db, config, ws_mgr, alert_engine, ai_handoff_service, ai_monitor, ai_rag_service

    logger.info("🚀 ICU智能预警系统启动中...")

    config = get_config()
    db = DatabaseManager(config)
    await db.connect()

    ws_mgr = WebSocketManager()
    alert_engine = AlertEngine(db, config, ws_mgr)
    await alert_engine.start()
    ai_handoff_service = AiHandoffService(db, config)
    ai_monitor = AiMonitor(db, config)
    ai_rag_service = RagService(config)

    runtime.set_runtime(
        db_value=db,
        config_value=config,
        ws_mgr_value=ws_mgr,
        alert_engine_value=alert_engine,
        ai_handoff_service_value=ai_handoff_service,
        ai_monitor_value=ai_monitor,
        ai_rag_service_value=ai_rag_service,
    )

    application.state.db = db
    application.state.config = config
    application.state.ws_mgr = ws_mgr
    application.state.alert_engine = alert_engine
    application.state.ai_handoff_service = ai_handoff_service
    application.state.ai_monitor = ai_monitor
    application.state.ai_rag_service = ai_rag_service

    logger.info("✅ ICU智能预警系统启动完成")
    yield

    logger.info("⏹️ ICU智能预警系统关闭中...")
    await alert_engine.stop()
    await db.disconnect()
    logger.info("✅ ICU智能预警系统已关闭")


app = FastAPI(title="ICU智能预警系统", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=bootstrap_config.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(system_router)
app.include_router(patients_router)
app.include_router(patient_data_router)
app.include_router(alerts_router)
app.include_router(analytics_router)
app.include_router(ai_router)
app.include_router(knowledge_router)
app.include_router(ws_router)

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

if os.path.exists(STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        if full_path.startswith("api") or full_path == "health" or full_path.startswith("ws"):
            return None
        file_path = os.path.join(STATIC_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
