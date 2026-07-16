"""
Handover — Context Service.

Aggregates patient data from MongoDB collections for the handover time window
("先查库再写" — query first, then write; never fabricate data).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from app.services.handover.schemas import HandoverContext
from app.utils.patient_helpers import patient_his_pid_candidates
from app.utils.serialization import safe_oid

logger = logging.getLogger("icu-alert")


def _safe_float(val: Any, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _safe_text(val: Any) -> str:
    return str(val or "").strip()


def _row_value(row: dict) -> Any:
    for key in ("fVal", "intVal", "strVal", "value"):
        value = row.get(key)
        if value is not None and value != "":
            return value
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[: len(fmt)], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


class HandoverContextService:
    """Assembles HandoverContext from raw MongoDB collections within a shift time window."""

    def __init__(self, db) -> None:
        self.db = db

    async def build(
        self,
        patient_id: str,
        time_window_start: datetime,
        time_window_end: datetime,
        shift: dict[str, Any] | None = None,
        shift_changes: list[dict[str, Any]] | None = None,
        previous_handover: dict[str, Any] | None = None,
    ) -> HandoverContext:
        """Aggregate all patient data for the given shift window.

        Args:
            patient_id: patient identifier
            time_window_start: shift start (naive or aware datetime)
            time_window_end: shift end
            shift: optional shift metadata dict {code, name, start_time, end_time}
            shift_changes: optional pre-computed change detection results
            previous_handover: optional previous handover snapshot for context
        """
        p = await self._get_patient(patient_id)
        p_ids = patient_his_pid_candidates(p)
        if patient_id not in p_ids:
            p_ids.append(patient_id)
        p_oid = str(p.get("_id"))
        if p_oid not in p_ids:
            p_ids.append(p_oid)
        bedside_pids = list(dict.fromkeys([p_oid, *p_ids]))

        return HandoverContext(
            patient_id=patient_id,
            patient=self._extract_patient_info(p),
            time_window={"start": time_window_start.isoformat(), "end": time_window_end.isoformat()},
            shift=shift or {},
            data_snapshot_at=datetime.now().isoformat(),
            situation=await self._build_situation(p, bedside_pids, time_window_start, time_window_end),
            background=self._extract_background(p),
            vitals=await self._build_vitals(bedside_pids, time_window_start, time_window_end),
            labs=await self._build_labs(p_ids, time_window_start, time_window_end),
            io=await self._build_io(bedside_pids, time_window_start, time_window_end),
            pumps=await self._build_pumps(bedside_pids, time_window_start, time_window_end),
            airway_vent=await self._build_airway_vent(bedside_pids, time_window_start, time_window_end),
            lines=await self._build_lines(bedside_pids, time_window_start, time_window_end),
            assessments=await self._build_assessments(bedside_pids, p_ids, time_window_start, time_window_end),
            events=await self._build_events(p_oid, time_window_start, time_window_end),
            pending_orders=await self._build_pending_orders(p_oid, time_window_start, time_window_end),
            alerts=await self._build_alerts(p_oid, time_window_start, time_window_end),
            shift_changes=shift_changes or [],
            previous_handover=previous_handover or {},
        )

    # ── patient ────────────────────────────────────────────────────

    async def _get_patient(self, patient_id: str) -> dict[str, Any]:
        for field in ("_id", "hisPid", "patientId"):
            try:
                doc = await self.db.col("patient").find_one({field: patient_id})
                if doc:
                    return doc
            except Exception:
                continue
        return {}

    def _extract_patient_info(self, p: dict) -> dict[str, Any]:
        return {
            "bed": _safe_text(p.get("bed") or p.get("bedNo")),
            "name": _safe_text(p.get("name") or p.get("hisName")),
            "sex": self._normalize_sex(p.get("sex") or p.get("hisSex")),
            "age": self._calc_age(p),
            "admission_no": _safe_text(p.get("hisPid") or p.get("inpatientNo")),
            "medical_group": _safe_text(p.get("medicalGroup") or p.get("dept")),
            "special_tags": self._extract_special_tags(p),
        }

    def _normalize_sex(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        if text in {"male", "m", "man", "1"} or text == "男":
            return "男"
        if text in {"female", "f", "woman", "2"} or text == "女":
            return "女"
        return _safe_text(value) or "未知"

    def _calc_age(self, p: dict) -> str:
        raw = p.get("age") or p.get("hisAge")
        try:
            return f"{int(float(str(raw).replace('岁', '').strip()))}岁"
        except (TypeError, ValueError):
            pass
        birth = _parse_datetime(p.get("birthDate") or p.get("birthday"))
        if birth:
            now = datetime.now()
            years = now.year - birth.year
            if (now.month, now.day) < (birth.month, birth.day):
                years -= 1
            return f"{max(years, 0)}岁"
        return ""

    def _extract_special_tags(self, p: dict) -> list[str]:
        tags = []
        for field in ("specialInfo", "specialTags", "tags"):
            val = p.get(field)
            if isinstance(val, list):
                tags.extend([_safe_text(v) for v in val if v])
            elif isinstance(val, str) and val.strip():
                tags.append(val.strip())
        return tags

    # ── situation ──────────────────────────────────────────────────

    async def _build_situation(self, p: dict, bedside_pids: list[str], start: datetime, end: datetime) -> dict[str, Any]:
        admit_date = _parse_datetime(p.get("admitTime") or p.get("icuAdmitTime") or p.get("icu_date"))
        icu_days = ""
        if admit_date:
            delta = (end - admit_date).days
            icu_days = f"第{max(delta, 0)}天"

        surgery_info = await self._get_latest_surgery(p, bedside_pids)

        return {
            "diagnosis": _safe_text(p.get("diagnosis") or p.get("diagnose") or p.get("hisDiagnosis")),
            "surgery": surgery_info.get("name", ""),
            "post_op_day": surgery_info.get("pod", ""),
            "icu_day": icu_days,
            "main_problems": "",  # AI fills in
            "life_support_level": "",
            "life_support_changes": "",
        }

    async def _get_latest_surgery(self, p: dict, bedside_pids: list[str]) -> dict[str, str]:
        pid_candidates = [safe_oid(p.get("_id")), *bedside_pids]
        try:
            doc = await self.db.col("surgery").find_one(
                {"pid": {"$in": pid_candidates}},
                sort=[("surgeryDate", -1), ("opDate", -1), ("date", -1)],
            )
            if doc:
                name = _safe_text(doc.get("surgeryName") or doc.get("name") or doc.get("procedure"))
                op_date = _parse_datetime(doc.get("surgeryDate") or doc.get("opDate") or doc.get("date"))
                pod = ""
                if op_date:
                    days = (datetime.now() - op_date).days
                    pod = f"术后第{max(days, 0)}天"
                return {"name": name, "pod": pod}
        except Exception:
            pass
        return {}

    # ── background ─────────────────────────────────────────────────

    def _extract_background(self, p: dict) -> dict[str, Any]:
        return {
            "admission_course": _safe_text(p.get("admissionCourse") or p.get("history") or p.get("hisSummary")),
            "past_history": _safe_text(p.get("pastHistory") or p.get("hisPastHistory")),
            "isolation": _safe_text(p.get("isolation") or p.get("isolationType")),
            "allergies": _safe_text(p.get("allergies") or p.get("drugAllergy")),
        }

    # ── vitals ─────────────────────────────────────────────────────

    async def _build_vitals(self, bedside_pids: list[str], start: datetime, end: datetime) -> list[dict[str, Any]]:
        vital_codes = {
            "HR": ["param_HR", "param_PR", "HR", "心率"],
            "SpO2": ["param_spo2", "SpO2", "血氧"],
            "RR": ["param_resp", "RR", "呼吸"],
            "T": ["param_T", "T", "体温"],
            "SBP": ["param_ibp_s", "param_nibp_s", "nibp_s", "无创收缩压"],
            "DBP": ["param_ibp_d", "param_nibp_d", "nibp_d", "无创舒张压"],
            "MAP": ["param_ibp_m", "param_nibp_m", "nibp_m", "平均动脉压"],
            "CVP": ["param_cvp", "CVP", "中心静脉压"],
        }
        results: list[dict[str, Any]] = []
        try:
            for label, codes in vital_codes.items():
                rows = (
                    await self.db.col("deviceCap")
                    .find({"deviceID": {"$in": bedside_pids}, "code": {"$in": codes}, "time": {"$gte": start, "$lte": end}})
                    .sort("time", 1)
                    .to_list(length=500)
                )
                source_collection = "deviceCap"
                if not rows:
                    rows = (
                        await self.db.col("bedside")
                        .find({"pid": {"$in": bedside_pids}, "code": {"$in": codes}, "time": {"$gte": start, "$lte": end}})
                        .sort("time", 1)
                        .to_list(length=500)
                    )
                    source_collection = "bedside"
                values = [_safe_float(_row_value(r)) for r in rows if _row_value(r) is not None]
                if values:
                    last_row = rows[-1]
                    results.append({
                        "label": label,
                        "min": min(values),
                        "max": max(values),
                        "latest": values[-1],
                        "latest_time": _safe_text(last_row.get("time")),
                        "unit": _safe_text(last_row.get("unit")),
                        "source": source_collection,
                        "count": len(values),
                    })
        except Exception as exc:
            logger.warning("handover context: vitals query failed: %s", exc)
        return results

    # ── labs ────────────────────────────────────────────────────────

    async def _build_labs(self, p_ids: list[str], start: datetime, end: datetime) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        try:
            rows = (
                await self.db.dc_col("VI_ICU_EXAM_ITEM")
                .find({"hisPid": {"$in": p_ids}, "$or": [{"authTime": {"$gte": start, "$lte": end}}, {"reportTime": {"$gte": start, "$lte": end}}]})
                .sort("authTime", -1)
                .to_list(length=200)
            )
            # Keep latest per item name
            seen: set[str] = set()
            for r in rows:
                name = _safe_text(r.get("itemCnName") or r.get("itemName"))
                if not name or name in seen:
                    continue
                seen.add(name)
                val = _safe_text(r.get("result") or r.get("fResult"))
                ref = _safe_text(r.get("refRange") or r.get("range"))
                unit = _safe_text(r.get("unit"))
                flag = ""
                if val and ref:
                    try:
                        f_val = float(val)
                        ref_parts = ref.replace(" ", "").split("-")
                        if len(ref_parts) == 2:
                            lo, hi = float(ref_parts[0]), float(ref_parts[1])
                            if f_val < lo:
                                flag = "↓"
                            elif f_val > hi:
                                flag = "↑"
                    except Exception:
                        pass
                results.append({"name": name, "value": val, "ref": ref, "unit": unit, "flag": flag})
        except Exception as exc:
            logger.warning("handover context: labs query failed: %s", exc)
        return results

    # ── IO / fluid balance ─────────────────────────────────────────

    async def _build_io(self, bedside_pids: list[str], start: datetime, end: datetime) -> dict[str, Any]:
        io_codes = {
            "intake": ["intake", "入量", "总入量", "液体入量"],
            "output": ["output", "出量", "总出量"],
            "urine": ["urine", "尿量", "urineOutput"],
        }
        result: dict[str, Any] = {}
        try:
            for key, codes in io_codes.items():
                rows = (
                    await self.db.col("bedside")
                    .find({"pid": {"$in": bedside_pids}, "code": {"$in": codes}, "time": {"$gte": start, "$lte": end}})
                    .sort("time", 1)
                    .to_list(length=200)
                )
                values = [_safe_float(_row_value(r)) for r in rows if _row_value(r) is not None]
                if values:
                    result[key] = round(sum(values), 1)
            if result:
                net = result.get("intake", 0) - result.get("output", 0)
                result["net_balance"] = round(net, 1)
        except Exception as exc:
            logger.warning("handover context: IO query failed: %s", exc)
        return result

    # ── pumps / infusions ──────────────────────────────────────────

    async def _build_pumps(self, bedside_pids: list[str], start: datetime, end: datetime) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        try:
            rows = (
                await self.db.col("medication_given")
                .find({"patient_id": {"$in": bedside_pids}, "record_time": {"$gte": start, "$lte": end}})
                .sort("record_time", -1)
                .to_list(length=200)
            )
            source_collection = "medication_given"
            if not rows:
                rows = (
                    await self.db.col("infusion")
                    .find({"pid": {"$in": bedside_pids}, "time": {"$gte": start, "$lte": end}})
                    .sort("time", -1)
                    .to_list(length=200)
                )
                source_collection = "infusion"
            seen: set[str] = set()
            for r in rows:
                name = _safe_text(r.get("drug_name") or r.get("name") or r.get("medication"))
                if not name or name in seen:
                    continue
                seen.add(name)
                dose = _safe_text(r.get("dose") or r.get("dosage"))
                rate = _safe_text(r.get("rate") or r.get("infusion_rate") or r.get("speed"))
                results.append({
                    "name": name,
                    "dose": dose,
                    "dose_unit": _safe_text(r.get("dose_unit")),
                    "rate": rate,
                    "rate_unit": _safe_text(r.get("rate_unit") or r.get("unit")),
                    "route": _safe_text(r.get("route")),
                    "record_time": _safe_text(r.get("record_time") or r.get("time")),
                    "source": source_collection,
                })
        except Exception as exc:
            logger.warning("handover context: pumps query failed: %s", exc)
        return results

    # ── airway / vent ──────────────────────────────────────────────

    async def _build_airway_vent(self, bedside_pids: list[str], start: datetime, end: datetime) -> dict[str, Any]:
        result: dict[str, Any] = {}
        try:
            vent = (
                await self.db.col("ventilator")
                .find_one({"pid": {"$in": bedside_pids}}, sort=[("time", -1)])
            )
            if not vent:
                vent = await self.db.col("respiratory").find_one(
                    {"patient_id": {"$in": bedside_pids}}, sort=[("time", -1)]
                )
            if vent:
                result = {
                    "mode": _safe_text(vent.get("mode") or vent.get("ventMode")),
                    "fio2": _safe_text(vent.get("fio2") or vent.get("FiO2")),
                    "peep": _safe_text(vent.get("peep") or vent.get("PEEP")),
                    "vt": _safe_text(vent.get("vt") or vent.get("VT")),
                    "rr_set": _safe_text(vent.get("rr_set") or vent.get("RR")),
                    "airway_type": _safe_text(vent.get("airwayType") or vent.get("airway")),
                }
        except Exception as exc:
            logger.warning("handover context: airway/vent query failed: %s", exc)
        return result

    # ── lines / tubes ──────────────────────────────────────────────

    async def _build_lines(self, bedside_pids: list[str], start: datetime, end: datetime) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        try:
            rows = await self.db.col("tubeExe").find(
                {"pid": {"$in": bedside_pids}, "$or": [
                    {"endTime": {"$exists": False}},
                    {"endTime": None},
                    {"endTime": ""},
                    {"stopTime": {"$exists": False}},
                    {"stopTime": None},
                    {"stopTime": ""},
                ]}
            ).to_list(length=100)
            if not rows:
                # fallback: bedside tubes
                rows = await self.db.col("bedside").find(
                    {"pid": {"$in": bedside_pids}, "tubeName": {"$exists": True}}
                ).to_list(length=100)
            for r in (rows or []):
                results.append({
                    "type": _safe_text(r.get("name") or r.get("type") or r.get("tubeName")),
                    "position": _safe_text(r.get("position") or r.get("site")),
                    "depth": _safe_text(r.get("depth") or r.get("insertDepth")),
                    "placed_at": _safe_text(r.get("insertTime") or r.get("startTime") or r.get("time")),
                    "patency": _safe_text(r.get("patency") or r.get("status")),
                })
        except Exception as exc:
            logger.warning("handover context: lines query failed: %s", exc)
        return results

    # ── assessments / scores ───────────────────────────────────────

    async def _build_assessments(self, bedside_pids: list[str], p_ids: list[str], start: datetime, end: datetime) -> dict[str, Any]:
        result: dict[str, Any] = {"neuro": "", "resp": "", "circ": "", "temp": "", "gi": "", "heme": "", "specialty": "", "nursing": "", "skin": "", "items": ""}
        try:
            # RASS / CAM-ICU / GCS
            for code, key in [("RASS", "neuro"), ("CAM-ICU", "neuro"), ("GCS", "neuro")]:
                doc = await self.db.col("score").find_one({"patient_id": {"$in": bedside_pids}, "code": code}, sort=[("time", -1)])
                if doc:
                    existing = result.get(key, "")
                    val = _row_value(doc)
                    if val is not None:
                        result[key] = f"{existing} {code}:{val}".strip()

            # Braden (skin)
            braden = await self.db.col("score").find_one({"patient_id": {"$in": bedside_pids}, "code": "Braden"}, sort=[("time", -1)])
            if braden:
                result["skin"] = f"Braden评分:{_row_value(braden)}"

            # SOFA
            sofa = await self.db.col("score").find_one({"patient_id": {"$in": bedside_pids}, "code": "SOFA"}, sort=[("time", -1)])
            if sofa:
                sofa_val = _row_value(sofa)
                if sofa_val is not None:
                    result["specialty"] = f"SOFA:{sofa_val}"
        except Exception as exc:
            logger.warning("handover context: assessments query failed: %s", exc)
        return result

    # ── events ─────────────────────────────────────────────────────

    async def _build_events(self, p_oid: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        try:
            rows = (
                await self.db.col("nursing_record")
                .find({"patient_id": p_oid, "record_time": {"$gte": start, "$lte": end}})
                .sort("record_time", -1)
                .to_list(length=50)
            )
            for r in (rows or []):
                results.append({
                    "time": _safe_text(r.get("record_time") or r.get("time")),
                    "event": _safe_text(r.get("content") or r.get("event") or r.get("note")),
                })
        except Exception as exc:
            logger.warning("handover context: events query failed: %s", exc)
        return results

    # ── pending orders ─────────────────────────────────────────────

    async def _build_pending_orders(self, p_oid: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        try:
            rows = (
                await self.db.col("orders")
                .find({"patient_id": p_oid, "status": {"$in": ["pending", "ordered", "active"]}})
                .sort("order_time", -1)
                .to_list(length=50)
            )
            for r in (rows or []):
                results.append({
                    "order": _safe_text(r.get("name") or r.get("content") or r.get("orderText")),
                    "status": _safe_text(r.get("status")),
                    "time": _safe_text(r.get("order_time") or r.get("time")),
                })
        except Exception as exc:
            logger.warning("handover context: pending orders query failed: %s", exc)
        return results

    # ── alerts ─────────────────────────────────────────────────────

    async def _build_alerts(self, p_oid: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        try:
            rows = (
                await self.db.col("alert_records")
                .find({
                    "patient_id": p_oid,
                    "created_at": {"$gte": start, "$lte": end},
                    "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
                })
                .sort("created_at", -1)
                .to_list(length=100)
            )
            for r in (rows or []):
                results.append({
                    "type": _safe_text(r.get("alert_type") or r.get("type")),
                    "value": _safe_text(r.get("value") or r.get("alert_value")),
                    "time": _safe_text(r.get("created_at") or r.get("time")),
                    "closed": bool(r.get("acknowledged_at") or r.get("ack_disposition")),
                    "priority": _safe_text(r.get("priority") or r.get("severity")),
                })
        except Exception as exc:
            logger.warning("handover context: alerts query failed: %s", exc)
        return results
