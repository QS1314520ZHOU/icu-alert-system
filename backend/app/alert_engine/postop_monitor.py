"""术后并发症监测。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.utils.clinical import _cap_time, _cap_value
from app.utils.labs import _lab_time
from app.utils.parse import _parse_dt, _parse_number


class PostopMonitorMixin:
    def _postop_cfg(self) -> dict:
        cfg = self.config.yaml_cfg.get("alert_engine", {}).get("postop_monitor", {})
        return cfg if isinstance(cfg, dict) else {}

    def _text_contains_any(self, text: str, keywords: list[str]) -> bool:
        blob = str(text or "").lower()
        return any(str(k).strip().lower() in blob for k in keywords if str(k).strip())

    def _patient_text_blob(self, patient_doc: dict) -> str:
        return " ".join(
            str(patient_doc.get(k) or "")
            for k in (
                "clinicalDiagnosis",
                "admissionDiagnosis",
                "history",
                "diagnosisHistory",
                "surgeryHistory",
                "operationHistory",
                "chiefComplaint",
                "presentIllness",
                "allDiagnosis",
            )
        ).lower()

    def _volume_to_ml(self, value: Any, unit: Any = None) -> float | None:
        num = _parse_number(value)
        if num is None or num <= 0:
            return None
        u = str(unit or "").strip().lower().replace(" ", "")
        if not u:
            return num
        if any(k in u for k in ("ml", "毫升", "cc")):
            return num
        if any(k in u for k in ("l", "升", "liter")) and "ml" not in u:
            return num * 1000.0
        if "dl" in u:
            return num * 100.0
        return num

    async def _is_postop_patient(self, patient_doc: dict, now: datetime) -> dict | None:
        surgery_time = (
            _parse_dt(patient_doc.get("surgeryTime"))
            or _parse_dt(patient_doc.get("operationTime"))
            or _parse_dt(patient_doc.get("recentSurgeryTime"))
            or _parse_dt(patient_doc.get("lastOperationTime"))
        )
        text_keywords = self._get_cfg_list(
            ("alert_engine", "postop_monitor", "postop_keywords"),
            ["术后", "手术后", "postop", "post-op"],
        )
        text_matched = self._text_contains_any(self._patient_text_blob(patient_doc), text_keywords)
        if not surgery_time and not text_matched:
            return None

        hours_since_surgery = 0.0
        if isinstance(surgery_time, datetime) and now >= surgery_time:
            hours_since_surgery = round((now - surgery_time).total_seconds() / 3600.0, 2)
        else:
            adm = _parse_dt(patient_doc.get("icuAdmissionTime"))
            if adm and now >= adm:
                hours_since_surgery = round((now - adm).total_seconds() / 3600.0, 2)

        return {
            "is_postop": True,
            "surgery_time": surgery_time,
            "hours_since_surgery": hours_since_surgery,
        }

    def _postop_since(self, postop_info: dict | None, patient_doc: dict, now: datetime, fallback_hours: int = 168) -> datetime:
        if postop_info and isinstance(postop_info.get("surgery_time"), datetime):
            return postop_info["surgery_time"]
        adm = _parse_dt(patient_doc.get("icuAdmissionTime"))
        if adm and adm <= now:
            return adm
        return now - timedelta(hours=fallback_hours)

    async def _get_named_lab_series(
        self,
        his_pid: str,
        keywords: list[str],
        since: datetime,
        *,
        limit: int = 600,
        kind: str = "",
    ) -> list[dict]:
        if not his_pid:
            return []
        cursor = self.db.dc_col("VI_ICU_EXAM_ITEM").find({"hisPid": his_pid}).sort("authTime", -1).limit(limit)
        series: list[dict] = []
        lower_keywords = [str(k).strip().lower() for k in keywords if str(k).strip()]
        async for doc in cursor:
            t = _lab_time(doc)
            if not t or t < since:
                continue
            name = str(doc.get("itemCnName") or doc.get("itemName") or doc.get("item") or doc.get("itemCode") or "").strip()
            if not name:
                continue
            if not any(k in name.lower() for k in lower_keywords):
                continue
            raw_val = doc.get("result") or doc.get("resultValue") or doc.get("value")
            num = _parse_number(raw_val)
            if num is None:
                continue
            unit = str(doc.get("unit") or doc.get("resultUnit") or "").strip()
            value = float(num)
            u = unit.lower().replace(" ", "")
            if kind == "crp":
                if "mg/dl" in u:
                    value = value * 10.0
            elif kind == "wbc":
                if any(k in u for k in ("/ul", "/μl", "/uml")):
                    value = value / 1000.0
            series.append({"time": t, "value": value, "unit": unit, "raw_name": name})
        series.sort(key=lambda x: x["time"])
        return series

    async def _get_postop_drainage(self, pid_str: str, since: datetime) -> dict:
        keywords = self._get_cfg_list(
            ("alert_engine", "postop_monitor", "drainage_keywords"),
            ["引流量", "drain", "引流", "drainage"],
        )
        cursor = self.db.col("bedside").find(
            {"pid": pid_str, "time": {"$gte": since}},
            {
                "time": 1,
                "code": 1,
                "name": 1,
                "paramName": 1,
                "itemName": 1,
                "remark": 1,
                "strVal": 1,
                "value": 1,
                "fVal": 1,
                "intVal": 1,
                "unit": 1,
            },
        ).sort("time", 1).limit(800)

        total_ml = 0.0
        max_single_ml = 0.0
        latest_time: datetime | None = None
        async for doc in cursor:
            text = " ".join(
                str(doc.get(k) or "")
                for k in ("code", "name", "paramName", "itemName", "remark")
            ).lower()
            if not self._text_contains_any(text, keywords):
                continue
            value_ml = None
            for field in ("fVal", "intVal", "value", "strVal"):
                value_ml = self._volume_to_ml(doc.get(field), doc.get("unit"))
                if value_ml is not None:
                    break
            if value_ml is None:
                continue
            total_ml += value_ml
            max_single_ml = max(max_single_ml, value_ml)
            t = _cap_time(doc)
            if isinstance(t, datetime):
                latest_time = t

        return {
            "total_6h_ml": round(total_ml, 1),
            "max_single_ml": round(max_single_ml, 1),
            "time": latest_time,
        }

    def _detect_temp_v_rebound(self, temp_series: list[dict]) -> tuple[bool, dict]:
        numeric = [float(x["value"]) for x in temp_series if x.get("value") is not None]
        if len(numeric) < 3:
            return False, {"low": None, "rebound": None, "pre_peak": None}

        before_max: float | None = None
        for idx, value in enumerate(numeric):
            before_max = value if before_max is None else max(before_max, value)
            if value >= 37.5:
                continue
            rebound = max(numeric[idx + 1 :], default=None)
            if rebound is not None and rebound > 38.5 and before_max is not None and before_max > value:
                return True, {
                    "low": round(value, 2),
                    "rebound": round(rebound, 2),
                    "pre_peak": round(before_max, 2),
                }
        return False, {"low": None, "rebound": None, "pre_peak": round(max(numeric), 2) if numeric else None}

    async def _get_postop_gi_status(self, pid_str: str, since: datetime) -> dict:
        gi_keywords = self._get_cfg_list(
            ("alert_engine", "postop_monitor", "gi_keywords"),
            ["肠鸣音", "bowel_sound", "排气", "排便", "flatus", "胃残余量", "gastric_residual"],
        )
        positive_keywords = self._get_cfg_list(
            ("alert_engine", "postop_monitor", "gi_positive_keywords"),
            ["排气", "排便", "肠鸣音恢复", "bowel sound recovered", "flatus", "defecation", "已恢复"],
        )
        grv_keywords = self._get_cfg_list(
            ("alert_engine", "postop_monitor", "grv_keywords"),
            ["胃残余量", "gastric_residual", "胃潴留", "grv"],
        )
        cursor = self.db.col("bedside").find(
            {"pid": pid_str, "time": {"$gte": since}},
            {
                "time": 1,
                "code": 1,
                "name": 1,
                "paramName": 1,
                "itemName": 1,
                "remark": 1,
                "strVal": 1,
                "value": 1,
                "fVal": 1,
                "intVal": 1,
                "unit": 1,
            },
        ).sort("time", -1).limit(1200)

        has_positive = False
        positive_time: datetime | None = None
        latest_grv: float | None = None
        latest_grv_time: datetime | None = None

        async for doc in cursor:
            text = " ".join(
                str(doc.get(k) or "")
                for k in ("code", "name", "paramName", "itemName", "remark", "strVal")
            ).lower()
            if not self._text_contains_any(text, gi_keywords):
                continue

            t = _cap_time(doc)
            if self._text_contains_any(text, positive_keywords):
                has_positive = True
                if isinstance(t, datetime):
                    positive_time = t

            if self._text_contains_any(text, grv_keywords):
                value = None
                for field in ("fVal", "intVal", "value", "strVal"):
                    value = self._volume_to_ml(doc.get(field), doc.get("unit"))
                    if value is not None:
                        break
                if value is not None and latest_grv is None:
                    latest_grv = round(value, 1)
                    latest_grv_time = t if isinstance(t, datetime) else None

        return {
            "has_positive_gi_recovery": has_positive,
            "positive_time": positive_time,
            "latest_grv_ml": latest_grv,
            "latest_grv_time": latest_grv_time,
        }

    async def scan_postop_complications(self) -> None:
        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        patient_cursor = self.db.col("patient").find(
            self._active_patient_query(),
            {
                "_id": 1,
                "name": 1,
                "hisPid": 1,
                "hisBed": 1,
                "dept": 1,
                "hisDept": 1,
                "deptCode": 1,
                "icuAdmissionTime": 1,
                "surgeryTime": 1,
                "operationTime": 1,
                "recentSurgeryTime": 1,
                "lastOperationTime": 1,
                "clinicalDiagnosis": 1,
                "admissionDiagnosis": 1,
                "history": 1,
                "diagnosisHistory": 1,
                "surgeryHistory": 1,
                "operationHistory": 1,
                "chiefComplaint": 1,
                "presentIllness": 1,
                "allDiagnosis": 1,
            },
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        triggered = 0
        now = datetime.now()

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = self._pid_str(pid)
            his_pid = str(patient_doc.get("hisPid") or "").strip()
            postop_info = await self._is_postop_patient(patient_doc, now)
            if not postop_info:
                continue

            surgery_time = self._postop_since(postop_info, patient_doc, now)
            hours_since_surgery = float(postop_info.get("hours_since_surgery") or 0.0)
            device_id = await self._get_device_id_for_patient(patient_doc, ["monitor"])

            latest_cap = await self._get_latest_param_snapshot_by_pid(
                pid,
                codes=["param_HR", "param_T", "param_nibp_m", "param_ibp_m", "param_nibp_s", "param_ibp_s"],
            )
            if not latest_cap and device_id:
                latest_cap = await self._get_latest_device_cap(
                    device_id,
                    codes=["param_HR", "param_T", "param_nibp_m", "param_ibp_m", "param_nibp_s", "param_ibp_s"],
                )
            if latest_cap:
                latest_cap, _ = await self._filter_snapshot_quality(
                    pid=pid,
                    pid_str=pid_str,
                    patient_doc=patient_doc,
                    cap=latest_cap,
                    device_id=device_id,
                    same_rule_sec=same_rule_sec,
                    max_per_hour=max_per_hour,
                )

            latest_hr = self._get_priority_param(latest_cap or {}, ["param_HR"]) if latest_cap else None
            latest_map = self._get_map(latest_cap or {}) if latest_cap else None

            # A. 术后出血
            bleed_score = 0.0
            hb_trend = None
            if his_pid:
                hb_series = await self._get_lab_series(his_pid, "hb", surgery_time, limit=120)
                if len(hb_series) >= 2:
                    baseline_hb = float(hb_series[0]["value"])
                    latest_hb = float(hb_series[-1]["value"])
                    hb_drop = baseline_hb - latest_hb
                    hb_trend = {
                        "baseline": baseline_hb,
                        "latest": latest_hb,
                        "drop": round(hb_drop, 1),
                        "time": hb_series[-1]["time"],
                    }
                    if hb_drop >= 20:
                        bleed_score += 3

            if (latest_map is not None and latest_map < 65) or (latest_hr is not None and latest_hr > 110):
                bleed_score += 3

            drain_info = await self._get_postop_drainage(pid_str, now - timedelta(hours=6))
            if drain_info["total_6h_ml"] > 200 or drain_info["max_single_ml"] > 100:
                bleed_score += 2

            if bleed_score >= 5:
                rule_id = "POSTOP_BLEEDING"
                if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    severity = "critical" if bleed_score >= 8 else "high"
                    source_time = max(
                        [
                            t
                            for t in [
                                latest_cap.get("time") if latest_cap else None,
                                hb_trend.get("time") if isinstance(hb_trend, dict) else None,
                                drain_info.get("time"),
                            ]
                            if isinstance(t, datetime)
                        ]
                        or [now]
                    )
                    alert = await self._create_alert(
                        rule_id=rule_id,
                        name="术后出血风险",
                        category="syndrome",
                        alert_type="postop_bleeding",
                        severity=severity,
                        parameter="postop_bleeding_score",
                        condition={"operator": ">=", "threshold": 5},
                        value=round(bleed_score, 1),
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        device_id=device_id,
                        source_time=source_time,
                        extra={
                            "hb_trend": hb_trend,
                            "map": latest_map,
                            "hr": latest_hr,
                            "drain_volume": drain_info,
                            "hours_since_surgery": hours_since_surgery,
                        },
                    )
                    if alert:
                        triggered += 1

            # B. 术后感染二次高峰/吻合口瘘风险
            if hours_since_surgery > 48:
                temp_series = await self._get_param_series_by_pid(pid, "param_T", surgery_time, prefer_device_types=["monitor"], limit=800)
                temp_series = self._filter_series_quality("param_T", temp_series)
                temp_rebound, temp_meta = self._detect_temp_v_rebound(temp_series)

                wbc_series = await self._get_named_lab_series(
                    his_pid,
                    self._get_cfg_list(("alert_engine", "postop_monitor", "wbc_keywords"), ["白细胞", "wbc"]),
                    surgery_time,
                    limit=200,
                    kind="wbc",
                ) if his_pid else []
                crp_series = await self._get_named_lab_series(
                    his_pid,
                    self._get_cfg_list(("alert_engine", "postop_monitor", "crp_keywords"), ["CRP", "C反应蛋白", "c-reactive"]),
                    surgery_time,
                    limit=200,
                    kind="crp",
                ) if his_pid else []

                wbc_latest = wbc_series[-1]["value"] if wbc_series else None
                wbc_min = min((float(x["value"]) for x in wbc_series if x.get("value") is not None), default=None)
                wbc_rise = bool(wbc_latest is not None and wbc_min not in (None, 0) and wbc_latest > 12 and float(wbc_latest) >= float(wbc_min) * 1.5)

                crp_latest = crp_series[-1]["value"] if crp_series else None
                crp_prev = crp_series[-2]["value"] if len(crp_series) >= 2 else None
                crp_doubled = bool(crp_latest is not None and crp_prev not in (None, 0) and float(crp_latest) >= float(crp_prev) * 2)

                if temp_rebound and (wbc_rise or crp_doubled):
                    rule_id = "POSTOP_ANASTOMOTIC_LEAK_RISK"
                    if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        source_time = max(
                            [
                                t
                                for t in [
                                    latest_cap.get("time") if latest_cap else None,
                                    wbc_series[-1]["time"] if wbc_series else None,
                                    crp_series[-1]["time"] if crp_series else None,
                                ]
                                if isinstance(t, datetime)
                            ]
                            or [now]
                        )
                        alert = await self._create_alert(
                            rule_id=rule_id,
                            name="术后感染二次高峰/吻合口瘘风险",
                            category="syndrome",
                            alert_type="postop_infection_resurgence",
                            severity="high",
                            parameter="postop_infection_pattern",
                            condition={"temp_rebound": True, "wbc_rise_or_crp_doubled": True},
                            value=1,
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=device_id,
                            source_time=source_time,
                            extra={
                                "hours_since_surgery": hours_since_surgery,
                                "temperature_pattern": temp_meta,
                                "wbc": {
                                    "latest": wbc_latest,
                                    "postop_min": wbc_min,
                                    "rise_ratio": round(float(wbc_latest) / float(wbc_min), 2) if wbc_latest is not None and wbc_min not in (None, 0) else None,
                                },
                                "crp": {
                                    "latest": crp_latest,
                                    "previous": crp_prev,
                                    "rise_ratio": round(float(crp_latest) / float(crp_prev), 2) if crp_latest is not None and crp_prev not in (None, 0) else None,
                                },
                            },
                        )
                        if alert:
                            triggered += 1

            # C. 术后肠麻痹
            if hours_since_surgery > 24:
                gi_status = await self._get_postop_gi_status(pid_str, surgery_time)
                ileus_reasons: list[str] = []
                if hours_since_surgery > 72 and not gi_status["has_positive_gi_recovery"]:
                    ileus_reasons.append("术后72h仍无排气/排便/肠鸣音恢复记录")
                latest_grv = gi_status.get("latest_grv_ml")
                if latest_grv is not None and latest_grv > 500:
                    ileus_reasons.append("胃残余量>500mL")

                if ileus_reasons:
                    rule_id = "POSTOP_ILEUS"
                    if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        source_time = max(
                            [
                                t
                                for t in [gi_status.get("positive_time"), gi_status.get("latest_grv_time"), latest_cap.get("time") if latest_cap else None]
                                if isinstance(t, datetime)
                            ]
                            or [now]
                        )
                        alert = await self._create_alert(
                            rule_id=rule_id,
                            name="术后肠麻痹",
                            category="syndrome",
                            alert_type="postop_ileus",
                            severity="warning",
                            parameter="postop_ileus",
                            condition={"operator": "postop_gi_recovery_delayed"},
                            value=1,
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=device_id,
                            source_time=source_time,
                            extra={
                                "hours_since_surgery": hours_since_surgery,
                                "reasons": ileus_reasons,
                                "has_positive_gi_recovery": gi_status["has_positive_gi_recovery"],
                                "latest_grv_ml": latest_grv,
                            },
                        )
                        if alert:
                            triggered += 1

        if triggered > 0:
            self._log_info("术后并发症", triggered)
