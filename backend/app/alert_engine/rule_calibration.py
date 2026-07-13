"""
规则级自校准控制器
把已有 outcome 闭环数据按 rule_id 聚合，产出降级/静默/保留/标红复核建议。
approved 后在出警时应用，绝不自动改 severity。
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

logger = logging.getLogger("icu-alert")

# severity 降级链：critical → high → warning → info（最低有效级）
SEVERITY_DOWNSTEP: dict[str, str] = {
    "critical": "high",
    "high": "warning",
    "warning": "info",
    "info": "info",
}

# 用于 ppv_proxy 计算的正向处置集合
_POSITIVE_DISPOSITIONS = {"resolved", "accepted", "escalate"}

# 用于 false_positive_rate 计算的负向处置集合
_FALSE_POSITIVE_DISPOSITIONS = {"false_positive", "override", "overridden", "ignored"}

# 有效处置（排除空串）
_VALID_DISPOSITIONS = {"resolved", "accepted", "watching", "later", "false_positive", "override", "overridden", "escalate", "ignored"}

# TTL 缓存（秒）
_CACHE_TTL = 300


class RuleCalibrationMixin:
    """规则级自校准 Mixin，挂载到 AlertEngine。"""

    # ── 配置 ──────────────────────────────────────────────────────────────

    def _rule_calibration_cfg(self) -> dict[str, Any]:
        """读取 alert_engine.rule_calibration 配置，给默认值。"""
        raw = self._cfg("alert_engine", "rule_calibration", default={}) or {}
        if not isinstance(raw, dict):
            raw = {}
        return {
            "enabled": bool(raw.get("enabled", True)),
            "window_days": int(raw.get("window_days", 30)),
            "min_sample": int(raw.get("min_sample", 20)),
            "fp_high": float(raw.get("fp_high", 0.6)),
            "eff_low": float(raw.get("eff_low", 0.2)),
            "eff_negative": float(raw.get("eff_negative", 0.15)),
            "act_ok": float(raw.get("act_ok", 0.5)),
            "silence_minutes": int(raw.get("silence_minutes", 360)),
        }

    # ── 缓存 ──────────────────────────────────────────────────────────────

    def _calibration_cache(self) -> dict[str, tuple[float, dict | None]]:
        """懒初始化 engine 级缓存 dict。"""
        if not hasattr(self, "_rule_cal_cache"):
            self._rule_cal_cache: dict[str, tuple[float, dict | None]] = {}
        return self._rule_cal_cache

    # ── 查询 approved 校准 ────────────────────────────────────────────────

    async def get_approved_rule_calibration(self, rule_id: str) -> dict | None:
        """获取指定 rule_id 最新一条 approved 校准。带 TTL 缓存。"""
        if not rule_id:
            return None
        cache = self._calibration_cache()
        now_ts = time.time()
        if rule_id in cache:
            ts, cached = cache[rule_id]
            if now_ts - ts < _CACHE_TTL:
                return cached
        doc = await self.db.col("score").find_one(
            {"score_type": "rule_calibration", "rule_id": rule_id, "status": "approved"},
            sort=[("created_at", -1)],
        )
        cache[rule_id] = (now_ts, doc)
        return doc

    def invalidate_calibration_cache(self, rule_id: str | None = None) -> None:
        """清除缓存，approve/reject 后调用。"""
        cache = self._calibration_cache()
        if rule_id:
            cache.pop(rule_id, None)
        else:
            cache.clear()

    # ── 出警时应用校准 ────────────────────────────────────────────────────

    async def _apply_rule_calibration(self, alert_doc: dict[str, Any]) -> dict[str, Any] | None:
        """
        在 _alert_intelligence_intercept 中调用。
        返回修改后的 alert_doc，或 None（静默）。
        """
        rule_id = alert_doc.get("rule_id")
        if not rule_id:
            return alert_doc

        cal = await self.get_approved_rule_calibration(rule_id)
        if not cal:
            return alert_doc

        suggestion = cal.get("suggestion", "keep")
        if suggestion == "keep":
            return alert_doc

        severity = str(alert_doc.get("severity") or "").lower()

        # ── silence_window：P0 硬保护 ──
        if suggestion == "suggest_silence_window":
            is_v2 = bool(alert_doc.get("alert_domain"))
            # V2: 仅 priority=="p0" 作为硬保护
            # V1（旧告警无 alert_domain）: severity=="critical" 兼容判断
            is_p0 = (
                (is_v2 and alert_doc.get("priority") == "p0")
                or (not is_v2 and severity == "critical")
            )
            if is_p0:
                return alert_doc
            if self._in_silence_window(cal):
                logger.info(
                    f"[rule_calibration] 静默 rule_id={rule_id} severity={severity} "
                    f"calibration_id={cal.get('_id')}"
                )
                return None  # 不出警

        # ── downgrade：降级 ──
        if suggestion == "suggest_downgrade":
            is_v2 = bool(alert_doc.get("alert_domain"))
            suggested_severity = cal.get("suggested_severity")
            if not suggested_severity:
                suggested_severity = SEVERITY_DOWNSTEP.get(severity, severity)
            new_severity = str(suggested_severity).lower()

            # V2 告警不自动执行旧 SEVERITY_DOWNSTEP；仅在有显式 suggested_severity 时应用
            if is_v2 and not cal.get("suggested_severity"):
                logger.debug(
                    f"[rule_calibration] V2告警跳过自动SEVERITY_DOWNSTEP "
                    f"rule_id={rule_id} domain={alert_doc.get('alert_domain')}"
                )
                return alert_doc

            if new_severity != severity:
                extra = alert_doc.get("extra")
                if not isinstance(extra, dict):
                    extra = {}
                    alert_doc["extra"] = extra
                cal_record = {
                    "applied": True,
                    "original_severity": severity,
                    "new_severity": new_severity,
                    "calibration_id": str(cal.get("_id", "")),
                    "reason": cal.get("reason", ""),
                }
                # V2: 同时记录 original_priority
                if is_v2:
                    cal_record["original_priority"] = alert_doc.get("priority")
                    cal_record["original_clinical_severity"] = alert_doc.get("clinical_severity")
                    # clinical_severity 不自动降低
                    cal_record["clinical_severity_preserved"] = True

                extra["calibration"] = cal_record
                alert_doc["severity"] = new_severity
                logger.info(
                    f"[rule_calibration] 降级 rule_id={rule_id} "
                    f"{severity} → {new_severity} v2={is_v2} calibration_id={cal.get('_id')}"
                )

        return alert_doc

    def _in_silence_window(self, cal: dict[str, Any]) -> bool:
        """检查当前是否在静默窗口内。默认 22:00-06:00。"""
        now = datetime.now()
        hour = now.hour
        return hour >= 22 or hour < 6

    # ── 拦截层扩展 ────────────────────────────────────────────────────────

    async def _alert_intelligence_intercept(
        self, alert_doc: dict[str, Any], patient_doc: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """
        在原有 intelligence 逻辑之前插入 calibration 检查。
        MRO 链式调用：先 calibration，再原有逻辑。
        """
        cfg = self._rule_calibration_cfg()
        if cfg.get("enabled", True):
            calibrated = await self._apply_rule_calibration(alert_doc)
            if calibrated is None:
                return None  # 被静默
            alert_doc = calibrated

        # 调用 MRO 中下一个 _alert_intelligence_intercept（AlertIntelligenceMixin）
        # Python MRO 保证 super() 会走到正确的下一个类
        parent = super()
        if hasattr(parent, "_alert_intelligence_intercept"):
            return await parent._alert_intelligence_intercept(alert_doc, patient_doc)
        return alert_doc
