from __future__ import annotations

import asyncio
import logging
import signal

from app.alert_engine import AlertEngine
from app.config import get_config
from app.database import DatabaseManager
from app.services.outcome_inference_worker import OutcomeInferenceWorker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("icu-alert")


async def _outcome_inference_loop(db: DatabaseManager, config, stop_event: asyncio.Event) -> None:
    cfg = ((getattr(config, "yaml_cfg", None) or {}).get("alert_engine", {}) or {}).get("outcome_inference_worker", {}) or {}
    if cfg and not bool(cfg.get("enabled", True)):
        return
    interval_seconds = int((cfg or {}).get("interval_seconds", 1800) or 1800)
    limit = int((cfg or {}).get("batch_limit", 200) or 200)
    min_age_minutes = int((cfg or {}).get("min_age_minutes", 30) or 30)
    worker = OutcomeInferenceWorker(db)
    while not stop_event.is_set():
        try:
            result = await worker.run_once(limit=limit, min_age_minutes=min_age_minutes)
            logger.info(
                "alert outcome inference completed seeded=%s processed=%s failed=%s missing=%s",
                result.get("seeded"),
                result.get("processed"),
                result.get("failed"),
                result.get("missing_alerts"),
            )
        except Exception as exc:
            logger.exception("alert outcome inference loop failed: %s", exc)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=max(interval_seconds, 60))
        except asyncio.TimeoutError:
            continue


async def _serve() -> None:
    config = get_config()
    db = DatabaseManager(config)
    await db.connect()
    engine = AlertEngine(db, config, ws_manager=None, runtime_role="worker")
    await engine.start()

    stop_event = asyncio.Event()
    outcome_task = asyncio.create_task(_outcome_inference_loop(db, config, stop_event))
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    logger.info("✅ 扫描 worker 已启动，等待队列任务...")
    try:
        await stop_event.wait()
    finally:
        logger.info("⏹️ 扫描 worker 正在停止...")
        outcome_task.cancel()
        try:
            await outcome_task
        except asyncio.CancelledError:
            pass
        await engine.stop()
        await db.disconnect()


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
