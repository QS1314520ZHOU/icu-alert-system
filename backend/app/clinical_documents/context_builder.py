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
    FluidBalance,
    InfectionEvidence,
    InfectionLabItem,
    LabDelta,
    LineDevices,
    NeuroAssessment,
    ProgressNoteContext,
    Scores,
    VentChange,
    Ventilator,
    TubeDevice,
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


def _safe_float_or_none(val: Any) -> float | None:
    try:
        if val is None or val == "":
            return None
        return float(val)
    except (TypeError, ValueError):
        return None


def _first_value(row: dict) -> Any:
    for key in ("fVal", "intVal", "strVal", "value"):
        value = row.get(key)
        if value is not None and value != "":
            return value
    return None


def _bedside_value(doc: dict, *codes: str) -> Any:
    code_set = {str(code) for code in codes if code}
    for item in doc.get("bedsides") or []:
        if not isinstance(item, dict) or str(item.get("code") or "") not in code_set:
            continue
        for key in ("fVal", "intVal", "strVal", "value"):
            value = item.get(key)
            if value is not None and value != "":
                return value
    return None


def _row_value(row: dict) -> Any:
    for key in ("fVal", "intVal", "strVal", "value"):
        value = row.get(key)
        if value is not None and value != "":
            return value
    return None


def _is_noninvasive_or_oxygen_mode(mode: Any) -> bool:
    text = str(mode or "").strip().lower()
    return bool(text) and any(
        token in text
        for token in [
            "hf",
            "hfnc",
            "oxygen",
            "氧",
            "吸氧",
            "高流量",
            "鼻导管",
            "面罩",
        ]
    )


def _is_active_tube(row: dict) -> bool:
    end_value = row.get("endTime") or row.get("stopTime") or row.get("removeTime") or row.get("drawingTime")
    if end_value:
        return False
    status = str(row.get("status") or row.get("tubeStatus") or "").strip().lower()
    return status not in {"stopped", "stop", "removed", "拔管", "已拔管", "结束"}


def _tube_category(row: dict) -> str:
    text = f"{row.get('name') or ''} {row.get('type') or ''}".lower()
    if any(key in text for key in ["气管", "插管", "气切", "ett", "tracheo"]):
        return "airway"
    if any(key in text for key in ["cvc", "picc", "动脉", "静脉", "导管", "穿刺", "swan", "留置针", "ecmo"]):
        return "vascular"
    if any(key in text for key in ["胃管", "鼻肠", "鼻胃", "空肠管"]):
        return "enteral"
    if any(key in text for key in ["引流", "胸管", "t管", "造瘘"]):
        return "drain"
    if any(key in text for key in ["导尿", "尿管", "foley"]):
        return "urinary"
    return "other"


def _tube_category_label(category: str) -> str:
    return {
        "airway": "人工气道",
        "vascular": "血管通路",
        "drain": "引流管",
        "enteral": "胃肠/营养管",
        "urinary": "尿管",
        "other": "其他管路",
    }.get(category, "其他管路")


def _lab_time(doc: dict) -> datetime | None:
    return (
        _parse_datetime(doc.get("authTime"))
        or _parse_datetime(doc.get("reportTime"))
        or _parse_datetime(doc.get("collectTime"))
        or _parse_datetime(doc.get("time"))
    )


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


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(text[: len(fmt)], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _calculate_age(p: dict, now: datetime) -> int:
    raw_age = p.get("age") or p.get("hisAge")
    try:
        age = int(float(str(raw_age).replace("岁", "").strip()))
    except (TypeError, ValueError):
        age = 0
    if age > 0:
        return age
    for field in (
        "birthDate",
        "birthday",
        "dateOfBirth",
        "dob",
        "hisBirthDate",
        "birth",
        "birthDay",
        "birthdayDate",
        "出生日期",
    ):
        birth_dt = _parse_datetime(p.get(field))
        if birth_dt:
            years = now.year - birth_dt.year
            if (now.month, now.day) < (birth_dt.month, birth_dt.day):
                years -= 1
            return max(years, 0)
    return 0


def _normalize_sex(value: Any) -> str:
    text = str(value or "").strip()
    lowered = text.lower()
    if lowered in {"male", "m", "man", "1"} or text == "男":
        return "男"
    if lowered in {"female", "f", "woman", "2"} or text == "女":
        return "女"
    return text or "未知"


def _compute_trend(values: list[float]) -> str:
    """Determine trend from a time-ordered list of numeric readings."""
    if len(values) < 3:
        return "数据不足"
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
        bedside_pids = list(dict.fromkeys([p_oid, *p_ids]))

        vitals = await self._build_vitals(bedside_pids, start, end)
        labs = await self._build_labs(p_ids, start, end)
        drugs = await self._build_drugs(p, start, end, p_ids)
        vent = await self._build_vent(bedside_pids, start, end)
        neuro = await self._build_neuro_assessment(bedside_pids, start, end)
        alerts = await self._build_alerts(p_oid, start, end)
        scores = await self._build_scores(p_ids)
        fluid_balance = await self._build_fluid_balance(bedside_pids, start, end)
        line_devices = await self._build_line_devices(bedside_pids, start, end)
        infection_evidence = await self._build_infection_evidence(p_ids, start - timedelta(hours=48), end)

        return ProgressNoteContext(
            patient_id=patient_id,
            window_start=start.strftime("%Y-%m-%d %H:%M"),
            window_end=end.strftime("%Y-%m-%d %H:%M"),
            basics=basics,
            v=vitals,
            labs=labs,
            drugs=drugs,
            vent=vent,
            neuro=neuro,
            alerts=alerts,
            scores=scores,
            fluid_balance=fluid_balance,
            line_devices=line_devices,
            infection_evidence=infection_evidence,
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
        age = _calculate_age(p, now)
        sex = _normalize_sex(p.get("sex") or p.get("gender") or p.get("hisSex"))
        diagnosis = str(
            p.get("diagnosis")
            or p.get("clinicalDiagnosis")
            or p.get("admissionDiagnosis")
            or p.get("admitDiagnosis")
            or "未提供"
        )
        admit_raw = p.get("admissionTime") or p.get("inTime") or p.get("inDeptTime")
        admit_dt = _parse_datetime(admit_raw)
        day = (now.date() - admit_dt.date()).days if admit_dt else 0
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

        async def _device_ids_for_patient_ids() -> list[str]:
            ids: list[str] = []
            try:
                cursor = self.db.col("deviceBind").find(
                    {"pid": {"$in": p_ids}, "unBindTime": None},
                    {"deviceID": 1},
                ).limit(100)
                async for row in cursor:
                    device_id = str(row.get("deviceID") or "").strip()
                    if device_id:
                        ids.append(device_id)
            except Exception:
                logger.debug("clinical document deviceBind lookup failed", exc_info=True)
            return list(dict.fromkeys(ids))

        # deviceCap is the primary live monitor source used by the patient pages.
        device_ids = await _device_ids_for_patient_ids()
        if device_ids:
            for key, aliases in field_alias.items():
                try:
                    cursor = self.db.col("deviceCap").find(
                        {
                            "deviceID": {"$in": device_ids},
                            "code": {"$in": aliases},
                            "time": {"$gte": start, "$lte": end},
                        },
                        {"code": 1, "time": 1, "fVal": 1, "intVal": 1, "strVal": 1, "value": 1},
                    ).sort("time", 1).limit(3000)
                    rows = await cursor.to_list(length=3000)
                except Exception:
                    rows = []
                for row in rows:
                    if str(row.get("code") or "") not in set(aliases):
                        continue
                    fv = _safe_float(_row_value(row))
                    if fv > 0:
                        param_map[key].append(fv)
                        if key == "hr" and fv > 150:
                            events.append(VitalEvent(time_hm=_hm(row.get("time")), type="心率过快", value=str(fv)))
                        if key == "spo2" and fv < 90:
                            events.append(VitalEvent(time_hm=_hm(row.get("time")), type="SpO2过低", value=str(fv)))

        # Prefer bedside monitor time series; bGATemp is only a fallback in many deployments.
        bedside_col = self.db.col("bedside")
        for key, aliases in field_alias.items():
            if param_map[key]:
                continue
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
                    if val is None:
                        val = _bedside_value(doc, alias)
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
                return VitalStat(min=None, max=None, trend="无数据")
            if len(values) < 3:
                return VitalStat(
                    min=round(min(values), 1),
                    max=round(max(values), 1),
                    trend="数据不足",
                )
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

    async def _build_infection_evidence(self, p_ids: list[str], start: datetime, end: datetime) -> InfectionEvidence | None:
        col = self.db.dc_col("VI_ICU_EXAM_ITEM")
        cursor = col.find(
            {
                "hisPid": {"$in": p_ids},
                "$or": [
                    {"authTime": {"$gte": start, "$lte": end}},
                    {"reportTime": {"$gte": start, "$lte": end}},
                    {"collectTime": {"$gte": start, "$lte": end}},
                ],
            },
            {
                "itemCnName": 1,
                "itemName": 1,
                "name": 1,
                "result": 1,
                "resultValue": 1,
                "value": 1,
                "unit": 1,
                "resultFlag": 1,
                "seriousFlag": 1,
                "authTime": 1,
                "reportTime": 1,
                "collectTime": 1,
                "time": 1,
            },
        ).sort("authTime", -1).limit(1200)
        docs = await cursor.to_list(length=1200)

        marker_keywords = ["白细胞", "wbc", "pct", "降钙素原", "crp", "c反应蛋白", "超敏c反应蛋白", "il-6", "白介素"]
        culture_keywords = ["培养", "culture", "菌", "药敏", "涂片", "mngs", "病原", "血培养", "痰培养", "尿培养"]

        def make_item(doc: dict) -> InfectionLabItem | None:
            name = str(doc.get("itemCnName") or doc.get("itemName") or doc.get("name") or "").strip()
            value = str(doc.get("result") or doc.get("resultValue") or doc.get("value") or "").strip()
            if not name or not value:
                return None
            t = _lab_time(doc)
            flag = str(doc.get("resultFlag") or doc.get("seriousFlag") or "").strip()
            if flag in {"0", "正常", "normal", "NORMAL"}:
                flag = ""
            return InfectionLabItem(
                name=name,
                value=value,
                unit=str(doc.get("unit") or ""),
                observed_at=t.strftime("%Y-%m-%d %H:%M") if t else None,
                flag=flag,
            )

        markers: list[InfectionLabItem] = []
        cultures: list[InfectionLabItem] = []
        seen_marker_names: set[str] = set()
        seen_culture_names: set[str] = set()
        for doc in docs:
            name = str(doc.get("itemCnName") or doc.get("itemName") or doc.get("name") or "")
            lowered = name.lower()
            item = make_item(doc)
            if not item:
                continue
            if any(token in lowered for token in marker_keywords) and item.name not in seen_marker_names:
                markers.append(item)
                seen_marker_names.add(item.name)
            if any(token in lowered for token in culture_keywords) and item.name not in seen_culture_names:
                cultures.append(item)
                seen_culture_names.add(item.name)
            if len(markers) >= 8 and len(cultures) >= 8:
                break

        if not markers and not cultures:
            return None
        return InfectionEvidence(inflammatory_markers=markers[:8], culture_results=cultures[:8])

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
        bedside_snapshot = await self._build_bedside_vent_snapshot(p_ids, start, end)
        if not latest and not bedside_snapshot:
            return None
        latest = latest or {}

        mode = (
            latest.get("ventMode")
            or latest.get("param_ventMode")
            or _bedside_value(latest, "param_HuXiMoShi", "param_vent_mode")
            or bedside_snapshot.get("mode")
        )
        if not mode:
            return None

        fio2 = _safe_float(
            latest.get("param_fio2")
            or latest.get("FiO2")
            or _bedside_value(latest, "param_FiO2", "param_bg_FiO2", "param_lis_xueQi_FiO2")
            or bedside_snapshot.get("fio2"),
            0,
        )
        peep = _safe_float(
            latest.get("param_peep")
            or latest.get("PEEP")
            or _bedside_value(latest, "param_vent_measure_peep", "param_vent_peep")
            or bedside_snapshot.get("peep"),
            0,
        )
        vt = int(_safe_float(latest.get("param_vt") or latest.get("VT") or _bedside_value(latest, "param_vent_vt") or bedside_snapshot.get("vt"), 0))
        pplat = _safe_float(
            latest.get("param_pplat")
            or latest.get("Pplat")
            or _bedside_value(latest, "param_vent_plat_pressure")
            or bedside_snapshot.get("pplat"),
            0,
        )
        # P/F ratio 必须使用动脉血气直接给出的值，不可用 SpO2 推算
        pf_raw = latest.get("param_bg_P/Fratio")
        if pf_raw is None:
            pf_raw = latest.get("param_bg_PFratio")  # 兼容可能的命名变体
        if pf_raw is None:
            pf_raw = _bedside_value(latest, "param_bg_P/Fratio", "param_bg_PFratio", "param_bg_OI")
        if pf_raw is None:
            pf_raw = bedside_snapshot.get("pf_ratio")
        pf_ratio = _safe_float(pf_raw, 0)
        pf_ratio = round(pf_ratio, 1) if pf_ratio > 0 else None

        return Ventilator(
            mode=str(mode),
            fio2=round(fio2, 2),
            peep=round(peep, 1),
            vt=vt,
            pplat=round(pplat, 1),
            pf_ratio=pf_ratio,
            changes=[],
        )

    async def _build_bedside_vent_snapshot(self, p_ids: list[str], start: datetime, end: datetime) -> dict[str, Any]:
        codes = {
            "mode": {"param_HuXiMoShi", "param_vent_mode"},
            "fio2": {"param_FiO2", "param_bg_FiO2", "param_lis_xueQi_FiO2", "param_XiYangNongdu"},
            "peep": {"param_vent_measure_peep", "param_vent_peep"},
            "vt": {"param_vent_vt"},
            "pplat": {"param_vent_plat_pressure"},
            "pf_ratio": {"param_bg_P/Fratio", "param_bg_PFratio", "param_bg_OI"},
        }
        all_codes = {code for group in codes.values() for code in group}
        cursor = self.db.col("bedside").find(
            {
                "pid": {"$in": p_ids},
                "code": {"$in": list(all_codes)},
                "time": {"$gte": start, "$lte": end},
            },
            {"code": 1, "time": 1, "fVal": 1, "intVal": 1, "strVal": 1, "value": 1},
        ).sort("time", -1).limit(200)
        snapshot: dict[str, Any] = {}
        async for row in cursor:
            code = str(row.get("code") or "")
            value = _first_value(row)
            if value is None:
                continue
            for key, group in codes.items():
                if key not in snapshot and code in group:
                    snapshot[key] = value
                    break
            if all(key in snapshot for key in codes):
                break
        return snapshot

    async def _build_neuro_assessment(self, p_ids: list[str], start: datetime, end: datetime) -> NeuroAssessment | None:
        codes = {
            "rass": {"param_score_rass_obs", "param_score_rass_obs_Q4H"},
            "cam_icu": {"param_score_cam_icu", "param_cam_icu", "param_CAM_ICU"},
        }
        all_codes = {code for group in codes.values() for code in group}
        cursor = self.db.col("bedside").find(
            {
                "pid": {"$in": p_ids},
                "code": {"$in": list(all_codes)},
                "time": {"$gte": start, "$lte": end},
            },
            {"code": 1, "time": 1, "fVal": 1, "intVal": 1, "strVal": 1, "value": 1},
        ).sort("time", -1).limit(50)
        rass = None
        cam_icu = None
        observed_at = None
        refs: list[str] = []
        async for row in cursor:
            code = str(row.get("code") or "")
            value = _first_value(row)
            if observed_at is None:
                observed_at = str(row.get("time") or "")
            if code in codes["rass"] and rass is None:
                rass = _safe_float_or_none(value)
                refs.append(code)
            elif code in codes["cam_icu"] and cam_icu is None:
                cam_icu = str(value)
                refs.append(code)
            if rass is not None and cam_icu is not None:
                break
        if rass is None and cam_icu is None:
            return None
        return NeuroAssessment(rass=rass, cam_icu=cam_icu, observed_at=observed_at, evidence_refs=refs)

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

    async def _build_fluid_balance(self, bedside_pids: list[str], start: datetime, end: datetime) -> FluidBalance | None:
        code_sets = await self._fluid_config_codes()

        async def latest_value(codes: set[str]) -> tuple[float | None, str | None]:
            if not codes:
                return None, None
            row = await self.db.col("bedside").find_one(
                {
                    "pid": {"$in": bedside_pids},
                    "code": {"$in": list(codes)},
                    "time": {"$gte": start, "$lte": end},
                },
                sort=[("time", -1)],
            )
            if not row:
                return None, None
            value = _safe_float_or_none(_first_value(row))
            return value, str(row.get("code") or "")

        async def sum_values(codes: set[str], source_label: str) -> tuple[float | None, str | None]:
            if not codes:
                return None, None
            rows = await self.db.col("bedside").find(
                {
                    "pid": {"$in": bedside_pids},
                    "code": {"$in": list(codes)},
                    "time": {"$gte": start, "$lte": end},
                },
                {"fVal": 1, "intVal": 1, "strVal": 1, "value": 1},
            ).to_list(length=5000)
            values = [_safe_float_or_none(_first_value(row)) for row in rows]
            values = [value for value in values if value is not None and value > 0]
            if not values:
                return None, None
            return round(sum(values), 1), source_label

        intake, intake_code = await latest_value(code_sets["intake_total"])
        output, output_code = await latest_value(code_sets["output_total"])
        if intake is None:
            intake, intake_code = await sum_values(code_sets["intake_detail"], "入量明细汇总")
        if output is None:
            output, output_code = await sum_values(code_sets["output_detail"], "出量明细汇总")
        urine, urine_code = await latest_value(code_sets["urine"])

        if urine is None:
            rows = await self.db.col("bedside").find(
                {
                    "pid": {"$in": bedside_pids},
                    "code": {"$in": list(code_sets["urine_hourly"])},
                    "time": {"$gte": start, "$lte": end},
                },
                {"fVal": 1, "intVal": 1, "strVal": 1, "value": 1},
            ).to_list(length=2000)
            values = [_safe_float_or_none(_first_value(row)) for row in rows]
            values = [value for value in values if value is not None and value > 0]
            if values:
                urine = round(sum(values), 1)
                urine_code = "尿量小时记录汇总"

        if intake is None and output is None and urine is None:
            return None

        net = round((intake or 0) - (output or 0), 1) if intake is not None and output is not None else None
        refs = [code for code in [intake_code, output_code, urine_code] if code]
        return FluidBalance(
            intake_24h_ml=round(intake, 1) if intake is not None else None,
            output_24h_ml=round(output, 1) if output is not None else None,
            urine_24h_ml=round(urine, 1) if urine is not None else None,
            net_24h_ml=net,
            evidence_refs=refs,
        )

    async def _fluid_config_codes(self) -> dict[str, set[str]]:
        defaults = {
            "intake_total": {"param_in_hour_sum"},
            "output_total": {"param_out_hour_sum"},
            "intake_detail": set(),
            "output_detail": set(),
            "urine": {"param_udd_urine_24h", "param_udd_urine_total"},
            "urine_hourly": {
                "param_niaoLiang",
                "param_niaoLiang_pure",
                "param_udd_urine_cur",
                "param_udd_urine_1h",
            },
        }
        try:
            rows = await self.db.col("configParam").find(
                {
                    "$or": [
                        {"calculation": {"$in": ["in", "out"]}},
                        {"code": {"$regex": "urine|niao|udd_urine|in_hour_sum|out_hour_sum", "$options": "i"}},
                    ],
                    "valid": {"$ne": False},
                },
                {"code": 1, "calculation": 1},
            ).to_list(length=500)
        except Exception:
            rows = []

        codes = {key: set(value) for key, value in defaults.items()}
        for row in rows:
            code = str(row.get("code") or "").strip()
            if not code:
                continue
            calc = str(row.get("calculation") or "").strip().lower()
            lowered = code.lower()
            if calc == "in":
                if "sum" in lowered or "total" in lowered or "24" in lowered:
                    codes["intake_total"].add(code)
                else:
                    codes["intake_detail"].add(code)
            if calc == "out":
                if "sum" in lowered or "total" in lowered or "24" in lowered:
                    codes["output_total"].add(code)
                else:
                    codes["output_detail"].add(code)
            if any(token in lowered for token in ["urine", "niao", "udd_urine"]):
                if any(token in lowered for token in ["24h", "24", "total"]):
                    codes["urine"].add(code)
                else:
                    codes["urine_hourly"].add(code)
        return codes

    async def _build_line_devices(self, bedside_pids: list[str], start: datetime, end: datetime) -> LineDevices | None:
        tube_rows = await self.db.col("tubeExe").find(
            {"pid": {"$in": bedside_pids}},
            {
                "name": 1,
                "type": 1,
                "body": 1,
                "startTime": 1,
                "endTime": 1,
                "stopTime": 1,
                "removeTime": 1,
                "drawingTime": 1,
                "status": 1,
                "tubeStatus": 1,
                "tubeRecordList": 1,
            },
        ).sort("startTime", 1).limit(100).to_list(length=100)

        now = end
        active_tubes: list[TubeDevice] = []
        for row in tube_rows:
            if not _is_active_tube(row):
                continue
            start_dt = _parse_datetime(row.get("startTime"))
            latest_record_time = None
            latest_status = ""
            records = row.get("tubeRecordList") if isinstance(row.get("tubeRecordList"), list) else []
            valid_records = [record for record in records if isinstance(record, dict) and record.get("valid") is not False]
            if valid_records:
                latest = max(valid_records, key=lambda item: _parse_datetime(item.get("time")) or datetime.min)
                latest_record_time = str(latest.get("time") or "")
                status_parts = [
                    str(latest.get(key) or "").strip()
                    for key in ("unobstructed", "piercingHole", "positionSituation", "location", "changeDressing")
                    if latest.get(key)
                ]
                latest_status = "，".join(dict.fromkeys(status_parts))
            category = _tube_category(row)
            active_tubes.append(
                TubeDevice(
                    name=str(row.get("name") or row.get("type") or _tube_category_label(category)),
                    category=category,
                    site=str(row.get("body") or ""),
                    dwell_days=max(0, (now - start_dt).days) if start_dt else None,
                    start_time=str(row.get("startTime") or ""),
                    latest_record_time=latest_record_time,
                    latest_status=latest_status,
                )
            )

        drainage_codes = await self._drainage_config_codes()
        drainage_24h_ml = None
        used_drainage_codes: list[str] = []
        if drainage_codes:
            rows = await self.db.col("bedside").find(
                {
                    "pid": {"$in": bedside_pids},
                    "code": {"$in": list(drainage_codes)},
                    "time": {"$gte": start, "$lte": end},
                },
                {"code": 1, "fVal": 1, "intVal": 1, "strVal": 1, "value": 1},
            ).to_list(length=2000)
            values = []
            for row in rows:
                value = _safe_float_or_none(_first_value(row))
                if value is not None and value > 0:
                    values.append(value)
                    used_drainage_codes.append(str(row.get("code") or ""))
            if values:
                drainage_24h_ml = round(sum(values), 1)

        if not active_tubes and drainage_24h_ml is None:
            return None
        return LineDevices(
            active_tubes=active_tubes,
            drainage_24h_ml=drainage_24h_ml,
            drainage_codes=sorted(set(used_drainage_codes)),
        )

    async def _drainage_config_codes(self) -> set[str]:
        try:
            rows = await self.db.col("configParam").find(
                {
                    "$or": [
                        {"code": {"$regex": "drain|引流|胸管|腹腔", "$options": "i"}},
                        {"name": {"$regex": "drain|引流|胸管|腹腔", "$options": "i"}},
                    ],
                    "valid": {"$ne": False},
                },
                {"code": 1, "calculation": 1},
            ).to_list(length=500)
        except Exception:
            rows = []
        codes: set[str] = set()
        for row in rows:
            code = str(row.get("code") or "").strip()
            if not code:
                continue
            lowered = code.lower()
            if str(row.get("calculation") or "").lower() == "out" or lowered.startswith("param_tube_"):
                codes.add(code)
        return codes
