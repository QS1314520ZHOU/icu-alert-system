from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


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
        trend = "stable" if abs(delta) < 1e-6 else ("up" if delta > 0 else "down")
        return {
            "points": len(values),
            "latest": round(latest, 3),
            "delta": delta,
            "trend": trend,
            "start_time": series[0].get("time"),
            "end_time": series[-1].get("time"),
        }

    async def _build_vitals_block(self, patient_id: str, hours: int) -> dict[str, Any]:
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
        return {
            "latest": latest or {},
            "snapshot": {key: self._series_snapshot(rows) for key, rows in series_map.items()},
            "series": {key: rows[-24:] for key, rows in series_map.items()},
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
            for doc in reversed(docs):
                text = " ".join(str(doc.get(key) or "") for key in ("drugName", "orderName", "drugSpec", "route", "routeName")).lower()
                if not any(token in text for token in ["去甲肾上腺素", "norepinephrine", "noradrenaline", "多巴胺", "dopamine", "肾上腺素", "epinephrine", "血管加压素", "vasopressin"]):
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

    def _build_event_timeline(self, *, vitals: dict[str, Any], labs: dict[str, Any], medications: dict[str, Any], scores: dict[str, Any], text_signals: dict[str, Any], alerts: dict[str, Any]) -> list[dict[str, Any]]:
        timeline: list[dict[str, Any]] = []
        for metric, rows in (vitals.get("series") or {}).items():
            if rows:
                latest = rows[-1]
                timeline.append({"time": latest.get("time"), "source": "vitals", "type": metric, "label": f"{metric.upper()} {latest.get('value')}"})
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
        timeline = [item for item in timeline if item.get("time")]
        timeline.sort(key=lambda item: item.get("time") or datetime.min, reverse=True)
        return timeline[:60]

    async def build_snapshot(self, patient_id: str, patient_doc: dict[str, Any], *, hours: int = 24) -> dict[str, Any]:
        facts = await self.alert_engine._collect_patient_facts(patient_doc, patient_doc.get("_id")) if hasattr(self.alert_engine, "_collect_patient_facts") else {}
        vitals = await self._build_vitals_block(patient_id, hours)
        labs = await self._build_labs_block(patient_doc, hours)
        medications = await self._build_medication_block(patient_id, patient_doc, hours)
        scores = await self._build_scores_block(patient_id, patient_doc, hours)
        text_signals = await self._build_text_signal_block(patient_doc, patient_id, hours)
        alerts = await self._build_alert_block(patient_id, patient_doc, hours)
        timeline = self._build_event_timeline(
            vitals=vitals,
            labs=labs,
            medications=medications,
            scores=scores,
            text_signals=text_signals,
            alerts=alerts,
        )
        now = datetime.now()
        snapshot = {
            "map": {"current": _safe_float(((vitals.get("snapshot") or {}).get("map") or {}).get("latest"))},
            "hr": {"current": _safe_float(((vitals.get("snapshot") or {}).get("hr") or {}).get("latest"))},
            "spo2": {"current": _safe_float(((vitals.get("snapshot") or {}).get("spo2") or {}).get("latest"))},
            "rr": {"current": _safe_float(((vitals.get("snapshot") or {}).get("rr") or {}).get("latest"))},
            "temp": {"current": _safe_float(((vitals.get("snapshot") or {}).get("temp") or {}).get("latest"))},
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
        latest = await self.db.col("score_records").find_one(
            {
                "patient_id": patient_id,
                "score_type": "digital_twin_snapshot",
                "calc_time": {"$gte": now - timedelta(minutes=max(int(upsert_window_minutes or 30), 1))},
            },
            sort=[("calc_time", -1)],
        )
        if latest:
            await self.db.col("score_records").update_one({"_id": latest["_id"]}, {"$set": snapshot})
            snapshot["_id"] = latest["_id"]
            return snapshot
        result = await self.db.col("score_records").insert_one(snapshot)
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
        if not refresh:
            cached = await self.latest_snapshot(patient_id, max_age_hours=min(max(int(hours or 24), 1), 12))
            if cached:
                return cached
        snapshot = await self.build_snapshot(patient_id, patient_doc, hours=hours)
        if persist:
            return await self.persist_snapshot(snapshot)
        return snapshot
