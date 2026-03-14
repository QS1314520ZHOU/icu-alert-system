"""AI monitoring utility for tracing LLM quality/latency."""
from __future__ import annotations

import hashlib
import math
import time
from datetime import datetime, timedelta
from typing import Any


class AiMonitor:
    def __init__(self, db, config) -> None:
        self.db = db
        self.config = config
        self._aggregate_markers: dict[str, datetime] = {}

    def _monitor_cfg(self) -> dict[str, Any]:
        cfg = (self.config.yaml_cfg or {}).get("ai_service", {}).get("monitor", {})
        return cfg if isinstance(cfg, dict) else {}

    def is_enabled(self) -> bool:
        return bool(self._monitor_cfg().get("enabled", True))

    def _aggregate_interval_seconds(self) -> int:
        return int(self._monitor_cfg().get("aggregate_interval_seconds", 300) or 300)

    def _success_rate_alert_threshold(self) -> float:
        return float(self._monitor_cfg().get("success_rate_alert_threshold", 0.9) or 0.9)

    def _p95_latency_alert_ms(self) -> float:
        return float(self._monitor_cfg().get("p95_latency_alert_ms", 15000) or 15000)

    def _min_samples_for_alert(self) -> int:
        return int(self._monitor_cfg().get("min_samples_for_alert", 5) or 5)

    @staticmethod
    def _usage_dict(usage: dict[str, Any] | None) -> dict[str, int]:
        if not isinstance(usage, dict):
            return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        prompt = int(usage.get("prompt_tokens") or 0)
        completion = int(usage.get("completion_tokens") or 0)
        total = int(usage.get("total_tokens") or (prompt + completion) or 0)
        return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": total}

    async def log_llm_call(
        self,
        *,
        module: str,
        model: str,
        prompt: str,
        output: str,
        latency_ms: float,
        success: bool,
        meta: dict[str, Any] | None = None,
        usage: dict[str, Any] | None = None,
    ) -> None:
        if not self.is_enabled():
            return
        now = datetime.now()
        usage_doc = self._usage_dict(usage)
        doc = {
            "module": module,
            "model": model,
            "input_hash": hashlib.sha256((prompt or "").encode("utf-8")).hexdigest(),
            "output_hash": hashlib.sha256((output or "").encode("utf-8")).hexdigest(),
            "latency_ms": round(float(latency_ms), 2),
            "success": bool(success),
            "output_chars": len(output or ""),
            "created_at": now,
            "meta": meta or {},
            "usage": usage_doc,
            **usage_doc,
        }

        try:
            await self.db.col("ai_monitor_logs").insert_one(doc)
        except Exception:
            return
        try:
            await self._maybe_refresh_aggregates(module, now)
        except Exception:
            return

    async def _maybe_refresh_aggregates(self, module: str, now: datetime) -> None:
        interval = self._aggregate_interval_seconds()
        for key in (str(module or "").strip() or "unknown", "__all__"):
            last = self._aggregate_markers.get(key)
            if last and (now - last).total_seconds() < interval:
                continue
            self._aggregate_markers[key] = now
            await self.refresh_daily_aggregate(module=None if key == "__all__" else key, now=now)

    async def refresh_daily_aggregate(self, *, module: str | None = None, now: datetime | None = None) -> dict[str, Any]:
        if not self.is_enabled():
            return {}
        now = now or datetime.now()
        day_start = datetime(now.year, now.month, now.day)
        day_end = day_start + timedelta(days=1)
        query: dict[str, Any] = {"created_at": {"$gte": day_start, "$lt": day_end}}
        if module:
            query["module"] = module
        cursor = self.db.col("ai_monitor_logs").find(
            query,
            {"latency_ms": 1, "success": 1, "prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 1, "output_chars": 1},
        )
        rows = [doc async for doc in cursor]
        if not rows:
            stats = {
                "date": day_start.strftime("%Y-%m-%d"),
                "module": module or "__all__",
                "calls": 0,
                "success_calls": 0,
                "failure_calls": 0,
                "success_rate": 1.0,
                "avg_latency_ms": 0.0,
                "p95_latency_ms": 0.0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "output_chars": 0,
                "updated_at": now,
            }
        else:
            latencies = sorted(max(0.0, float(doc.get("latency_ms") or 0.0)) for doc in rows)
            calls = len(rows)
            success_calls = sum(1 for doc in rows if bool(doc.get("success")))
            failure_calls = calls - success_calls
            stats = {
                "date": day_start.strftime("%Y-%m-%d"),
                "module": module or "__all__",
                "calls": calls,
                "success_calls": success_calls,
                "failure_calls": failure_calls,
                "success_rate": round(success_calls / calls, 4) if calls else 1.0,
                "avg_latency_ms": round(sum(latencies) / calls, 2) if calls else 0.0,
                "p95_latency_ms": round(self._percentile(latencies, 95), 2) if calls else 0.0,
                "prompt_tokens": int(sum(int(doc.get("prompt_tokens") or 0) for doc in rows)),
                "completion_tokens": int(sum(int(doc.get("completion_tokens") or 0) for doc in rows)),
                "total_tokens": int(sum(int(doc.get("total_tokens") or 0) for doc in rows)),
                "output_chars": int(sum(int(doc.get("output_chars") or 0) for doc in rows)),
                "updated_at": now,
            }

        try:
            await self.db.col("ai_monitor_daily_stats").update_one(
                {"date": stats["date"], "module": stats["module"]},
                {"$set": stats},
                upsert=True,
            )
        except Exception:
            return stats

        await self._upsert_threshold_alerts(stats, now)
        return stats

    async def _upsert_threshold_alerts(self, stats: dict[str, Any], now: datetime) -> None:
        calls = int(stats.get("calls") or 0)
        if calls < self._min_samples_for_alert():
            await self._clear_threshold_alerts(stats, now)
            return

        success_rate = float(stats.get("success_rate") or 0.0)
        p95_latency_ms = float(stats.get("p95_latency_ms") or 0.0)
        checks = [
            (
                "success_rate_low",
                success_rate < self._success_rate_alert_threshold(),
                success_rate,
                self._success_rate_alert_threshold(),
                "AI调用成功率低于阈值",
            ),
            (
                "p95_latency_high",
                p95_latency_ms > self._p95_latency_alert_ms(),
                p95_latency_ms,
                self._p95_latency_alert_ms(),
                "AI调用 P95 延迟高于阈值",
            ),
        ]
        for code, active, value, threshold, message in checks:
            selector = {"date": stats["date"], "module": stats["module"], "alert_code": code}
            if active:
                await self.db.col("ai_monitor_alerts").update_one(
                    selector,
                    {
                        "$set": {
                            "is_active": True,
                            "message": message,
                            "value": value,
                            "threshold": threshold,
                            "updated_at": now,
                            "calls": calls,
                        },
                        "$setOnInsert": {"created_at": now},
                    },
                    upsert=True,
                )
            else:
                await self.db.col("ai_monitor_alerts").update_one(
                    selector,
                    {"$set": {"is_active": False, "resolved_at": now, "updated_at": now, "value": value, "threshold": threshold, "calls": calls}},
                    upsert=True,
                )

    async def _clear_threshold_alerts(self, stats: dict[str, Any], now: datetime) -> None:
        for code in ("success_rate_low", "p95_latency_high"):
            await self.db.col("ai_monitor_alerts").update_one(
                {"date": stats["date"], "module": stats["module"], "alert_code": code},
                {"$set": {"is_active": False, "resolved_at": now, "updated_at": now, "calls": int(stats.get("calls") or 0)}},
                upsert=True,
            )

    async def get_daily_summary(self, *, date: str | None = None) -> dict[str, Any]:
        target = date or datetime.now().strftime("%Y-%m-%d")
        cursor = self.db.col("ai_monitor_daily_stats").find({"date": target}).sort("module", 1)
        rows = [doc async for doc in cursor]
        active_alerts = [doc async for doc in self.db.col("ai_monitor_alerts").find({"date": target, "is_active": True})]
        return {"date": target, "stats": rows, "active_alerts": active_alerts}

    async def log_prediction_feedback(
        self,
        *,
        module: str,
        prediction_id: str,
        outcome: str,
        detail: dict[str, Any] | None = None,
    ) -> None:
        if not self.is_enabled():
            return
        doc = {
            "module": module,
            "prediction_id": prediction_id,
            "outcome": outcome,
            "detail": detail or {},
            "created_at": datetime.now(),
        }
        try:
            await self.db.col("ai_prediction_feedback").insert_one(doc)
        except Exception:
            return

    @staticmethod
    def _percentile(nums: list[float], pct: float) -> float:
        if not nums:
            return 0.0
        if len(nums) == 1:
            return float(nums[0])
        rank = (max(0.0, min(100.0, pct)) / 100.0) * (len(nums) - 1)
        lo = int(math.floor(rank))
        hi = int(math.ceil(rank))
        if lo == hi:
            return float(nums[lo])
        frac = rank - lo
        return float(nums[lo] + (nums[hi] - nums[lo]) * frac)

    @staticmethod
    def now_ms() -> float:
        return time.perf_counter() * 1000.0
