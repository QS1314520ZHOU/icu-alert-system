"""监护数据可信度过滤."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


class DataQualityFilterMixin:
    def _dq_cfg(self) -> dict[str, Any]:
        cfg = self._cfg("alert_engine", "data_quality_filter", default={})
        return cfg if isinstance(cfg, dict) else {}

    def _nullify_cap_param(self, cap: dict, key: str) -> None:
        if not isinstance(cap, dict):
            return
        if key in cap:
            cap[key] = None
        params = cap.get("params")
        if isinstance(params, dict) and key in params:
            params[key] = None

    async def _emit_data_quality_alert(
        self,
        *,
        pid_str: str,
        patient_doc: dict | None,
        device_id: str | None,
        issue: dict[str, Any],
        same_rule_sec: int,
        max_per_hour: int,
        source_time: datetime | None = None,
    ) -> None:
        code = str(issue.get("code") or "signal").upper()
        rule_id = f"DQ_{code}_{str(issue.get('type') or 'UNRELIABLE').upper()}"
        if await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
            return
        await self._create_alert(
            rule_id=rule_id,
            name="设备信号异常",
            category="device_management",
            alert_type="signal_quality",
            severity="warning",
            parameter=issue.get("code") or "signal_quality",
            condition={"operator": "unreliable", "reason": issue.get("type")},
            value=issue.get("value"),
            patient_id=pid_str,
            patient_doc=patient_doc,
            device_id=device_id,
            source_time=source_time,
            extra=issue,
            explanation={
                "summary": str(issue.get("message") or "监护信号可信度不足，暂不进入临床预警判断。"),
                "evidence": [str(issue.get("detail") or "")] if issue.get("detail") else [],
                "suggestion": "请检查导联、电极、袖带或探头位置，确认信号后再判读。",
            },
        )

    async def _filter_snapshot_quality(
        self,
        *,
        pid,
        pid_str: str,
        patient_doc: dict | None,
        cap: dict,
        device_id: str | None,
        same_rule_sec: int,
        max_per_hour: int,
    ) -> tuple[dict, list[dict[str, Any]]]:
        filtered = dict(cap or {})
        issues: list[dict[str, Any]] = []
        if not filtered:
            return filtered, issues

        cfg = self._dq_cfg()
        hr_code = self._cfg("vital_signs", "heart_rate", "code", default="param_HR")
        spo2_code = self._cfg("vital_signs", "spo2", "code", default="param_spo2")
        temp_code = self._cfg("vital_signs", "temperature", "code", default="param_T")
        sbp_codes = self._cfg("vital_signs", "sbp_priority", default=["param_ibp_s", "param_nibp_s"]) or ["param_ibp_s", "param_nibp_s"]

        hr = self._get_priority_param(filtered, [hr_code, "param_PR"])
        spo2 = self._get_priority_param(filtered, [spo2_code])
        temp = self._get_priority_param(filtered, [temp_code])

        if hr is not None and hr <= 0 and spo2 is not None and spo2 > float(cfg.get("lead_off_spo2_threshold", 90)):
            self._nullify_cap_param(filtered, hr_code)
            issues.append(
                {
                    "type": "lead_off_suspected",
                    "code": hr_code,
                    "value": hr,
                    "message": "心率显示为0，但SpO₂仍维持较高水平，更像导联脱落而非真实停搏。",
                    "detail": f"HR={hr}, SpO₂={spo2}",
                }
            )

        if temp is not None:
            min_temp = float(cfg.get("temp_min_c", 30))
            max_temp = float(cfg.get("temp_max_c", 43))
            if temp < min_temp or temp > max_temp:
                self._nullify_cap_param(filtered, temp_code)
                issues.append(
                    {
                        "type": "temp_probe_suspected",
                        "code": temp_code,
                        "value": temp,
                        "message": "体温超出生理可信范围，疑似探头位置异常。",
                        "detail": f"T={temp}℃",
                    }
                )

        sbp_delta_threshold = float(cfg.get("nibp_delta_threshold", 40))
        for code in [str(c) for c in sbp_codes if str(c)]:
            latest = self._get_priority_param(filtered, [code])
            if latest is None or "nibp" not in code.lower():
                continue
            series = await self._get_param_series_by_pid(
                pid,
                code,
                datetime.now() - timedelta(minutes=60),
                prefer_device_types=["monitor"],
                limit=20,
            )
            series = [s for s in series if s.get("value") is not None]
            if len(series) < 2:
                continue
            v1 = float(series[-1]["value"])
            v2 = float(series[-2]["value"])
            unstable = abs(v1 - v2) > sbp_delta_threshold
            if unstable and len(series) >= 3:
                v3 = float(series[-3]["value"])
                unstable = abs(v1 - v3) > sbp_delta_threshold
            if unstable:
                self._nullify_cap_param(filtered, code)
                issues.append(
                    {
                        "type": "nibp_unstable",
                        "code": code,
                        "value": v1,
                        "message": "无创血压相邻读数波动过大，暂按测量不可靠处理，等待再次确认。",
                        "detail": f"{code}: {v2} → {v1} mmHg",
                    }
                )

        for issue in issues:
            await self._emit_data_quality_alert(
                pid_str=pid_str,
                patient_doc=patient_doc,
                device_id=device_id,
                issue=issue,
                same_rule_sec=same_rule_sec,
                max_per_hour=max_per_hour,
                source_time=filtered.get("time"),
            )
        return filtered, issues

    def _filter_series_quality(self, code: str, series: list[dict]) -> list[dict]:
        code_l = str(code or "").lower()
        cleaned: list[dict] = []
        for idx, point in enumerate(series or []):
            value = point.get("value")
            if value is None:
                continue
            v = float(value)
            if ("param_t" in code_l or code_l == "temp") and (v < 30 or v > 43):
                continue
            if ("param_hr" in code_l or code_l == "hr") and (v <= 0 or v > 250):
                continue
            if ("spo2" in code_l) and (v < 30 or v > 100):
                continue
            if (("nibp" in code_l) or ("ibp" in code_l)) and (v < 20 or v > 280):
                continue
            if cleaned:
                prev = float(cleaned[-1]["value"])
                if "nibp" in code_l and abs(v - prev) > 40 and idx < len(series) - 1:
                    nxt = float(series[idx + 1].get("value") or v)
                    if abs(nxt - prev) <= 40:
                        continue
            cleaned.append(point)
        return cleaned
