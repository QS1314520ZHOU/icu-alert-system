"""转出交接扫描器：检测转出候选患者，生成风险分与交接清单。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .scanners import BaseScanner, ScannerSpec


class TransferHandoffScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="transfer_handoff",
                interval_key="transfer_handoff",
                default_interval=1800,
                initial_delay=61,
            ),
        )

    async def scan(self) -> None:
        cfg = self.engine._transfer_handoff_cfg()
        if not cfg.get("enabled", True):
            return

        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "deptCode": 1, "age": 1, "gender": 1, "hisSex": 1},
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        triggered = 0
        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            now = datetime.now()

            # 检测转出信号（复用 discharge_readiness 的检测逻辑）
            signal = await self.engine._detect_transfer_candidate_signal(patient_doc, pid_str, now)
            if not signal.get("candidate"):
                continue

            # 检查是否已有近期评估（避免重复）
            existing = await self.engine.db.col("score").find_one({
                "patient_id": pid_str,
                "score_type": "transfer_handoff",
                "calc_time": {"$gte": now - timedelta(seconds=same_rule_sec)},
            })
            if existing:
                continue

            # 计算风险分
            result = await self.engine.compute_transfer_risk_score(patient_doc)
            risk_level = result.get("risk_level", "low")

            # 生成完整文档
            doc = await self.engine.evaluate_transfer_handoff(patient_doc)
            await self.engine.persist_transfer_handoff(doc)

            # 出警
            if risk_level in ("high", "moderate"):
                rule_id = f"TRANSFER_HANDOFF_{risk_level.upper()}"
                if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    continue
                severity_map = {"high": "high", "moderate": "warning"}
                alert = await self.engine._create_alert(
                    rule_id=rule_id,
                    name="转出交接风险评估",
                    category="transfer",
                    alert_type="transfer_handoff",
                    severity=severity_map.get(risk_level, "info"),
                    parameter="post_transfer_risk",
                    condition={"risk_level": risk_level, "score": result["score"]},
                    value=result["score"],
                    patient_id=pid_str,
                    patient_doc=patient_doc,
                    source_time=now,
                    extra={
                        "risk_level": risk_level,
                        "risk_factors": result["risk_factors"],
                        "handoff_checklist": doc.get("handoff_checklist", []),
                        "narrative": doc.get("narrative"),
                        "transfer_signal": signal,
                    },
                )
                if alert:
                    triggered += 1

        if triggered > 0:
            self.engine._log_info("转出交接风险评估", triggered)


class TransferHandoffVerifyScanner(BaseScanner):
    """72h 回填验证扫描器：对已转出患者回填实际结局。"""

    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="transfer_handoff_verify",
                interval_key="transfer_handoff_verify",
                default_interval=3600,
                initial_delay=120,
            ),
        )

    async def scan(self) -> None:
        cfg = self.engine._transfer_handoff_cfg()
        if not cfg.get("enabled", True):
            return

        processed = await self.engine.verify_transfer_outcomes()
        if processed > 0:
            self.engine._log_info("转出交接72h回填验证", processed)
