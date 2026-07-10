"""Liberation 方向建议扫描器 — 每日遍历患者产出 liberation_advice 告警。"""
from __future__ import annotations

import logging
from datetime import datetime

from .scanners import BaseScanner, ScannerSpec

logger = logging.getLogger("icu-alert")


class LiberationOrchestratorScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="liberation_orchestrator",
                interval_key="liberation_orchestrator",
                default_interval=1800,
                initial_delay=120,
                maturity="experimental",
            ),
        )

    async def scan(self) -> None:
        cfg = self.engine._lib_cfg()
        if not cfg.get("enabled", True):
            return

        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {
                "_id": 1,
                "name": 1,
                "hisPid": 1,
                "hisBed": 1,
                "dept": 1,
                "hisDept": 1,
                "deptCode": 1,
                "admissionType": 1,
                "admitType": 1,
                "inType": 1,
                "admissionSource": 1,
                "admissionWay": 1,
                "source": 1,
                "age": 1,
                "hisAge": 1,
                "clinicalDiagnosis": 1,
                "admissionDiagnosis": 1,
                "diagnosis": 1,
                "history": 1,
                "diagnosisHistory": 1,
                "surgeryHistory": 1,
                "remark": 1,
            },
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        now = datetime.now()
        triggered = 0

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)

            # 每日去重：同患者同日只产出一次
            day_sig = self.engine._liberation_day_signature(pid_str, now)
            rule_id = "LIBERATION_DAILY_ADVICE"

            # 先检查 _is_suppressed (基于冷却时间)
            # 使用 86400s 冷却实现每日去重
            daily_cooldown = int(cfg.get("same_rule_same_patient_seconds", 86400))
            if await self.engine._is_suppressed(pid_str, rule_id, daily_cooldown, max_per_hour):
                continue

            # 额外检查：同日签名是否已存在（防止跨次扫描间隔内重复）
            existing = await self.engine.db.col("alert_records").find_one(
                {
                    "patient_id": pid_str,
                    "rule_id": rule_id,
                    "extra._day_signature": day_sig,
                },
                {"_id": 1},
            )
            if existing:
                continue

            extra = await self.engine.get_liberation_daily_advice(patient_doc)
            if not extra:
                continue

            # 写入去重签名
            extra["_day_signature"] = day_sig

            direction = extra.get("direction", "hold_and_optimize")
            direction_labels = {
                "lean_awakening": "倾向唤醒减镇静",
                "maintain_sedation": "维持当前镇静策略",
                "advance_sbt": "可推进SBT自主呼吸试验",
                "hold_and_optimize": "暂缓并优化当前策略",
            }
            name = f"Liberation建议: {direction_labels.get(direction, direction)}"

            trade_offs = extra.get("trade_offs") or []
            severity = "info"
            if direction == "maintain_sedation":
                severity = "warning"
            elif direction == "hold_and_optimize" and len(trade_offs) >= 2:
                severity = "warning"

            alert = await self.engine._create_alert(
                rule_id=rule_id,
                name=name,
                category="liberation",
                alert_type="liberation_advice",
                severity=severity,
                parameter="multi_parameter",
                condition={
                    "direction": direction,
                    "rass_actual": extra.get("rass_actual"),
                    "cam_icu": extra.get("cam_icu"),
                    "sbt_candidate": extra.get("sbt_candidate"),
                },
                value=direction,
                patient_id=pid_str,
                patient_doc=patient_doc,
                source_time=extra.get("snapshots", {}).get("sedation", {}).get("updated_at") or now,
                extra=extra,
            )
            if alert:
                triggered += 1

        if triggered > 0:
            self.engine._log_info("Liberation编排", triggered)
