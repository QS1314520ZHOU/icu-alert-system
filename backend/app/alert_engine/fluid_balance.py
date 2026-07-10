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

    async def _get_ppv_svv_snapshot(self, pid, now: datetime, hours: int = 12) -> dict:
        snapshot = await self._get_latest_param_snapshot_by_pid(pid, codes=["param_ppv", "ppv", "PPV", "param_svv", "svv", "SVV"])
        params = (snapshot or {}).get("params") or {}
        ppv = None
        for key in ("param_ppv", "ppv", "PPV"):
            if params.get(key) is not None:
                ppv = float(params.get(key))
                break
        svv = None
        for key in ("param_svv", "svv", "SVV"):
            if params.get(key) is not None:
                svv = float(params.get(key))
                break
        return {
            "ppv": ppv,
            "svv": svv,
            "poor_tolerance": bool((ppv is not None and ppv < 13) or (svv is not None and svv < 12)),
            "time": (snapshot or {}).get("time"),
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

    async def _get_pf_ratio_hint(self, his_pid: str | None, patient_doc: dict, pid, now: datetime) -> dict:
        if not his_pid:
            return {"latest": None, "baseline": None, "delta": None, "worsening": False}
        pao2_series = await self._get_lab_series(his_pid, "pao2", now - timedelta(hours=24), limit=60)
        fio2_series = await self._get_param_series_by_pid(pid, "param_FiO2", now - timedelta(hours=24), prefer_device_types=["vent", "monitor"], limit=120)
        if hasattr(self, "_filter_series_quality"):
            fio2_series = self._filter_series_quality("param_FiO2", fio2_series)
        pf_pairs: list[tuple[datetime, float]] = []
        for pao2_row in pao2_series:
            pt = pao2_row.get("time")
            pv = pao2_row.get("value")
            if not isinstance(pt, datetime) or pv is None:
                continue
            nearest_fio2 = None
            nearest_gap = None
            for fio2_row in fio2_series:
                ft = fio2_row.get("time")
                fv = fio2_row.get("value")
                if not isinstance(ft, datetime) or fv is None:
                    continue
                gap = abs((ft - pt).total_seconds())
                if gap > 4 * 3600:
                    continue
                if nearest_gap is None or gap < nearest_gap:
                    nearest_gap = gap
                    nearest_fio2 = float(fv)
            if nearest_fio2 in (None, 0):
                continue
            fio2 = nearest_fio2 / 100.0 if nearest_fio2 > 1 else nearest_fio2
            if fio2 <= 0:
                continue
            pf_pairs.append((pt, round(float(pv) / fio2, 1)))
        baseline = pf_pairs[0][1] if pf_pairs else None
        pf = pf_pairs[-1][1] if pf_pairs else None
        delta = round(float(pf) - float(baseline), 1) if pf is not None and baseline is not None else None
        ards_alert = await self._get_latest_active_alert(str(pid), ["ards"], hours=24)
        return {
            "latest": pf,
            "baseline": baseline,
            "delta": delta,
            "worsening": bool(ards_alert and delta is not None and delta < -20),
        }

    async def _get_bline_hint(self, pid, now: datetime) -> dict:
        events = await self._get_recent_text_events(pid, ["b线", "b-line", "肺水", "肺超声"], hours=24, limit=200)
        if not events:
            return {"present": False, "text": None}
        text = " ".join(str(events[0].get(k) or "") for k in ("code", "strVal", "value"))
        return {"present": True, "text": text}

    async def _build_deresuscitation_plan(
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
    ) -> dict:
        hemo_ctx = await self._get_hemodynamic_responsiveness_context(pid_str, now, hours=12)
        ppv_svv = await self._get_ppv_svv_snapshot(pid, now, hours=12)
        pf = await self._get_pf_ratio_hint(his_pid, patient_doc, pid, now)
        bline = await self._get_bline_hint(pid, now)
        uf_24h = self._sum_window(await self._collect_output_events(pid_str, now - timedelta(hours=24)), 24, now, category="ultrafiltration")
        target_negative = float(cfg.get("deresuscitation_target_negative_ml_24h", 500))
        if (
            percent_fluid_overload >= float(cfg.get("positive_balance_high_pct", 10))
            or net_24h >= float(cfg.get("deresuscitation_positive_net_high_ml", 2000))
            or pf.get("worsening")
            or ppv_svv.get("poor_tolerance")
            or bline.get("present")
        ):
            target_negative = float(cfg.get("deresuscitation_target_negative_high_ml_24h", 1000))
        recommendation = {
            "net_negative_goal_ml_24h": int(target_negative),
            "diuretic_start": "考虑呋塞米 20-40mg 起始" if uf_24h <= 0 else None,
            "crrt_uf_rate_ml_h": int(round(target_negative / 24.0)) if uf_24h > 0 else None,
        }
        return {
            "hemodynamic_context": hemo_ctx,
            "ppv_svv_context": ppv_svv,
            "pf_ratio": pf,
            "bline_hint": bline,
            "current_ultrafiltration_24h_ml": uf_24h,
            "recommendation": recommendation,
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
        from .scanner_fluid_balance import FluidBalanceScanner

        await FluidBalanceScanner(self).scan()
