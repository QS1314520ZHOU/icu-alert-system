"""
ICU智能预警系统 - 预警引擎基础工具
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId

logger = logging.getLogger("icu-alert")


# =============================================
# 基础工具函数
# =============================================
def _safe_oid(value: Any) -> ObjectId | None:
    if isinstance(value, ObjectId):
        return value
    if value is None:
        return None
    try:
        return ObjectId(str(value))
    except Exception:
        return None


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _extract_param(doc: dict, key: str) -> float | None:
    """
    从 deviceCap / bedside 文档中提取参数值。
    兼容多种数据结构:
      - doc[key]                    (顶层)
      - doc["params"][key]          (params 字典)
      - doc["params"][key]["value"] (嵌套对象)
    """
    # 单参数文档（code + 数值）
    if doc.get("code") == key:
        for v in (doc.get("fVal"), doc.get("intVal"), doc.get("strVal"), doc.get("value")):
            try:
                return float(v)
            except (TypeError, ValueError):
                continue
    v = doc.get(key)
    if v is None:
        params = doc.get("params", {})
        if isinstance(params, dict):
            v = params.get(key)
    if isinstance(v, dict):
        v = v.get("value", v.get("v"))
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _eval_condition(value: float | None, condition: dict) -> bool:
    """评估单条规则条件"""
    if value is None:
        return False
    op = condition.get("operator")
    thr = condition.get("threshold")
    lo = condition.get("min")
    hi = condition.get("max")
    try:
        if op == ">":
            return value > float(thr)
        if op == ">=":
            return value >= float(thr)
        if op == "<":
            return value < float(thr)
        if op == "<=":
            return value <= float(thr)
        if op in ("==", "="):
            return value == float(thr)
        if op == "!=":
            return value != float(thr)
        if op == "between":
            return float(lo) <= value <= float(hi)
        if op == "outside":
            return value < float(lo) or value > float(hi)
    except Exception:
        return False
    return False


def _detect_trend(values: list[float], window: int = 5) -> dict:
    """
    分析最近 N 个采样点的趋势。
    返回 {"direction": "rising"|"falling"|"stable", "slope": float, "volatility": float}
    """
    if len(values) < 2:
        return {"direction": "stable", "slope": 0.0, "volatility": 0.0}

    recent = values[-window:] if len(values) >= window else values
    n = len(recent)

    x_mean = (n - 1) / 2
    y_mean = sum(recent) / n
    num = sum((i - x_mean) * (recent[i] - y_mean) for i in range(n))
    den = sum((i - x_mean) ** 2 for i in range(n))
    slope = num / den if den != 0 else 0.0

    volatility = (sum((v - y_mean) ** 2 for v in recent) / n) ** 0.5

    if slope > 0.5:
        direction = "rising"
    elif slope < -0.5:
        direction = "falling"
    else:
        direction = "stable"

    return {"direction": direction, "slope": round(slope, 3), "volatility": round(volatility, 2)}

# =============================================
# 检验结果解析工具
# =============================================
_LAB_TESTS_ORDERED = [
    ("ph", {"keywords": ["ph", "酸碱度"], "unit": ""}),
    ("pco2", {"keywords": ["paco2", "pco2", "二氧化碳分压"], "unit": "mmHg"}),
    ("hco3", {"keywords": ["hco3", "碳酸氢根", "标准碳酸氢根", "实际碳酸氢根"], "unit": "mmol/L"}),
    ("ica", {"keywords": ["离子钙", "离子鈣", "ionized calcium", "ica", "ica²⁺"], "unit": "mmol/L"}),
    ("ca", {"keywords": ["总钙", "钙", "calcium", "ca"], "unit": "mmol/L"}),
    ("k", {"keywords": ["钾", "potassium", "k+"], "unit": "mmol/L"}),
    ("na", {"keywords": ["钠", "sodium", "na+"], "unit": "mmol/L"}),
    ("cl", {"keywords": ["氯", "chloride", "cl-"], "unit": "mmol/L"}),
    ("lac", {"keywords": ["乳酸", "lactate", "lac"], "unit": "mmol/L"}),
    ("mg", {"keywords": ["镁", "magnesium", "mg"], "unit": "mg/dL"}),
    ("po4", {"keywords": ["磷", "无机磷", "血磷", "phosphate", "phos", "po4"], "unit": "mg/dL"}),
    ("albumin", {"keywords": ["白蛋白", "albumin", "alb"], "unit": "g/L"}),
    ("glu", {"keywords": ["葡萄糖", "血糖", "glucose", "glu"], "unit": "mmol/L"}),
    ("hb", {"keywords": ["血红蛋白", "血紅蛋白", "hemoglobin", "hb"], "unit": "g/L"}),
    ("plt", {"keywords": ["血小板", "platelet", "plt"], "unit": "10^9/L"}),
    ("cr", {"keywords": ["肌酐", "creatinine", "cr"], "unit": "umol/L"}),
    ("egfr", {"keywords": ["egfr", "估算肾小球滤过率", "肾小球滤过率"], "unit": "mL/min/1.73m2"}),
    ("pct", {"keywords": ["降钙素原", "pct", "procalcitonin"], "unit": "ng/mL"}),
    ("inr", {"keywords": ["inr"], "unit": ""}),
    ("pt", {"keywords": ["凝血酶原时间", "pt"], "unit": "s"}),
    ("fib", {"keywords": ["纤维蛋白原", "fibrinogen", "fib"], "unit": "g/L"}),
    ("ddimer", {"keywords": ["d-dimer", "d二聚体", "d-二聚体", "fdp"], "unit": "mg/L"}),
    ("alt", {"keywords": ["谷丙转氨酶", "丙氨酸氨基转移酶", "alanine aminotransferase", "alt"], "unit": "U/L"}),
    ("ast", {"keywords": ["谷草转氨酶", "天门冬氨酸氨基转移酶", "aspartate aminotransferase", "ast"], "unit": "U/L"}),
    ("act", {"keywords": ["act", "活化凝血时间"], "unit": "s"}),
    ("trop", {"keywords": ["肌钙蛋白", "troponin"], "unit": ""}),
    ("bnp", {"keywords": ["bnp", "nt-probnp", "ntprobnp"], "unit": "pg/mL"}),
    ("bil", {"keywords": ["胆红素", "bilirubin", "tbil"], "unit": "umol/L"}),
    ("pao2", {"keywords": ["pao2", "po2", "氧分压"], "unit": "mmHg"}),
]


def _parse_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    s = s.replace("≥", "").replace("≤", "").replace(">", "").replace("<", "").strip()
    if s.lower() in ("neg", "negative", "trace", "无", "阴性", "阳性"):
        return None
    m = re.search(r"[-+]?\d+(\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None


def _normalize_bed(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = s.upper().replace("床", "")
    if s.startswith("BED"):
        s = s[3:]
    s = s.strip()
    m = re.search(r"\d+", s)
    if m:
        try:
            return str(int(m.group(0)))
        except Exception:
            return m.group(0)
    return s


def _bed_match(a: Any, b: Any) -> bool:
    na = _normalize_bed(a)
    nb = _normalize_bed(b)
    if not na or not nb:
        return False
    return na == nb


def _cap_time(doc: dict) -> datetime | None:
    return _parse_dt(doc.get("time")) or _parse_dt(doc.get("recordTime"))


def _cap_value(doc: dict) -> float | None:
    for key in ("fVal", "intVal", "strVal", "value"):
        num = _parse_number(doc.get(key))
        if num is not None:
            return num
    return None


def _normalize_unit(unit: Any) -> str:
    if unit is None:
        return ""
    return str(unit).strip().lower().replace("μ", "u")


def _convert_lab_value(test_key: str, value: float, unit: str) -> float:
    """必要的单位换算（尽量保守）"""
    u = _normalize_unit(unit)

    if test_key == "cr":
        if "mg/dl" in u:
            return value * 88.4
        return value

    if test_key == "bil":
        if "mg/dl" in u:
            return value * 17.1
        return value

    if test_key == "pao2":
        if "kpa" in u:
            return value * 7.5
        return value

    if test_key == "pco2":
        if "kpa" in u:
            return value * 7.5
        return value

    if test_key == "albumin":
        if "g/dl" in u:
            return value * 10.0
        return value

    if test_key == "po4":
        if "mmol/l" in u:
            return value * 3.1
        return value

    if test_key == "mg":
        if "mmol/l" in u:
            return value * 2.43
        return value

    if test_key == "ddimer":
        # 标准化为 mg/L FEU
        # DDU 单位需 ×2 换算为 FEU（DDU ≈ FEU / 2）
        is_ddu = "ddu" in u
        if "g/l" in u:
            converted = value * 1000.0
            return converted * 2 if is_ddu else converted
        if "mg/dl" in u:
            converted = value * 10.0
            return converted * 2 if is_ddu else converted
        if "ug/l" in u or "ng/ml" in u:
            converted = value / 1000.0
            return converted * 2 if is_ddu else converted
        if "ug/ml" in u:
            return value * 2 if is_ddu else value
        if "ng/l" in u:
            converted = value / 1_000_000.0
            return converted * 2 if is_ddu else converted
        if "mg/l" in u or not u:
            # mg/L 直接使用; 无单位时假定 mg/L（最常见 ICU 报告单位）
            return value * 2 if is_ddu else value
        logger.warning(f"D-Dimer 单位无法识别: '{unit}'，按 mg/L FEU 处理")
        return value

    return value


def _match_lab_test(name: str) -> str | None:
    if not name:
        return None
    n = str(name).lower()
    for k, meta in _LAB_TESTS_ORDERED:
        for kw in meta["keywords"]:
            kw_l = kw.lower()
            if kw_l in n:
                if k == "mg" and not any(x in n for x in ["镁", "magnesium", "血镁"]):
                    continue
                if k == "k" and "肌酐" in n:
                    continue
                return k
    return None


def _lab_time(doc: dict) -> datetime | None:
    return (
        _parse_dt(doc.get("authTime"))
        or _parse_dt(doc.get("collectTime"))
        or _parse_dt(doc.get("requestTime"))
        or _parse_dt(doc.get("reportTime"))
        or _parse_dt(doc.get("resultTime"))
        or _parse_dt(doc.get("time"))
    )

class BaseEngine:
    def __init__(self, db, config, ws_manager=None) -> None:
        self.db = db
        self.config = config
        self.ws = ws_manager
        self._param_codes_all = self._collect_param_codes()

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
        cursor = self.db.dc_col("VI_ICU_EXAM_ITEM").find({"hisPid": his_pid}).sort("authTime", -1).limit(300)
        results: dict = {}
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
        cursor = self.db.dc_col("VI_ICU_EXAM_ITEM").find({"hisPid": his_pid}).sort("authTime", -1).limit(limit)
        series = []
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
            if ratio >= 3 or current["value"] >= 353.6:
                stage = max(stage, 3)
            elif ratio >= 2:
                stage = max(stage, 2)
            elif ratio >= 1.5:
                stage = max(stage, 1)
            condition["ratio"] = ratio

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
    async def _create_alert(
        self, *, rule_id, name, category, alert_type, severity,
        parameter, condition, value, patient_id, patient_doc,
        device_id=None, source_time=None, extra=None,
    ) -> dict | None:
        now = datetime.now()
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

        try:
            res = await self.db.col("alert_records").insert_one(alert_doc)
            alert_doc["_id"] = res.inserted_id
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
        try:
            await self.ws.broadcast({"type": "alert", "data": alert_doc})
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
