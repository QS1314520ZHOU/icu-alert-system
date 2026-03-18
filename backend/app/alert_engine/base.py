"""
ICU智能预警系统 - 预警引擎基础工具
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np
from app.alert_engine.acid_base_analyzer import extract_bga_temp_items
from app.services.llm_runtime import call_llm_chat
from app.services.temporal_model_runtime import TemporalRiskModelRuntime
from app.utils.bed_matching import _bed_match, _normalize_bed
from app.utils.clinical import _cap_time, _cap_value, _detect_trend, _eval_condition, _extract_param
from app.utils.labs import _convert_lab_value, _lab_time, _match_lab_test
from app.utils.parse import API_TZ, _parse_dt, _parse_number, _safe_oid, _to_output_iso

logger = logging.getLogger("icu-alert")

class BaseEngine:
    def __init__(self, db, config, ws_manager=None) -> None:
        self.db = db
        self.config = config
        self.ws = ws_manager
        self._param_codes_all = self._collect_param_codes()
        self._temporal_model_runtime: TemporalRiskModelRuntime | None = None
        self._baseline_cache: dict[tuple[str, str, int], dict[str, Any] | None] = {}

    def _log_info(self, name: str, count: int) -> None:
        logger.info(f"[{name}] 本轮触发 {count} 条预警")

    def _cfg(self, *path, default=None):
        cfg = self.config.yaml_cfg
        for p in path:
            if not isinstance(cfg, dict) or p not in cfg:
                return default
            cfg = cfg[p]
        return cfg

    def _get_cfg_list(self, path: tuple[str, ...], default: list[str]) -> list[str]:
        v = self._cfg(*path, default=None)
        if isinstance(v, list):
            return v
        if isinstance(v, str) and v:
            return [v]
        return default

    def _get_temporal_model_runtime(self) -> TemporalRiskModelRuntime:
        if self._temporal_model_runtime is None:
            self._temporal_model_runtime = TemporalRiskModelRuntime(self.config)
        return self._temporal_model_runtime

    def _patient_icu_start_time(self, patient_doc: dict | None) -> datetime | None:
        if not isinstance(patient_doc, dict):
            return None
        for key in ("icuAdmissionTime", "admissionTime", "admitTime", "inTime", "createTime"):
            dt = _parse_dt(patient_doc.get(key))
            if dt:
                return dt
        return None

    async def _get_patient_baseline(
        self,
        pid,
        parameter: str,
        hours: int = 12,
        patient_doc: dict | None = None,
        prefer_device_types: list[str] | None = None,
    ) -> dict[str, Any] | None:
        pid_str = self._pid_str(pid)
        param_key = str(parameter or "").strip()
        if not pid_str or not param_key:
            return None

        cache_key = (pid_str, param_key, int(hours))
        if cache_key in self._baseline_cache:
            return self._baseline_cache[cache_key]

        if patient_doc is None:
            patient_doc, _ = await self._load_patient(pid)
        baseline_start = self._patient_icu_start_time(patient_doc)
        series: list[dict] = []
        source = "vital"

        if baseline_start:
            baseline_end = baseline_start + timedelta(hours=max(1, int(hours)))
        else:
            since = datetime.now() - timedelta(hours=max(24, int(hours) * 2))
            if param_key.startswith("param_"):
                fallback_series = await self._get_param_series_by_pid(
                    pid,
                    param_key,
                    since,
                    prefer_device_types=prefer_device_types or ["monitor"],
                    limit=4000,
                )
                if fallback_series:
                    baseline_start = fallback_series[0]["time"]
                    baseline_end = baseline_start + timedelta(hours=max(1, int(hours)))
                else:
                    baseline_end = None
            else:
                baseline_end = None

        if param_key.startswith("param_") and baseline_start and baseline_end:
            series = await self._get_param_series_by_pid(
                pid,
                param_key,
                baseline_start,
                prefer_device_types=prefer_device_types or ["monitor"],
                limit=4000,
            )
            series = [s for s in series if baseline_start <= s.get("time", baseline_start) <= baseline_end]
        elif patient_doc and patient_doc.get("hisPid") and baseline_start and baseline_end:
            source = "lab"
            series = await self._get_lab_series(patient_doc.get("hisPid"), param_key, baseline_start, baseline_end, limit=400)

        values = [float(s["value"]) for s in series if _parse_number(s.get("value")) is not None]
        if not values:
            self._baseline_cache[cache_key] = None
            return None

        mean = sum(values) / len(values)
        variance = sum((v - mean) ** 2 for v in values) / max(len(values), 1)
        std = math.sqrt(max(variance, 0.0))
        result = {
            "parameter": param_key,
            "mean": round(mean, 4),
            "std": round(std, 4),
            "min": round(min(values), 4),
            "max": round(max(values), 4),
            "count": len(values),
            "start": series[0]["time"] if series else baseline_start,
            "end": series[-1]["time"] if series else baseline_end,
            "source": source,
        }
        self._baseline_cache[cache_key] = result
        return result

    def _infer_device_type(self, name: str | None) -> str | None:
        if not name:
            return None
        n = str(name)
        if any(k in n for k in ["呼吸机", "vent", "Vent"]):
            return "vent"
        if any(k in n for k in ["监护", "中央站", "monitor", "Monitor", "监视"]):
            return "monitor"
        if any(k in n for k in ["CRRT", "血滤", "血液净化"]):
            return "crrt"
        return None

    def _device_type_match(self, name: str | None, prefer_types: list[str] | None) -> bool:
        if not prefer_types:
            return True
        inferred = self._infer_device_type(name)
        if inferred is None:
            return True
        return inferred in prefer_types

    def _pid_str(self, pid) -> str:
        return str(pid) if pid is not None else ""

    def _active_patient_query(self) -> dict:
        # SmartCare.patient 使用 status 字段，无 isLeave
        return {
            "$or": [
                {"status": {"$nin": ["discharged", "invalid", "invaild"]}},
                {"status": {"$exists": False}},
            ]
        }

    def _collect_param_codes(self) -> list[str]:
        codes: set[str] = set()
        for section in ("vital_signs", "ventilator", "assessments"):
            sec = self.config.yaml_cfg.get(section, {})
            if isinstance(sec, dict):
                for v in sec.values():
                    if isinstance(v, dict):
                        code = v.get("code")
                        if code:
                            codes.add(code)

        vs = self.config.yaml_cfg.get("vital_signs", {})
        for key in ("map_priority", "sbp_priority", "dbp_priority"):
            if isinstance(vs, dict):
                for code in vs.get(key, []) or []:
                    if code:
                        codes.add(code)

        data_mapping = self.config.yaml_cfg.get("alert_engine", {}).get("data_mapping", {})
        if isinstance(data_mapping, dict):
            for v in data_mapping.values():
                if isinstance(v, dict):
                    for code in v.get("codes", []) or []:
                        if code:
                            codes.add(code)

        return sorted(codes)

    async def _get_device_id(self, pid, prefer_types: list[str] | None = None) -> str | None:
        pid_str = self._pid_str(pid)
        if not pid_str:
            return None
        query = {"pid": pid_str, "unBindTime": None}
        if prefer_types:
            query["type"] = {"$in": prefer_types}
        doc = await self.db.col("deviceBind").find_one(query, sort=[("bindTime", -1)])
        if doc:
            return doc.get("deviceID")
        if prefer_types:
            # fallback: 任意类型的当前绑定
            doc = await self.db.col("deviceBind").find_one({"pid": pid_str, "unBindTime": None}, sort=[("bindTime", -1)])
            if doc:
                return doc.get("deviceID")
        # fallback: 使用床号 + deviceOnline / deviceInfo 映射
        patient = await self.db.col("patient").find_one(
            {"_id": _safe_oid(pid) or pid},
            {"hisBed": 1, "bed": 1, "deptCode": 1},
        )
        if patient:
            bed = patient.get("hisBed") or patient.get("bed")
            dept_code = patient.get("deptCode")
            return await self._get_device_id_by_bed(bed, dept_code, prefer_types)
        return None

    async def _get_device_id_for_patient(self, patient_doc: dict, prefer_types: list[str] | None = None) -> str | None:
        if not patient_doc:
            return None
        pid = patient_doc.get("_id") or patient_doc.get("pid")
        pid_str = self._pid_str(pid)
        if pid_str:
            query = {"pid": pid_str, "unBindTime": None}
            if prefer_types:
                query["type"] = {"$in": prefer_types}
            doc = await self.db.col("deviceBind").find_one(query, sort=[("bindTime", -1)])
            if doc:
                return doc.get("deviceID")
            if prefer_types:
                doc = await self.db.col("deviceBind").find_one({"pid": pid_str, "unBindTime": None}, sort=[("bindTime", -1)])
                if doc:
                    return doc.get("deviceID")

        bed = patient_doc.get("hisBed") or patient_doc.get("bed")
        dept_code = patient_doc.get("deptCode")
        return await self._get_device_id_by_bed(bed, dept_code, prefer_types)

    async def _get_device_id_by_bed(
        self,
        bed: Any,
        dept_code: str | None = None,
        prefer_types: list[str] | None = None,
    ) -> str | None:
        norm_bed = _normalize_bed(bed)
        if not norm_bed:
            return None

        query = {"isConnected": True}
        if dept_code:
            query["deptCode"] = dept_code
        cursor = self.db.col("deviceOnline").find(query, {"deviceID": 1, "curBed": 1, "lastBed": 1})
        candidates: list[str] = []
        async for doc in cursor:
            if _bed_match(norm_bed, doc.get("curBed")) or _bed_match(norm_bed, doc.get("lastBed")):
                device_id = doc.get("deviceID")
                if device_id:
                    candidates.append(device_id)

        if candidates:
            if not prefer_types:
                return candidates[0]
            for device_id in candidates:
                info = await self.db.col("deviceInfo").find_one(
                    {"_id": _safe_oid(device_id) or device_id},
                    {"deviceName": 1},
                )
                if self._device_type_match(info.get("deviceName") if info else None, prefer_types):
                    return device_id
            return candidates[0]

        query = {"defaultBed": {"$ne": ""}}
        if dept_code:
            query["deptCode"] = dept_code
        cursor = self.db.col("deviceInfo").find(query, {"_id": 1, "defaultBed": 1, "deviceName": 1})
        async for doc in cursor:
            if _bed_match(norm_bed, doc.get("defaultBed")):
                if self._device_type_match(doc.get("deviceName"), prefer_types):
                    return str(doc.get("_id"))
        return None

    def _vent_code(self, name: str, default: str | None = None) -> str | None:
        return self._cfg("ventilator", name, "code", default=default)

    def _vent_param(self, cap: dict, name: str, default: str | None = None) -> float | None:
        code = self._vent_code(name, default)
        if not code:
            return None
        return _extract_param(cap, code)

    def _vent_param_priority(self, cap: dict, names: list[str], defaults: list[str]) -> float | None:
        for i, name in enumerate(names):
            code = self._vent_code(name, defaults[i] if i < len(defaults) else None)
            if not code:
                continue
            v = _extract_param(cap, code)
            if v is not None:
                return v
        return None

    def _get_map(self, cap: dict) -> float | None:
        keys = self._cfg("vital_signs", "map_priority", default=["param_ibp_m", "param_nibp_m"])
        return self._get_priority_param(cap, keys)

    def _get_sbp(self, cap: dict) -> float | None:
        keys = self._cfg("vital_signs", "sbp_priority", default=["param_ibp_s", "param_nibp_s"])
        return self._get_priority_param(cap, keys)

    async def _get_latest_param_snapshot_by_device(
        self,
        device_id: str,
        codes: list[str] | None = None,
        lookback_minutes: int = 60,
        limit: int = 2000,
    ) -> dict | None:
        if not device_id:
            return None
        codes = codes or self._param_codes_all
        if not codes:
            return None
        since = datetime.now() - timedelta(minutes=lookback_minutes)
        query = {"deviceID": device_id, "code": {"$in": codes}, "time": {"$gte": since}}
        cursor = self.db.col("deviceCap").find(query).sort("time", -1).limit(limit)
        params: dict = {}
        latest_time = None
        async for doc in cursor:
            code = doc.get("code")
            if not code or code in params:
                continue
            v = _cap_value(doc)
            if v is None:
                continue
            params[code] = v
            t = _cap_time(doc)
            if t and (latest_time is None or t > latest_time):
                latest_time = t
            if len(params) >= len(codes):
                break
        if not params and lookback_minutes:
            # fallback: 不限制时间窗口
            query = {"deviceID": device_id, "code": {"$in": codes}}
            cursor = self.db.col("deviceCap").find(query).sort("time", -1).limit(limit)
            async for doc in cursor:
                code = doc.get("code")
                if not code or code in params:
                    continue
                v = _cap_value(doc)
                if v is None:
                    continue
                params[code] = v
                t = _cap_time(doc)
                if t and (latest_time is None or t > latest_time):
                    latest_time = t
                if len(params) >= len(codes):
                    break
        if not params:
            return None
        return {"params": params, "time": latest_time}

    async def _get_latest_param_snapshot_by_pid(
        self,
        pid,
        codes: list[str] | None = None,
        lookback_minutes: int = 60,
        limit: int = 2000,
    ) -> dict | None:
        pid_str = self._pid_str(pid)
        if not pid_str:
            return None
        codes = codes or self._param_codes_all
        if not codes:
            return None
        since = datetime.now() - timedelta(minutes=lookback_minutes)
        query = {"pid": pid_str, "code": {"$in": codes}, "time": {"$gte": since}}
        cursor = self.db.col("bedside").find(query).sort("time", -1).limit(limit)
        params: dict = {}
        latest_time = None
        async for doc in cursor:
            code = doc.get("code")
            if not code or code in params:
                continue
            v = _cap_value(doc)
            if v is None:
                continue
            params[code] = v
            t = _cap_time(doc)
            if t and (latest_time is None or t > latest_time):
                latest_time = t
            if len(params) >= len(codes):
                break
        if not params and lookback_minutes:
            query = {"pid": pid_str, "code": {"$in": codes}}
            cursor = self.db.col("bedside").find(query).sort("time", -1).limit(limit)
            async for doc in cursor:
                code = doc.get("code")
                if not code or code in params:
                    continue
                v = _cap_value(doc)
                if v is None:
                    continue
                params[code] = v
                t = _cap_time(doc)
                if t and (latest_time is None or t > latest_time):
                    latest_time = t
                if len(params) >= len(codes):
                    break
        if not params:
            return None
        return {"params": params, "time": latest_time}

    async def _get_latest_device_cap(self, device_id: str, codes: list[str] | None = None) -> dict | None:
        return await self._get_latest_param_snapshot_by_device(device_id, codes=codes)

    async def _get_param_series_by_pid(
        self,
        pid,
        code: str,
        since: datetime,
        prefer_device_types: list[str] | None = None,
        limit: int = 2000,
    ) -> list[dict]:
        pid_str = self._pid_str(pid)
        points: list[dict] = []
        if pid_str:
            cursor = self.db.col("bedside").find(
                {"pid": pid_str, "code": code, "time": {"$gte": since}},
                {"time": 1, "strVal": 1, "intVal": 1, "fVal": 1},
            ).sort("time", 1).limit(limit)
            async for doc in cursor:
                v = _cap_value(doc)
                if v is None:
                    continue
                t = _cap_time(doc)
                if t:
                    points.append({"time": t, "value": v})
        if points:
            return points

        device_id = await self._get_device_id(pid, prefer_device_types)
        if not device_id:
            return []
        cursor = self.db.col("deviceCap").find(
            {"deviceID": device_id, "code": code, "time": {"$gte": since}},
            {"time": 1, "strVal": 1, "intVal": 1, "fVal": 1},
        ).sort("time", 1).limit(limit)
        async for doc in cursor:
            v = _cap_value(doc)
            if v is None:
                continue
            t = _cap_time(doc)
            if t:
                points.append({"time": t, "value": v})
        return points

    def _get_priority_param(self, cap: dict, keys: list[str]) -> float | None:
        for k in keys:
            v = _extract_param(cap, k)
            if v is not None:
                return v
        return None

    async def _get_latest_vitals_by_patient(self, pid) -> dict:
        codes = [
            "param_HR",
            "param_resp",
            "param_ibp_m",
            "param_nibp_m",
            "param_ibp_s",
            "param_nibp_s",
        ]
        cap = await self._get_latest_param_snapshot_by_pid(pid, codes=codes)
        if not cap:
            device_id = await self._get_device_id(pid, ["monitor"])
            cap = await self._get_latest_device_cap(device_id, codes=codes) if device_id else None
        if not cap:
            return {}
        return {
            "hr": _extract_param(cap, "param_HR"),
            "rr": _extract_param(cap, "param_resp"),
            "sbp": self._get_sbp(cap),
            "map": self._get_map(cap),
            "time": cap.get("time"),
        }

    async def _get_latest_assessment(self, pid, kind: str) -> float | None:
        code = self._cfg("assessments", kind, "code", default=None)
        if not code:
            return None

        doc = await self.db.col("score_records").find_one(
            {"patient_id": pid, "score_type": kind},
            sort=[("calc_time", -1)]
        )
        if doc:
            val = doc.get("score") or doc.get("value") or doc.get("score_value")
            num = _parse_number(val)
            if num is not None:
                return num
        pid_str = self._pid_str(pid)
        score_types = {
            "gcs": ["gcsScore"],
            "rass": ["rass"],
            "pain": ["painScore", "cpotScore", "cpotScoreV2"],
            "cpot": ["cpotScore", "cpotScoreV2", "cpot", "CPOT"],
            "bps": ["bpsScore", "bps", "BPS"],
            "delirium": ["deliriumScore"],
            "braden": ["bradenScore", "bradenNurseScore"],
        }.get(kind, [])
        if score_types and pid_str:
            sdoc = await self.db.col("score").find_one(
                {"pid": pid_str, "scoreType": {"$in": score_types}},
                sort=[("time", -1)],
            )
            if sdoc:
                num = _parse_number(sdoc.get("total") or sdoc.get("score"))
                if num is not None:
                    return num

        # fallback: 从 bedside 单参数记录获取
        series = await self._get_param_series_by_pid(pid, code, datetime.now() - timedelta(hours=24))
        if series:
            return series[-1]["value"]
        return None

    async def _get_assessment_series(self, pid, kind: str, hours: int) -> list[dict]:
        code = self._cfg("assessments", kind, "code", default=None)
        if not code:
            return []
        since = datetime.now() - timedelta(hours=hours)
        pid_str = self._pid_str(pid)
        score_types = {
            "gcs": ["gcsScore"],
            "rass": ["rass"],
            "pain": ["painScore", "cpotScore", "cpotScoreV2"],
            "cpot": ["cpotScore", "cpotScoreV2", "cpot", "CPOT"],
            "bps": ["bpsScore", "bps", "BPS"],
            "delirium": ["deliriumScore"],
            "braden": ["bradenScore", "bradenNurseScore"],
        }.get(kind, [])
        points: list[dict] = []
        if score_types and pid_str:
            cursor = self.db.col("score").find(
                {"pid": pid_str, "scoreType": {"$in": score_types}, "time": {"$gte": since}},
                {"time": 1, "total": 1, "score": 1},
            ).sort("time", 1)
            async for doc in cursor:
                num = _parse_number(doc.get("total") or doc.get("score"))
                if num is not None:
                    points.append({"time": doc.get("time"), "value": num})
        if points:
            return points
        return await self._get_param_series_by_pid(pid, code, since)

    async def _get_assessment_value_in_window(self, pid, kind: str, start: datetime, end: datetime) -> float | None:
        code = self._cfg("assessments", kind, "code", default=None)
        if not code:
            return None

        doc = await self.db.col("score_records").find_one(
            {"patient_id": pid, "score_type": kind, "calc_time": {"$gte": start, "$lte": end}},
            sort=[("calc_time", -1)]
        )
        if doc:
            val = doc.get("score") or doc.get("value") or doc.get("score_value")
            num = _parse_number(val)
            if num is not None:
                return num
        pid_str = self._pid_str(pid)
        score_types = {
            "gcs": ["gcsScore"],
            "rass": ["rass"],
            "pain": ["painScore", "cpotScore", "cpotScoreV2"],
            "cpot": ["cpotScore", "cpotScoreV2", "cpot", "CPOT"],
            "bps": ["bpsScore", "bps", "BPS"],
            "delirium": ["deliriumScore"],
            "braden": ["bradenScore", "bradenNurseScore"],
        }.get(kind, [])
        if score_types and pid_str:
            sdoc = await self.db.col("score").find_one(
                {"pid": pid_str, "scoreType": {"$in": score_types}, "time": {"$gte": start, "$lte": end}},
                sort=[("time", -1)],
            )
            if sdoc:
                num = _parse_number(sdoc.get("total") or sdoc.get("score"))
                if num is not None:
                    return num

        series = await self._get_param_series_by_pid(pid, code, start)
        for doc in reversed(series):
            if doc["time"] <= end:
                return doc["value"]
        return None

    def _is_positive_text_result(self, value: Any) -> bool | None:
        if value is None:
            return None
        num = _parse_number(value)
        if num is not None:
            return num > 0
        text = str(value).strip().lower()
        if not text:
            return None
        positive_keywords = ["阳性", "positive", "pos", "yes", "是", "谵妄", "存在", "异常"]
        negative_keywords = ["阴性", "negative", "neg", "no", "否", "未见", "正常", "无"]
        if any(k in text for k in negative_keywords):
            return False
        if any(k in text for k in positive_keywords):
            return True
        return None

    async def _get_latest_cam_icu_status(self, pid, lookback_hours: int = 48) -> dict | None:
        pid_str = self._pid_str(pid)
        if not pid_str:
            return None
        since = datetime.now() - timedelta(hours=lookback_hours)
        code = self._cfg("assessments", "cam_icu", "code", default="param_delirium_score")

        # 1) score_records
        doc = await self.db.col("score_records").find_one(
            {
                "patient_id": {"$in": [pid, pid_str]},
                "score_type": {"$in": ["cam_icu", "cam-icu", "delirium", "camicu"]},
                "calc_time": {"$gte": since},
            },
            sort=[("calc_time", -1)],
        )
        if doc:
            raw = doc.get("score") or doc.get("value") or doc.get("score_value") or doc.get("result")
            positive = self._is_positive_text_result(raw)
            if positive is not None:
                return {"positive": positive, "time": _parse_dt(doc.get("calc_time")), "source": "score_records", "raw": raw}

        # 2) score
        doc = await self.db.col("score").find_one(
            {
                "pid": pid_str,
                "scoreType": {"$in": ["cam_icu", "cam-icu", "camicu", "CAMICU", "deliriumScore"]},
                "time": {"$gte": since},
            },
            sort=[("time", -1)],
        )
        if doc:
            raw = doc.get("total") or doc.get("score") or doc.get("result")
            positive = self._is_positive_text_result(raw)
            if positive is not None:
                return {"positive": positive, "time": _parse_dt(doc.get("time")), "source": "score", "raw": raw}

        # 3) bedside: 先精确 code，再关键词兜底
        exact_doc = await self.db.col("bedside").find_one(
            {"pid": pid_str, "code": code, "time": {"$gte": since}},
            sort=[("time", -1)],
        )
        candidates = [exact_doc] if exact_doc else []
        if not candidates:
            cursor = self.db.col("bedside").find(
                {"pid": pid_str, "time": {"$gte": since}},
                {"time": 1, "code": 1, "strVal": 1, "value": 1},
            ).sort("time", -1).limit(300)
            async for row in cursor:
                text = " ".join(str(row.get(k) or "") for k in ("code", "strVal", "value")).lower()
                if any(k in text for k in ["cam-icu", "cam icu", "cam_icu", "谵妄"]):
                    candidates.append(row)
                    break
        for doc in candidates:
            raw = doc.get("strVal")
            if raw is None:
                raw = doc.get("value")
            positive = self._is_positive_text_result(raw)
            if positive is not None:
                return {"positive": positive, "time": _cap_time(doc), "source": "bedside", "raw": raw}
        return None

    async def _get_gcs_drop(self, pid) -> dict | None:
        series = await self._get_assessment_series(pid, "gcs", hours=24)
        if len(series) < 2:
            return None
        first = series[0]
        last = series[-1]
        drop = first["value"] - last["value"]
        if drop <= 0:
            return None
        return {
            "drop": drop,
            "baseline": first["value"],
            "current": last["value"],
            "time": last["time"],
        }

    async def _get_rass_status(self, pid) -> dict | None:
        series = await self._get_assessment_series(pid, "rass", hours=24)
        if not series:
            return None
        last = series[-1]
        over_sedation = False
        if last["value"] <= -3:
            earlier = [p for p in series if p["value"] <= -3]
            if len(earlier) >= 2 and earlier[-1]["time"] and earlier[0]["time"]:
                if (earlier[-1]["time"] - earlier[0]["time"]).total_seconds() >= 12 * 3600:
                    over_sedation = True
        return {"rass": last["value"], "time": last["time"], "over_sedation": over_sedation}

    async def _get_pupil_status(self, pid) -> dict | None:
        pid_str = self._pid_str(pid)
        if not pid_str:
            return None
        left_codes = ["param_左瞳孔/光反射", "左瞳孔", "pupil_left"]
        right_codes = ["param_右瞳孔/光反射", "右瞳孔", "pupil_right"]
        left_doc = await self.db.col("bedside").find_one(
            {"pid": pid_str, "code": {"$in": left_codes}},
            sort=[("time", -1)],
        )
        right_doc = await self.db.col("bedside").find_one(
            {"pid": pid_str, "code": {"$in": right_codes}},
            sort=[("time", -1)],
        )
        left = left_doc.get("strVal") if left_doc else None
        right = right_doc.get("strVal") if right_doc else None
        t = _cap_time(left_doc) if left_doc else _cap_time(right_doc) if right_doc else None
        abnormal = False
        text = f"{left} {right}"
        if "不等" in text or "散大" in text or "固定" in text or "迟钝" in text:
            abnormal = True
        if left and right and str(left) != str(right):
            abnormal = True
        return {"left": left, "right": right, "abnormal": abnormal, "time": t}

    async def _get_latest_labs_map(self, his_pid, lookback_hours: int = 72) -> dict:
        since = datetime.now() - timedelta(hours=lookback_hours)
        results: dict = {}
        bga_items = await self._get_bga_temp_items(his_pid, limit=80)
        for doc in bga_items:
            t = _lab_time(doc)
            if t and t < since:
                continue
            name = doc.get("itemCnName") or doc.get("itemName") or doc.get("item") or doc.get("itemCode")
            test_key = _match_lab_test(name)
            if not test_key or test_key in results:
                continue
            raw_val = doc.get("result") or doc.get("resultValue") or doc.get("value")
            num = _parse_number(raw_val)
            if num is None:
                continue
            unit = doc.get("unit") or doc.get("resultUnit") or ""
            value = _convert_lab_value(test_key, num, unit)
            results[test_key] = {
                "value": value,
                "time": t,
                "unit": unit,
                "raw_name": name,
                "raw_value": raw_val,
                "raw_flag": doc.get("resultFlag") or doc.get("flag") or doc.get("sourceTable") or "bGATemp",
            }

        cursor = self.db.dc_col("VI_ICU_EXAM_ITEM").find({"hisPid": his_pid}).sort("authTime", -1).limit(300)
        async for doc in cursor:
            t = _lab_time(doc)
            if t and t < since:
                continue
            name = doc.get("itemCnName") or doc.get("itemName") or doc.get("item") or doc.get("itemCode")
            test_key = _match_lab_test(name)
            if not test_key or test_key in results:
                continue
            raw_val = doc.get("result") or doc.get("resultValue") or doc.get("value")
            num = _parse_number(raw_val)
            if num is None:
                continue
            unit = doc.get("unit") or doc.get("resultUnit") or ""
            value = _convert_lab_value(test_key, num, unit)
            results[test_key] = {
                "value": value,
                "time": t,
                "unit": unit,
                "raw_name": name,
                "raw_value": raw_val,
                "raw_flag": doc.get("resultFlag")
                or doc.get("flag")
                or doc.get("abnormalFlag")
                or doc.get("seriousFlag")
                or doc.get("resultStatus"),
            }
        return results

    async def _get_lab_series(
        self,
        his_pid,
        test_key: str,
        since: datetime,
        end: datetime | None = None,
        limit: int = 200,
    ) -> list[dict]:
        series = []
        bga_items = await self._get_bga_temp_items(his_pid, limit=limit)
        for doc in bga_items:
            t = _lab_time(doc)
            if not t or t < since:
                continue
            if end and t > end:
                continue
            name = doc.get("itemCnName") or doc.get("itemName") or doc.get("item") or doc.get("itemCode")
            if _match_lab_test(name) != test_key:
                continue
            raw_val = doc.get("result") or doc.get("resultValue") or doc.get("value")
            num = _parse_number(raw_val)
            if num is None:
                continue
            unit = doc.get("unit") or doc.get("resultUnit") or ""
            value = _convert_lab_value(test_key, num, unit)
            series.append({"time": t, "value": value, "unit": unit})

        cursor = self.db.dc_col("VI_ICU_EXAM_ITEM").find({"hisPid": his_pid}).sort("authTime", -1).limit(limit)
        async for doc in cursor:
            t = _lab_time(doc)
            if not t or t < since:
                continue
            if end and t > end:
                continue
            name = doc.get("itemCnName") or doc.get("itemName") or doc.get("item") or doc.get("itemCode")
            if _match_lab_test(name) != test_key:
                continue
            raw_val = doc.get("result") or doc.get("resultValue") or doc.get("value")
            num = _parse_number(raw_val)
            if num is None:
                continue
            unit = doc.get("unit") or doc.get("resultUnit") or ""
            value = _convert_lab_value(test_key, num, unit)
            series.append({"time": t, "value": value, "unit": unit})
        series.sort(key=lambda x: x["time"])
        return series

    async def _get_bga_temp_items(self, his_pid: Any, limit: int = 80) -> list[dict]:
        pid_text = str(his_pid or "").strip()
        if not pid_text:
            return []
        query_values: list[Any] = [pid_text]
        maybe_oid = _safe_oid(pid_text)
        if maybe_oid is not None:
            query_values.append(maybe_oid)
        or_list: list[dict[str, Any]] = []
        for field in ("hisPid", "his_pid", "pid", "patientId", "patient_id"):
            for value in query_values:
                or_list.append({field: value})
        rows = [
            row async for row in self.db.col("bGATemp").find({"$or": or_list}).sort("inputTime", -1).limit(max(int(limit or 80), 20))
        ]
        items: list[dict] = []
        for row in rows:
            items.extend(extract_bga_temp_items(row))
        items.sort(key=lambda x: _lab_time(x) or datetime.min, reverse=True)
        return items

    def _calc_qsofa(self, sbp: float | None, rr: float | None, gcs: float | None) -> int:
        score = 0
        if sbp is not None and sbp <= 100:
            score += 1
        if rr is not None and rr >= 22:
            score += 1
        if gcs is not None and gcs < 15:
            score += 1
        return score

    async def _calc_sofa(self, patient_doc: dict, pid, device_id, his_pid) -> dict | None:
        labs = await self._get_latest_labs_map(his_pid, lookback_hours=48) if his_pid else {}
        cap = await self._get_latest_device_cap(device_id) if device_id else None

        pao2 = labs.get("pao2", {}).get("value") if labs else None
        fio2 = self._vent_param(cap, "fio2", "param_FiO2") if cap else None
        peep = self._vent_param_priority(cap, ["peep_measured", "peep_set"], ["param_vent_measure_peep", "param_vent_peep"]) if cap else None
        ventilated = peep is not None and peep >= 5
        fio2_frac = None
        if fio2 is not None:
            fio2_frac = fio2 / 100.0 if fio2 > 1 else fio2
        pf = pao2 / fio2_frac if (pao2 is not None and fio2_frac and fio2_frac > 0) else None
        resp_score = 0
        if pf is not None:
            if pf < 100 and ventilated:
                resp_score = 4
            elif pf < 200 and ventilated:
                resp_score = 3
            elif pf < 300:
                resp_score = 2
            elif pf < 400:
                resp_score = 1

        plt = labs.get("plt", {}).get("value") if labs else None
        coag_score = 0
        if plt is not None:
            if plt < 20:
                coag_score = 4
            elif plt < 50:
                coag_score = 3
            elif plt < 100:
                coag_score = 2
            elif plt < 150:
                coag_score = 1

        bil = labs.get("bil", {}).get("value") if labs else None
        liver_score = 0
        if bil is not None:
            if bil > 204:
                liver_score = 4
            elif bil > 102:
                liver_score = 3
            elif bil > 33:
                liver_score = 2
            elif bil >= 20:
                liver_score = 1

        map_value = self._get_map(cap) if cap else None
        vaso_level = await self._get_vasopressor_level(pid)
        cardio_score = 0
        if vaso_level > 0:
            cardio_score = vaso_level
        elif map_value is not None and map_value < 70:
            cardio_score = 1

        gcs = await self._get_latest_assessment(pid, "gcs")
        neuro_score = 0
        if gcs is not None:
            if gcs < 6:
                neuro_score = 4
            elif gcs < 10:
                neuro_score = 3
            elif gcs < 13:
                neuro_score = 2
            elif gcs < 15:
                neuro_score = 1

        cr = labs.get("cr", {}).get("value") if labs else None
        renal_score = 0
        if cr is not None:
            if cr > 440:
                renal_score = 4
            elif cr >= 300:
                renal_score = 3
            elif cr >= 171:
                renal_score = 2
            elif cr >= 110:
                renal_score = 1

        score = resp_score + coag_score + liver_score + cardio_score + neuro_score + renal_score

        baseline_score = 0
        baseline_available = False
        if his_pid:
            admission_time = _parse_dt(patient_doc.get("icuAdmissionTime"))
            if admission_time:
                baseline_start = admission_time - timedelta(hours=24)
                baseline_end = admission_time + timedelta(hours=24)
            else:
                baseline_start = datetime.now() - timedelta(days=7)
                baseline_end = datetime.now() - timedelta(hours=48)

            baseline_available = True
            if (series := await self._get_lab_series(his_pid, "pao2", baseline_start, baseline_end)):
                pf_list = []
                for s in series:
                    if fio2_frac:
                        # NOTE: 基线P/F使用当前FiO2近似，可能导致SOFA呼吸子分baseline偏高
                        # 理想实现应使用基线时间窗内的FiO2，但呼吸机历史参数可能不完整
                        pf_list.append(s["value"] / fio2_frac)
                if pf_list:
                    pf_best = max(pf_list)
                    if pf_best < 100 and ventilated:
                        baseline_score += 4
                    elif pf_best < 200 and ventilated:
                        baseline_score += 3
                    elif pf_best < 300:
                        baseline_score += 2
                    elif pf_best < 400:
                        baseline_score += 1
            if (series := await self._get_lab_series(his_pid, "plt", baseline_start, baseline_end)):
                best = max(s["value"] for s in series)
                if best < 20:
                    baseline_score += 4
                elif best < 50:
                    baseline_score += 3
                elif best < 100:
                    baseline_score += 2
                elif best < 150:
                    baseline_score += 1
            if (series := await self._get_lab_series(his_pid, "bil", baseline_start, baseline_end)):
                best = min(s["value"] for s in series)
                if best > 204:
                    baseline_score += 4
                elif best > 102:
                    baseline_score += 3
                elif best > 33:
                    baseline_score += 2
                elif best >= 20:
                    baseline_score += 1
            if (series := await self._get_lab_series(his_pid, "cr", baseline_start, baseline_end)):
                best = min(s["value"] for s in series)
                if best > 440:
                    baseline_score += 4
                elif best >= 300:
                    baseline_score += 3
                elif best >= 171:
                    baseline_score += 2
                elif best >= 110:
                    baseline_score += 1
            if (baseline_gcs := await self._get_assessment_value_in_window(pid, "gcs", baseline_start, baseline_end)) is not None:
                if baseline_gcs < 6:
                    baseline_score += 4
                elif baseline_gcs < 10:
                    baseline_score += 3
                elif baseline_gcs < 13:
                    baseline_score += 2
                elif baseline_gcs < 15:
                    baseline_score += 1
        else:
            baseline_available = False

        return {
            "score": score,
            "baseline": baseline_score,
            "delta": score - baseline_score,
            "baseline_available": baseline_available,
            "components": {
                "resp": resp_score,
                "coag": coag_score,
                "liver": liver_score,
                "cardio": cardio_score,
                "neuro": neuro_score,
                "renal": renal_score,
            },
            "vitals": {"map": map_value},
            "labs": labs,
        }

    async def _get_urine_series(self, pid, hours: int = 24) -> list[dict]:
        codes = self._get_cfg_list(
            ("alert_engine", "data_mapping", "urine_output", "codes"),
            ["param_urine", "param_尿量", "urine_output", "urine_ml_h"],
        )
        since = datetime.now() - timedelta(hours=hours)
        pid_str = self._pid_str(pid)
        if not pid_str:
            return []
        cursor = self.db.col("bedside").find(
            {"pid": pid_str, "code": {"$in": codes}, "time": {"$gte": since}},
            {"time": 1, "strVal": 1, "intVal": 1, "fVal": 1, "code": 1},
        ).sort("time", 1)
        points = []
        async for doc in cursor:
            v = _cap_value(doc)
            if v is not None:
                points.append({"time": doc.get("time"), "value": v})
        if points:
            return points

        fallback_keywords = self._get_cfg_list(
            ("alert_engine", "data_mapping", "urine_output", "keywords"),
            ["尿量", "urine", "output", "foley"],
        )
        cursor = self.db.col("bedside").find(
            {"pid": pid_str, "time": {"$gte": since}},
            {"time": 1, "strVal": 1, "intVal": 1, "fVal": 1, "code": 1, "value": 1},
        ).sort("time", 1).limit(4000)
        keywords = [str(x).lower() for x in [*codes, *fallback_keywords] if str(x).strip()]
        for doc in cursor:
            text = " ".join(str(doc.get(k) or "") for k in ("code", "strVal")).lower()
            if not any(k in text for k in keywords):
                continue
            v = _cap_value(doc)
            if v is not None:
                points.append({"time": doc.get("time"), "value": v, "fallback": True, "code": doc.get("code")})
        return points

    def _get_patient_weight(self, patient_doc: dict | None) -> float | None:
        if not patient_doc:
            return None
        for key in ["weight", "bodyWeight", "body_weight", "weightKg", "weight_kg"]:
            val = patient_doc.get(key)
            num = _parse_number(val)
            if num is not None and 20 < num < 300:
                return num
        return None

    async def _get_urine_rate(self, pid, patient_doc: dict | None, hours: int) -> float | None:
        series = await self._get_urine_series(pid, hours=hours)
        if not series:
            return None
        avg_ml_per_h = sum(p["value"] for p in series) / len(series)
        weight = self._get_patient_weight(patient_doc)
        if not weight:
            return None
        return avg_ml_per_h / weight

    async def _calc_aki_stage(self, patient_doc: dict | None, pid, his_pid) -> dict | None:
        since_7d = datetime.now() - timedelta(days=7)
        series = await self._get_lab_series(his_pid, "cr", since_7d, limit=300)
        if not series:
            return None
        current = series[-1]
        baseline = min(s["value"] for s in series)
        baseline_meta = await self._get_patient_baseline(pid, "cr", hours=12, patient_doc=patient_doc)
        baseline_mean = _parse_number((baseline_meta or {}).get("mean"))
        if baseline_mean is not None and baseline_mean > 0:
            baseline = min(baseline, baseline_mean)
        ratio = current["value"] / baseline if baseline > 0 else None

        since_48h = datetime.now() - timedelta(hours=48)
        series_48 = [s for s in series if s["time"] >= since_48h]
        inc_48 = None
        if series_48:
            inc_48 = current["value"] - min(s["value"] for s in series_48)

        stage = 0
        condition = {}
        if inc_48 is not None and inc_48 >= 26.5:
            stage = max(stage, 1)
            condition["delta_48h"] = inc_48
        if ratio is not None:
            absolute_cr_stage3 = False
            if current["value"] >= 353.6:
                if (ratio is not None and ratio >= 1.5) or (inc_48 is not None and inc_48 >= 26.5):
                    absolute_cr_stage3 = True
                elif baseline_mean is not None and current["value"] >= baseline_mean + 88.4:
                    absolute_cr_stage3 = True
            if ratio >= 3 or absolute_cr_stage3:
                stage = max(stage, 3)
            elif ratio >= 2:
                stage = max(stage, 2)
            elif ratio >= 1.5:
                stage = max(stage, 1)
            condition["ratio"] = ratio
            if absolute_cr_stage3:
                condition["absolute_cr_stage3"] = True

        if pid is not None:
            u6 = await self._get_urine_rate(pid, patient_doc, hours=6)
            u12 = await self._get_urine_rate(pid, patient_doc, hours=12)
            u24 = await self._get_urine_rate(pid, patient_doc, hours=24)
            if u24 is not None and u24 < 0.3:
                stage = max(stage, 3)
                condition["urine_24h_ml_kg_h"] = u24
            elif u12 is not None and u12 < 0.5:
                stage = max(stage, 2)
                condition["urine_12h_ml_kg_h"] = u12
            elif u6 is not None and u6 < 0.5:
                stage = max(stage, 1)
                condition["urine_6h_ml_kg_h"] = u6

        if stage == 0:
            return None

        return {
            "stage": stage,
            "baseline": baseline,
            "baseline_mean_12h": baseline_mean,
            "current": current["value"],
            "time": current["time"],
            "condition": condition,
        }

    async def _calc_dic_score(self, his_pid) -> dict | None:
        labs = await self._get_latest_labs_map(his_pid, lookback_hours=72)
        if not labs:
            return None

        score = 0
        detail = {}

        plt = labs.get("plt", {}).get("value")
        if plt is not None:
            if plt < 50:
                score += 2
                detail["plt"] = 2
            elif plt < 100:
                score += 1
                detail["plt"] = 1
            else:
                detail["plt"] = 0

        # D-Dimer 阈值基于 ISTH DIC 评分标准，单位: mg/L FEU
        # _convert_lab_value 已将 µg/L、ng/mL、DDU 等统一换算为 mg/L FEU
        dd = labs.get("ddimer", {}).get("value")
        if dd is not None:
            if dd >= 5:
                score += 3
                detail["ddimer"] = 3
            elif dd >= 1:
                score += 2
                detail["ddimer"] = 2
            else:
                detail["ddimer"] = 0

        inr = labs.get("inr", {}).get("value")
        pt = labs.get("pt", {}).get("value")
        if inr is not None:
            if inr > 2.0:
                score += 2
                detail["pt"] = 2
            elif inr >= 1.5:
                score += 1
                detail["pt"] = 1
            else:
                detail["pt"] = 0
        elif pt is not None:
            if pt > 6:
                score += 2
                detail["pt"] = 2
            elif pt >= 3:
                score += 1
                detail["pt"] = 1
            else:
                detail["pt"] = 0

        fib = labs.get("fib", {}).get("value")
        if fib is not None:
            if fib < 1.0:
                score += 1
                detail["fib"] = 1
            else:
                detail["fib"] = 0

        times = [v.get("time") for v in labs.values() if isinstance(v, dict) and v.get("time")]
        t = max(times) if times else None

        return {"score": score, "detail": detail, "time": t, "labs": labs}

    async def _get_hb_drop(self, his_pid, hours: int = 24) -> dict | None:
        since = datetime.now() - timedelta(hours=hours)
        series = await self._get_lab_series(his_pid, "hb", since)
        if len(series) < 2:
            return None
        current = series[-1]
        baseline = max(s["value"] for s in series)
        drop = baseline - current["value"]
        return {"drop": drop, "baseline": baseline, "current": current["value"], "time": current["time"]}

    async def _get_platelet_drop(self, his_pid, days: int = 7) -> dict | None:
        since = datetime.now() - timedelta(days=days)
        series = await self._get_lab_series(his_pid, "plt", since)
        if len(series) < 2:
            return None
        current = series[-1]
        baseline = max(s["value"] for s in series)
        drop_ratio = (baseline - current["value"]) / baseline if baseline > 0 else 0
        return {
            "baseline": baseline,
            "current": current["value"],
            "drop_ratio": drop_ratio,
            "time": current["time"],
        }

    async def _get_recent_drugs(self, pid, hours: int = 24) -> list[str]:
        since = datetime.now() - timedelta(hours=hours)
        pid_str = self._pid_str(pid)
        cursor = self.db.col("drugExe").find(
            {"pid": pid_str},
            {"drugName": 1, "executeTime": 1},
        ).sort("executeTime", -1).limit(200)
        names = []
        async for doc in cursor:
            t = _parse_dt(doc.get("executeTime"))
            if t and t < since:
                continue
            name = str(doc.get("drugName") or "").strip()
            if name:
                names.append(name)
        return names

    async def _get_vasopressor_level(self, pid) -> int:
        """
        返回心血管SOFA子分: 0-4（剂量未知时保守估计）

        SOFA 心血管评分标准 (Vincent 1996):
          - 0分: MAP ≥ 70 mmHg
          - 1分: MAP < 70 mmHg
          - 2分: 多巴胺 ≤5 µg/kg/min 或任意剂量多巴酚丁胺
          - 3分: 去甲肾上腺素/肾上腺素 ≤0.1 µg/kg/min 或多巴胺 >5
          - 4分: 去甲肾上腺素/肾上腺素 >0.1 µg/kg/min 或多巴胺 >15

        当前系统限制:
          - drugExe 记录仅含药品名称，无法获取实时输注速率（µg/kg/min）
          - 从 drugName 自由文本中提取剂量既脆弱又易出错

        保守策略:
          - 去甲肾上腺素/肾上腺素/血管加压素 → 3分（不评4分，因无法确认剂量 >0.1）
          - 多巴胺/多巴酚丁胺 → 2分（使用最低升压药评分）
          - 避免SOFA过高估计导致误报脓毒症/脓毒性休克

        未来改进: 接入输液泵数据可实现精确剂量计算，区分3分与4分
        """
        drugs = await self._get_recent_drugs(pid, hours=6)
        if not drugs:
            return 0

        has_ne = any("去甲肾上腺素" in d for d in drugs)
        has_epi = any(("肾上腺素" in d) and ("去甲" not in d) for d in drugs)
        has_vaso = any("血管加压素" in d for d in drugs)
        has_dopa = any(("多巴胺" in d) and ("多巴酚" not in d) for d in drugs)
        # 多巴酚丁胺是正性肌力药（非血管升压药），但 SOFA 心血管评分纳入
        has_dobu = any("多巴酚丁胺" in d for d in drugs)

        if has_ne or has_epi or has_vaso:
            return 3
        if has_dopa or has_dobu:
            return 2
        return 0

    async def _has_vasopressor(self, pid) -> bool:
        return (await self._get_vasopressor_level(pid)) > 0

    def _drug_text(self, doc: dict) -> str:
        return " ".join(
            str(doc.get(k) or "")
            for k in ("drugName", "orderName", "drugSpec", "route", "routeName", "orderType")
        ).strip()

    async def _get_recent_drug_docs_window(self, pid, hours: int = 24, limit: int = 600) -> list[dict]:
        pid_str = self._pid_str(pid)
        if not pid_str:
            return []
        since = datetime.now() - timedelta(hours=hours)
        cursor = self.db.col("drugExe").find(
            {"pid": pid_str},
            {
                "executeTime": 1,
                "startTime": 1,
                "orderTime": 1,
                "drugName": 1,
                "orderName": 1,
                "drugSpec": 1,
                "dose": 1,
                "doseUnit": 1,
                "unit": 1,
                "route": 1,
                "routeName": 1,
                "orderType": 1,
                "frequency": 1,
            },
        ).sort("executeTime", -1).limit(limit)
        rows: list[dict] = []
        async for doc in cursor:
            t = _parse_dt(doc.get("executeTime")) or _parse_dt(doc.get("startTime")) or _parse_dt(doc.get("orderTime"))
            if t and t < since:
                continue
            doc["_event_time"] = t
            rows.append(doc)
        rows.sort(key=lambda x: x.get("_event_time") or datetime.min)
        return rows

    async def _find_recent_drug_docs(self, pid, keywords: list[str], hours: int = 24, limit: int = 600) -> list[dict]:
        docs = await self._get_recent_drug_docs_window(pid, hours=hours, limit=limit)
        out: list[dict] = []
        kw_lower = [str(x).lower() for x in keywords if str(x).strip()]
        for doc in docs:
            text = self._drug_text(doc).lower()
            if any(k in text for k in kw_lower):
                out.append(doc)
        return out

    async def _has_recent_drug(self, pid, keywords: list[str], hours: int = 24) -> bool:
        docs = await self._find_recent_drug_docs(pid, keywords, hours=hours, limit=200)
        return bool(docs)

    async def _get_recent_text_events(
        self,
        pid,
        keywords: list[str],
        *,
        hours: int = 72,
        limit: int = 1200,
    ) -> list[dict]:
        pid_str = self._pid_str(pid)
        if not pid_str:
            return []
        since = datetime.now() - timedelta(hours=hours)
        cursor = self.db.col("bedside").find(
            {"pid": pid_str, "time": {"$gte": since}},
            {"time": 1, "code": 1, "strVal": 1, "value": 1},
        ).sort("time", -1).limit(limit)
        kw_lower = [str(x).lower() for x in keywords if str(x).strip()]
        rows: list[dict] = []
        async for doc in cursor:
            text = " ".join(str(doc.get(k) or "") for k in ("code", "strVal", "value")).lower()
            if any(k in text for k in kw_lower):
                rows.append(doc)
        return rows

    async def _get_latest_active_alert(self, patient_id: str, alert_types: list[str], hours: int = 48) -> dict | None:
        since = datetime.now() - timedelta(hours=hours)
        return await self.db.col("alert_records").find_one(
            {
                "patient_id": str(patient_id),
                "alert_type": {"$in": alert_types},
                "created_at": {"$gte": since},
            },
            sort=[("created_at", -1)],
        )

    def _estimate_egfr(self, patient_doc: dict | None, cr_umol_l: float | None) -> float | None:
        if cr_umol_l is None or cr_umol_l <= 0:
            return None
        age_text = str((patient_doc or {}).get("age") or "").strip()
        age_num = _parse_number(age_text)
        if age_num is None:
            age_num = _parse_number((patient_doc or {}).get("hisAge"))
        if age_num is None:
            return None
        sex_text = str((patient_doc or {}).get("gender") or (patient_doc or {}).get("hisSex") or "").lower()
        female = any(k in sex_text for k in ["female", "女", "f"])
        scr_mg_dl = cr_umol_l / 88.4
        kappa = 0.7 if female else 0.9
        alpha = -0.241 if female else -0.302
        egfr = 142 * (min(scr_mg_dl / kappa, 1) ** alpha) * (max(scr_mg_dl / kappa, 1) ** -1.2) * (0.9938 ** age_num)
        if female:
            egfr *= 1.012
        return round(float(egfr), 1)

    # =============================================
    # 通用方法
    # =============================================
    def _clamp(self, value: float, lower: float, upper: float) -> float:
        return max(lower, min(upper, float(value)))

    def _sigmoid(self, value: float) -> float:
        try:
            return 1.0 / (1.0 + math.exp(-float(value)))
        except Exception:
            return 0.5

    def _risk_level_from_probability(self, prob: float) -> str:
        p = self._clamp(prob, 0.0, 1.0)
        if p >= 0.82:
            return "critical"
        if p >= 0.64:
            return "high"
        if p >= 0.42:
            return "warning"
        return "low"

    def _series_value_before(self, series: list[dict] | None, cutoff: datetime | None) -> dict | None:
        if not isinstance(series, list) or not series:
            return None
        if cutoff is None:
            for item in reversed(series):
                if item.get("value") is not None:
                    return item
            return None
        for item in reversed(series):
            t = item.get("time")
            if not isinstance(t, datetime):
                continue
            if t <= cutoff and item.get("value") is not None:
                return item
        return None

    def _series_prev_before(self, series: list[dict] | None, cutoff: datetime | None) -> dict | None:
        current = self._series_value_before(series, cutoff)
        if not current:
            return None
        current_time = current.get("time")
        if not isinstance(current_time, datetime):
            return None
        for item in reversed(series or []):
            t = item.get("time")
            if not isinstance(t, datetime):
                continue
            if t < current_time and item.get("value") is not None:
                return item
        return None

    def _series_delta_per_hour(self, series: list[dict] | None, cutoff: datetime | None) -> float:
        current = self._series_value_before(series, cutoff)
        prev = self._series_prev_before(series, cutoff)
        if not current or not prev:
            return 0.0
        t1 = current.get("time")
        t0 = prev.get("time")
        if not isinstance(t1, datetime) or not isinstance(t0, datetime):
            return 0.0
        hours = max((t1 - t0).total_seconds() / 3600.0, 0.25)
        try:
            return (float(current.get("value")) - float(prev.get("value"))) / hours
        except Exception:
            return 0.0

    def _append_temporal_signal(
        self,
        rows: list[dict[str, Any]],
        organ_scores: dict[str, float],
        *,
        organ: str,
        feature: str,
        score: float,
        evidence: str,
        direction: str = "up",
    ) -> None:
        if score <= 0:
            return
        rows.append(
            {
                "organ": organ,
                "feature": feature,
                "score": round(float(score), 3),
                "evidence": evidence,
                "direction": direction,
            }
        )
        organ_scores[organ] = organ_scores.get(organ, 0.0) + float(score)

    def _build_temporal_risk_snapshot(
        self,
        *,
        cutoff: datetime | None,
        series_map: dict[str, list[dict]],
        lab_series_map: dict[str, list[dict]],
        alert_rows: list[dict],
    ) -> dict[str, Any]:
        contributors: list[dict[str, Any]] = []
        organ_scores: dict[str, float] = {}

        def latest(metric: str):
            row = self._series_value_before(series_map.get(metric), cutoff)
            return row.get("value") if row else None

        def latest_lab(metric: str):
            row = self._series_value_before(lab_series_map.get(metric), cutoff)
            return row.get("value") if row else None

        hr = latest("hr")
        rr = latest("rr")
        spo2 = latest("spo2")
        sbp = latest("sbp")
        temp = latest("temp")
        gcs = latest("gcs")
        lac = latest_lab("lac")
        pct = latest_lab("pct")
        cr = latest_lab("cr")

        hr_rate = self._series_delta_per_hour(series_map.get("hr"), cutoff)
        rr_rate = self._series_delta_per_hour(series_map.get("rr"), cutoff)
        spo2_rate = self._series_delta_per_hour(series_map.get("spo2"), cutoff)
        sbp_rate = self._series_delta_per_hour(series_map.get("sbp"), cutoff)
        lac_rate = self._series_delta_per_hour(lab_series_map.get("lac"), cutoff)
        cr_rate = self._series_delta_per_hour(lab_series_map.get("cr"), cutoff)

        if sbp is not None:
            if sbp <= 85:
                self._append_temporal_signal(contributors, organ_scores, organ="circulatory", feature="SBP", score=0.23, evidence=f"SBP {self._format_alert_measure(sbp, 'mmHg', 0)}")
            elif sbp <= 95:
                self._append_temporal_signal(contributors, organ_scores, organ="circulatory", feature="SBP", score=0.17, evidence=f"SBP {self._format_alert_measure(sbp, 'mmHg', 0)}")
            elif sbp <= 100:
                self._append_temporal_signal(contributors, organ_scores, organ="circulatory", feature="SBP", score=0.11, evidence=f"SBP {self._format_alert_measure(sbp, 'mmHg', 0)}")
            if sbp_rate <= -6:
                self._append_temporal_signal(contributors, organ_scores, organ="circulatory", feature="SBP趋势", score=0.08, evidence=f"SBP 下降速率 {self._format_alert_number(abs(sbp_rate), 1)} mmHg/h", direction="down")

        if rr is not None:
            if rr >= 30:
                self._append_temporal_signal(contributors, organ_scores, organ="respiratory", feature="RR", score=0.18, evidence=f"RR {self._format_alert_measure(rr, '次/分', 0)}")
            elif rr >= 24:
                self._append_temporal_signal(contributors, organ_scores, organ="respiratory", feature="RR", score=0.13, evidence=f"RR {self._format_alert_measure(rr, '次/分', 0)}")
            elif rr >= 22:
                self._append_temporal_signal(contributors, organ_scores, organ="respiratory", feature="RR", score=0.09, evidence=f"RR {self._format_alert_measure(rr, '次/分', 0)}")
            if rr_rate >= 2.0:
                self._append_temporal_signal(contributors, organ_scores, organ="respiratory", feature="RR趋势", score=0.05, evidence=f"RR 上升速率 {self._format_alert_number(rr_rate, 1)} 次/分/h")

        if spo2 is not None:
            if spo2 <= 88:
                self._append_temporal_signal(contributors, organ_scores, organ="respiratory", feature="SpO₂", score=0.20, evidence=f"SpO₂ {self._format_alert_measure(spo2, '%', 0)}")
            elif spo2 <= 92:
                self._append_temporal_signal(contributors, organ_scores, organ="respiratory", feature="SpO₂", score=0.13, evidence=f"SpO₂ {self._format_alert_measure(spo2, '%', 0)}")
            elif spo2 <= 94:
                self._append_temporal_signal(contributors, organ_scores, organ="respiratory", feature="SpO₂", score=0.07, evidence=f"SpO₂ {self._format_alert_measure(spo2, '%', 0)}")
            if spo2_rate <= -1.5:
                self._append_temporal_signal(contributors, organ_scores, organ="respiratory", feature="SpO₂趋势", score=0.06, evidence=f"SpO₂ 下降速率 {self._format_alert_number(abs(spo2_rate), 1)} %/h", direction="down")

        if hr is not None:
            if hr >= 130 or hr <= 40:
                self._append_temporal_signal(contributors, organ_scores, organ="circulatory", feature="HR", score=0.13, evidence=f"HR {self._format_alert_measure(hr, 'bpm', 0)}")
            elif hr >= 120 or hr <= 50:
                self._append_temporal_signal(contributors, organ_scores, organ="circulatory", feature="HR", score=0.09, evidence=f"HR {self._format_alert_measure(hr, 'bpm', 0)}")

        if temp is not None and (temp >= 38.5 or temp <= 35.5):
            self._append_temporal_signal(contributors, organ_scores, organ="circulatory", feature="体温", score=0.05, evidence=f"体温 {self._format_alert_measure(temp, '℃')}")

        if gcs is not None:
            if gcs < 13:
                self._append_temporal_signal(contributors, organ_scores, organ="neurologic", feature="GCS", score=0.11, evidence=f"GCS {self._format_alert_number(gcs, 0)}")
            elif gcs < 15:
                self._append_temporal_signal(contributors, organ_scores, organ="neurologic", feature="GCS", score=0.06, evidence=f"GCS {self._format_alert_number(gcs, 0)}")

        if lac is not None:
            if lac >= 4:
                self._append_temporal_signal(contributors, organ_scores, organ="circulatory", feature="乳酸", score=0.20, evidence=f"乳酸 {self._format_alert_measure(lac, 'mmol/L')}")
            elif lac >= 2:
                self._append_temporal_signal(contributors, organ_scores, organ="circulatory", feature="乳酸", score=0.12, evidence=f"乳酸 {self._format_alert_measure(lac, 'mmol/L')}")
            if lac_rate >= 0.3:
                self._append_temporal_signal(contributors, organ_scores, organ="circulatory", feature="乳酸趋势", score=0.06, evidence=f"乳酸上升 {self._format_alert_number(lac_rate, 2)} mmol/L/h")

        if pct is not None:
            if pct >= 2:
                self._append_temporal_signal(contributors, organ_scores, organ="circulatory", feature="PCT", score=0.13, evidence=f"PCT {self._format_alert_measure(pct, 'ng/mL')}")
            elif pct >= 0.5:
                self._append_temporal_signal(contributors, organ_scores, organ="circulatory", feature="PCT", score=0.07, evidence=f"PCT {self._format_alert_measure(pct, 'ng/mL')}")

        if cr is not None:
            if cr >= 265:
                self._append_temporal_signal(contributors, organ_scores, organ="renal", feature="肌酐", score=0.14, evidence=f"Cr {self._format_alert_measure(cr, 'umol/L', 0)}")
            elif cr >= 177:
                self._append_temporal_signal(contributors, organ_scores, organ="renal", feature="肌酐", score=0.09, evidence=f"Cr {self._format_alert_measure(cr, 'umol/L', 0)}")
            if cr_rate >= 12:
                self._append_temporal_signal(contributors, organ_scores, organ="renal", feature="肌酐趋势", score=0.05, evidence=f"Cr 上升 {self._format_alert_number(cr_rate, 1)} umol/L/h")

        recent_high = 0
        recent_critical = 0
        for row in alert_rows:
            ts = row.get("created_at")
            if cutoff is not None and isinstance(ts, datetime) and ts > cutoff:
                continue
            sev = str(row.get("severity") or "").lower()
            if sev == "critical":
                recent_critical += 1
            elif sev == "high":
                recent_high += 1
        if recent_critical > 0:
            self._append_temporal_signal(contributors, organ_scores, organ="circulatory", feature="近期危急预警", score=min(0.14, 0.06 * recent_critical), evidence=f"{recent_critical} 条 critical 预警")
        elif recent_high >= 2:
            self._append_temporal_signal(contributors, organ_scores, organ="circulatory", feature="近期高危预警", score=min(0.10, 0.04 * recent_high), evidence=f"{recent_high} 条 high 预警")

        contributors.sort(key=lambda x: float(x.get("score") or 0), reverse=True)
        raw_score = 0.10 + sum(float(item.get("score") or 0) for item in contributors)
        current_prob = self._clamp(self._sigmoid((raw_score - 0.46) * 4.5), 0.02, 0.98)
        trend_pressure = (
            max(0.0, -sbp_rate) * 0.008 +
            max(0.0, rr_rate) * 0.025 +
            max(0.0, -spo2_rate) * 0.04 +
            max(0.0, lac_rate) * 0.05 +
            max(0.0, cr_rate) * 0.002 +
            recent_high * 0.01 +
            recent_critical * 0.03
        )
        top_organs = [
            organ for organ, _score in
            sorted(organ_scores.items(), key=lambda x: x[1], reverse=True)
            if _score > 0
        ]
        return {
            "probability": round(current_prob, 4),
            "risk_level": self._risk_level_from_probability(current_prob),
            "raw_score": round(raw_score, 4),
            "trend_pressure": round(trend_pressure, 4),
            "contributors": contributors[:8],
            "top_organs": top_organs[:3],
            "organ_scores": {k: round(v, 3) for k, v in organ_scores.items() if v > 0},
            "latest_values": {
                "hr": hr, "rr": rr, "spo2": spo2, "sbp": sbp, "temp": temp, "gcs": gcs,
                "lac": lac, "pct": pct, "cr": cr,
            },
        }

    def _render_temporal_risk_summary(
        self,
        *,
        snapshot: dict[str, Any],
        horizon_probs: list[dict[str, Any]],
    ) -> str:
        current_prob = int(round(float(snapshot.get("probability") or 0) * 100))
        risk_text = {
            "critical": "极高",
            "high": "高",
            "warning": "中",
            "low": "低",
        }.get(str(snapshot.get("risk_level") or "low"), "低")
        top_contribs = snapshot.get("contributors") if isinstance(snapshot.get("contributors"), list) else []
        reasons = [str(item.get("evidence") or "").strip("；;。 ") for item in top_contribs[:3] if item.get("evidence")]
        h4 = next((item for item in horizon_probs if int(item.get("hours") or 0) == 4), None)
        h12 = next((item for item in horizon_probs if int(item.get("hours") or 0) == 12), None)
        horizon_text = []
        if h4:
            horizon_text.append(f"4h约{int(round(float(h4.get('probability') or 0) * 100))}%")
        if h12:
            horizon_text.append(f"12h约{int(round(float(h12.get('probability') or 0) * 100))}%")
        reason_text = "；".join(reasons[:2]) if reasons else "当前生命体征未见明显立即失代偿信号，但仍需结合趋势观察"
        horizon_line = f"，{ '，'.join(horizon_text) }" if horizon_text else ""
        return f"模型判断当前恶化风险为{risk_text}风险（{current_prob}%）{horizon_line}。主要依据：{reason_text}。"

    def _normalize_temporal_feature(self, name: str, value: Any) -> float:
        num = _parse_number(value)
        if num is None:
            return -1.0
        bounds = {
            "hr": (0.0, 200.0),
            "rr": (0.0, 45.0),
            "spo2": (0.0, 100.0),
            "sbp": (0.0, 220.0),
            "temp": (30.0, 42.0),
            "gcs": (0.0, 15.0),
            "lac": (0.0, 12.0),
            "pct": (0.0, 20.0),
            "cr": (0.0, 800.0),
        }
        low, high = bounds.get(name, (0.0, 1.0))
        if high <= low:
            return float(num)
        return round(self._clamp((float(num) - low) / (high - low), 0.0, 1.0), 6)

    def _build_temporal_feature_sequence(
        self,
        *,
        anchor_time: datetime,
        history_offsets: list[int],
        series_map: dict[str, list[dict]],
        lab_series_map: dict[str, list[dict]],
    ) -> np.ndarray:
        feature_order = ["hr", "rr", "spo2", "sbp", "temp", "gcs", "lac", "pct", "cr"]
        rows: list[list[float]] = []
        for offset in history_offsets:
            cutoff = anchor_time + timedelta(hours=int(offset))
            row: list[float] = []
            for feature in feature_order:
                pool = series_map.get(feature) if feature in series_map else lab_series_map.get(feature)
                point = self._series_value_before(pool, cutoff)
                row.append(self._normalize_temporal_feature(feature, point.get("value") if point else None))
            rows.append(row)
        return np.asarray(rows, dtype=np.float32)

    def _build_temporal_meta_vector(self, snapshot: dict[str, Any]) -> np.ndarray:
        organ_scores = snapshot.get("organ_scores") if isinstance(snapshot.get("organ_scores"), dict) else {}
        organs = ["respiratory", "circulatory", "renal", "neurologic"]
        values = [
            float(snapshot.get("probability") or 0.0),
            float(snapshot.get("raw_score") or 0.0),
            float(snapshot.get("trend_pressure") or 0.0),
        ]
        for organ in organs:
            values.append(float(organ_scores.get(organ) or 0.0))
        return np.asarray(values, dtype=np.float32)

    def _normalize_organ_risk_scores(self, scores: dict[str, Any]) -> dict[str, float]:
        if not isinstance(scores, dict):
            return {}
        max_score = max([float(v) for v in scores.values() if _parse_number(v) is not None] or [0.0])
        if max_score <= 0:
            return {}
        return {str(k): round(self._clamp(float(v) / max_score, 0.0, 1.0), 4) for k, v in scores.items() if _parse_number(v) is not None}

    def _temporal_threshold_bands(self) -> list[dict[str, Any]]:
        return [
            {"name": "低危", "min": 0.0, "max": 0.42, "color": "rgba(52,211,153,0.08)"},
            {"name": "警戒", "min": 0.42, "max": 0.64, "color": "rgba(250,204,21,0.08)"},
            {"name": "高危", "min": 0.64, "max": 1.0, "color": "rgba(239,68,68,0.10)"},
        ]

    async def _predict_temporal_with_local_model(
        self,
        *,
        sequence: np.ndarray,
        meta_features: np.ndarray,
        organ_keys: list[str],
        horizons: tuple[int, ...],
    ) -> dict[str, Any]:
        runtime = self._get_temporal_model_runtime()
        return await asyncio.to_thread(
            runtime.predict,
            sequence=sequence,
            meta_features=meta_features,
            organ_keys=organ_keys,
            horizons=horizons,
        )

    async def _build_temporal_risk_forecast(
        self,
        patient_doc: dict,
        pid,
        *,
        lookback_hours: int = 12,
        horizons: tuple[int, ...] = (4, 8, 12),
        include_history: bool = True,
    ) -> dict[str, Any]:
        pid_str = self._pid_str(pid)
        his_pid = (patient_doc or {}).get("hisPid")
        since = datetime.now() - timedelta(hours=max(lookback_hours, 8))
        lab_since = datetime.now() - timedelta(hours=max(lookback_hours * 2, 24))

        async def load_metric_series(code: str) -> list[dict]:
            return await self._get_param_series_by_pid(pid, code, since, prefer_device_types=["monitor"], limit=600)

        hr_series = await load_metric_series("param_HR")
        rr_series = await load_metric_series("param_resp")
        spo2_series = await load_metric_series("param_spo2")
        temp_series = await load_metric_series("param_T")
        sbp_series = await load_metric_series("param_nibp_s")
        if not sbp_series:
            sbp_series = await load_metric_series("param_ibp_s")
        gcs_series = await self._get_assessment_series(pid, "gcs", hours=max(lookback_hours, 24))

        lab_series_map: dict[str, list[dict]] = {"lac": [], "pct": [], "cr": []}
        if his_pid:
            for key in lab_series_map.keys():
                lab_series_map[key] = await self._get_lab_series(his_pid, key, lab_since, limit=80)

        alert_cursor = self.db.col("alert_records").find(
            {
                "patient_id": {"$in": [pid_str, pid]},
                "created_at": {"$gte": since},
            },
            {"severity": 1, "created_at": 1},
        ).sort("created_at", 1).limit(120)
        alert_rows = [row async for row in alert_cursor]

        series_map = {
            "hr": hr_series,
            "rr": rr_series,
            "spo2": spo2_series,
            "sbp": sbp_series,
            "temp": temp_series,
            "gcs": gcs_series,
        }

        anchor_candidates = []
        for dataset in list(series_map.values()) + list(lab_series_map.values()):
            if isinstance(dataset, list) and dataset:
                row = self._series_value_before(dataset, None)
                if row and isinstance(row.get("time"), datetime):
                    anchor_candidates.append(row.get("time"))
        anchor_time = max(anchor_candidates) if anchor_candidates else datetime.now(timezone.utc)
        temporal_cfg = self.config.yaml_cfg.get("ai_service", {}).get("temporal_model", {})
        history_offsets = temporal_cfg.get("history_offsets_hours", [-8, -6, -4, -2, 0]) if isinstance(temporal_cfg, dict) else [-8, -6, -4, -2, 0]
        history_offsets = [int(x) for x in history_offsets if _parse_number(x) is not None]
        if 0 not in history_offsets:
            history_offsets.append(0)
        history_offsets = sorted(set(history_offsets))

        snapshot = self._build_temporal_risk_snapshot(
            cutoff=anchor_time,
            series_map=series_map,
            lab_series_map=lab_series_map,
            alert_rows=alert_rows,
        )
        current_prob = float(snapshot.get("probability") or 0.0)
        current_raw = float(snapshot.get("raw_score") or 0.0)
        trend_pressure = float(snapshot.get("trend_pressure") or 0.0)
        organ_keys = ["respiratory", "circulatory", "renal", "neurologic"]

        sequence = self._build_temporal_feature_sequence(
            anchor_time=anchor_time,
            history_offsets=history_offsets,
            series_map=series_map,
            lab_series_map=lab_series_map,
        )
        model_result = await self._predict_temporal_with_local_model(
            sequence=sequence,
            meta_features=self._build_temporal_meta_vector(snapshot),
            organ_keys=organ_keys,
            horizons=horizons,
        )

        if model_result.get("available") and model_result.get("probability") is not None:
            current_prob = self._clamp(float(model_result.get("probability") or current_prob), 0.01, 0.99)
            snapshot["probability"] = round(current_prob, 4)
            snapshot["risk_level"] = self._risk_level_from_probability(current_prob)

        history_curve: list[dict[str, Any]] = []
        organ_history: dict[str, list[dict[str, Any]]] = {k: [] for k in organ_keys}
        if include_history:
            for offset in history_offsets:
                cutoff = anchor_time + timedelta(hours=offset)
                hist = self._build_temporal_risk_snapshot(
                    cutoff=cutoff,
                    series_map=series_map,
                    lab_series_map=lab_series_map,
                    alert_rows=alert_rows,
                )
                hist_prob = float(hist.get("probability") or 0.0)
                hist_sequence = self._build_temporal_feature_sequence(
                    anchor_time=cutoff,
                    history_offsets=history_offsets,
                    series_map=series_map,
                    lab_series_map=lab_series_map,
                )
                hist_model = await self._predict_temporal_with_local_model(
                    sequence=hist_sequence,
                    meta_features=self._build_temporal_meta_vector(hist),
                    organ_keys=organ_keys,
                    horizons=(),
                )
                if hist_model.get("available") and hist_model.get("probability") is not None:
                    hist_prob = self._clamp(float(hist_model.get("probability") or hist_prob), 0.01, 0.99)
                history_curve.append(
                    {
                        "label": "现在" if offset == 0 else f"{offset}h",
                        "offset_hours": offset,
                        "phase": "history" if offset < 0 else "current",
                        "probability": round(hist_prob, 4),
                        "risk_level": self._risk_level_from_probability(hist_prob),
                        "time": _to_output_iso(cutoff),
                    }
                )
                base_org = self._normalize_organ_risk_scores(hist.get("organ_scores", {}))
                model_org = hist_model.get("organ_probabilities") if isinstance(hist_model.get("organ_probabilities"), dict) else {}
                for organ in organ_keys:
                    organ_prob = float(model_org.get(organ)) if model_org.get(organ) is not None else float(base_org.get(organ, hist_prob * 0.7))
                    organ_prob = self._clamp(organ_prob, 0.0, 0.99)
                    organ_history[organ].append(
                        {
                            "label": "现在" if offset == 0 else f"{offset}h",
                            "offset_hours": offset,
                            "phase": "history" if offset < 0 else "current",
                            "probability": round(organ_prob, 4),
                            "time": _to_output_iso(cutoff),
                        }
                    )
        else:
            history_curve.append(
                {
                    "label": "现在",
                    "offset_hours": 0,
                    "phase": "current",
                    "probability": round(current_prob, 4),
                    "risk_level": snapshot.get("risk_level") or "low",
                    "time": _to_output_iso(anchor_time),
                }
            )

        future_from_model = model_result.get("future_probabilities") if isinstance(model_result.get("future_probabilities"), dict) else {}
        organ_base_scores = self._normalize_organ_risk_scores(snapshot.get("organ_scores", {}))
        current_organ_probs = {
            organ: self._clamp(
                float(((model_result.get("organ_probabilities") or {}) if isinstance(model_result.get("organ_probabilities"), dict) else {}).get(organ, organ_base_scores.get(organ, current_prob * 0.75))),
                0.0,
                0.99,
            )
            for organ in organ_keys
        }
        horizon_probs: list[dict[str, Any]] = []
        forecast_curve: list[dict[str, Any]] = []
        organ_forecast: dict[str, list[dict[str, Any]]] = {k: [] for k in organ_keys}
        for hours in horizons:
            hours_i = int(hours)
            if hours_i in future_from_model:
                probability = self._clamp(float(future_from_model.get(hours_i) or current_prob), 0.01, 0.99)
            else:
                future_raw = current_raw + trend_pressure * max(0.8, float(hours_i) / 4.0)
                probability = self._clamp(self._sigmoid((future_raw - 0.46) * 4.5), 0.02, 0.985)
                if model_result.get("available"):
                    probability = self._clamp(probability * 0.45 + current_prob * 0.55, 0.01, 0.99)
            horizon_probs.append(
                {
                    "hours": hours_i,
                    "probability": round(probability, 4),
                    "risk_level": self._risk_level_from_probability(probability),
                }
            )
            forecast_curve.append(
                {
                    "label": f"+{hours_i}h",
                    "offset_hours": hours_i,
                    "phase": "forecast",
                    "probability": round(probability, 4),
                    "risk_level": self._risk_level_from_probability(probability),
                    "time": _to_output_iso(anchor_time + timedelta(hours=hours_i)),
                }
            )
            scale = max(0.7, min(1.4, probability / max(current_prob, 0.08)))
            for organ in organ_keys:
                organ_prob = self._clamp(current_organ_probs.get(organ, 0.0) * scale, 0.0, 0.99)
                organ_forecast[organ].append(
                    {
                        "label": f"+{hours_i}h",
                        "offset_hours": hours_i,
                        "phase": "forecast",
                        "probability": round(organ_prob, 4),
                        "time": _to_output_iso(anchor_time + timedelta(hours=hours_i)),
                    }
                )

        risk_curve = history_curve + forecast_curve
        organ_risk_curves = {
            organ: organ_history.get(organ, []) + organ_forecast.get(organ, [])
            for organ in organ_keys
            if organ_history.get(organ) or organ_forecast.get(organ)
        }
        organ_risk_scores = {organ: round(prob, 4) for organ, prob in current_organ_probs.items() if prob > 0}

        composite_signal = {
            "enabled": current_prob >= 0.58,
            "probability_4h": round(float((horizon_probs[0] if horizon_probs else {}).get("probability") or current_prob), 4),
            "risk_level": self._risk_level_from_probability(float((horizon_probs[0] if horizon_probs else {}).get("probability") or current_prob)),
            "organs": [k for k, _ in sorted(organ_risk_scores.items(), key=lambda x: x[1], reverse=True)[:3]],
            "contributors": snapshot.get("contributors", [])[:4],
        }

        runtime_meta = self._get_temporal_model_runtime().meta()
        mode = "local_weight_runtime" if runtime_meta.get("available") else "heuristic_sequence_v1"
        architecture = "本地权重推理(Pytorch/ONNX)" if runtime_meta.get("available") else "启发式时序评分（待接入本地权重时自动切换）"
        return {
            "patient_id": pid_str,
            "model_meta": {
                "name": "Temporal ICU Risk Predictor",
                "mode": mode,
                "architecture": architecture,
                "input_modalities": ["vitals", "labs", "assessments", "recent_alerts"],
                "prediction_horizons_hours": list(horizons),
                "runtime": runtime_meta,
            },
            "anchor_time": _to_output_iso(anchor_time),
            "risk_level": snapshot.get("risk_level") or "low",
            "current_probability": round(current_prob, 4),
            "horizon_probabilities": horizon_probs,
            "risk_curve": risk_curve,
            "history_risk_curve": history_curve,
            "forecast_risk_curve": forecast_curve,
            "threshold_bands": self._temporal_threshold_bands(),
            "high_risk_zone": {"min": 0.64, "max": 1.0},
            "top_contributors": snapshot.get("contributors", [])[:6],
            "organ_risk_scores": organ_risk_scores,
            "organ_risk_curves": organ_risk_curves,
            "summary": self._render_temporal_risk_summary(snapshot=snapshot, horizon_probs=horizon_probs),
            "composite_signal": composite_signal,
        }

    def _format_alert_number(self, value: Any, digits: int = 1) -> str:
        num = _parse_number(value)
        if num is None:
            return "—"
        rounded = round(float(num), digits)
        if digits <= 0 or abs(rounded - round(rounded)) < 1e-9:
            return str(int(round(rounded)))
        return f"{rounded:.{digits}f}".rstrip("0").rstrip(".")

    def _format_alert_measure(self, value: Any, unit: str = "", digits: int = 1) -> str:
        text = self._format_alert_number(value, digits=digits)
        if text == "—":
            return text
        return f"{text}{unit}"

    def _format_condition_text(self, condition: dict | None, value: Any = None) -> str:
        if not isinstance(condition, dict) or not condition:
            return ""
        op = str(condition.get("operator") or "").strip()
        thr = condition.get("threshold")
        if op and thr is not None:
            return f"{op} {thr}"
        lo = condition.get("min")
        hi = condition.get("max")
        if op == "between" and lo is not None and hi is not None:
            return f"介于 {lo}~{hi}"
        if op == "outside" and lo is not None and hi is not None:
            return f"低于 {lo} 或高于 {hi}"
        if value is not None:
            return f"当前值 {value}"
        keys = []
        for k in ("qsofa", "delta", "score", "lactate", "map", "vasopressor", "risk_level"):
            if condition.get(k) is not None:
                keys.append(f"{k}={condition.get(k)}")
        return "，".join(keys)

    async def _collect_explanation_context(
        self,
        *,
        patient_doc: dict | None,
        patient_id: str | None,
        alert_type: str | None,
        extra: dict | None,
    ) -> dict[str, Any]:
        context: dict[str, Any] = {}
        alert_type = str(alert_type or "").lower()
        if alert_type not in {"qsofa", "sofa", "septic_shock"}:
            return context
        his_pid = (patient_doc or {}).get("hisPid")
        if not his_pid:
            return context
        try:
            labs = await self._get_latest_labs_map(his_pid, lookback_hours=72)
            if not isinstance(labs, dict):
                labs = {}
            context["labs"] = labs

            pct_latest = labs.get("pct", {}).get("value")
            if pct_latest is not None:
                pct_series = await self._get_lab_series(his_pid, "pct", datetime.now() - timedelta(days=7), limit=30)
                if len(pct_series) >= 2:
                    prev = pct_series[-2].get("value")
                    if prev not in (None, 0):
                        context["pct_ratio_vs_prev"] = round(float(pct_latest) / float(prev), 2)

            lac_latest = labs.get("lac", {}).get("value")
            if lac_latest is not None:
                lac_series = await self._get_lab_series(his_pid, "lac", datetime.now() - timedelta(days=7), limit=30)
                if len(lac_series) >= 2:
                    prev = lac_series[-2].get("value")
                    if prev not in (None, 0):
                        context["lac_ratio_vs_prev"] = round(float(lac_latest) / float(prev), 2)
        except Exception as e:
            logger.debug(f"收集预警解释上下文失败: {e}")
        return context

    def _sanitize_context_vital(self, code: str, value: Any) -> float | None:
        num = _parse_number(value)
        if num is None:
            return None
        code_l = str(code or "").lower()
        if "hr" in code_l:
            return None if num <= 0 or num > 250 else round(float(num), 1)
        if "resp" in code_l:
            return None if num <= 0 or num > 80 else round(float(num), 1)
        if "spo2" in code_l:
            return None if num < 30 or num > 100 else round(float(num), 1)
        if code_l.endswith("_m") or "map" in code_l or "ibp" in code_l or "nibp" in code_l:
            return None if num < 20 or num > 280 else round(float(num), 1)
        if code_l.endswith("_t") or code_l == "param_t":
            return None if num < 30 or num > 43 else round(float(num), 1)
        return round(float(num), 1)

    def _context_rate_to_ug_kg_min(self, value: Any, unit: Any, weight_kg: float | None) -> float | None:
        num = _parse_number(value)
        if num is None or num <= 0:
            return None
        u = str(unit or "").lower().replace(" ", "").replace("μ", "u")
        if "mcg/kg/min" in u or "ug/kg/min" in u:
            return round(float(num), 4)
        if "mg/kg/min" in u:
            return round(float(num) * 1000.0, 4)
        if "mg/kg/h" in u or "mg/kg/hr" in u:
            return round(float(num) * 1000.0 / 60.0, 4)
        if weight_kg is None or weight_kg <= 0:
            return None
        if "mg/h" in u or "mg/hr" in u:
            return round(float(num) * 1000.0 / 60.0 / weight_kg, 4)
        if "mg/min" in u:
            return round(float(num) * 1000.0 / weight_kg, 4)
        if "ug/h" in u or "mcg/h" in u:
            return round(float(num) / 60.0 / weight_kg, 4)
        if "ug/min" in u or "mcg/min" in u:
            return round(float(num) / weight_kg, 4)
        return None

    def _extract_vasopressor_rate_ug_kg_min(self, doc: dict, weight_kg: float | None) -> float | None:
        value_unit_pairs = [
            (doc.get("dose"), doc.get("doseUnit") or doc.get("unit")),
            (doc.get("rate"), doc.get("rateUnit") or doc.get("unit")),
            (doc.get("speed"), doc.get("speedUnit") or doc.get("unit")),
            (doc.get("flowRate"), doc.get("flowRateUnit") or doc.get("unit")),
        ]
        for value, unit in value_unit_pairs:
            dose = self._context_rate_to_ug_kg_min(value, unit, weight_kg)
            if dose is not None:
                return dose

        text = " ".join(str(doc.get(k) or "") for k in ("dose", "drugSpec", "orderName", "drugName", "remark"))
        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(mcg/kg/min|ug/kg/min|mg/kg/min|mg/kg/h|mg/kg/hr|mg/h|mg/hr|mg/min|ug/h|mcg/h|ug/min|mcg/min)",
            text,
            flags=re.I,
        )
        if not m:
            return None
        return self._context_rate_to_ug_kg_min(m.group(1), m.group(2), weight_kg)

    async def _get_current_vasopressor_snapshot(
        self,
        pid,
        patient_doc: dict | None,
        *,
        hours: int = 8,
        max_items: int = 4,
    ) -> list[dict[str, Any]]:
        docs = await self._get_recent_drug_docs_window(pid, hours=hours, limit=800)
        if not docs:
            return []

        weight_kg = self._get_patient_weight(patient_doc)
        drug_specs = [
            ("去甲肾上腺素", ["去甲肾上腺素", "norepinephrine", "noradrenaline"]),
            ("肾上腺素", ["肾上腺素", "epinephrine", "adrenaline"]),
            ("多巴胺", ["多巴胺", "dopamine"]),
            ("多巴酚丁胺", ["多巴酚丁胺", "dobutamine"]),
            ("血管加压素", ["血管加压素", "vasopressin"]),
            ("去氧肾上腺素", ["去氧肾上腺素", "phenylephrine"]),
        ]
        infusion_keywords = ["泵", "微泵", "泵入", "泵注", "持续", "静脉", "iv", "静滴", "维持"]

        latest_by_name: dict[str, dict[str, Any]] = {}
        for doc in docs:
            text = " ".join(
                str(doc.get(k) or "")
                for k in ("drugName", "orderName", "drugSpec", "route", "routeName", "remark", "orderType")
            ).lower()
            matched_name = None
            for display_name, keywords in drug_specs:
                if any(str(k).lower() in text for k in keywords):
                    matched_name = display_name
                    break
            if not matched_name:
                continue

            route_text = str(doc.get("routeName") or doc.get("route") or "").strip()
            dose = self._extract_vasopressor_rate_ug_kg_min(doc, weight_kg)
            infusion_like = dose is not None or any(k in text for k in infusion_keywords)
            if not infusion_like:
                continue

            t = _parse_dt(doc.get("_event_time")) or _parse_dt(doc.get("executeTime")) or _parse_dt(doc.get("startTime")) or _parse_dt(doc.get("orderTime"))
            entry = {
                "drug": matched_name,
                "dose_ug_kg_min": dose,
                "dose_display": f"{dose:.3f} μg/kg/min" if dose is not None else None,
                "route": route_text or None,
                "frequency": str(doc.get("frequency") or "").strip() or None,
                "time": t,
                "raw_name": str(doc.get("drugName") or doc.get("orderName") or "").strip() or matched_name,
            }
            prev = latest_by_name.get(matched_name)
            if prev is None or (isinstance(t, datetime) and (prev.get("time") is None or t >= prev.get("time"))):
                latest_by_name[matched_name] = entry

        rows = list(latest_by_name.values())
        rows.sort(key=lambda x: x.get("time") or datetime.min, reverse=True)
        return rows[:max_items]

    async def _build_alert_context_snapshot(
        self,
        *,
        patient_id,
        patient_doc: dict | None,
        device_id: str | None = None,
    ) -> dict[str, Any] | None:
        patient = patient_doc
        pid = (patient or {}).get("_id")
        if patient is None or pid is None:
            patient, _ = await self._load_patient(patient_id)
            pid = (patient or {}).get("_id") or patient_id
        if not pid:
            return None

        monitor_codes = ["param_HR", "param_resp", "param_ibp_m", "param_nibp_m", "param_spo2", "param_T"]
        cap = await self._get_latest_param_snapshot_by_pid(pid, codes=monitor_codes, lookback_minutes=180)
        if not cap:
            monitor_id = device_id or (await self._get_device_id_for_patient(patient, ["monitor"]) if patient else None)
            cap = await self._get_latest_device_cap(monitor_id, codes=monitor_codes) if monitor_id else None

        vitals: dict[str, Any] = {
            "hr": {"value": None, "unit": "bpm", "time": None},
            "rr": {"value": None, "unit": "次/分", "time": None},
            "map": {"value": None, "unit": "mmHg", "time": None},
            "spo2": {"value": None, "unit": "%", "time": None},
            "temp": {"value": None, "unit": "℃", "time": None},
        }
        snapshot_times: list[datetime] = []
        cap_time = _parse_dt((cap or {}).get("time"))
        if isinstance(cap_time, datetime):
            snapshot_times.append(cap_time)
        if cap:
            hr = self._sanitize_context_vital("param_HR", _extract_param(cap, "param_HR"))
            rr = self._sanitize_context_vital("param_resp", _extract_param(cap, "param_resp"))
            map_value = self._sanitize_context_vital("param_map", self._get_map(cap))
            spo2 = self._sanitize_context_vital("param_spo2", _extract_param(cap, "param_spo2"))
            temp = self._sanitize_context_vital("param_T", _extract_param(cap, "param_T"))
            for key, value_num, unit in [
                ("hr", hr, "bpm"),
                ("rr", rr, "次/分"),
                ("map", map_value, "mmHg"),
                ("spo2", spo2, "%"),
                ("temp", temp, "℃"),
            ]:
                if value_num is not None:
                    vitals[key] = {"value": value_num, "unit": unit, "time": cap_time}

        labs_snapshot: dict[str, Any] = {
            "lac": {"value": None, "unit": "mmol/L", "time": None, "raw_name": None},
            "cr": {"value": None, "unit": "μmol/L", "time": None, "raw_name": None},
            "pct": {"value": None, "unit": "ng/mL", "time": None, "raw_name": None},
        }
        his_pid = str((patient or {}).get("hisPid") or "").strip()
        if his_pid:
            labs = await self._get_latest_labs_map(his_pid, lookback_hours=72)
            for key, unit in [("lac", "mmol/L"), ("cr", "μmol/L"), ("pct", "ng/mL")]:
                item = labs.get(key) if isinstance(labs, dict) else None
                if not isinstance(item, dict):
                    continue
                value_num = _parse_number(item.get("value"))
                if value_num is None:
                    continue
                item_time = _parse_dt(item.get("time"))
                if isinstance(item_time, datetime):
                    snapshot_times.append(item_time)
                labs_snapshot[key] = {
                    "value": round(float(value_num), 3),
                    "unit": item.get("unit") or unit,
                    "time": item_time,
                    "raw_name": item.get("raw_name"),
                }

        vasopressors = await self._get_current_vasopressor_snapshot(pid, patient, hours=8, max_items=4)
        for row in vasopressors:
            if isinstance(row.get("time"), datetime):
                snapshot_times.append(row["time"])

        has_vital = any(isinstance(v, dict) and v.get("value") is not None for v in vitals.values())
        has_lab = any(isinstance(v, dict) and v.get("value") is not None for v in labs_snapshot.values())
        if not has_vital and not has_lab and not vasopressors:
            return None

        return {
            "vitals": vitals,
            "labs": labs_snapshot,
            "vasopressors": vasopressors,
            "snapshot_time": max(snapshot_times) if snapshot_times else datetime.now(),
        }

    def _split_explanation_text(self, text: str) -> tuple[str, str | None]:
        raw = str(text or "").strip().strip("；;")
        if not raw:
            return "", None
        for marker in ("；建议：", "；建议:", "建议：", "建议:"):
            if marker in raw:
                left, right = raw.split(marker, 1)
                summary = left.strip("；; ，,。")
                suggestion = right.strip("；; ，,。")
                return summary, suggestion or None
        return raw, None

    def _fallback_suggestion_by_severity(self, severity: str) -> str:
        return {
            "critical": "建议立即床旁复核并启动紧急处置。",
            "high": "建议尽快复核并进行针对性干预。",
            "warning": "建议尽快复评并结合病情调整处理。",
        }.get(str(severity or "").lower(), "建议结合临床情况进一步复核。")

    def _build_alert_explanation(
        self,
        *,
        rule_id: str,
        name: str,
        category: str,
        alert_type: str,
        severity: str,
        parameter: str,
        condition: dict | None,
        value: Any,
        patient_doc: dict | None,
        extra: dict | None,
        context: dict | None = None,
    ) -> str:
        extra = extra if isinstance(extra, dict) else {}
        context = context if isinstance(context, dict) else {}
        alert_type = str(alert_type or "").lower()
        severity = str(severity or "").lower()

        if alert_type == "qsofa":
            qsofa = value if value is not None else condition.get("qsofa") if isinstance(condition, dict) else None
            reasons: list[str] = []
            sbp = extra.get("sbp")
            rr = extra.get("rr")
            gcs = extra.get("gcs")
            if sbp is not None and float(sbp) <= 100:
                reasons.append(f"SBP {self._format_alert_measure(sbp, 'mmHg', 0)}↓")
            if rr is not None and float(rr) >= 22:
                reasons.append(f"RR {self._format_alert_measure(rr, '次/分', 0)}↑")
            if gcs is not None and float(gcs) < 15:
                reasons.append(f"GCS {self._format_alert_number(gcs, 0)}↓")

            labs = context.get("labs") or {}
            pct = labs.get("pct", {}).get("value")
            lac = labs.get("lac", {}).get("value")
            pct_ratio = context.get("pct_ratio_vs_prev")
            lac_ratio = context.get("lac_ratio_vs_prev")
            lab_parts: list[str] = []
            if pct is not None:
                pct_text = f"PCT {self._format_alert_measure(pct, 'ng/mL')}"
                if pct_ratio and pct_ratio >= 1.2:
                    pct_text += f"（较前值升高{self._format_alert_number(pct_ratio, 1)}倍）"
                lab_parts.append(pct_text)
            if lac is not None:
                lac_text = f"乳酸 {self._format_alert_measure(lac, 'mmol/L')}"
                if lac_ratio and lac_ratio >= 1.2:
                    lac_text += f"（较前值升高{self._format_alert_number(lac_ratio, 1)}倍）"
                lab_parts.append(lac_text)

            reason_text = " + ".join(reasons) if reasons else "存在感染相关器官功能恶化线索"
            lab_text = f"，结合{'、'.join(lab_parts)}" if lab_parts else ""
            return (
                f"该患者 qSOFA = {self._format_alert_number(qsofa, 0)}（{reason_text}）{lab_text}，"
                "需警惕脓毒症可能；建议：复测乳酸、完善血培养并评估感染灶，必要时启动 1h Bundle。"
            )

        if alert_type == "sofa":
            sofa = extra.get("score") if extra.get("score") is not None else value
            delta = extra.get("delta") if extra.get("delta") is not None else condition.get("delta") if isinstance(condition, dict) else None
            components = extra.get("components") if isinstance(extra.get("components"), dict) else {}
            organ_bits: list[str] = []
            organ_map = {
                "resp": "呼吸",
                "coag": "凝血",
                "liver": "肝脏",
                "cardio": "循环",
                "neuro": "神经",
                "renal": "肾脏",
            }
            for key, label in organ_map.items():
                score = components.get(key)
                if score is not None and float(score) > 0:
                    organ_bits.append(f"{label}{self._format_alert_number(score, 0)}分")
            organ_text = f"，主要受{'、'.join(organ_bits[:3])}影响" if organ_bits else ""
            return (
                f"SOFA {self._format_alert_number(sofa, 0)} 分，较基线增加 {self._format_alert_number(delta, 0)} 分{organ_text}，"
                "提示器官功能恶化；若合并感染证据，支持脓毒症诊断，建议尽快完成感染源评估与复苏处置。"
            )

        if alert_type == "septic_shock":
            sofa = ((extra.get("sofa") or {}) if isinstance(extra.get("sofa"), dict) else {})
            lactate = condition.get("lactate") if isinstance(condition, dict) else None
            map_value = condition.get("map") if isinstance(condition, dict) else None
            vaso = condition.get("vasopressor") if isinstance(condition, dict) else None
            return (
                f"当前存在{'血管活性药支持' if vaso else '循环支持需求'}，"
                f"乳酸 {self._format_alert_measure(lactate, 'mmol/L')}、MAP {self._format_alert_measure(map_value, 'mmHg', 0)}，"
                f"并伴 SOFA {self._format_alert_number(sofa.get('score'), 0)} 分，提示脓毒性休克高危；"
                "建议：立即复苏、持续监测灌注并升级感染控制策略。"
            )

        if alert_type == "ards":
            pf = value if value is not None else extra.get("pf_ratio")
            pao2 = extra.get("pao2")
            fio2 = extra.get("fio2")
            peep = extra.get("peep")
            return (
                f"P/F {self._format_alert_number(pf, 0)}，PaO₂ {self._format_alert_measure(pao2, 'mmHg', 0)}，"
                f"FiO₂ {self._format_alert_measure(fio2, '%', 0)}，PEEP {self._format_alert_measure(peep, 'cmH₂O', 0)}，"
                "提示氧合受损；建议执行肺保护通气并复核影像/液体负荷。"
            )

        if alert_type == "aki":
            current = extra.get("current")
            baseline = extra.get("baseline")
            cond = extra.get("condition") if isinstance(extra.get("condition"), dict) else {}
            return (
                f"当前 AKI {self._format_alert_number(extra.get('stage') or value, 0)} 期，"
                f"肌酐 {self._format_alert_measure(current, 'umol/L', 0)}，基线 {self._format_alert_measure(baseline, 'umol/L', 0)}，"
                f"并伴尿量线索（6h {cond.get('urine_6h_ml_kg_h') or '—'} mL/kg/h）；"
                "建议复核容量状态、停评肾毒性药物并追踪尿量。"
            )

        if alert_type == "lab_threshold":
            raw_name = extra.get("raw_name") or parameter or name
            unit = extra.get("unit") or ""
            correction_plan = extra.get("correction_plan") if isinstance(extra.get("correction_plan"), dict) else {}
            action_text = ""
            actions = correction_plan.get("actions")
            if isinstance(actions, list) and actions:
                action_text = f"；建议：{'；'.join(str(a) for a in actions[:3])}"
            elif correction_plan.get("title"):
                action_text = f"；建议：{correction_plan.get('title')}"
            return (
                f"{raw_name} {self._format_alert_measure(value, unit)}，"
                f"触发条件为 {self._format_condition_text(condition, value)}，提示存在实验室异常需要及时复核{action_text}。"
            )

        if alert_type == "trend_analysis":
            trend = extra.get("trend") if isinstance(extra.get("trend"), dict) else {}
            recent_values = extra.get("recent_values") if isinstance(extra.get("recent_values"), list) else []
            recent = " → ".join(self._format_alert_number(v, 1) for v in recent_values[-4:] if _parse_number(v) is not None)
            recent_text = f"，近4次为 {recent}" if recent else ""
            return (
                f"{parameter or name} 近期呈 {trend.get('direction') or '波动'} 趋势，"
                f"斜率 {self._format_alert_number(trend.get('slope'), 2)}{recent_text}，"
                "提示病情正在持续变化，建议结合原发病与干预后反应复核。"
            )

        if alert_type == "liberation_bundle":
            red_items = extra.get("red_items") if isinstance(extra.get("red_items"), list) else []
            yellow_items = extra.get("yellow_items") if isinstance(extra.get("yellow_items"), list) else []
            missing = red_items[:]
            if len(missing) < 3:
                missing.extend(yellow_items[: max(0, 3 - len(missing))])
            item_text = "、".join(str(x) for x in missing if x) or "多项 Bundle 环节"
            return f"ABCDEF Bundle 中 {item_text} 未按时完成，提示护理/镇静/活动流程存在延迟；建议本班次尽快补齐并记录原因。"

        if alert_type == "fluid_balance":
            windows = extra.get("windows") if isinstance(extra.get("windows"), dict) else {}
            win24 = windows.get("24h") if isinstance(windows.get("24h"), dict) else {}
            return (
                f"24h 净平衡 {self._format_alert_measure(win24.get('net_ml'), 'mL', 0)}，"
                f"约占体重 {self._format_alert_measure(win24.get('pct_body_weight'), '%')}，"
                "提示容量负荷偏离目标；建议结合肺部影像、尿量及血流动力学重新评估补液/利尿策略。"
            )

        if alert_type == "delirium_risk":
            factors = extra.get("factors") if isinstance(extra.get("factors"), list) else []
            factor_text = "、".join(str((f or {}).get("factor") or "") for f in factors[:3] if isinstance(f, dict) and (f or {}).get("factor"))
            if factor_text:
                factor_text = f"主要因素包括 {factor_text}；"
            return f"当前谵妄风险评分 {self._format_alert_number(value, 0)}，{factor_text}建议复核镇静深度、睡眠节律及 CAM-ICU。"

        if alert_type == "ai_risk":
            primary = extra.get("primary_risk") or name
            evidence = extra.get("deterioration_signals") if isinstance(extra.get("deterioration_signals"), list) else []
            evidence_text = "；".join(str(x) for x in evidence[:2] if x)
            return f"AI 评估提示 {primary} 风险升高{f'：{evidence_text}' if evidence_text else ''}；建议结合证据脚注与临床现况复核后处置。"

        condition_text = self._format_condition_text(condition, value)
        severity_hint = {
            "critical": "需立即处置",
            "high": "需尽快干预",
            "warning": "建议尽快复核",
            "normal": "建议持续观察",
        }.get(severity, "建议结合病情复核")
        if condition_text:
            return f"{name} 已触发：{parameter or rule_id} {condition_text}，当前值 {value if value is not None else '—'}；{severity_hint}并结合原发病进行针对性处理。"
        return f"{name} 已触发，提示当前病情存在 {category or alert_type} 风险；{severity_hint}。"

    def _build_alert_explanation_evidence(
        self,
        *,
        alert_type: str,
        parameter: str,
        value: Any,
        extra: dict | None,
        context: dict | None,
    ) -> list[str]:
        extra = extra if isinstance(extra, dict) else {}
        context = context if isinstance(context, dict) else {}
        alert_type = str(alert_type or "").lower()
        evidence: list[str] = []

        if parameter and value is not None:
            evidence.append(f"{parameter}={value}")

        factors = extra.get("factors") if isinstance(extra.get("factors"), list) else []
        for factor in factors[:4]:
            if not isinstance(factor, dict):
                continue
            ev = str(factor.get("evidence") or "").strip()
            if ev:
                evidence.append(ev)

        if alert_type == "qsofa":
            for label, key, cond in (("SBP", "sbp", lambda x: x <= 100), ("RR", "rr", lambda x: x >= 22), ("GCS", "gcs", lambda x: x < 15)):
                raw = extra.get(key)
                if raw is None:
                    continue
                try:
                    fv = float(raw)
                except Exception:
                    continue
                if cond(fv):
                    evidence.append(f"{label} {raw}")
            labs = context.get("labs") or {}
            pct = ((labs.get("pct") or {}) if isinstance(labs.get("pct"), dict) else {}).get("value")
            lac = ((labs.get("lac") or {}) if isinstance(labs.get("lac"), dict) else {}).get("value")
            if pct is not None:
                ratio = context.get("pct_ratio_vs_prev")
                evidence.append(f"PCT {pct}" + (f"（较前{ratio}倍）" if ratio else ""))
            if lac is not None:
                ratio = context.get("lac_ratio_vs_prev")
                evidence.append(f"乳酸 {lac}" + (f"（较前{ratio}倍）" if ratio else ""))

        elif alert_type == "sofa":
            components = extra.get("components") if isinstance(extra.get("components"), dict) else {}
            for key, label in {"resp": "呼吸", "coag": "凝血", "liver": "肝脏", "cardio": "循环", "neuro": "神经", "renal": "肾脏"}.items():
                if components.get(key) is not None:
                    evidence.append(f"{label}{components.get(key)}分")

        elif alert_type == "ai_risk":
            signals = extra.get("deterioration_signals") if isinstance(extra.get("deterioration_signals"), list) else []
            evidence.extend(str(x) for x in signals[:4] if str(x).strip())

        elif alert_type == "pe_suspected":
            matched = extra.get("matched_criteria") if isinstance(extra.get("matched_criteria"), list) else []
            if matched:
                evidence.append("匹配条件：" + "、".join(str(x) for x in matched))
            spo2 = extra.get("spo2_drop") if isinstance(extra.get("spo2_drop"), dict) else {}
            if spo2.get("drop") is not None:
                evidence.append(f"SpO₂下降 {spo2.get('drop')}% ({spo2.get('from')}→{spo2.get('to')})")
            hr = extra.get("hr_change") if isinstance(extra.get("hr_change"), dict) else {}
            if hr.get("latest") is not None:
                evidence.append(f"HR {hr.get('baseline')}→{hr.get('latest')}")
            if extra.get("ddimer") is not None:
                evidence.append(f"D-Dimer {extra.get('ddimer')} mg/L")

        elif alert_type == "postop_bleeding":
            hb = extra.get("hb_trend") if isinstance(extra.get("hb_trend"), dict) else {}
            if hb.get("drop") is not None:
                evidence.append(f"Hb下降 {hb.get('drop')} g/L")
            if extra.get("map") is not None:
                evidence.append(f"MAP {extra.get('map')} mmHg")
            if extra.get("hr") is not None:
                evidence.append(f"HR {extra.get('hr')} 次/分")
            drain = extra.get("drain_volume") if isinstance(extra.get("drain_volume"), dict) else {}
            if drain.get("total_6h_ml") is not None:
                evidence.append(f"近6h引流 {drain.get('total_6h_ml')} mL")

        elif alert_type == "postop_infection_resurgence":
            tp = extra.get("temperature_pattern") if isinstance(extra.get("temperature_pattern"), dict) else {}
            if tp.get("low") is not None and tp.get("rebound") is not None:
                evidence.append(f"体温V型反转 {tp.get('low')}→{tp.get('rebound')}℃")
            wbc = extra.get("wbc") if isinstance(extra.get("wbc"), dict) else {}
            if wbc.get("latest") is not None:
                evidence.append(f"WBC {wbc.get('latest')}")
            crp = extra.get("crp") if isinstance(extra.get("crp"), dict) else {}
            if crp.get("latest") is not None:
                evidence.append(f"CRP {crp.get('latest')}")

        elif alert_type == "postop_ileus":
            reasons = extra.get("reasons") if isinstance(extra.get("reasons"), list) else []
            evidence.extend(str(x) for x in reasons[:4] if str(x).strip())

        elif alert_type == "ecash_pain_uncontrolled":
            drugs = extra.get("current_analgesics") if isinstance(extra.get("current_analgesics"), list) else []
            if drugs:
                evidence.append("当前镇痛药：" + "、".join(str(x) for x in drugs[:4]))

        elif alert_type == "ecash_rass_off_target":
            if extra.get("latest_rass") is not None:
                evidence.append(f"RASS {extra.get('latest_rass')}")
            if extra.get("target_range") is not None:
                evidence.append(f"目标范围 {extra.get('target_range')}")

        elif alert_type == "ecash_sat_stress_reaction":
            sat_window = extra.get("sat_window") if isinstance(extra.get("sat_window"), dict) else {}
            if sat_window.get("baseline_rass") is not None and sat_window.get("latest_rass") is not None:
                evidence.append(f"SAT中 RASS {sat_window.get('baseline_rass')}→{sat_window.get('latest_rass')}")
            matched_signals = extra.get("matched_signals") if isinstance(extra.get("matched_signals"), list) else []
            evidence.extend(str(x) for x in matched_signals[:3] if str(x).strip())
            if extra.get("map") is not None:
                evidence.append(f"MAP {extra.get('map')} mmHg")
            if extra.get("sbp") is not None:
                evidence.append(f"SBP {extra.get('sbp')} mmHg")
            if extra.get("hr") is not None:
                evidence.append(f"HR {extra.get('hr')} 次/分")
            if extra.get("new_arrhythmia"):
                evidence.append("SAT期间新发心律失常")

        elif alert_type == "icu_aw_risk":
            if extra.get("risk_score") is not None:
                evidence.append(f"ICU-AW评分 {extra.get('risk_score')}")
            if extra.get("ventilation_days") is not None:
                evidence.append(f"机械通气 {extra.get('ventilation_days')} 天")
            if extra.get("sedative_days") is not None:
                evidence.append(f"镇静药暴露 {extra.get('sedative_days')} 天")
            if extra.get("immobility_hours") is not None:
                evidence.append(f"卧床 {extra.get('immobility_hours')} h")

        elif alert_type == "early_mobility_recommendation":
            if extra.get("recommended_level") is not None:
                evidence.append(f"建议活动等级 L{extra.get('recommended_level')}")
            if extra.get("immobility_hours") is not None:
                evidence.append(f"持续卧床 {extra.get('immobility_hours')} h")
            readiness = extra.get("mobility_readiness") if isinstance(extra.get("mobility_readiness"), dict) else {}
            if readiness.get("fio2_fraction") is not None or readiness.get("peep") is not None:
                evidence.append(f"FiO₂/PEEP {readiness.get('fio2_fraction')} / {readiness.get('peep')}")

        elif alert_type == "fluid_responsiveness_lost":
            map_info = extra.get("map") if isinstance(extra.get("map"), dict) else {}
            lac_info = extra.get("lactate") if isinstance(extra.get("lactate"), dict) else {}
            if extra.get("intake_6h_ml") is not None:
                evidence.append(f"6h入量 {extra.get('intake_6h_ml')} mL")
            if map_info.get("change") is not None:
                evidence.append(f"MAP变化 {map_info.get('change')} mmHg")
            if lac_info.get("ratio") is not None:
                evidence.append(f"乳酸比值 {lac_info.get('ratio')}")

        elif alert_type == "fluid_deresuscitation":
            if extra.get("percent_fluid_overload") is not None:
                evidence.append(f"%FO {extra.get('percent_fluid_overload')}%")
            if extra.get("net_24h_ml") is not None:
                evidence.append(f"24h净平衡 {extra.get('net_24h_ml')} mL")
            lac_info = extra.get("lactate") if isinstance(extra.get("lactate"), dict) else {}
            if lac_info.get("latest") is not None:
                evidence.append(f"乳酸 {lac_info.get('baseline')}→{lac_info.get('latest')}")

        elif alert_type in {"sepsis_abx_overdue_1h", "sepsis_abx_overdue_3h"}:
            if extra.get("elapsed_minutes") is not None:
                evidence.append(f"已延迟 {extra.get('elapsed_minutes')} 分钟")
            if extra.get("bundle_started_at") is not None:
                evidence.append(f"起点 {extra.get('bundle_started_at')}")
            sources = extra.get("source_rules") if isinstance(extra.get("source_rules"), list) else []
            if sources:
                evidence.append("触发来源：" + " / ".join(str(x) for x in sources[:3]))

        elif alert_type == "cardiac_arrest_risk":
            snapshots = extra.get("snapshots") if isinstance(extra.get("snapshots"), dict) else {}
            for key in ("hr", "sbp", "map", "k", "ica", "lac_latest", "qrs_duration"):
                if snapshots.get(key) is not None:
                    evidence.append(f"{key}={snapshots.get(key)}")

        # 去重与截断
        deduped: list[str] = []
        seen: set[str] = set()
        for item in evidence:
            s = str(item or "").strip()
            if not s:
                continue
            if s in seen:
                continue
            seen.add(s)
            deduped.append(s)
        return deduped[:5]

    def _format_structured_explanation_text(self, payload: dict[str, Any]) -> str:
        summary = str(payload.get("summary") or "").strip()
        evidence = payload.get("evidence") if isinstance(payload.get("evidence"), list) else []
        suggestion = str(payload.get("suggestion") or "").strip()
        parts: list[str] = []
        if summary:
            parts.append(summary.rstrip("；;。") + "。")
        if evidence:
            ev = "；".join(str(x).strip().rstrip("；;。") for x in evidence if str(x).strip())
            if ev:
                parts.append(f"依据：{ev}。")
        if suggestion:
            parts.append(f"建议：{suggestion.rstrip('；;。')}。")
        return " ".join(parts).strip()

    async def _polish_structured_alert_explanation(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return payload
        summary = str(payload.get("summary") or "").strip()
        evidence = payload.get("evidence") if isinstance(payload.get("evidence"), list) else []
        suggestion = str(payload.get("suggestion") or "").strip()
        if not summary:
            payload["text"] = self._format_structured_explanation_text(payload)
            return payload

        try:
            model = self.config.llm_fallback_model or self.config.llm_model_medical or self.config.settings.LLM_MODEL
            if not model:
                payload["text"] = self._format_structured_explanation_text(payload)
                return payload
            result = await call_llm_chat(
                cfg=self.config,
                system_prompt=(
                    "你是ICU临床预警解释润色助手。"
                    "请将给定结构化解释润色成更自然、更简洁的临床中文。"
                    "必须保留原始医学事实，不新增未提供的数据。"
                    "输出严格JSON对象，字段仅包含 summary, suggestion。"
                ),
                user_prompt=json.dumps(
                    {
                        "summary": summary,
                        "evidence": evidence,
                        "suggestion": suggestion,
                    },
                    ensure_ascii=False,
                ),
                model=model,
                temperature=0.1,
                max_tokens=220,
                timeout_seconds=12,
            )
            text = str((result or {}).get("text") or "").strip()
            if text:
                match = re.search(r"\{[\s\S]*\}", text)
                if match:
                    parsed = json.loads(match.group(0))
                    if isinstance(parsed, dict):
                        polished_summary = str(parsed.get("summary") or "").strip()
                        polished_suggestion = str(parsed.get("suggestion") or "").strip()
                        if polished_summary:
                            payload["summary"] = polished_summary
                        if polished_suggestion:
                            payload["suggestion"] = polished_suggestion
                        payload["polished_by_llm"] = True
                        payload["llm_model"] = (result or {}).get("model")
        except Exception as e:
            logger.debug(f"预警解释LLM润色失败: {e}")

        payload["text"] = self._format_structured_explanation_text(payload)
        return payload

    async def _generate_alert_explanation(
        self,
        *,
        rule_id,
        name,
        category,
        alert_type,
        severity,
        parameter,
        condition,
        value,
        patient_id,
        patient_doc,
        extra,
    ) -> dict[str, Any]:
        context = await self._collect_explanation_context(
            patient_doc=patient_doc,
            patient_id=patient_id,
            alert_type=alert_type,
            extra=extra,
        )
        raw_text = self._build_alert_explanation(
            rule_id=rule_id,
            name=name,
            category=category,
            alert_type=alert_type,
            severity=severity,
            parameter=parameter,
            condition=condition,
            value=value,
            patient_doc=patient_doc,
            extra=extra,
            context=context,
        )
        summary, suggestion = self._split_explanation_text(raw_text)
        payload = {
            "summary": summary or raw_text,
            "evidence": self._build_alert_explanation_evidence(
                alert_type=str(alert_type or ""),
                parameter=str(parameter or ""),
                value=value,
                extra=extra,
                context=context,
            ),
            "suggestion": suggestion or self._fallback_suggestion_by_severity(str(severity or "")),
            "text": "",
        }
        return await self._polish_structured_alert_explanation(payload)

    async def _create_alert(
        self, *, rule_id, name, category, alert_type, severity,
        parameter, condition, value, patient_id, patient_doc,
        device_id=None, source_time=None, extra=None, explanation: Any | None = None,
    ) -> dict | None:
        now = datetime.now()
        severity_l = str(severity or "").lower()
        extra_payload = dict(extra) if isinstance(extra, dict) else ({"raw_extra": extra} if extra is not None else {})
        if severity_l in {"high", "critical"} and "context_snapshot" not in extra_payload:
            try:
                context_snapshot = await self._build_alert_context_snapshot(
                    patient_id=patient_id,
                    patient_doc=patient_doc,
                    device_id=device_id,
                )
                if context_snapshot:
                    extra_payload["context_snapshot"] = context_snapshot
            except Exception as e:
                logger.debug(f"生成预警上下文快照失败: {e}")
        extra = extra_payload or None
        if explanation is None:
            try:
                explanation = await self._generate_alert_explanation(
                    rule_id=rule_id,
                    name=name,
                    category=category,
                    alert_type=alert_type,
                    severity=severity,
                    parameter=parameter,
                    condition=condition,
                    value=value,
                    patient_id=patient_id,
                    patient_doc=patient_doc,
                    extra=extra,
                )
            except Exception as e:
                logger.debug(f"生成预警解释失败: {e}")
                explanation = None
        alert_doc = {
            "rule_id": rule_id,
            "name": name,
            "category": category,
            "alert_type": alert_type,
            "severity": severity,
            "parameter": parameter,
            "condition": condition,
            "value": value,
            "patient_id": patient_id,
            "patient_name": patient_doc.get("name") if patient_doc else None,
            "bed": patient_doc.get("hisBed") if patient_doc else None,
            "dept": patient_doc.get("dept") or patient_doc.get("hisDept") if patient_doc else None,
            "deptCode": patient_doc.get("deptCode") if patient_doc else None,
            "device_id": device_id,
            "source_time": source_time,
            "created_at": now,
            "is_active": True,
            }
        if extra:
            alert_doc["extra"] = extra
        if explanation:
            if isinstance(explanation, str):
                explanation = {
                    "summary": explanation,
                    "evidence": [],
                    "suggestion": None,
                    "text": explanation,
                }
            if isinstance(explanation, dict):
                if not explanation.get("text"):
                    explanation["text"] = self._format_structured_explanation_text(explanation)
                alert_doc["explanation"] = explanation
                alert_doc["explanation_text"] = explanation.get("text")
            else:
                alert_doc["explanation"] = explanation

        if hasattr(self, "_alert_intelligence_intercept"):
            try:
                alert_doc = await self._alert_intelligence_intercept(alert_doc, patient_doc)
            except Exception as e:
                logger.debug(f"报警智能拦截失败: {e}")
            if not alert_doc:
                return None

        try:
            res = await self.db.col("alert_records").insert_one(alert_doc)
            alert_doc["_id"] = res.inserted_id
            if hasattr(self, "_after_alert_persisted"):
                try:
                    await self._after_alert_persisted(alert_doc, patient_doc)
                except Exception as e:
                    logger.debug(f"报警持久化后处理失败: {e}")
            await self._broadcast_alert(alert_doc)
            return alert_doc
        except Exception as e:
            logger.error(f"写入预警记录失败: {e}")
            return None

    async def _create_assessment_alert(self, reminder_doc: dict) -> None:
        score_type = reminder_doc.get("score_type")
        alert_doc = {
            "rule_id": reminder_doc.get("rule_id") or f"NURSE_{score_type}",
            "name": reminder_doc.get("name") or f"{str(score_type or '').upper()}评估超时",
            "category": "assessments",
            "parameter": reminder_doc.get("code"),
            "condition": {"operator": "overdue"},
            "severity": reminder_doc.get("severity", "warning"),
            "alert_type": "nurse_reminder",
            "patient_id": reminder_doc.get("patient_id"),
            "patient_name": reminder_doc.get("patient_name"),
            "bed": reminder_doc.get("bed"),
            "dept": reminder_doc.get("dept"),
            "deptCode": reminder_doc.get("deptCode"),
            "value": None,
            "source_time": reminder_doc.get("last_score_time"),
            "created_at": reminder_doc.get("created_at"),
            "is_active": True,
            "related_id": reminder_doc.get("_id"),
        }
        if reminder_doc.get("extra") is not None:
            alert_doc["extra"] = reminder_doc.get("extra")
        try:
            res = await self.db.col("alert_records").insert_one(alert_doc)
            alert_doc["_id"] = res.inserted_id
            await self._broadcast_alert(alert_doc)
        except Exception as e:
            logger.error(f"写入护理提醒失败: {e}")

    async def _broadcast_alert(self, alert_doc: dict) -> None:
        if not self.ws:
            return
        if hasattr(self, "_should_broadcast_alert"):
            try:
                if not self._should_broadcast_alert(alert_doc):
                    return
            except Exception as e:
                logger.debug(f"报警广播策略判定失败: {e}")
        try:
            roles = alert_doc.get("route_targets")
            if not roles:
                extra = alert_doc.get("extra") if isinstance(alert_doc.get("extra"), dict) else {}
                roles = extra.get("route_targets")
            await self.ws.broadcast({"type": "alert", "data": alert_doc}, roles=roles)
        except Exception as e:
            logger.warning(f"WebSocket 广播失败: {e}")

    async def _is_suppressed(self, patient_id: str, rule_id: str | None, same_rule_seconds: int, max_per_hour: int) -> bool:
        if not rule_id:
            return False
        now = datetime.now()
        if same_rule_seconds > 0:
            since = now - timedelta(seconds=same_rule_seconds)
            cnt = await self.db.col("alert_records").count_documents({
                "patient_id": patient_id,
                "rule_id": rule_id,
                "created_at": {"$gte": since}
            })
            if cnt > 0:
                return True
        if max_per_hour > 0:
            since = now - timedelta(hours=1)
            cnt = await self.db.col("alert_records").count_documents({
                "patient_id": patient_id,
                "created_at": {"$gte": since}
            })
            if cnt >= max_per_hour:
                return True
        return False

    async def _load_patient(self, pid: Any) -> tuple[dict | None, str | None]:
        oid = _safe_oid(pid)
        pid_str = str(oid) if oid else str(pid)
        patient = None
        if oid:
            patient = await self.db.col("patient").find_one({"_id": oid})
        if not patient:
            patient = await self.db.col("patient").find_one({"_id": pid})
        return patient, pid_str

    async def _get_latest_score_time(self, pid_candidates: list, code: str) -> datetime | None:
        pid_strs = [str(p) for p in pid_candidates if p is not None]
        code_map = {
            self._cfg("assessments", "gcs", "code", default="param_score_gcs_obs"): ("gcs", ["gcsScore"]),
            self._cfg("assessments", "rass", "code", default="param_score_rass_obs"): ("rass", ["rass"]),
            self._cfg("assessments", "pain", "code", default="param_tengTong_score"): ("pain", ["painScore", "cpotScore", "cpotScoreV2"]),
            self._cfg("assessments", "cpot", "code", default="param_score_cpot"): ("cpot", ["cpotScore", "cpotScoreV2", "cpot", "CPOT"]),
            self._cfg("assessments", "bps", "code", default="param_score_bps"): ("bps", ["bpsScore", "bps", "BPS"]),
            self._cfg("assessments", "delirium", "code", default="param_delirium_score"): ("delirium", ["deliriumScore"]),
            self._cfg("assessments", "braden", "code", default="param_score_braden"): ("braden", ["bradenScore", "bradenNurseScore"]),
        }
        kind, score_types = code_map.get(code, (None, []))

        if kind:
            doc = await self.db.col("score_records").find_one(
                {"patient_id": {"$in": pid_candidates}, "score_type": kind},
                sort=[("calc_time", -1)],
            )
            if doc:
                return _parse_dt(doc.get("calc_time"))

        if score_types and pid_strs:
            doc = await self.db.col("score").find_one(
                {"pid": {"$in": pid_strs}, "scoreType": {"$in": score_types}},
                sort=[("time", -1)],
            )
            if doc:
                return _parse_dt(doc.get("time"))

        if pid_strs:
            doc = await self.db.col("bedside").find_one(
                {"pid": {"$in": pid_strs}, "code": code},
                sort=[("time", -1)],
            )
            if doc:
                return _cap_time(doc)

        return None
