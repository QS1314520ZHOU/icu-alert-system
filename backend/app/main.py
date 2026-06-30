"""
ICU智能协同工作台 - FastAPI 主应用
"""
from __future__ import annotations

import os
# 内网环境：禁止 HuggingFace / transformers 请求外网
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("HF_DATASETS_OFFLINE", "1")

import logging
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import traceback

from app import runtime
from app.alert_engine import AlertEngine
from app.config import AppConfig, get_config
from app.database import DatabaseManager
from app.routers.admin import router as admin_router
from app.routers.ai import router as ai_router
from app.routers.alerts import router as alerts_router
from app.routers.analytics import router as analytics_router
from app.routers.followup import router as followup_router
from app.routers.home import router as home_router
from app.routers.knowledge import router as knowledge_router
from app.routers.patient_data import router as patient_data_router
from app.routers.patients import router as patients_router
from app.routers.rounding import router as rounding_router
from app.routers.respiratory import router as respiratory_router
from app.routers.nutrition import router as nutrition_router
from app.routers.research_support import router as research_support_router
from app.routers.clinical_trials import router as clinical_trials_router
from app.routers.clinical_workflow import router as clinical_workflow_router
from app.routers.mobile import router as mobile_router
from app.routers.research_platform import router as research_platform_router
from app.routers.system import router as system_router
from app.routers.treatment_policy import router as treatment_policy_router
from app.routers.waveforms import router as waveforms_router
from app.routers.clinical_documents import router as clinical_documents_router
from app.routers.quality import router as quality_router
from app.routers.voice_rounding import router as voice_rounding_router
from app.routers.ws import router as ws_router
from app.services.ai_handoff import AiHandoffService
from app.services.ai_monitor import AiMonitor
from app.services.ai_watching_service import AiWatchingService
from app.services.clinical_reasoning_agent import ClinicalReasoningAgent
from app.services.multi_agent_orchestrator import ICUMultiAgentOrchestrator
from app.services.pulse_service import PulseService
from app.services.rag_service import RagService
from app.services.voice_rounding import VoiceRoundingService
from app.utils.runtime_paths import static_dir
from app.ws_manager import WebSocketManager

try:
    from app.routers.research_analytics import router as research_analytics_router
except ModuleNotFoundError as exc:
    research_analytics_router = None
    logging.getLogger("icu-alert").warning("研究分析路由未加载，缺少依赖: %s", exc)

try:
    from app.routers.research_export import router as research_export_router
except ModuleNotFoundError as exc:
    research_export_router = None
    logging.getLogger("icu-alert").warning("科研导出路由未加载，缺少依赖: %s", exc)

try:
    from app.research_cohort_router import router as research_cohort_router
except ModuleNotFoundError as exc:
    research_cohort_router = None
    logging.getLogger("icu-alert").warning("科研队列路由未加载，缺少依赖: %s", exc)

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
ai_watching_service: AiWatchingService = None  # type: ignore[assignment]
pulse_service: PulseService = None  # type: ignore[assignment]
pulse_task = None
bootstrap_config = get_config()


def _error_log_path() -> Path:
    system_cfg = bootstrap_config.yaml_cfg.get("system", {}) if isinstance(bootstrap_config.yaml_cfg, dict) else {}
    raw_dir = str(system_cfg.get("log_dir") or "./logs").strip() or "./logs"
    log_dir = Path(raw_dir)
    if not log_dir.is_absolute():
        log_dir = Path.cwd() / log_dir
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "error.log"


@asynccontextmanager
async def lifespan(application: FastAPI):
    global db, config, ws_mgr, alert_engine, ai_handoff_service, ai_monitor, ai_rag_service, ai_watching_service, pulse_service, pulse_task

    logger.info("🚀 ICU智能协同工作台启动中...")

    config = get_config()
    db = DatabaseManager(config)
    await db.connect()

    ws_mgr = WebSocketManager()
    if db.redis:
        from app.alert_engine.task_queue import load_queue_settings

        await ws_mgr.start_redis_relay(db.redis, load_queue_settings(config).redis_pubsub_channel)
    alert_engine = AlertEngine(db, config, ws_mgr, runtime_role="api")
    await alert_engine.start()
    ai_handoff_service = AiHandoffService(db, config)
    ai_monitor = AiMonitor(db, config)
    ai_rag_service = RagService(config)
    clinical_reasoning_agent = ClinicalReasoningAgent(
        db=db,
        config=config,
        alert_engine=alert_engine,
        rag_service=ai_rag_service,
        ai_monitor=ai_monitor,
        ai_handoff_service=ai_handoff_service,
    )
    multi_agent_orchestrator = ICUMultiAgentOrchestrator(
        db=db,
        config=config,
        alert_engine=alert_engine,
        rag_service=ai_rag_service,
        ai_monitor=ai_monitor,
        ai_handoff_service=ai_handoff_service,
    )
    ai_watching_service = AiWatchingService(db, config)
    voice_rounding_service = VoiceRoundingService(db, config)
    pulse_service = PulseService(
        db=db,
        config=config,
        ws_mgr=ws_mgr,
        alert_engine=alert_engine,
        multi_agent_orchestrator=multi_agent_orchestrator,
        clinical_reasoning_agent=clinical_reasoning_agent,
        ai_monitor=ai_monitor,
    )

    runtime.set_runtime(
        db_value=db,
        config_value=config,
        ws_mgr_value=ws_mgr,
        alert_engine_value=alert_engine,
        ai_handoff_service_value=ai_handoff_service,
        ai_monitor_value=ai_monitor,
        ai_rag_service_value=ai_rag_service,
        ai_watching_service_value=ai_watching_service,
        pulse_service_value=pulse_service,
        voice_rounding_service_value=voice_rounding_service,
    )

    application.state.db = db
    application.state.config = config
    application.state.ws_mgr = ws_mgr
    application.state.alert_engine = alert_engine
    application.state.ai_handoff_service = ai_handoff_service
    application.state.ai_monitor = ai_monitor
    application.state.ai_rag_service = ai_rag_service
    application.state.ai_watching_service = ai_watching_service
    application.state.pulse_service = pulse_service
    application.state.voice_rounding_service = voice_rounding_service
    try:
        from app.services.shift_service import ShiftService

        await ShiftService(db).refresh_cache()
    except Exception as exc:
        logger.warning("班次配置加载失败（非致命）: %s", exc)

    if pulse_service.is_enabled():
        pulse_task = asyncio.create_task(pulse_service.run_loop(), name="pulse-service-loop")

    logger.info("✅ ICU智能协同工作台启动完成")
    yield

    logger.info("⏹️ ICU智能协同工作台关闭中...")
    if pulse_service:
        pulse_service.stop()
    if pulse_task:
        pulse_task.cancel()
        await asyncio.gather(pulse_task, return_exceptions=True)
    await alert_engine.stop()
    await ws_mgr.stop_redis_relay()
    await db.disconnect()
    logger.info("✅ ICU智能协同工作台已关闭")


app = FastAPI(title="ICU智能协同工作台", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=bootstrap_config.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception: {exc}")
    logger.error(traceback.format_exc())
    try:
        error_log = _error_log_path()
        with error_log.open("a", encoding="utf-8") as f:
            f.write(f"\n--- {datetime.now()} ---\n")
            f.write(f"URL: {request.url}\n")
            f.write(traceback.format_exc())
    except Exception as log_exc:
        logger.error("Failed to persist error log: %s", log_exc)
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": "Internal Server Error", "detail": str(exc)},
    )


app.include_router(admin_router)
app.include_router(research_platform_router)
if research_export_router is not None:
    app.include_router(research_export_router)
if research_analytics_router is not None:
    app.include_router(research_analytics_router)
if research_cohort_router is not None:
    app.include_router(research_cohort_router)
app.include_router(system_router)
app.include_router(patients_router)
app.include_router(patient_data_router)
app.include_router(alerts_router)
app.include_router(analytics_router)
app.include_router(followup_router)
app.include_router(home_router)
app.include_router(rounding_router)
app.include_router(voice_rounding_router)
app.include_router(respiratory_router)
app.include_router(nutrition_router)
app.include_router(research_support_router)
app.include_router(clinical_trials_router)
app.include_router(clinical_workflow_router)
app.include_router(mobile_router)
app.include_router(treatment_policy_router)
app.include_router(ai_router)
app.include_router(knowledge_router)
app.include_router(clinical_documents_router)
app.include_router(quality_router)
app.include_router(waveforms_router)
app.include_router(ws_router)

STATIC_DIR = str(static_dir())

if os.path.exists(STATIC_DIR):
    assets_dir = os.path.join(STATIC_DIR, "assets")
    if os.path.isdir(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        if full_path.startswith("api") or full_path == "health" or full_path.startswith("ws"):
            return None
        file_path = os.path.join(STATIC_DIR, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        # 只有前端路由才应该回退到 index.html；静态资源丢失时返回 404，
        # 避免把 JS/CSS/manifest 请求错误地回成 HTML，触发 MIME 报错。
        suffix = Path(full_path).suffix.lower()
        if suffix:
            raise HTTPException(status_code=404, detail=f"Static asset not found: {full_path}")
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
