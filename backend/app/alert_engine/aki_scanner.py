from __future__ import annotations

import logging
from datetime import datetime, timezone

from .scanners import BaseScanner, ScannerSpec

logger = logging.getLogger(__name__)


class AkiScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="aki",
                interval_key="aki",
                default_interval=600,
                initial_delay=25,
                maturity="validated",
            ),
        )

    async def scan(self) -> None:
        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {
                "_id": 1,
                "name": 1,
                "hisPid": 1,
                "hisBed": 1,
                "dept": 1,
                "hisDept": 1,
                "weight": 1,
                "bodyWeight": 1,
                "body_weight": 1,
                "weightKg": 1,
                "weight_kg": 1,
            },
        )
        patients = [patient async for patient in patient_cursor]
        if not patients:
            return

        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        triggered = 0
        for patient_doc in patients:
            his_pid = patient_doc.get("hisPid")
            if not his_pid:
                continue

            stage = await self.engine._calc_aki_stage(patient_doc, patient_doc.get("_id"), his_pid)
            if not stage:
                continue

            rule_id = f"AKI_STAGE_{stage['stage']}"
            patient_id = str(patient_doc.get("_id"))
            if await self.engine._is_suppressed(patient_id, rule_id, same_rule_sec, max_per_hour):
                continue

            severity = {1: "warning", 2: "high", 3: "critical"}.get(stage["stage"], "warning")
            alert = await self.engine._create_alert(
                rule_id=rule_id,
                name=f"急性肾损伤KDIGO {stage['stage']}期",
                category="syndrome",
                alert_type="aki",
                severity=severity,
                parameter="creatinine",
                condition=stage.get("condition", {}),
                value=stage.get("current"),
                patient_id=patient_id,
                patient_doc=patient_doc,
                device_id=None,
                source_time=stage.get("time"),
                extra=stage,
            )
            if alert:
                triggered += 1
                # Bridge to DiseaseCase
                await self._bridge_to_disease_case(patient_doc, patient_id, stage, alert)

        if triggered > 0:
            self.engine._log_info("AKI预警", triggered)

    async def _bridge_to_disease_case(
        self, patient_doc: dict, patient_id: str, stage: dict, alert: dict
    ) -> None:
        """将 AKI 预警桥接到病种中心 DiseaseCase + CaseEvidence。"""
        try:
            from app.services.disease_case_bridge import (
                add_or_update_evidence,
                mark_screen_positive,
                upsert_case_from_scanner,
                ALERT_TO_CASE_RISK,
            )

            alert_id = str(alert.get("_id", ""))
            aki_stage = stage.get("stage", 0)

            # 1. 创建/更新 DiseaseCase
            case = await upsert_case_from_scanner(
                patient_id=patient_id,
                disease_code="AKI",
                disease_name="急性肾损伤",
                encounter_id=patient_id,  # AKI 无独立 encounter，用 patient_id
                patient_name=patient_doc.get("name", ""),
                bed=patient_doc.get("hisBed", ""),
                dept=patient_doc.get("dept", ""),
                scanner_id="aki",
                rule_id=f"AKI_STAGE_{aki_stage}",
                rule_version="KDIGO_v2012",
                risk_level=ALERT_TO_CASE_RISK.get(severity, "warning"),
                screening_score=stage.get("current"),
                confidence=stage.get("ratio"),
                source_alert_id=alert_id,
            )
            if not case:
                return

            case_id = str(case["id"])

            # 2. 添加肌酐证据
            current_value = stage.get("current")
            baseline = stage.get("baseline")
            ratio = stage.get("ratio")

            if current_value is not None:
                await add_or_update_evidence(
                    case_id=case_id,
                    patient_id=patient_id,
                    disease_code="AKI",
                    evidence_type="lab_value",
                    feature_name="creatinine",
                    raw_value=current_value,
                    raw_unit="μmol/L",
                    observed_at=stage.get("time") or datetime.now(timezone.utc),
                    source_collection="lab_report",
                    source_record_id=f"{patient_id}_cr_{stage.get('time', '')}",
                    source_field="creatinine",
                    rule_id=f"AKI_STAGE_{aki_stage}",
                    rule_version="KDIGO_v2012",
                    matched=True,
                    confidence=ratio or 1.0,
                    baseline_value=baseline,
                    baseline_source="historical",
                    explanation=f"肌酐 {current_value} μmol/L，基线 {baseline} μmol/L，比值 {ratio}",
                )

            # 3. 添加基线肌酐证据（如果有）
            if baseline is not None:
                await add_or_update_evidence(
                    case_id=case_id,
                    patient_id=patient_id,
                    disease_code="AKI",
                    evidence_type="lab_value",
                    feature_name="creatinine_baseline",
                    raw_value=baseline,
                    raw_unit="μmol/L",
                    observed_at=datetime.now(timezone.utc),
                    source_collection="lab_report",
                    source_record_id=f"{patient_id}_cr_baseline",
                    source_field="creatinine",
                    rule_id=f"AKI_STAGE_{aki_stage}",
                    rule_version="KDIGO_v2012",
                    matched=True,
                    confidence=1.0,
                    explanation=f"基线肌酐 {baseline} μmol/L",
                )

            # 4. 标记筛阳（会自动进入 pending_review）
            await mark_screen_positive(
                case_id=case_id,
                risk_level=ALERT_TO_CASE_RISK.get(severity, "warning"),
                screening_score=stage.get("current"),
                confidence=ratio,
                source_alert_id=alert_id,
            )

        except Exception as e:
            logger.error("AKI DiseaseCase bridge failed: %s", e, exc_info=True)
