from __future__ import annotations

import asyncio
import logging
import signal

from app.alert_engine import AlertEngine
from app.config import get_config
from app.database import DatabaseManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("icu-alert")


async def _serve() -> None:
    config = get_config()
    db = DatabaseManager(config)
    await db.connect()
    engine = AlertEngine(db, config, ws_manager=None, runtime_role="worker")
    await engine.start()

    stop_event = asyncio.Event()
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
        await engine.stop()
        await db.disconnect()


def main() -> None:
    asyncio.run(_serve())


if __name__ == "__main__":
    main()
