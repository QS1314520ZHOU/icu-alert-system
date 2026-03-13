"""颅脑损伤/颅高压"""
from __future__ import annotations

from .base import _extract_param


class TbiMixin:
    async def scan_tbi(self) -> None:
        binds = [b async for b in self.db.col("deviceBind").find({"unBindTime": None}, {"pid": 1, "deviceID": 1})]
        if not binds:
            return

        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        icp_codes = self._get_cfg_list(("alert_engine", "data_mapping", "icp_codes"), ["param_ICP", "param_icp"])
        cpp_codes = self._get_cfg_list(("alert_engine", "data_mapping", "cpp_codes"), ["param_CPP", "param_cpp"])

        triggered = 0
        for b in binds:
            pid = b.get("pid")
            device_id = b.get("deviceID")
            if not pid or not device_id:
                continue

            patient_doc, pid_str = await self._load_patient(pid)
            if not patient_doc or not pid_str:
                continue

            cap = await self._get_latest_device_cap(device_id)
            if not cap:
                continue

            icp = None
            for c in icp_codes:
                icp = _extract_param(cap, c)
                if icp is not None:
                    break

            cpp = None
            for c in cpp_codes:
                cpp = _extract_param(cap, c)
                if cpp is not None:
                    break

            if icp is not None:
                if icp > 25:
                    rule_id = "ICP_CRIT"
                    if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self._create_alert(
                            rule_id=rule_id,
                            name="颅内压危急升高",
                            category="tbi",
                            alert_type="icp",
                            severity="critical",
                            parameter="icp",
                            condition={">": 25},
                            value=icp,
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=device_id,
                            source_time=cap.get("time"),
                        )
                        if alert:
                            triggered += 1
                elif icp > 22:
                    rule_id = "ICP_HIGH"
                    if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self._create_alert(
                            rule_id=rule_id,
                            name="颅内压升高",
                            category="tbi",
                            alert_type="icp",
                            severity="high",
                            parameter="icp",
                            condition={">": 22},
                            value=icp,
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=device_id,
                            source_time=cap.get("time"),
                        )
                        if alert:
                            triggered += 1

            if cpp is not None and cpp < 60:
                rule_id = "CPP_LOW"
                if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self._create_alert(
                        rule_id=rule_id,
                        name="脑灌注不足(CPP<60)",
                        category="tbi",
                        alert_type="cpp",
                        severity="critical",
                        parameter="cpp",
                        condition={"<": 60},
                        value=cpp,
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        device_id=device_id,
                        source_time=cap.get("time"),
                    )
                    if alert:
                        triggered += 1

            gcs_drop = await self._get_gcs_drop(pid)
            if gcs_drop and gcs_drop["drop"] >= 2:
                rule_id = "GCS_DROP"
                if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self._create_alert(
                        rule_id=rule_id,
                        name="意识急性恶化(GCS下降)",
                        category="tbi",
                        alert_type="gcs_drop",
                        severity="high",
                        parameter="gcs",
                        condition={"drop": gcs_drop["drop"]},
                        value=gcs_drop["current"],
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        device_id=device_id,
                        source_time=gcs_drop.get("time"),
                        extra=gcs_drop,
                    )
                    if alert:
                        triggered += 1

            pupil = await self._get_pupil_status(pid)
            if pupil and pupil.get("abnormal"):
                rule_id = "PUPIL_ABN"
                if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self._create_alert(
                        rule_id=rule_id,
                        name="瞳孔变化异常",
                        category="tbi",
                        alert_type="pupil",
                        severity="critical",
                        parameter="pupil",
                        condition={"abnormal": True},
                        value=None,
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        device_id=device_id,
                        source_time=pupil.get("time"),
                        extra=pupil,
                    )
                    if alert:
                        triggered += 1

        if triggered > 0:
            self._log_info("颅脑预警", triggered)

    def _log_info(self, name: str, count: int) -> None:
        import logging

        logger = logging.getLogger("icu-alert")
        logger.info(f"[{name}] 本轮触发 {count} 条预警")