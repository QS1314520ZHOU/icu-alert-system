from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.utils.clinical import _detect_trend
from app.utils.parse import _parse_dt


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except Exception:
        return None


def _round_number(value: Any, digits: int = 2) -> float | None:
    number = _safe_float(value)
    if number is None:
        return None
    return round(number, digits)


def _event_time(value: dict[str, Any]) -> datetime | None:
    if not isinstance(value, dict):
        return None
    for key in ("time", "recordTime", "calc_time", "created_at", "executeTime", "startTime", "orderTime", "bindTime", "unBindTime", "stopTime"):
        parsed = _parse_dt(value.get(key))
        if parsed is not None:
            return parsed
    return None


def _trim_event_meta(meta: dict[str, Any], *, limit: int = 8) -> dict[str, Any]:
    trimmed: dict[str, Any] = {}
    for key in list(meta.keys())[:limit]:
        value = meta.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None or isinstance(value, datetime):
            trimmed[key] = value
    return trimmed


def _diff_threshold(path: str, current: float | str | None) -> float | None:
    numeric_thresholds = {
        "snapshot.map.current": 5.0,
        "snapshot.hr.current": 10.0,
        "snapshot.spo2.current": 3.0,
        "snapshot.rr.current": 4.0,
        "snapshot.temp.current": 0.5,
        "snapshot.lactate.current": 0.5,
        "snapshot.fio2.current": 5.0,
        "snapshot.peep.current": 2.0,
        "snapshot.vasoactive_support.current_dose_ug_kg_min": 0.03,
        "snapshot.urine_ml_kg_h_6h": 0.2,
    }
    if path == "snapshot.vent_mode.current":
        return 0.0 if current else None
    return numeric_thresholds.get(path)


class PatientDigitalTwinService:
    def __init__(self, *, db, alert_engine, config=None) -> None:
        self.db = db
        self.alert_engine = alert_engine
        self.config = config

    def _cfg(self) -> dict[str, Any]:
        root = getattr(self.config, "yaml_cfg", {}) if self.config is not None else {}
        cfg = ((root or {}).get("ai_service", {}) or {}).get("patient_digital_twin", {})
        return cfg if isinstance(cfg, dict) else {}

    def _series_snapshot(self, series: list[dict[str, Any]]) -> dict[str, Any]:
        if not series:
            return {"points": 0, "latest": None, "delta": None, "trend": "insufficient"}
        values = [_safe_float(item.get("value")) for item in series]
        values = [item for item in values if item is not None]
        if not values:
            return {"points": 0, "latest": None, "delta": None, "trend": "insufficient"}
        latest = values[-1]
        first = values[0]
        delta = round(latest - first, 3)
        trend_info = _detect_trend(values, window=len(values))
        recent_window = max(2, len(values) // 3)
        recent_values = values[-recent_window:]
        overall_mean = sum(values) / len(values)
        recent_mean = sum(recent_values) / len(recent_values)
        mean_shift = recent_mean - overall_mean
        volatility = max(abs(trend_info.get("volatility", 0.0)), 0.0)
        mean_threshold = max(abs(overall_mean) * 0.05, volatility * 0.35, 0.2)
        direction = str(trend_info.get("direction") or "stable").lower()
        if direction == "rising":
            trend = "up"
        elif direction == "falling":
            trend = "down"
        elif abs(mean_shift) >= mean_threshold:
            trend = "up" if mean_shift > 0 else "down"
        else:
            trend = "stable"
        return {
            "points": len(values),
            "latest": round(latest, 3),
            "delta": delta,
            "trend": trend,
            "mean_shift": round(mean_shift, 3),
            "slope": trend_info.get("slope"),
            "volatility": trend_info.get("volatility"),
            "start_time": series[0].get("time"),
            "end_time": series[-1].get("time"),
        }

    async def _build_vitals_block(self, patient_id: str, patient_doc: dict[str, Any], hours: int) -> dict[str, Any]:
        now = datetime.now()
        since = now - timedelta(hours=max(int(hours or 24), 1))
        latest = await self.alert_engine._get_latest_vitals_by_patient(patient_id) if hasattr(self.alert_engine, "_get_latest_vitals_by_patient") else {}
        code_groups = {
            "hr": ["param_HR"],
            "map": ["param_ibp_m", "param_nibp_m"],
            "spo2": ["param_spo2"],
            "rr": ["param_resp"],
            "temp": [str(self.alert_engine._cfg("vital_signs", "temperature", "code", default="param_T"))] if hasattr(self.alert_engine, "_cfg") else ["param_T"],
        }
        series_map: dict[str, list[dict[str, Any]]] = {}
        for key, codes in code_groups.items():
            rows: list[dict[str, Any]] = []
            if hasattr(self.alert_engine, "_get_param_series_by_pid"):
                for code in codes:
                    rows = await self.alert_engine._get_param_series_by_pid(
                        patient_id,
                        str(code),
                        since,
                        prefer_device_types=["monitor", "vent"],
                        limit=480,
                    )
                    if rows:
                        break
            series_map[key] = rows or []
        vent_latest: dict[str, Any] = {}
        if hasattr(self.alert_engine, "_get_device_id_for_patient") and hasattr(self.alert_engine, "_get_latest_device_cap"):
            vent_device_id = await self.alert_engine._get_device_id_for_patient(patient_doc, ["vent"])
            vent_cap = await self.alert_engine._get_latest_device_cap(vent_device_id) if vent_device_id else None
            if vent_cap:
                params = vent_cap.get("params") if isinstance(vent_cap.get("params"), dict) else {}
                fio2 = self.alert_engine._vent_param(vent_cap, "fio2", "param_FiO2") if hasattr(self.alert_engine, "_vent_param") else None
                peep = self.alert_engine._vent_param_priority(vent_cap, ["peep_measured", "peep_set"], ["param_vent_measure_peep", "param_vent_peep"]) if hasattr(self.alert_engine, "_vent_param_priority") else None
                vent_mode = (
                    vent_cap.get("param_HuXiMoShi")
                    or vent_cap.get("param_vent_mode")
                    or vent_cap.get("vent_mode")
                    or params.get("param_HuXiMoShi")
                    or params.get("param_vent_mode")
                    or params.get("vent_mode")
                )
                vent_time = _event_time(vent_cap)
                vent_latest = {
                    "fio2": {"current": _round_number(fio2, 2), "time": vent_time},
                    "peep": {"current": _round_number(peep, 2), "time": vent_time},
                    "vent_mode": {"current": str(vent_mode).strip() if vent_mode not in (None, "") else None, "time": vent_time},
                }
        return {
            "latest": latest or {},
            "snapshot": {key: self._series_snapshot(rows) for key, rows in series_map.items()},
            "series": {key: rows[-24:] for key, rows in series_map.items()},
            "ventilator": vent_latest,
            "generated_at": now,
        }

    async def _build_labs_block(self, patient_doc: dict[str, Any], hours: int) -> dict[str, Any]:
        his_pid = str(patient_doc.get("hisPid") or patient_doc.get("hisPID") or "").strip()
        if not his_pid or not hasattr(self.alert_engine, "_get_latest_labs_map"):
            return {"latest": {}, "series": {}, "tracked_keys": []}
        now = datetime.now()
        since = now - timedelta(hours=max(int(hours or 24), 1))
        tracked_keys = list(self._cfg().get("tracked_labs", ["lac", "lactate", "cr", "wbc", "plt", "tbil", "inr", "pao2", "ph"]))[:12]
        latest = await self.alert_engine._get_latest_labs_map(his_pid, lookback_hours=max(hours, 24))
        series: dict[str, list[dict[str, Any]]] = {}
        if hasattr(self.alert_engine, "_get_lab_series"):
            for key in tracked_keys:
                try:
                    rows = await self.alert_engine._get_lab_series(his_pid, str(key), since, limit=80)
                except Exception:
                    rows = []
                if rows:
                    series[str(key)] = rows[-20:]
        return {"latest": latest or {}, "series": series, "tracked_keys": tracked_keys}

    async def _build_medication_block(self, patient_id: str, patient_doc: dict[str, Any], hours: int) -> dict[str, Any]:
        if not hasattr(self.alert_engine, "_get_recent_drug_docs_window"):
            return {"recent_orders": [], "vasoactive_support": {"current_dose_ug_kg_min": None}}
        docs = await self.alert_engine._get_recent_drug_docs_window(patient_id, hours=hours, limit=300)
        rows = []
        vasoactive_support = {"current_dose_ug_kg_min": None}
        weight_kg = self.alert_engine._get_patient_weight(patient_doc) if hasattr(self.alert_engine, "_get_patient_weight") else None
        for doc in docs[-30:]:
            rows.append(
                {
                    "name": doc.get("drugName") or doc.get("orderName") or "",
                    "time": doc.get("_event_time") or doc.get("executeTime") or doc.get("startTime") or doc.get("orderTime"),
                    "route": doc.get("route") or doc.get("routeName") or "",
                    "dose": doc.get("dose"),
                    "dose_unit": doc.get("doseUnit"),
                    "frequency": doc.get("frequency"),
                    "status": doc.get("status"),
                }
            )
        if hasattr(self.alert_engine, "_extract_vasopressor_rate_ug_kg_min"):
            keywords = ["去甲肾上腺素", "norepinephrine", "noradrenaline", "多巴胺", "dopamine", "肾上腺素", "epinephrine", "血管加压素", "vasopressin", "多巴酚丁胺", "dobutamine"]
            for doc in reversed(docs):
                text = " ".join(str(doc.get(key) or "") for key in ("drugName", "orderName", "drugSpec", "route", "routeName")).lower()
                if not any(token in text for token in keywords):
                    continue
                dose = self.alert_engine._extract_vasopressor_rate_ug_kg_min(doc, weight_kg)
                if dose is not None:
                    vasoactive_support = {"current_dose_ug_kg_min": _round_number(dose, 3)}
                    break
        return {"recent_orders": rows, "vasoactive_support": vasoactive_support}

    async def _build_scores_block(self, patient_id: str, patient_doc: dict[str, Any], hours: int) -> dict[str, Any]:
        now = datetime.now()
        since = now - timedelta(hours=max(int(hours or 24), 1))
        rows = [
            doc async for doc in self.db.col("score_records").find(
                {"patient_id": {"$in": [patient_id, patient_doc.get("_id")]}, "calc_time": {"$gte": since}},
                {"score_type": 1, "score": 1, "risk_level": 1, "summary": 1, "calc_time": 1, "value": 1, "sofa_score": 1},
            ).sort("calc_time", -1).limit(60)
        ]
        latest_by_type: dict[str, dict[str, Any]] = {}
        for row in rows:
            score_type = str(row.get("score_type") or "").strip()
            if score_type and score_type not in latest_by_type:
                latest_by_type[score_type] = row
        sofa = None
        if hasattr(self.alert_engine, "_calc_sofa"):
            try:
                device_id = await self.alert_engine._get_device_id_for_patient(patient_doc, ["monitor", "vent"]) if hasattr(self.alert_engine, "_get_device_id_for_patient") else None
                his_pid = str(patient_doc.get("hisPid") or "").strip() or None
                sofa = await self.alert_engine._calc_sofa(patient_doc, patient_doc.get("_id"), device_id, his_pid)
            except Exception:
                sofa = None
        return {"latest_by_type": latest_by_type, "recent": rows, "sofa": sofa or {}}

    async def _build_text_signal_block(self, patient_doc: dict[str, Any], patient_id: str, hours: int) -> dict[str, Any]:
        imaging = None
        nursing = None
        if hasattr(self.alert_engine, "get_imaging_report_analysis"):
            try:
                imaging = await self.alert_engine.get_imaging_report_analysis(patient_doc, patient_id, hours=max(hours, 24), max_age_hours=8, persist_if_refresh=False)
            except Exception:
                imaging = None
        if hasattr(self.alert_engine, "latest_nursing_note_analysis"):
            try:
                nursing = await self.alert_engine.latest_nursing_note_analysis(patient_id, hours=max(hours, 24))
            except Exception:
                nursing = None
        if nursing is None and hasattr(self.alert_engine, "analyze_nursing_notes"):
            try:
                nursing = await self.alert_engine.analyze_nursing_notes(patient_doc, patient_id, hours=min(max(hours, 12), 24), persist=False)
            except Exception:
                nursing = None
        return {"imaging": imaging or {}, "nursing": nursing or {}}

    async def _build_alert_block(self, patient_id: str, patient_doc: dict[str, Any], hours: int) -> dict[str, Any]:
        since = datetime.now() - timedelta(hours=max(int(hours or 24), 1))
        patient_keys = [patient_id]
        if patient_doc.get("_id") is not None:
            patient_keys.append(patient_doc.get("_id"))
        rows = [
            doc async for doc in self.db.col("alert_records").find(
                {"patient_id": {"$in": patient_keys}, "created_at": {"$gte": since}},
                {"name": 1, "alert_type": 1, "severity": 1, "created_at": 1, "viewed_at": 1, "acknowledged_at": 1, "action_taken": 1},
            ).sort("created_at", -1).limit(80)
        ]
        return {
            "recent": rows,
            "summary": {
                "count": len(rows),
                "high_count": sum(1 for row in rows if str(row.get("severity") or "").lower() in {"high", "critical"}),
                "viewed_count": sum(1 for row in rows if row.get("viewed_at")),
                "ack_count": sum(1 for row in rows if row.get("acknowledged_at")),
                "action_count": sum(1 for row in rows if row.get("action_taken")),
            },
        }

    async def _build_device_timeline_events(self, patient_id: str, hours: int) -> list[dict[str, Any]]:
        since = datetime.now() - timedelta(hours=max(int(hours or 24), 1))
        timeline: list[dict[str, Any]] = []
        bind_rows = [
            row async for row in self.db.col("deviceBind").find(
                {
                    "pid": patient_id,
                    "$or": [
                        {"bindTime": {"$gte": since}},
                        {"unBindTime": {"$gte": since}},
                    ],
                },
                {"type": 1, "bindTime": 1, "unBindTime": 1, "deviceName": 1, "name": 1, "deviceID": 1},
            ).sort("bindTime", -1).limit(80)
        ]
        for row in bind_rows:
            device_name = str(row.get("deviceName") or row.get("name") or row.get("type") or "设备").strip()
            device_type = str(row.get("type") or "").strip().lower()
            bind_time = _parse_dt(row.get("bindTime"))
            unbind_time = _parse_dt(row.get("unBindTime"))
            meta = _trim_event_meta(row)
            if bind_time and bind_time >= since:
                timeline.append({"time": bind_time, "source": "deviceBind", "type": "device_bind", "label": f"设备绑定: {device_name}", "meta": {"device_type": device_type, **meta}})
            if unbind_time and unbind_time >= since:
                timeline.append({"time": unbind_time, "source": "deviceBind", "type": "device_unbind", "label": f"设备解绑: {device_name}", "meta": {"device_type": device_type, **meta}})

        tube_rows = [
            row async for row in self.db.col("tubeExe").find(
                {
                    "pid": patient_id,
                    "$or": [
                        {"startTime": {"$gte": since}},
                        {"stopTime": {"$gte": since}},
                    ],
                },
                {"name": 1, "type": 1, "body": 1, "startTime": 1, "stopTime": 1},
            ).sort("startTime", -1).limit(80)
        ]
        for row in tube_rows:
            tube_name = str(row.get("name") or row.get("type") or "管路").strip()
            site = str(row.get("body") or "").strip()
            start_time = _parse_dt(row.get("startTime"))
            stop_time = _parse_dt(row.get("stopTime"))
            label_suffix = f" ({site})" if site else ""
            meta = _trim_event_meta(row)
            if start_time and start_time >= since:
                timeline.append({"time": start_time, "source": "tubeExe", "type": "tube_insert", "label": f"置管: {tube_name}{label_suffix}", "meta": meta})
            if stop_time and stop_time >= since:
                timeline.append({"time": stop_time, "source": "tubeExe", "type": "tube_remove", "label": f"拔管: {tube_name}{label_suffix}", "meta": meta})
        return timeline

    def _build_event_timeline(
        self,
        *,
        vitals: dict[str, Any],
        labs: dict[str, Any],
        medications: dict[str, Any],
        scores: dict[str, Any],
        text_signals: dict[str, Any],
        alerts: dict[str, Any],
        device_events: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        timeline: list[dict[str, Any]] = []
        for metric, rows in (vitals.get("series") or {}).items():
            if rows:
                latest = rows[-1]
                timeline.append({"time": latest.get("time"), "source": "vitals", "type": metric, "label": f"{metric.upper()} {latest.get('value')}"})
        vent_latest = vitals.get("ventilator") if isinstance(vitals.get("ventilator"), dict) else {}
        for metric in ("fio2", "peep", "vent_mode"):
            entry = vent_latest.get(metric) if isinstance(vent_latest.get(metric), dict) else {}
            if entry.get("time") and entry.get("current") not in (None, ""):
                label = f"{metric.upper()} {entry.get('current')}" if metric != "vent_mode" else f"通气模式 {entry.get('current')}"
                timeline.append({"time": entry.get("time"), "source": "ventilator", "type": metric, "label": label})
        for lab_key, rows in (labs.get("series") or {}).items():
            if rows:
                latest = rows[-1]
                timeline.append({"time": latest.get("time"), "source": "labs", "type": lab_key, "label": f"{lab_key.upper()} {latest.get('value')}"})
        for item in (medications.get("recent_orders") or [])[-12:]:
            timeline.append({"time": item.get("time"), "source": "medication", "type": "drug_order", "label": item.get("name") or "用药执行", "meta": item})
        for score_type, row in (scores.get("latest_by_type") or {}).items():
            timeline.append({"time": row.get("calc_time"), "source": "score_records", "type": score_type, "label": row.get("summary") or score_type, "meta": row})
        imaging = text_signals.get("imaging") if isinstance(text_signals.get("imaging"), dict) else {}
        if imaging:
            timeline.append({"time": imaging.get("latest_report_time") or imaging.get("calc_time"), "source": "imaging", "type": "imaging_report_signal_analysis", "label": imaging.get("summary") or "影像信号更新"})
        nursing = text_signals.get("nursing") if isinstance(text_signals.get("nursing"), dict) else {}
        if nursing:
            timeline.append({"time": nursing.get("calc_time"), "source": "nursing", "type": "nursing_note_signal_analysis", "label": nursing.get("summary") or "护理文本信号更新"})
        for row in (alerts.get("recent") or [])[:20]:
            timeline.append({"time": row.get("created_at"), "source": "alert", "type": row.get("alert_type"), "label": row.get("name") or row.get("alert_type"), "meta": row})
        timeline.extend(device_events or [])
        timeline = [item for item in timeline if item.get("time")]
        timeline.sort(key=lambda item: item.get("time") or datetime.min, reverse=True)
        return timeline[:60]

    def _iter_diff_candidates(self, payload: Any, prefix: str = "") -> list[tuple[str, float | str | None]]:
        rows: list[tuple[str, float | str | None]] = []
        if isinstance(payload, dict):
            for key, value in payload.items():
                path = f"{prefix}.{key}" if prefix else str(key)
                if isinstance(value, dict):
                    rows.extend(self._iter_diff_candidates(value, path))
                elif isinstance(value, (int, float, str)) or value is None:
                    rows.append((path, value))
        return rows

    def _diff_from_previous(self, previous: dict[str, Any] | None, current: dict[str, Any]) -> dict[str, Any]:
        if not previous:
            return {"available": False, "fields": [], "previous_calc_time": None}
        previous_snapshot = previous.get("snapshot") if isinstance(previous.get("snapshot"), dict) else {}
        current_snapshot = current.get("snapshot") if isinstance(current.get("snapshot"), dict) else {}
        previous_values = dict(self._iter_diff_candidates(previous_snapshot, "snapshot"))
        fields: list[dict[str, Any]] = []
        for path, current_value in self._iter_diff_candidates(current_snapshot, "snapshot"):
            previous_value = previous_values.get(path)
            if current_value in (None, "") and previous_value in (None, ""):
                continue
            threshold = _diff_threshold(path, current_value)
            if isinstance(current_value, (int, float)) and isinstance(previous_value, (int, float)):
                delta = round(float(current_value) - float(previous_value), 3)
                if threshold is None or abs(delta) < threshold:
                    continue
                fields.append({"path": path, "previous": previous_value, "current": current_value, "delta": delta, "threshold": threshold})
            elif current_value != previous_value and threshold == 0.0:
                fields.append({"path": path, "previous": previous_value, "current": current_value, "delta": None, "threshold": threshold})
        fields.sort(key=lambda item: abs(item.get("delta") or 0.0), reverse=True)
        return {"available": True, "previous_calc_time": previous.get("calc_time"), "fields": fields}

    def _apply_diff_markers(self, snapshot: dict[str, Any], diff_payload: dict[str, Any]) -> None:
        fields = diff_payload.get("fields") if isinstance(diff_payload.get("fields"), list) else []
        field_map = {str(item.get("path") or ""): item for item in fields if isinstance(item, dict)}
        for path, row in field_map.items():
            parts = path.split(".")
            if len(parts) < 2 or parts[0] != "snapshot":
                continue
            target: Any = snapshot.get("snapshot")
            for key in parts[1:-1]:
                if not isinstance(target, dict):
                    target = None
                    break
                target = target.get(key)
            if isinstance(target, dict):
                target["_diff_from_previous"] = {
                    "previous": row.get("previous"),
                    "current": row.get("current"),
                    "delta": row.get("delta"),
                    "threshold": row.get("threshold"),
                    "previous_calc_time": diff_payload.get("previous_calc_time"),
                }

    def _storage_view(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        data = dict(snapshot)
        vitals = dict(data.get("vitals") or {})
        labs = dict(data.get("labs") or {})
        if "series" in vitals:
            vitals["series"] = {}
        if "series" in labs:
            labs["series"] = {}
        data["vitals"] = vitals
        data["labs"] = labs
        return data

    async def build_snapshot(self, patient_id: str, patient_doc: dict[str, Any], *, hours: int = 24) -> dict[str, Any]:
        facts = await self.alert_engine._collect_patient_facts(patient_doc, patient_doc.get("_id")) if hasattr(self.alert_engine, "_collect_patient_facts") else {}
        vitals = await self._build_vitals_block(patient_id, patient_doc, hours)
        labs = await self._build_labs_block(patient_doc, hours)
        medications = await self._build_medication_block(patient_id, patient_doc, hours)
        scores = await self._build_scores_block(patient_id, patient_doc, hours)
        text_signals = await self._build_text_signal_block(patient_doc, patient_id, hours)
        alerts = await self._build_alert_block(patient_id, patient_doc, hours)
        device_events = await self._build_device_timeline_events(patient_id, min(max(int(hours or 24), 1), 24))
        timeline = self._build_event_timeline(
            vitals=vitals,
            labs=labs,
            medications=medications,
            scores=scores,
            text_signals=text_signals,
            alerts=alerts,
            device_events=device_events,
        )
        now = datetime.now()
        snapshot = {
            "map": {"current": _safe_float(((vitals.get("snapshot") or {}).get("map") or {}).get("latest"))},
            "hr": {"current": _safe_float(((vitals.get("snapshot") or {}).get("hr") or {}).get("latest"))},
            "spo2": {"current": _safe_float(((vitals.get("snapshot") or {}).get("spo2") or {}).get("latest"))},
            "rr": {"current": _safe_float(((vitals.get("snapshot") or {}).get("rr") or {}).get("latest"))},
            "temp": {"current": _safe_float(((vitals.get("snapshot") or {}).get("temp") or {}).get("latest"))},
            "fio2": {"current": _safe_float(((vitals.get("ventilator") or {}).get("fio2") or {}).get("current"))},
            "peep": {"current": _safe_float(((vitals.get("ventilator") or {}).get("peep") or {}).get("current"))},
            "vent_mode": {"current": ((vitals.get("ventilator") or {}).get("vent_mode") or {}).get("current")},
            "lactate": {
                "current": _safe_float(
                    (
                        ((labs.get("latest") or {}).get("lac"))
                        or ((labs.get("latest") or {}).get("lactate"))
                        or {}
                    ).get("value")
                )
            },
            "urine_ml_kg_h_6h": _round_number((facts.get("urine_ml_kg_h_6h") if isinstance(facts, dict) else None), 2),
            "vasoactive_support": medications.get("vasoactive_support") or {"current_dose_ug_kg_min": None},
        }
        return {
            "patient_id": patient_id,
            "patient_name": patient_doc.get("name") or patient_doc.get("hisName"),
            "bed": patient_doc.get("hisBed") or patient_doc.get("bed"),
            "dept": patient_doc.get("dept") or patient_doc.get("hisDept"),
            "score_type": "digital_twin_snapshot",
            "twin_version": "v1",
            "calc_time": now,
            "updated_at": now,
            "snapshot_window_hours": hours,
            "patient": {
                "id": patient_id,
                "name": patient_doc.get("name") or patient_doc.get("hisName"),
                "bed": patient_doc.get("hisBed") or patient_doc.get("bed"),
                "dept": patient_doc.get("dept") or patient_doc.get("hisDept"),
                "diagnosis": patient_doc.get("clinicalDiagnosis") or patient_doc.get("admissionDiagnosis") or "",
                "nursing_level": patient_doc.get("nursingLevel") or "",
            },
            "facts": facts,
            "snapshot": snapshot,
            "vitals": vitals,
            "labs": labs,
            "medications": medications,
            "scores": scores,
            "text_signals": text_signals,
            "alerts": alerts,
            "timeline": timeline,
            "summary": {
                "problem_count": len((facts.get("active_alerts") or []) if isinstance(facts, dict) else []),
                "timeline_events": len(timeline),
                "active_alerts_24h": (alerts.get("summary") or {}).get("count", 0),
            },
            "month": now.strftime("%Y-%m"),
            "day": now.strftime("%Y-%m-%d"),
        }

    async def latest_snapshot(self, patient_id: str, *, max_age_hours: int = 8) -> dict[str, Any] | None:
        since = datetime.now() - timedelta(hours=max(int(max_age_hours or 8), 1))
        return await self.db.col("score_records").find_one(
            {"patient_id": patient_id, "score_type": "digital_twin_snapshot", "calc_time": {"$gte": since}},
            sort=[("calc_time", -1)],
        )

    async def persist_snapshot(self, snapshot: dict[str, Any], *, upsert_window_minutes: int = 30) -> dict[str, Any]:
        now = snapshot.get("calc_time") if isinstance(snapshot.get("calc_time"), datetime) else datetime.now()
        patient_id = str(snapshot.get("patient_id") or "").strip()
        stored_snapshot = self._storage_view(snapshot)
        latest = await self.db.col("score_records").find_one(
            {
                "patient_id": patient_id,
                "score_type": "digital_twin_snapshot",
                "calc_time": {"$gte": now - timedelta(minutes=max(int(upsert_window_minutes or 30), 1))},
            },
            sort=[("calc_time", -1)],
        )
        if latest:
            await self.db.col("score_records").update_one({"_id": latest["_id"]}, {"$set": stored_snapshot})
            snapshot["_id"] = latest["_id"]
            return snapshot
        result = await self.db.col("score_records").insert_one(stored_snapshot)
        snapshot["_id"] = result.inserted_id
        return snapshot

    async def get_or_build_snapshot(
        self,
        patient_id: str,
        patient_doc: dict[str, Any],
        *,
        hours: int = 24,
        refresh: bool = False,
        persist: bool = True,
    ) -> dict[str, Any]:
        previous = None
        if not refresh:
            cached = await self.latest_snapshot(patient_id, max_age_hours=min(max(int(hours or 24), 1), 12))
            if cached:
                return cached
        previous = await self.latest_snapshot(patient_id, max_age_hours=72)
        snapshot = await self.build_snapshot(patient_id, patient_doc, hours=hours)
        diff_payload = self._diff_from_previous(previous, snapshot)
        snapshot["_diff_from_previous"] = diff_payload
        snapshot["diff"] = diff_payload
        self._apply_diff_markers(snapshot, diff_payload)
        if persist:
            return await self.persist_snapshot(snapshot)
        return snapshot
