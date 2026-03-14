"""液体平衡预警（入量/出量/净平衡）"""
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

        # fallback: 若配置 code 与库内实际编码不匹配，退化为关键词/文本识别
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

        warning_pct = float(fluid_cfg.get("positive_balance_warning_pct", 5))
        critical_pct = float(fluid_cfg.get("positive_balance_critical_pct", 10))
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
                pct_bw = round((net / (weight_kg * 1000.0)) * 100.0, 2)
                if pct_bw > max_positive_pct:
                    max_positive_pct = pct_bw
                by_window[f"{h}h"] = {
                    "intake_ml": intake_total,
                    "output_ml": output_total,
                    "net_ml": net,
                    "pct_body_weight": pct_bw,
                }

            severity: str | None = None
            reasons: list[str] = []
            if max_positive_pct >= critical_pct:
                severity = "critical"
                reasons.append(f"累计正平衡 {max_positive_pct:.2f}% > {critical_pct:.1f}%")
            elif max_positive_pct >= warning_pct:
                severity = "warning"
                reasons.append(f"累计正平衡 {max_positive_pct:.2f}% > {warning_pct:.1f}%")

            intake_6h = self._sum_window(intake_events, 6, now)
            urine_6h = self._sum_window(output_events, 6, now, category="urine")
            rapid_threshold_ml = round(rapid_ml_per_kg_6h * weight_kg, 1)
            urine_response_threshold_ml = round(urine_resp_ml_per_kg_h * weight_kg * 6.0, 1)

            rapid_intake = intake_6h >= rapid_threshold_ml
            no_urine_response = urine_6h < urine_response_threshold_ml
            if rapid_intake and no_urine_response:
                severity = self._max_severity(severity, "high")
                reasons.append(
                    f"6h快速输液 {intake_6h:.1f}mL(>{rapid_threshold_ml:.1f}mL) 且尿量响应不足 {urine_6h:.1f}mL(<{urine_response_threshold_ml:.1f}mL)"
                )

            if not severity:
                continue

            linked = await self._has_recent_aki_or_ards(pid_str, now, linkage_lookback_h)
            if linked:
                upgraded = self._upgrade_once(severity)
                if upgraded != severity:
                    reasons.append("合并AKI/ARDS预警，联动升级严重程度")
                severity = upgraded

            rapid_tag = "RAPID_" if (rapid_intake and no_urine_response) else ""
            rule_id = f"FLUID_BALANCE_{rapid_tag}{str(severity).upper()}"
            if await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                continue

            net_24h = by_window.get("24h", {}).get("net_ml")
            alert = await self._create_alert(
                rule_id=rule_id,
                name="液体平衡异常风险",
                category="fluid_balance",
                alert_type="fluid_balance",
                severity=str(severity),
                parameter="fluid_net_balance",
                condition={
                    "weight_kg": weight_kg,
                    "warning_pct": warning_pct,
                    "critical_pct": critical_pct,
                    "rapid_ml_per_kg_6h": rapid_ml_per_kg_6h,
                    "urine_response_ml_per_kg_h": urine_resp_ml_per_kg_h,
                    "linked_aki_ards": linked,
                },
                value=net_24h if isinstance(net_24h, (int, float)) else None,
                patient_id=pid_str,
                patient_doc=patient_doc,
                device_id=None,
                source_time=now,
                extra={
                    "weight_kg": weight_kg,
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

        if triggered > 0:
            self._log_info("液体平衡", triggered)
