"""液体平衡 / 液体过负荷 / 去复苏时机预警。"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None


def _severity_rank(sev: str) -> int:
    return {"warning": 1, "high": 2, "critical": 3}.get(str(sev), 0)


class FluidBalanceMixin:
    def _volume_to_ml(self, value: Any, unit: Any = None, assume_ml: bool = False) -> float | None:
        num = _to_float(value)
        if num is None or num <= 0:
            return None
        u = str(unit or "").strip().lower().replace(" ", "")
        if not u:
            return num if assume_ml else None
        if any(k in u for k in ("ml", "毫升", "cc")):
            return num
        if any(k in u for k in ("l", "升", "liter")) and "ml" not in u:
            return num * 1000.0
        if "dl" in u:
            return num * 100.0
        return num if assume_ml else None

    def _parse_volume_text_ml(self, text: Any) -> float | None:
        s = str(text or "").strip()
        if not s:
            return None
        m = re.search(r"(\d+(?:\.\d+)?)\s*(ml|mL|ML|l|L|升|毫升|cc)", s)
        if not m:
            return None
        val = _to_float(m.group(1))
        if val is None or val <= 0:
            return None
        unit = m.group(2)
        return self._volume_to_ml(val, unit, assume_ml=False)

    def _get_weight_kg(self, patient_doc: dict) -> float | None:
        for key in ("weight", "bodyWeight", "body_weight", "weightKg", "weight_kg"):
            v = _to_float(patient_doc.get(key))
            if v is not None and 20 <= v <= 300:
                return v
        return None

    def _classify_intake(self, doc: dict) -> str:
        text = " ".join(
            str(doc.get(k) or "")
            for k in ("route", "routeName", "exeMethod", "orderType", "drugName", "orderName")
        ).lower()

        oral_kw = ("口服", "po", "oral", "鼻饲口服")
        enteral_kw = ("肠内", "鼻饲", "胃管", "enteral", "tube feeding")
        iv_kw = ("静脉", "iv", "ivgtt", "静滴", "输液", "滴注", "微泵", "pump", "注射")

        if any(k in text for k in oral_kw):
            return "oral"
        if any(k in text for k in enteral_kw):
            return "enteral"
        if any(k in text for k in iv_kw):
            return "iv"
        return "iv"

    def _classify_output(self, doc: dict, code_map: dict[str, set[str]]) -> str | None:
        code = str(doc.get("code") or "").strip()
        if code:
            for cat, codes in code_map.items():
                if code in codes:
                    return cat

        text = " ".join(
            str(doc.get(k) or "")
            for k in ("code", "name", "paramName", "itemName", "remark")
        ).lower()

        if any(k in text for k in ("urine", "尿量", "导尿", "uop", "param_urine", "udd_urine")):
            return "urine"
        if any(k in text for k in ("drain", "引流", "胸腔", "腹腔", "引流量")):
            return "drainage"
        if any(k in text for k in ("ultra", "超滤", "uf", "净超")):
            return "ultrafiltration"
        if any(k in text for k in ("胃肠减压", "胃液", "胃管", "ngt", "nasogastric")):
            return "gi_decompression"
        return None

    def _max_severity(self, left: str | None, right: str | None) -> str | None:
        l = str(left or "")
        r = str(right or "")
        return l if _severity_rank(l) >= _severity_rank(r) else r

    def _upgrade_once(self, severity: str | None) -> str | None:
        s = str(severity or "")
        if s == "warning":
            return "high"
        if s == "high":
            return "critical"
        return severity

    def _sum_window(self, events: list[dict], hours: int, now: datetime, *, category: str | None = None) -> float:
        since = now - timedelta(hours=hours)
        total = 0.0
        for e in events:
            t = e.get("time")
            if not isinstance(t, datetime):
                continue
            if t < since or t > now:
                continue
            if category and e.get("category") != category:
                continue
            v = _to_float(e.get("volume_ml"))
            if v is not None and v > 0:
                total += v
        return round(total, 1)

    async def _collect_intake_events(self, pid_str: str, since: datetime) -> list[dict]:
        cursor = self.db.col("drugExe").find(
            {"pid": pid_str},
            {
                "executeTime": 1,
                "startTime": 1,
                "orderTime": 1,
                "route": 1,
                "routeName": 1,
                "exeMethod": 1,
                "orderType": 1,
                "drugName": 1,
                "orderName": 1,
                "dose": 1,
                "doseUnit": 1,
                "volume": 1,
                "volumeUnit": 1,
                "totalVolume": 1,
                "inputVolume": 1,
                "infusionVolume": 1,
                "unit": 1,
                "drugSpec": 1,
            },
        ).sort("executeTime", -1).limit(800)

        events: list[dict] = []
        async for doc in cursor:
            t = _parse_dt(doc.get("executeTime")) or _parse_dt(doc.get("startTime")) or _parse_dt(doc.get("orderTime"))
            if not t or t < since:
                continue

            volume_ml = None
            vol_unit = doc.get("volumeUnit") or doc.get("unit") or doc.get("doseUnit")

            for field in ("volume", "totalVolume", "inputVolume", "infusionVolume"):
                volume_ml = self._volume_to_ml(doc.get(field), vol_unit, assume_ml=True)
                if volume_ml:
                    break

            if not volume_ml:
                volume_ml = self._volume_to_ml(doc.get("dose"), doc.get("doseUnit"), assume_ml=False)

            if not volume_ml:
                for field in ("dose", "drugSpec", "drugName", "orderName"):
                    volume_ml = self._parse_volume_text_ml(doc.get(field))
                    if volume_ml:
                        break

            if not volume_ml or volume_ml <= 0:
                continue

            category = self._classify_intake(doc)
            events.append(
                {
                    "time": t,
                    "volume_ml": round(volume_ml, 1),
                    "category": category,
                    "source": "drugExe",
                }
            )
        return events

    async def _collect_output_events(self, pid_str: str, since: datetime) -> list[dict]:
        mapping_cfg = self.config.yaml_cfg.get("alert_engine", {}).get("data_mapping", {})
        output_cfg = mapping_cfg.get("fluid_output", {}) if isinstance(mapping_cfg, dict) else {}
        urine_codes = set(
            self._get_cfg_list(
                ("alert_engine", "data_mapping", "urine_output", "codes"),
                ["param_urine", "param_尿量", "urine_output", "urine_ml_h", "param_udd_urine_total"],
            )
        )
        drainage_codes = set(output_cfg.get("drainage_codes", ["param_drainage", "param_引流量", "drainage_output"]))
        uf_codes = set(output_cfg.get("ultrafiltration_codes", ["param_uf", "param_超滤量", "ultrafiltration_output"]))
        gi_codes = set(output_cfg.get("gi_decompression_codes", ["param_gi_decompression", "param_胃肠减压", "gi_decompression_output"]))

        code_map: dict[str, set[str]] = {
            "urine": urine_codes,
            "drainage": drainage_codes,
            "ultrafiltration": uf_codes,
            "gi_decompression": gi_codes,
        }
        all_codes = set().union(*code_map.values())
        projection = {
            "time": 1,
            "code": 1,
            "name": 1,
            "paramName": 1,
            "itemName": 1,
            "remark": 1,
            "fVal": 1,
            "intVal": 1,
            "strVal": 1,
            "value": 1,
            "unit": 1,
        }

        async def _load_events(query: dict, *, fallback: bool = False) -> list[dict]:
            cursor = self.db.col("bedside").find(query, projection).sort("time", -1).limit(3000)
            rows: list[dict] = []
            async for doc in cursor:
                t = _parse_dt(doc.get("time"))
                if not t or t < since:
                    continue

                category = self._classify_output(doc, code_map)
                if not category:
                    continue

                volume_ml = None
                for field in ("fVal", "intVal", "value"):
                    volume_ml = self._volume_to_ml(doc.get(field), doc.get("unit"), assume_ml=True)
                    if volume_ml:
                        break
                if not volume_ml:
                    volume_ml = self._volume_to_ml(doc.get("strVal"), doc.get("unit"), assume_ml=True)
                if not volume_ml or volume_ml <= 0:
                    continue

                rows.append(
                    {
                        "time": t,
                        "volume_ml": round(volume_ml, 1),
                        "category": category,
                        "source": "bedside",
                        "code": doc.get("code"),
                        "fallback": fallback,
                    }
                )
            return rows

        exact_query: dict = {"pid": pid_str, "time": {"$gte": since}}
        if all_codes:
            exact_query["code"] = {"$in": list(all_codes)}
        events = await _load_events(exact_query, fallback=False)
        if events or not all_codes:
            return events

        fuzzy_query = {"pid": pid_str, "time": {"$gte": since}}
        return await _load_events(fuzzy_query, fallback=True)

    async def _has_recent_aki_or_ards(self, pid_str: str, now: datetime, lookback_hours: int) -> bool:
        since = now - timedelta(hours=max(1, lookback_hours))
        cnt = await self.db.col("alert_records").count_documents(
            {
                "patient_id": pid_str,
                "alert_type": {"$in": ["aki", "ards"]},
                "created_at": {"$gte": since},
            }
        )
        return cnt > 0

    async def _get_map_series(self, pid, since: datetime) -> list[dict]:
        ibp = await self._get_param_series_by_pid(pid, "param_ibp_m", since, prefer_device_types=["monitor"], limit=300)
        ibp = self._filter_series_quality("param_ibp_m", ibp) if hasattr(self, "_filter_series_quality") else ibp
        if len(ibp) >= 2:
            return ibp
        nibp = await self._get_param_series_by_pid(pid, "param_nibp_m", since, prefer_device_types=["monitor"], limit=300)
        nibp = self._filter_series_quality("param_nibp_m", nibp) if hasattr(self, "_filter_series_quality") else nibp
        return nibp or ibp

    def _series_first_last(self, series: list[dict]) -> tuple[float | None, float | None]:
        nums = [float(row.get("value")) for row in series if row.get("value") is not None]
        if not nums:
            return None, None
        return nums[0], nums[-1]

    async def _get_lactate_trend(self, his_pid: str | None, now: datetime, hours: int = 6) -> dict:
        if not his_pid:
            return {"series": [], "earliest": None, "latest": None, "ratio": None, "down": False}
        series = await self._get_lab_series(his_pid, "lac", now - timedelta(hours=max(2, hours)), limit=60)
        earliest = series[0]["value"] if series else None
        latest = series[-1]["value"] if series else None
        ratio = None
        if earliest not in (None, 0) and latest is not None:
            ratio = round(float(latest) / float(earliest), 3)
        down = bool(ratio is not None and ratio < 1.0)
        return {"series": series, "earliest": earliest, "latest": latest, "ratio": ratio, "down": down}

    async def _has_recent_sepsis_or_shock(self, pid_str: str, now: datetime, lookback_hours: int) -> bool:
        since = now - timedelta(hours=max(1, lookback_hours))
        cnt = await self.db.col("alert_records").count_documents(
            {
                "patient_id": pid_str,
                "alert_type": {"$in": ["qsofa", "sofa", "septic_shock"]},
                "created_at": {"$gte": since},
            }
        )
        return cnt > 0

    async def _get_hemodynamic_responsiveness_context(self, pid_str: str, now: datetime, hours: int = 12) -> dict:
        alert = await self._get_latest_active_alert(pid_str, ["fluid_responsiveness"], hours=hours)
        extra = alert.get("extra") if isinstance(alert, dict) and isinstance(alert.get("extra"), dict) else {}
        message = str(extra.get("message") or "")
        return {
            "has_alert": bool(alert),
            "message": message,
            "ppv": extra.get("ppv"),
            "svv": extra.get("svv"),
            "nonresponsive": any(k in message for k in ["补液可能无效", "容量反应性低"]),
        }

    async def _assess_fluid_responsiveness_lost(
        self,
        *,
        pid,
        pid_str: str,
        his_pid: str | None,
        now: datetime,
        intake_6h: float,
        urine_6h: float,
        rapid_threshold_ml: float,
        urine_response_threshold_ml: float,
        cfg: dict,
    ) -> dict | None:
        if intake_6h < rapid_threshold_ml:
            return None

        map_series = await self._get_map_series(pid, now - timedelta(hours=6))
        map_first, map_last = self._series_first_last(map_series)
        map_gain = round(float(map_last) - float(map_first), 1) if map_first is not None and map_last is not None else None
        map_min_increase = float(cfg.get("map_min_increase_mmHg", 3))
        map_not_improved = map_gain is not None and map_gain < map_min_increase

        lactate = await self._get_lactate_trend(his_pid, now, hours=6)
        lactate_ratio = lactate.get("ratio")
        lactate_nonresponse_ratio = float(cfg.get("lactate_nonresponse_ratio", 0.9))
        lactate_not_improved = lactate_ratio is not None and lactate_ratio >= lactate_nonresponse_ratio

        urine_low = urine_6h < urine_response_threshold_ml
        hemo_ctx = await self._get_hemodynamic_responsiveness_context(pid_str, now, hours=12)

        corroborators = 0
        if map_not_improved:
            corroborators += 1
        if lactate_not_improved:
            corroborators += 1
        if urine_low:
            corroborators += 1
        if hemo_ctx.get("nonresponsive"):
            corroborators += 1

        core_nonresponse = map_not_improved or lactate_not_improved
        if not core_nonresponse or corroborators < 2:
            return None

        return {
            "severity": "high",
            "intake_6h_ml": intake_6h,
            "rapid_threshold_ml": rapid_threshold_ml,
            "urine_6h_ml": urine_6h,
            "urine_response_threshold_ml": urine_response_threshold_ml,
            "map": {"baseline": map_first, "latest": map_last, "change": map_gain},
            "lactate": {"baseline": lactate.get("earliest"), "latest": lactate.get("latest"), "ratio": lactate_ratio},
            "hemodynamic_context": hemo_ctx,
            "corroborators": corroborators,
        }

    async def _assess_deresuscitation_window(
        self,
        *,
        pid,
        pid_str: str,
        patient_doc: dict,
        his_pid: str | None,
        now: datetime,
        percent_fluid_overload: float,
        net_24h: float,
        cfg: dict,
    ) -> dict | None:
        sepsis_context = await self._has_recent_sepsis_or_shock(pid_str, now, int(cfg.get("linkage_lookback_hours", 24)))
        if not sepsis_context:
            return None

        map_series = await self._get_map_series(pid, now - timedelta(hours=max(2, int(cfg.get("deresuscitation_map_stable_hours", 2)))))
        map_values = [float(row.get("value")) for row in map_series if row.get("value") is not None]
        map_stable_threshold = float(cfg.get("deresuscitation_map_threshold", 65))
        map_stable = len(map_values) >= 2 and all(v >= map_stable_threshold for v in map_values[-3:])
        if not map_stable:
            return None

        nurse_cfg = self.config.yaml_cfg.get("nurse_reminders", {}).get("early_mobility", {})
        norepi_keywords = nurse_cfg.get("norepi_keywords", ["去甲肾上腺素", "norepinephrine", "noradrenaline", "去甲"])
        weight_kg = self._get_weight_kg(patient_doc)
        norepi_series = await self._get_norepi_dose_series(
            pid_str,
            now,
            float(cfg.get("deresuscitation_vaso_lookback_hours", 12)),
            norepi_keywords,
            weight_kg,
        )
        norepi_latest = norepi_series[-1]["dose_ug_kg_min"] if norepi_series else None
        norepi_tapering = self._is_series_tapering(norepi_series, float(nurse_cfg.get("norepi_taper_min_drop_ratio", 0.1)))
        current_vasopressors = await self._get_current_vasopressor_snapshot(pid, patient_doc, hours=8, max_items=4)
        vaso_ok = (not current_vasopressors) or norepi_tapering or (norepi_latest is not None and norepi_latest <= float(nurse_cfg.get("norepi_threshold_ug_kg_min", 0.2)))
        if not vaso_ok:
            return None

        lactate = await self._get_lactate_trend(his_pid, now, hours=12)
        lactate_ratio = lactate.get("ratio")
        lactate_down_ratio = float(cfg.get("deresuscitation_lactate_down_ratio", 0.9))
        lactate_down = lactate_ratio is not None and lactate_ratio <= lactate_down_ratio
        if not lactate_down:
            return None

        positive_net_hint = float(cfg.get("deresuscitation_positive_net_ml", 1000))
        high_net_hint = float(cfg.get("deresuscitation_positive_net_high_ml", 2000))
        fluid_burden = percent_fluid_overload >= float(cfg.get("positive_balance_warning_pct", 5)) or net_24h >= positive_net_hint
        if not fluid_burden:
            return None

        severity = "high" if (percent_fluid_overload >= float(cfg.get("positive_balance_high_pct", 10)) or net_24h >= high_net_hint) else "warning"
        return {
            "severity": severity,
            "map_series": [round(v, 1) for v in map_values[-3:]],
            "map_stable_threshold": map_stable_threshold,
            "lactate": {"baseline": lactate.get("earliest"), "latest": lactate.get("latest"), "ratio": lactate_ratio},
            "current_vasopressors": current_vasopressors,
            "norepi_latest_ug_kg_min": norepi_latest,
            "norepi_tapering": norepi_tapering,
            "percent_fluid_overload": percent_fluid_overload,
            "net_24h_ml": net_24h,
        }

    async def _build_fluid_explanation(self, *, summary: str, evidence: list[str], suggestion: str) -> dict:
        return await self._polish_structured_alert_explanation(
            {
                "summary": summary,
                "evidence": [str(item) for item in evidence if str(item).strip()][:5],
                "suggestion": suggestion,
                "text": "",
            }
        )

    async def scan_fluid_balance(self) -> None:
        patient_cursor = self.db.col("patient").find(
            self._active_patient_query(),
            {
                "_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1,
                "weight": 1, "bodyWeight": 1, "body_weight": 1, "weightKg": 1, "weight_kg": 1,
            },
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        fluid_cfg = self.config.yaml_cfg.get("alert_engine", {}).get("fluid_balance", {})
        windows = fluid_cfg.get("windows_hours", [6, 12, 24]) if isinstance(fluid_cfg, dict) else [6, 12, 24]
        windows = sorted({int(w) for w in windows if isinstance(w, (int, float, str)) and int(w) > 0})
        if not windows:
            windows = [6, 12, 24]

        warning_pct = float(fluid_cfg.get("percent_fluid_overload_warning_pct", fluid_cfg.get("positive_balance_warning_pct", 5)))
        high_pct = float(fluid_cfg.get("percent_fluid_overload_high_pct", fluid_cfg.get("positive_balance_high_pct", fluid_cfg.get("positive_balance_critical_pct", 10))))
        rapid_ml_per_kg_6h = float(fluid_cfg.get("rapid_infusion_ml_per_kg_6h", 30))
        urine_resp_ml_per_kg_h = float(fluid_cfg.get("urine_response_ml_per_kg_h", 0.5))
        linkage_lookback_h = int(fluid_cfg.get("linkage_lookback_hours", 24))

        now = datetime.now()
        lookback = max(windows)
        since = now - timedelta(hours=lookback)
        triggered = 0

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            his_pid = str(patient_doc.get("hisPid") or "").strip() or None
            weight_kg = self._get_weight_kg(patient_doc)
            if not weight_kg:
                continue

            intake_events = await self._collect_intake_events(pid_str, since)
            output_events = await self._collect_output_events(pid_str, since)
            if not intake_events and not output_events:
                continue

            by_window: dict[str, dict[str, float | None]] = {}
            max_positive_pct = 0.0
            for h in windows:
                intake_total = self._sum_window(intake_events, h, now)
                output_total = self._sum_window(output_events, h, now)
                net = round(intake_total - output_total, 1)
                pct_fo = round((net / (weight_kg * 1000.0)) * 100.0, 2)
                if pct_fo > max_positive_pct:
                    max_positive_pct = pct_fo
                by_window[f"{h}h"] = {
                    "intake_ml": intake_total,
                    "output_ml": output_total,
                    "net_ml": net,
                    "pct_body_weight": pct_fo,
                    "percent_fluid_overload": pct_fo,
                }

            intake_6h = self._sum_window(intake_events, 6, now)
            urine_6h = self._sum_window(output_events, 6, now, category="urine")
            rapid_threshold_ml = round(rapid_ml_per_kg_6h * weight_kg, 1)
            urine_response_threshold_ml = round(urine_resp_ml_per_kg_h * weight_kg * 6.0, 1)
            rapid_intake = intake_6h >= rapid_threshold_ml
            no_urine_response = urine_6h < urine_response_threshold_ml
            linked = await self._has_recent_aki_or_ards(pid_str, now, linkage_lookback_h)

            if max_positive_pct >= warning_pct:
                severity = "high" if max_positive_pct >= high_pct else "warning"
                if linked:
                    severity = self._upgrade_once(severity)
                rule_id = f"FLUID_OVERLOAD_{str(severity).upper()}"
                if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    net_24h = by_window.get("24h", {}).get("net_ml")
                    reasons = [f"%FO {max_positive_pct:.2f}%"]
                    if rapid_intake and no_urine_response:
                        reasons.append(f"6h大量补液 {intake_6h:.0f}mL 后尿量仅 {urine_6h:.0f}mL")
                    if linked:
                        reasons.append("近24h伴 AKI/ARDS 风险")
                    explanation = await self._build_fluid_explanation(
                        summary=f"患者已出现液体过负荷征象（%FO {max_positive_pct:.2f}%）。",
                        evidence=reasons,
                        suggestion="建议复核累计液体平衡、评估肺水肿/组织水肿，并结合尿量与器官灌注调整补液策略。",
                    )
                    alert = await self._create_alert(
                        rule_id=rule_id,
                        name="液体过负荷风险",
                        category="fluid_balance",
                        alert_type="fluid_balance",
                        severity=str(severity),
                        parameter="percent_fluid_overload",
                        condition={
                            "weight_kg": weight_kg,
                            "warning_pct": warning_pct,
                            "high_pct": high_pct,
                            "linked_aki_ards": linked,
                        },
                        value=round(max_positive_pct, 2),
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        device_id=None,
                        source_time=now,
                        explanation=explanation,
                        extra={
                            "weight_kg": weight_kg,
                            "percent_fluid_overload": round(max_positive_pct, 2),
                            "max_positive_pct_body_weight": round(max_positive_pct, 2),
                            "windows": by_window,
                            "intake_breakdown_24h": {
                                "iv_ml": self._sum_window(intake_events, 24, now, category="iv"),
                                "enteral_ml": self._sum_window(intake_events, 24, now, category="enteral"),
                                "oral_ml": self._sum_window(intake_events, 24, now, category="oral"),
                            },
                            "output_breakdown_24h": {
                                "urine_ml": self._sum_window(output_events, 24, now, category="urine"),
                                "drainage_ml": self._sum_window(output_events, 24, now, category="drainage"),
                                "ultrafiltration_ml": self._sum_window(output_events, 24, now, category="ultrafiltration"),
                                "gi_decompression_ml": self._sum_window(output_events, 24, now, category="gi_decompression"),
                            },
                            "rapid_infusion_check_6h": {
                                "intake_ml": intake_6h,
                                "urine_ml": urine_6h,
                                "rapid_threshold_ml": rapid_threshold_ml,
                                "urine_response_threshold_ml": urine_response_threshold_ml,
                                "triggered": rapid_intake and no_urine_response,
                            },
                            "reasons": reasons,
                        },
                    )
                    if alert:
                        triggered += 1

            responsiveness_lost = await self._assess_fluid_responsiveness_lost(
                pid=pid,
                pid_str=pid_str,
                his_pid=his_pid,
                now=now,
                intake_6h=intake_6h,
                urine_6h=urine_6h,
                rapid_threshold_ml=rapid_threshold_ml,
                urine_response_threshold_ml=urine_response_threshold_ml,
                cfg=fluid_cfg,
            )
            if responsiveness_lost:
                rule_id = "FLUID_RESPONSIVENESS_LOST"
                if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    explanation = await self._build_fluid_explanation(
                        summary="近期大量补液后，乳酸/血压改善不足，液体反应性可能丧失。",
                        evidence=[
                            f"6h入量 {responsiveness_lost.get('intake_6h_ml')}mL",
                            f"MAP变化 {responsiveness_lost.get('map', {}).get('change')} mmHg",
                            f"乳酸比值 {responsiveness_lost.get('lactate', {}).get('ratio')}",
                            f"尿量 {responsiveness_lost.get('urine_6h_ml')}mL",
                        ],
                        suggestion="建议停止经验性继续扩容，优先复核容量反应性并评估升压药/器官灌注策略。",
                    )
                    alert = await self._create_alert(
                        rule_id=rule_id,
                        name="液体反应性可能丧失",
                        category="fluid_balance",
                        alert_type="fluid_responsiveness_lost",
                        severity=str(responsiveness_lost.get("severity") or "high"),
                        parameter="fluid_responsiveness",
                        condition={
                            "intake_6h_ml": intake_6h,
                            "rapid_threshold_ml": rapid_threshold_ml,
                            "urine_response_threshold_ml": urine_response_threshold_ml,
                        },
                        value=responsiveness_lost.get("corroborators"),
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        device_id=None,
                        source_time=now,
                        explanation=explanation,
                        extra=responsiveness_lost,
                    )
                    if alert:
                        triggered += 1

            net_24h = float(by_window.get("24h", {}).get("net_ml") or 0.0)
            deresuscitation = await self._assess_deresuscitation_window(
                pid=pid,
                pid_str=pid_str,
                patient_doc=patient_doc,
                his_pid=his_pid,
                now=now,
                percent_fluid_overload=round(max_positive_pct, 2),
                net_24h=net_24h,
                cfg=fluid_cfg,
            )
            if deresuscitation:
                rule_id = "FLUID_DERESUSCITATION_WINDOW"
                if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    explanation = await self._build_fluid_explanation(
                        summary="休克初始复苏阶段可能已过，可考虑转入去复苏策略。",
                        evidence=[
                            f"MAP稳定 {deresuscitation.get('map_series')}",
                            f"乳酸 {deresuscitation.get('lactate', {}).get('baseline')}→{deresuscitation.get('lactate', {}).get('latest')}",
                            f"%FO {deresuscitation.get('percent_fluid_overload')}%",
                            f"24h净平衡 {deresuscitation.get('net_24h_ml')}mL",
                        ],
                        suggestion="建议评估限制入量、利尿/超滤与每日负平衡目标，避免进入液体迟发伤害阶段。",
                    )
                    alert = await self._create_alert(
                        rule_id=rule_id,
                        name="可考虑进入去复苏阶段",
                        category="fluid_balance",
                        alert_type="fluid_deresuscitation",
                        severity=str(deresuscitation.get("severity") or "warning"),
                        parameter="deresuscitation_window",
                        condition={
                            "map_stable": True,
                            "lactate_down": True,
                            "sepsis_context": True,
                        },
                        value=round(max_positive_pct, 2),
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        device_id=None,
                        source_time=now,
                        explanation=explanation,
                        extra=deresuscitation,
                    )
                    if alert:
                        triggered += 1

        if triggered > 0:
            self._log_info("液体平衡", triggered)
