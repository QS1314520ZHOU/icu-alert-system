from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from .scanners import BaseScanner, ScannerSpec


class DeviceManagementScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="device_management",
                interval_key="device_management",
                default_interval=3600,
                initial_delay=37,
            ),
        )

    async def scan(self) -> None:
        now = datetime.now()
        if not (7 <= now.hour <= 9):
            return

        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "clinicalDiagnosis": 1},
        )
        patients = [p async for p in patient_cursor]
        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        triggered = 0
        for patient_doc in patients:
            summary = await self.engine._device_management_summary(patient_doc)
            pid_str = str(patient_doc.get("_id"))
            imaging = await self.engine.get_imaging_report_analysis(
                patient_doc,
                pid_str,
                hours=96,
                max_age_hours=8,
                persist_if_refresh=False,
            )
            device_imaging = self.engine._select_imaging_signals(imaging, module_tags={"device"}, max_items=3)
            device_imaging_lines = self.engine._format_imaging_evidence_lines(device_imaging, max_items=2)

            line_malposition = next((item for item in device_imaging if str(item.get("code") or "") == "line_position_abnormal"), None)
            if line_malposition:
                rule_id = "DEVICE_POSITION_ABNORMAL"
                if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    explanation = await self.engine._polish_structured_alert_explanation(
                        {
                            "summary": "最新影像提示导管位置异常，存在装置相关风险。",
                            "evidence": device_imaging_lines or [str(line_malposition.get("sentence") or "影像提示导管位置异常")],
                            "suggestion": "建议尽快复核导管尖端/管端位置，必要时立即调整并复查影像。",
                            "text": "",
                        }
                    )
                    alert = await self.engine._create_alert(
                        rule_id=rule_id,
                        name="影像提示导管位置异常",
                        category="device_management",
                        alert_type="device_position_abnormal",
                        severity="high",
                        parameter="imaging_report",
                        condition={"report_signal": "line_position_abnormal"},
                        value=1,
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        source_time=line_malposition.get("report_time"),
                        explanation=explanation,
                        extra={
                            "imaging_findings": {
                                "summary": self.engine._build_imaging_summary(device_imaging),
                                "matched_signals": device_imaging,
                            },
                        },
                    )
                    if alert:
                        triggered += 1

            for device in summary.get("devices", []):
                if device["type"] == "cvc" and device.get("can_remove"):
                    rule_id = "DEVICE_CVC_REVIEW"
                    if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        continue
                    alert = await self.engine._create_alert(
                        rule_id=rule_id,
                        name="CVC必要性评估",
                        category="device_management",
                        alert_type="cvc_review",
                        severity="high" if device.get("line_days", 0) >= 7 else "warning",
                        parameter="cvc_line_days",
                        condition={"operator": ">=", "threshold": 3},
                        value=device.get("line_days"),
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        source_time=device.get("inserted_at"),
                        extra=device | ({
                            "imaging_findings": {
                                "summary": self.engine._build_imaging_summary(device_imaging),
                                "matched_signals": device_imaging,
                            }
                        } if device_imaging else {}),
                    )
                    if alert:
                        triggered += 1

                if device["type"] == "foley" and device.get("can_remove"):
                    rule_id = "DEVICE_FOLEY_REVIEW"
                    if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        continue
                    alert = await self.engine._create_alert(
                        rule_id=rule_id,
                        name="导尿管必要性评估",
                        category="device_management",
                        alert_type="foley_review",
                        severity="warning",
                        parameter="foley_line_days",
                        condition={"operator": ">=", "threshold": 1},
                        value=device.get("line_days"),
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        source_time=device.get("inserted_at"),
                        extra=device | ({
                            "imaging_findings": {
                                "summary": self.engine._build_imaging_summary(device_imaging),
                                "matched_signals": device_imaging,
                            }
                        } if device_imaging else {}),
                    )
                    if alert:
                        triggered += 1

                if device["type"] == "ett" and device.get("sbt_passed_no_extubation"):
                    rule_id = "DEVICE_ETT_EXTUBATION_DELAY"
                    if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        continue
                    alert = await self.engine._create_alert(
                        rule_id=rule_id,
                        name="SBT通过后24h未尝试拔管",
                        category="device_management",
                        alert_type="ett_extubation_delay",
                        severity="high",
                        parameter="ett_line_days",
                        condition={"operator": ">=", "threshold_hours": 24},
                        value=device.get("line_days"),
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        source_time=device.get("inserted_at"),
                        extra=device | ({
                            "imaging_findings": {
                                "summary": self.engine._build_imaging_summary(device_imaging),
                                "matched_signals": device_imaging,
                            }
                        } if device_imaging else {}),
                    )
                    if alert:
                        triggered += 1

        if triggered > 0:
            self.engine._log_info("装置管理", triggered)
