from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .scanners import BaseScanner

logger = logging.getLogger("icu-alert")


@dataclass(frozen=True)
class QueueSettings:
    mode: str = "inline"
    redis_queue_name: str = "icu:alert_engine:scan_queue"
    redis_pubsub_channel: str = "icu:alerts:broadcast"
    dedupe_ttl_seconds: int = 900
    worker_concurrency: int = 4
    worker_poll_timeout: int = 5
    dispatcher_enabled: bool = True


def load_queue_settings(config: Any) -> QueueSettings:
    root = config.yaml_cfg.get("alert_engine", {}) if getattr(config, "yaml_cfg", None) else {}
    queue_cfg = root.get("task_queue", {}) if isinstance(root, dict) else {}
    mode = str(root.get("execution_mode") or queue_cfg.get("mode") or "inline").strip().lower() or "inline"
    queue_name = str(queue_cfg.get("redis_queue_name") or "icu:alert_engine:scan_queue").strip() or "icu:alert_engine:scan_queue"
    pubsub_channel = str(queue_cfg.get("redis_pubsub_channel") or "icu:alerts:broadcast").strip() or "icu:alerts:broadcast"
    dedupe_ttl = int(queue_cfg.get("dedupe_ttl_seconds") or 900)
    worker_concurrency = int(queue_cfg.get("worker_concurrency") or root.get("max_concurrent_scans") or 4)
    worker_poll_timeout = int(queue_cfg.get("worker_poll_timeout") or 5)
    dispatcher_enabled = bool(queue_cfg.get("dispatcher_enabled", True))
    return QueueSettings(
        mode=mode,
        redis_queue_name=queue_name,
        redis_pubsub_channel=pubsub_channel,
        dedupe_ttl_seconds=max(30, dedupe_ttl),
        worker_concurrency=max(1, worker_concurrency),
        worker_poll_timeout=max(1, worker_poll_timeout),
        dispatcher_enabled=dispatcher_enabled,
    )


class RedisScannerQueue:
    def __init__(self, redis_client: Any, settings: QueueSettings) -> None:
        self.redis = redis_client
        self.settings = settings

    def _dedupe_key(self, scanner_name: str) -> str:
        return f"{self.settings.redis_queue_name}:dedupe:{scanner_name}"

    async def enqueue(self, scanner: BaseScanner) -> bool:
        if not self.redis:
            return False
        ttl = max(self.settings.dedupe_ttl_seconds, scanner.interval_seconds() * 2)
        dedupe_key = self._dedupe_key(scanner.name)
        task_id = uuid.uuid4().hex
        payload = {
            "task_id": task_id,
            "scanner": scanner.name,
            "interval_seconds": scanner.interval_seconds(),
        }
        claimed = await self.redis.set(dedupe_key, task_id, ex=ttl, nx=True)
        if not claimed:
            return False
        await self.redis.rpush(self.settings.redis_queue_name, json.dumps(payload, ensure_ascii=False))
        return True

    async def dequeue(self, timeout: int | None = None) -> dict[str, Any] | None:
        if not self.redis:
            return None
        result = await self.redis.blpop(self.settings.redis_queue_name, timeout=timeout or self.settings.worker_poll_timeout)
        if not result:
            return None
        _, raw = result
        try:
            payload = json.loads(raw)
        except Exception:
            logger.warning("scan queue payload decode failed: %s", raw)
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    async def ack(self, scanner_name: str, task_id: str | None = None) -> None:
        if not self.redis:
            return
        key = self._dedupe_key(scanner_name)
        if task_id:
            try:
                current = await self.redis.get(key)
            except Exception:
                current = None
            if current and current != task_id:
                return
        await self.redis.delete(key)


class ScanTaskDispatcher:
    def __init__(
        self,
        *,
        scanners: list[BaseScanner],
        queue: RedisScannerQueue,
        stop_event: asyncio.Event,
    ) -> None:
        self.scanners = scanners
        self.queue = queue
        self.stop_event = stop_event
        self._tasks: list[asyncio.Task] = []

    async def start(self) -> list[asyncio.Task]:
        self._tasks = [
            asyncio.create_task(self._loop(scanner), name=f"dispatch:{scanner.name}")
            for scanner in self.scanners
        ]
        return self._tasks

    async def _loop(self, scanner: BaseScanner) -> None:
        await self._sleep(scanner.initial_delay)
        while not self.stop_event.is_set():
            try:
                enqueued = await self.queue.enqueue(scanner)
                if not enqueued:
                    logger.debug("[dispatcher:%s] skipped duplicate in-flight task", scanner.name)
            except Exception as exc:
                logger.exception("[dispatcher:%s] enqueue failed: %s", scanner.name, exc)
            await self._sleep(scanner.interval_seconds())

    async def _sleep(self, seconds: int) -> None:
        try:
            await asyncio.wait_for(self.stop_event.wait(), timeout=max(1, seconds))
        except asyncio.TimeoutError:
            return


class ScanTaskWorker:
    def __init__(
        self,
        *,
        queue: RedisScannerQueue,
        scanners: list[BaseScanner],
        stop_event: asyncio.Event,
        concurrency: int,
    ) -> None:
        self.queue = queue
        self.stop_event = stop_event
        self._scanner_map = {scanner.name: scanner for scanner in scanners}
        self._concurrency = max(1, concurrency)
        self._workers: list[asyncio.Task] = []

    async def start(self) -> list[asyncio.Task]:
        self._workers = [
            asyncio.create_task(self._run_worker(idx), name=f"scan-worker:{idx}")
            for idx in range(self._concurrency)
        ]
        return self._workers

    async def _run_worker(self, idx: int) -> None:
        while not self.stop_event.is_set():
            try:
                payload = await self.queue.dequeue()
                if not payload:
                    continue
                scanner_name = str(payload.get("scanner") or "").strip()
                task_id = str(payload.get("task_id") or "").strip()
                scanner = self._scanner_map.get(scanner_name)
                if scanner is None:
                    logger.warning("[scan-worker:%s] unknown scanner %s", idx, scanner_name)
                    await self.queue.ack(scanner_name, task_id)
                    continue
                await scanner.run_with_telemetry()
                await self.queue.ack(scanner_name, task_id)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("[scan-worker:%s] task failed: %s", idx, exc)


def _load_schedule_config(config: Any | None) -> dict[str, dict] | None:
    """从 config.yaml 读取 scanner_schedule 节，失败返回 None（回退到旧行为）"""
    if config is None:
        return None
    try:
        yaml_cfg = getattr(config, "yaml_cfg", None) or {}
        schedule = yaml_cfg.get("scanner_schedule")
        if not isinstance(schedule, dict) or not schedule:
            return None
        return schedule
    except Exception:
        return None


async def run_inline_loops(
    *,
    scanners: list[BaseScanner],
    stop_event: asyncio.Event,
    semaphore: asyncio.Semaphore,
    config: Any | None = None,
) -> list[asyncio.Task]:
    async def _sleep(seconds: float) -> None:
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=max(seconds, 1))
        except asyncio.TimeoutError:
            return

    schedule_cfg = _load_schedule_config(config)

    # ---- 旧行为：无 scanner_schedule 配置时回退 ----
    if not schedule_cfg:
        async def _loop(scanner: BaseScanner) -> None:
            await _sleep(scanner.initial_delay)
            while not stop_event.is_set():
                try:
                    async with semaphore:
                        await scanner.run_with_telemetry()
                except Exception as exc:
                    logger.exception("[%s] 扫描失败: %s", scanner.name, exc)
                await _sleep(scanner.interval_seconds())

        return [
            asyncio.create_task(_loop(scanner), name=f"inline:{scanner.name}")
            for scanner in scanners
        ]

    # ---- 新行为：分级调度 ----
    scanner_map = {s.name: s for s in scanners}

    # 构建分组：{group_name: {interval, [scanner, ...]}}
    groups: list[dict] = []
    assigned: set[str] = set()
    for group_name, group_cfg in schedule_cfg.items():
        interval = int(group_cfg.get("interval_seconds", 60))
        names = group_cfg.get("scanners") or []
        group_scanners = [scanner_map[n] for n in names if n in scanner_map]
        if group_scanners:
            groups.append({"name": group_name, "interval": interval, "scanners": group_scanners})
            assigned.update(n for n in names if n in scanner_map)

    # 未被分组的 scanner 统一归入默认组（兼容旧 scanner）
    unassigned = [s for s in scanners if s.name not in assigned]
    if unassigned:
        default_interval = min(s.interval_seconds() for s in unassigned)
        groups.append({"name": "_default", "interval": default_interval, "scanners": unassigned})
        logger.info(
            "[scheduler] %d scanners not in schedule config, using default interval %ds",
            len(unassigned),
            default_interval,
        )

    if not groups:
        return []

    min_interval = min(g["interval"] for g in groups)
    poll_interval = max(min_interval / 2, 5)  # 主循环 tick，最少 5 秒
    pending: set[asyncio.Task] = set()

    async def _run_scanner(scanner: BaseScanner) -> None:
        try:
            async with semaphore:
                await scanner.run_with_telemetry()
        except Exception as exc:
            logger.exception("[%s] 扫描失败: %s", scanner.name, exc)

    def _schedule(scanner: BaseScanner) -> None:
        if stop_event.is_set():
            return
        task = asyncio.create_task(_run_scanner(scanner), name=f"inline:{scanner.name}")
        pending.add(task)

        def _cleanup(t: asyncio.Task) -> None:
            pending.discard(t)

        task.add_done_callback(_cleanup)

    async def _tiered_master_loop() -> None:
        import time

        last_run: dict[str, float] = {g["name"]: 0.0 for g in groups}
        # 错开各组初始延迟，避免启动时全部同时触发
        for idx, g in enumerate(groups):
            last_run[g["name"]] = time.monotonic() + idx * 2.0

        while not stop_event.is_set():
            now = time.monotonic()
            for g in groups:
                if now - last_run[g["name"]] >= g["interval"]:
                    last_run[g["name"]] = now
                    for scanner in g["scanners"]:
                        _schedule(scanner)
            await _sleep(poll_interval)

        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    return [asyncio.create_task(_tiered_master_loop(), name="inline:tiered-scheduler")]


async def run_scanners_once(scanners: list[BaseScanner], semaphore: asyncio.Semaphore) -> None:
    for scanner in scanners:
        try:
            async with semaphore:
                await scanner.run_with_telemetry()
        except Exception as exc:
            logger.exception("[%s] 单次执行失败: %s", scanner.name, exc)


async def publish_event(redis_client: Any, channel: str, payload: dict[str, Any]) -> bool:
    if not redis_client:
        return False
    await redis_client.publish(channel, json.dumps(payload, ensure_ascii=False, default=str))
    return True


async def relay_pubsub_forever(
    *,
    redis_client: Any,
    channel: str,
    stop_event: asyncio.Event,
    handler: Callable[[dict[str, Any]], Awaitable[None]],
) -> None:
    pubsub = redis_client.pubsub()
    await pubsub.subscribe(channel)
    try:
        while not stop_event.is_set():
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if not message:
                await asyncio.sleep(0.1)
                continue
            data = message.get("data")
            if not isinstance(data, str):
                continue
            try:
                payload = json.loads(data)
            except Exception:
                logger.warning("pubsub payload decode failed: %s", data)
                continue
            if isinstance(payload, dict):
                await handler(payload)
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()
