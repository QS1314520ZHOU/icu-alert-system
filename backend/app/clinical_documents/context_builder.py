"""
Clinical Documents — Context builder.

Reads patient data from MongoDB collections and compresses it into
a ProgressNoteContext suitable for the LLM prompt template.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from app.utils.patient_helpers import patient_his_pid_candidates, patient_his_pid
from app.utils.serialization import safe_oid

from .schemas import (
    AlertItem,
    Basics,
    DrugEvent,
    LabDelta,
    ProgressNoteContext,
    Scores,
    VentChange,
    Ventilator,
    VitalEvent,
    VitalStat,
    Vitals,
)

logger = logging.getLogger("icu-alert")


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _hm(dt: datetime | str | None) -> str:
    """Format datetime or ISO string to HH:MM."""
    if dt is None:
        return "--:--"
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt)
        except Exception:
            return dt[:5] if len(dt) >= 5 else dt
    return dt.strftime("%H:%M")


def _compute_trend(values: list[float]) -> str:
    """Determine trend from a time-ordered list of numeric readings."""
    if len(values) < 2:
        return "平稳"
    first_half = values[: len(values) // 2]
    second_half = values[len(values) // 2 :]
    avg1 = sum(first_half) / len(first_half) if first_half else 0
    avg2 = sum(second_half) / len(second_half) if second_half else 0
    diff_pct = abs(avg2 - avg1) / max(abs(avg1), 1e-6)
    if diff_pct < 0.05:
        return "平稳"
    # Check for consistent direction
    ups = sum(1 for a, b in zip(values, values[1:]) if b > a)
    downs = sum(1 for a, b in zip(values, values[1:]) if b < a)
    total = len(values) - 1
    if ups / total >= 0.7:
        return "上升"
    if downs / total >= 0.7:
        return "下降"
    if diff_pct > 0.15:
        return "波动"
    return "上升" if avg2 > avg1 else "下降"


class ProgressNoteContextBuilder:
    """Assembles ProgressNoteContext from raw MongoDB collections."""

    def __init__(self, db):
        self.db = db

    async def build(self, patient_id: str, hours: int = 24) -> ProgressNoteContext:
        end = datetime.now()
        start = end - timedelta(hours=hours)

        p = await self._get_patient(patient_id)
        basics = self._extract_basics(p, end)

        p_ids = patient_his_pid_candidates(p)
        if patient_id not in p_ids:
            p_ids.append(patient_id)
        p_oid = str(p.get("_id"))
        if p_oid not in p_ids:
            p_ids.append(p_oid)

        vitals = await self._build_vitals(p_ids, start, end)
        labs = await self._build_labs(p_ids, start, end)
        drugs = await self._build_drugs(p, start, end, p_ids)
        vent = await self._build_vent(p_ids, start, end)
        alerts = await self._build_alerts(p_oid, start, end)
        scores = await self._build_scores(p_ids)

        return ProgressNoteContext(
            patient_id=patient_id,
            window_start=start.strftime("%Y-%m-%d %H:%M"),
            window_end=end.strftime("%Y-%m-%d %H:%M"),
            basics=basics,
            v=vitals,
            labs=labs,
            drugs=drugs,
            vent=vent,
            alerts=alerts,
            scores=scores,
        )

    # ── Patient basics ───────────────────────────────────────────────
    async def _get_patient(self, patient_id: str) -> dict:
        col = self.db.col("patient")
        doc = await col.find_one({"_id": patient_id}) or await col.find_one({"hisPid": patient_id})
        if not doc:
            doc = await col.find_one({"patientId": patient_id})
        # Try converting to ObjectId if valid
        oid = safe_oid(patient_id)
        if not doc and oid is not None:
            doc = await col.find_one({"_id": oid})
        if not doc:
            raise ValueError(f"患者 {patient_id} 未找到")
        return doc

    def _extract_basics(self, p: dict, now: datetime) -> Basics:
        name = str(p.get("name") or p.get("hisName") or "未知患者")
        bed = str(p.get("bedNo") or p.get("bed") or p.get("bedLabel") or p.get("hisBed") or "?")
        age = int(p.get("age") or 0)
        sex = str(p.get("sex") or p.get("gender") or "未知")
        diagnosis = str(p.get("diagnosis") or p.get("admitDiagnosis") or "未提供")
        admit_raw = p.get("admissionTime") or p.get("inTime") or p.get("inDeptTime")
        if isinstance(admit_raw, datetime):
            day = (now.date() - admit_raw.date()).days
        elif isinstance(admit_raw, str):
            try:
                day = (now.date() - datetime.fromisoformat(admit_raw).date()).days
            except Exception:
                day = 0
        else:
            day = 0
        return Basics(
            name=name,
            bed=bed,
            age=age,
            sex=sex,
            day=max(day, 0),
            diagnosis=diagnosis,
        )

    # ── Vitals ───────────────────────────────────────────────────────
    async def _build_vitals(self, p_ids: list[str], start: datetime, end: datetime) -> Vitals:
        param_map: dict[str, list[float]] = {
            "hr": [], "map": [], "spo2": [], "temp": [], "rr": [],
        }
        field_alias = {
            "hr": ["param_HR", "HR", "hr", "heartRate"],
            "map": ["param_nibp_m", "param_ibp_m", "MAP", "map", "meanBP"],
            "spo2": ["param_spo2", "SpO2", "spo2"],
            "temp": ["param_T", "T", "temp", "temperature"],
            "rr": ["param_resp", "RR", "rr", "respRate"],
        }
        events: list[VitalEvent] = []

        # Prefer bedside monitor time series; bGATemp is only a fallback in many deployments.
        bedside_col = self.db.col("bedside")
        for key, aliases in field_alias.items():
            for code in aliases:
                try:
                    cursor = bedside_col.find(
                        {"pid": {"$in": p_ids}, "code": code, "time": {"$gte": start, "$lte": end}},
                    ).sort("time", 1)
                    rows = await cursor.to_list(length=2000)
                except Exception:
                    rows = []
                for row in rows:
                    raw = row.get("fVal")
                    if raw is None:
                        raw = row.get("intVal")
                    if raw is None:
                        raw = row.get("strVal")
                    if raw is None:
                        raw = row.get("value")
                    fv = _safe_float(raw)
                    if fv > 0:
                        param_map[key].append(fv)
                        if key == "hr" and fv > 150:
                            events.append(VitalEvent(time_hm=_hm(row.get("time")), type="心率过快", value=str(raw)))
                        if key == "spo2" and fv < 90:
                            events.append(VitalEvent(time_hm=_hm(row.get("time")), type="SpO2过低", value=str(raw)))
                if param_map[key]:
                    break

        col = self.db.col("bGATemp")
        cursor = col.find(
            {"mrn": {"$in": p_ids}, "inputTime": {"$gte": start, "$lte": end}},
        ).sort("inputTime", 1)
        docs = await cursor.to_list(length=2000)

        for doc in docs:
            for key, aliases in field_alias.items():
                if param_map[key]:
                    continue
                for alias in aliases:
                    val = doc.get(alias)
                    if val is not None:
                        fv = _safe_float(val)
                        if fv > 0:
                            param_map[key].append(fv)
                        break

        # Detect abnormal events
        for doc in docs:
            for alias in field_alias["hr"]:
                v = doc.get(alias)
                if v is not None and _safe_float(v) > 150:
                    events.append(VitalEvent(
                        time_hm=_hm(doc.get("inputTime")),
                        type="心率过快",
                        value=str(v),
                    ))
                    break
            for alias in field_alias["spo2"]:
                v = doc.get(alias)
                if v is not None and 0 < _safe_float(v) < 90:
                    events.append(VitalEvent(
                        time_hm=_hm(doc.get("inputTime")),
                        type="SpO2过低",
                        value=str(v),
                    ))
                    break

        def _stat(values: list[float]) -> VitalStat:
            if not values:
                return VitalStat(min=0, max=0, trend="平稳")
            return VitalStat(
                min=round(min(values), 1),
                max=round(max(values), 1),
                trend=_compute_trend(values),
            )

        return Vitals(
            hr=_stat(param_map["hr"]),
            map=_stat(param_map["map"]),
            spo2=_stat(param_map["spo2"]),
            temp=_stat(param_map["temp"]),
            rr=_stat(param_map["rr"]),
            events=events[:10],
        )

    # ── Labs ──────────────────────────────────────────────────────────
    async def _build_labs(self, p_ids: list[str], start: datetime, end: datetime) -> list[LabDelta]:
        col = self.db.dc_col("VI_ICU_EXAM_ITEM")
        cursor = col.find(
            {
                "hisPid": {"$in": p_ids},
                "$or": [
                    {"authTime": {"$gte": start, "$lte": end}},
                    {"reportTime": {"$gte": start, "$lte": end}},
                ]
            },
        ).sort("authTime", -1)
        docs = await cursor.to_list(length=500)

        # Group by item name, pick latest two
        by_name: dict[str, list[dict]] = {}
        for doc in docs:
            name = str(doc.get("itemCnName") or doc.get("itemName") or doc.get("name") or "")
            if not name:
                continue
            by_name.setdefault(name, []).append(doc)

        results: list[LabDelta] = []
        for idx, (name, items) in enumerate(by_name.items(), start=1):
            if len(items) < 1:
                continue
            curr_val = _safe_float(items[0].get("result") or items[0].get("resultValue") or items[0].get("value"))
            prev_val = _safe_float(items[1].get("result") or items[1].get("resultValue") or items[1].get("value")) if len(items) > 1 else curr_val
            unit = str(items[0].get("unit") or "")
            ref_hi = _safe_float(items[0].get("refHigh") or items[0].get("upperLimit"), 1e9)
            ref_lo = _safe_float(items[0].get("refLow") or items[0].get("lowerLimit"), -1e9)

            if curr_val > ref_hi * 1.5:
                flag = "↑↑"
            elif curr_val > ref_hi:
                flag = "↑"
            elif curr_val < ref_lo * 0.5 and ref_lo > 0:
                flag = "↓↓"
            elif curr_val < ref_lo:
                flag = "↓"
            else:
                flag = "→"

            # Only include items that changed or are abnormal
            if flag == "→" and abs(curr_val - prev_val) < 0.01:
                continue

            results.append(LabDelta(
                id=idx,
                name=name,
                prev=round(prev_val, 2),
                curr=round(curr_val, 2),
                unit=unit,
                flag=flag,
            ))
            if len(results) >= 20:
                break
        return results

    # ── Drugs ─────────────────────────────────────────────────────────
    async def _build_drugs(self, p: dict, start: datetime, end: datetime, p_ids: list[str]) -> list[DrugEvent]:
        # Try drugExe first (primary logs)
        p_oid = str(p.get("_id"))
        col_exe = self.db.col("drugExe")
        
        cursor_exe = col_exe.find({
            "pid": p_oid,
            "$or": [
                {"executeTime": {"$gte": start, "$lte": end}},
                {"startTime": {"$gte": start, "$lte": end}},
                {"orderTime": {"$gte": start, "$lte": end}},
            ]
        }).sort("executeTime", -1)
        
        docs_exe = await cursor_exe.to_list(length=100)
        
        results: list[DrugEvent] = []
        idx = 1
        
        for doc in docs_exe:
            name = str(doc.get("drugName") or doc.get("orderName") or "")
            if not name:
                continue
            status = str(doc.get("status") or "").lower()
            if "停" in status or "stop" in status:
                action = "停用"
            elif "新" in status or "new" in status:
                action = "新增"
            else:
                action = "新增"
            dose = doc.get("dose") or doc.get("dosage")
            dose_str = f"{dose}{doc.get('doseUnit') or ''}" if dose else None
            time_val = doc.get("executeTime") or doc.get("startTime") or doc.get("orderTime")
            
            results.append(DrugEvent(
                id=idx,
                time_hm=_hm(time_val),
                action=action,
                name=name,
                dose_after=dose_str,
            ))
            idx += 1
            if len(results) >= 30:
                break
                
        # If no drugExe, fallback to datacenter doctor orders (VI_ICU_ZYYZ)
        if not results:
            col_zyyz = self.db.dc_col("VI_ICU_ZYYZ")
            his_pid = patient_his_pid(p)
            if his_pid:
                cursor_zyyz = col_zyyz.find({
                    "pid": his_pid,
                    "orderTime": {"$gte": start, "$lte": end}
                }).sort("orderTime", -1)
                
                docs_zyyz = await cursor_zyyz.to_list(length=100)
                for doc in docs_zyyz:
                    name = str(doc.get("orderName") or "")
                    if not name:
                        continue
                    status = str(doc.get("orderType") or "").lower()
                    if "停" in status or "stop" in status:
                        action = "停用"
                    elif "新" in status or "new" in status:
                        action = "新增"
                    else:
                        action = "新增"
                    dose_str = doc.get("spec")
                    time_val = doc.get("orderTime")
                    
                    results.append(DrugEvent(
                        id=idx,
                        time_hm=_hm(time_val),
                        action=action,
                        name=name,
                        dose_after=dose_str,
                    ))
                    idx += 1
                    if len(results) >= 30:
                        break
        return results

    # ── Ventilator ────────────────────────────────────────────────────
    async def _build_vent(self, p_ids: list[str], start: datetime, end: datetime) -> Ventilator | None:
        col = self.db.col("bGATemp")
        latest = await col.find_one(
            {"mrn": {"$in": p_ids}, "inputTime": {"$gte": start, "$lte": end}},
            sort=[("inputTime", -1)],
        )
        if not latest:
            return None

        mode = latest.get("ventMode") or latest.get("param_ventMode")
        if not mode:
            return None

        fio2 = _safe_float(latest.get("param_fio2") or latest.get("FiO2"), 0)
        peep = _safe_float(latest.get("param_peep") or latest.get("PEEP"), 0)
        vt = int(_safe_float(latest.get("param_vt") or latest.get("VT"), 0))
        pplat = _safe_float(latest.get("param_pplat") or latest.get("Pplat"), 0)
        spo2_val = _safe_float(latest.get("param_spo2") or latest.get("SpO2"), 0)
        pf_ratio = round(spo2_val / fio2 * 100, 1) if fio2 > 0 and spo2_val > 0 else 0

        return Ventilator(
            mode=str(mode),
            fio2=round(fio2, 2),
            peep=round(peep, 1),
            vt=vt,
            pplat=round(pplat, 1),
            pf_ratio=pf_ratio,
            changes=[],
        )

    # ── Alerts ────────────────────────────────────────────────────────
    async def _build_alerts(self, p_oid: str, start: datetime, end: datetime) -> list[AlertItem]:
        col = self.db.col("alert_records")
        pipeline = [
            {"$match": {
                "patient_id": {"$in": [p_oid, safe_oid(p_oid)]}, 
                "created_at": {"$gte": start, "$lte": end}
            }},
            {"$group": {
                "_id": {"type": "$alert_type", "severity": "$severity"},
                "count": {"$sum": 1},
                "latest_active": {"$last": "$is_active"},
            }},
            {"$sort": {"count": -1}},
            {"$limit": 10},
        ]
        cursor = await col.aggregate(pipeline)
        docs = [doc async for doc in cursor]
        results: list[AlertItem] = []
        for idx, doc in enumerate(docs, start=1):
            results.append(AlertItem(
                id=idx,
                type=str(doc["_id"].get("type", "")),
                severity=str(doc["_id"].get("severity", "")),
                count=int(doc.get("count", 0)),
                active=bool(doc.get("latest_active", False)),
            ))
        return results

    # ── Scores ────────────────────────────────────────────────────────
    async def _build_scores(self, p_ids: list[str]) -> Scores | None:
        col = self.db.col("score")
        
        # Match either patient_id or pid in p_ids
        score_filter = {"$or": [{"patient_id": {"$in": p_ids}}, {"pid": {"$in": p_ids}}]}
        
        gcs_doc = await col.find_one(
            {"$and": [score_filter, {"score_type": {"$in": ["GCS", "gcs"]}}]},
            sort=[("calc_time", -1), ("time", -1)],
        )
        sofa_doc = await col.find_one(
            {"$and": [score_filter, {"score_type": {"$in": ["SOFA", "sofa"]}}]},
            sort=[("calc_time", -1), ("time", -1)],
        )
        apache_doc = await col.find_one(
            {"$and": [score_filter, {"score_type": {"$in": ["APACHE", "apache", "APACHE_II"]}}]},
            sort=[("calc_time", -1), ("time", -1)],
        )
        
        if not gcs_doc and not sofa_doc and not apache_doc:
            return None
            
        return Scores(
            gcs=int(_safe_float(gcs_doc.get("score") or gcs_doc.get("total_score"), 0)) if gcs_doc else 0,
            sofa=int(_safe_float(sofa_doc.get("score") or sofa_doc.get("total_score"), 0)) if sofa_doc else 0,
            apache=int(_safe_float(apache_doc.get("score") or apache_doc.get("total_score"), 0)) if apache_doc else 0,
        )
