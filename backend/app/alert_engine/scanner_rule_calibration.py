"""
规则级自校准扫描器
定时聚合近 N 天 alert_records，按 rule_id 计算指标，写入 scores 集合。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from .scanners import BaseScanner, ScannerSpec

logger = logging.getLogger("icu-alert")

# 夜间时段
_NIGHT_START = 22
_NIGHT_END = 6

# 有效处置集合（排除空串）
_VALID_DISPOSITIONS = {"resolved", "accepted", "watching", "later", "false_positive", "override", "overridden", "escalate", "ignored"}
_POSITIVE_DISPOSITIONS = {"resolved", "accepted", "escalate"}
_FALSE_POSITIVE_DISPOSITIONS = {"false_positive", "override", "overridden", "ignored"}


class RuleCalibrationScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="rule_calibration",
                interval_key="rule_calibration",
                default_interval=7200,
                initial_delay=90,
            ),
        )

    # ── 配置快捷访问 ──────────────────────────────────────────────────────

    def _cfg(self) -> dict[str, Any]:
        return self.engine._rule_calibration_cfg()

    # ── 主入口 ─────────────────────────────────────────────────────────────

    async def scan(self) -> None:
        cfg = self._cfg()
        if not cfg.get("enabled", True):
            return

        window_days = int(cfg.get("window_days", 30))
        cutoff = datetime.now() - timedelta(days=window_days)

        # 聚合所有 rule_id 的统计
        rule_stats = await self._aggregate_rule_stats(cutoff)
        if not rule_stats:
            return

        now = datetime.now()
        month = now.strftime("%Y-%m")
        day = now.strftime("%Y-%m-%d")

        for rule_id, stats in rule_stats.items():
            suggestion, suggested_severity, suggested_silence, reasoning = self._decide(stats, cfg)
            score_doc = {
                "score_type": "rule_calibration",
                "rule_id": rule_id,
                "alert_type": stats.get("alert_type", ""),
                "status": "pending_review",
                "window_days": window_days,
                "sample_size": stats["total"],
                "metrics": {
                    "ppv_proxy": round(stats["ppv_proxy"], 4),
                    "false_positive_rate": round(stats["fp_rate"], 4),
                    "action_rate": round(stats["action_rate"], 4),
                    "effectiveness_30m": round(stats["eff_30m"], 4),
                    "effectiveness_2h": round(stats["eff_2h"], 4),
                    "night_trigger_ratio": round(stats["night_ratio"], 4),
                    "trigger_count": stats["total"],
                },
                "suggestion": suggestion,
                "suggested_severity": suggested_severity,
                "suggested_silence_minutes": suggested_silence,
                "reasoning": reasoning,
                "calc_time": now,
                "created_at": now,
                "month": month,
                "day": day,
            }
            await self.engine.db.col("score").insert_one(score_doc)

        logger.info(f"[rule_calibration] 完成，处理 {len(rule_stats)} 条规则")

    # ── 聚合 ──────────────────────────────────────────────────────────────

    async def _aggregate_rule_stats(self, cutoff: datetime) -> dict[str, dict[str, Any]]:
        """按 rule_id 聚合近 window_days 天的 alert_records。"""
        cursor = self.engine.db.col("alert_records").find(
            {"created_at": {"$gte": cutoff}},
            {"rule_id": 1, "ack_disposition": 1, "alert_type": 1, "source_time": 1, "outcome_delta": 1},
        )

        buckets: dict[str, dict[str, Any]] = {}
        async for doc in cursor:
            rule_id = doc.get("rule_id")
            if not rule_id:
                continue
            if rule_id not in buckets:
                buckets[rule_id] = {
                    "alert_type": doc.get("alert_type", ""),
                    "total": 0,
                    "has_disposition": 0,
                    "positive_outcome": 0,
                    "false_positive": 0,
                    "action_taken": 0,
                    "eff_30m_improved": 0,
                    "eff_30m_total": 0,
                    "eff_2h_improved": 0,
                    "eff_2h_total": 0,
                    "night_count": 0,
                }
            b = buckets[rule_id]
            b["total"] += 1

            disp = str(doc.get("ack_disposition") or "")
            if disp and disp in _VALID_DISPOSITIONS:
                b["has_disposition"] += 1
                if disp in _POSITIVE_DISPOSITIONS:
                    b["positive_outcome"] += 1
                if disp in _FALSE_POSITIVE_DISPOSITIONS:
                    b["false_positive"] += 1
                b["action_taken"] += 1

            # 夜间触发
            src_time = doc.get("source_time")
            if isinstance(src_time, datetime):
                if src_time.hour >= _NIGHT_START or src_time.hour < _NIGHT_END:
                    b["night_count"] += 1

            # effectiveness
            od = doc.get("outcome_delta")
            if isinstance(od, dict):
                windows = od.get("windows") or {}
                for window_key, eff_key in [("30m", "eff_30m"), ("2h", "eff_2h")]:
                    window_data = windows.get(window_key)
                    if isinstance(window_data, dict):
                        # 检查任一 metric 的 improved
                        any_improved = False
                        has_metric = False
                        for metric_data in window_data.values():
                            if isinstance(metric_data, dict) and "improved" in metric_data:
                                has_metric = True
                                if metric_data["improved"]:
                                    any_improved = True
                        if has_metric:
                            b[f"{eff_key}_total"] += 1
                            if any_improved:
                                b[f"{eff_key}_improved"] += 1

        # 计算比率
        result: dict[str, dict[str, Any]] = {}
        for rule_id, b in buckets.items():
            if b["total"] == 0:
                continue
            disp_total = b["has_disposition"] if b["has_disposition"] > 0 else 1
            b["ppv_proxy"] = b["positive_outcome"] / disp_total
            b["fp_rate"] = b["false_positive"] / disp_total
            b["action_rate"] = b["action_taken"] / b["total"]
            b["eff_30m"] = b["eff_30m_improved"] / b["eff_30m_total"] if b["eff_30m_total"] > 0 else 0.0
            b["eff_2h"] = b["eff_2h_improved"] / b["eff_2h_total"] if b["eff_2h_total"] > 0 else 0.0
            b["night_ratio"] = b["night_count"] / b["total"]
            result[rule_id] = b

        return result

    # ── 判定规则 ──────────────────────────────────────────────────────────

    def _decide(
        self, stats: dict[str, Any], cfg: dict[str, Any]
    ) -> tuple[str, str | None, int | None, str]:
        """
        返回 (suggestion, suggested_severity, suggested_silence_minutes, reasoning)
        """
        total = stats["total"]
        min_sample = int(cfg.get("min_sample", 20))
        fp_high = float(cfg.get("fp_high", 0.6))
        eff_low = float(cfg.get("eff_low", 0.2))
        eff_negative = float(cfg.get("eff_negative", 0.15))
        act_ok = float(cfg.get("act_ok", 0.5))
        silence_minutes = int(cfg.get("silence_minutes", 360))

        fp_rate = stats["fp_rate"]
        eff_2h = stats["eff_2h"]
        action_rate = stats["action_rate"]
        night_ratio = stats["night_ratio"]

        # 样本不足 → 保护
        if total < min_sample:
            return "keep", None, None, f"样本不足({total}<{min_sample})，保持现状"

        # 高误报 + 低效果 → 降级
        if fp_rate >= fp_high and eff_2h < eff_low:
            return (
                "suggest_downgrade",
                None,  # 由应用层根据 SEVERITY_DOWNSTEP 计算
                None,
                f"误报率{fp_rate:.0%}高且2h有效率{eff_2h:.0%}低，建议降级",
            )

        # 高误报 + 夜间高频 → 夜间静默
        if fp_rate >= fp_high and night_ratio >= 0.5:
            return (
                "suggest_silence_window",
                None,
                silence_minutes,
                f"误报率{fp_rate:.0%}高且夜间触发占比{night_ratio:.0%}，建议夜间静默{silence_minutes}分钟",
            )

        # 有行动但持续无效 → 人工复核
        if action_rate >= act_ok and eff_2h < eff_negative:
            return (
                "flag_review",
                None,
                None,
                f"处置率{action_rate:.0%}但2h有效率仅{eff_2h:.0%}，需人工复核",
            )

        return "keep", None, None, "各项指标正常，保持现状"
