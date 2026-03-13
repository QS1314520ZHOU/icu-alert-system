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
    ("ica", {"keywords": ["离子钙", "离子鈣", "ionized calcium", "ica", "ica²⁺"], "unit": "mmol/L"}),
    ("ca", {"keywords": ["总钙", "钙", "calcium", "ca"], "unit": "mmol/L"}),
    ("k", {"keywords": ["钾", "potassium", "k+"], "unit": "mmol/L"}),
    ("na", {"keywords": ["钠", "sodium", "na+"], "unit": "mmol/L"}),
    ("lac", {"keywords": ["乳酸", "lactate", "lac"], "unit": "mmol/L"}),
    ("glu", {"keywords": ["葡萄糖", "血糖", "glucose", "glu"], "unit": "mmol/L"}),
    ("hb", {"keywords": ["血红蛋白", "血紅蛋白", "hemoglobin", "hb"], "unit": "g/L"}),
    ("plt", {"keywords": ["血小板", "platelet", "plt"], "unit": "10^9/L"}),
    ("cr", {"keywords": ["肌酐", "creatinine", "cr"], "unit": "umol/L"}),
    ("pct", {"keywords": ["降钙素原", "pct", "procalcitonin"], "unit": "ng/mL"}),
    ("inr", {"keywords": ["inr"], "unit": ""}),
    ("pt", {"keywords": ["凝血酶原时间", "pt"], "unit": "s"}),
    ("fib", {"keywords": ["纤维蛋白原", "fibrinogen", "fib"], "unit": "g/L"}),
    ("ddimer", {"keywords": ["d-dimer", "d二聚体", "d-二聚体", "fdp"], "unit": "mg/L"}),
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
            if kw.lower() in n:
                return k
    return None


def _lab_time(doc: dict) -> datetime | None:
    return (
        _parse_dt(doc.get("requestTime"))
        or _parse_dt(doc.get("reportTime"))
        or _parse_dt(doc.get("resultTime"))
        or _parse_dt(doc.get("time"))
    )

class BaseEngine:
    def __init__(self, db, config, ws_manager=None) -> None:
        self.db = db
        self.config = config
        self.ws = ws_manager

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

    async def _get_latest_device_cap(self, device_id: str) -> dict | None:
        if not device_id:
            return None
        return await self.db.col("deviceCap").find_one(
            {"deviceID": device_id},
            sort=[("time", -1)]
        )

    def _get_priority_param(self, cap: dict, keys: list[str]) -> float | None:
        for k in keys:
            v = _extract_param(cap, k)
            if v is not None:
                return v
        return None

    async def _get_latest_vitals_by_patient(self, pid) -> dict:
        bind = await self.db.col("deviceBind").find_one({"pid": pid, "unBindTime": None})
        if not bind:
            return {}
        cap = await self._get_latest_device_cap(bind.get("deviceID"))
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

        cursor = self.db.col("bedside").find(
            {"pid": pid},
            {"recordTime": 1, "params": 1},
        ).sort("recordTime", -1).limit(50)
        async for doc in cursor:
            v = _extract_param(doc, code)
            if v is not None:
                return v
        return None

    async def _get_assessment_series(self, pid, kind: str, hours: int) -> list[dict]:
        code = self._cfg("assessments", kind, "code", default=None)
        if not code:
            return []
        since = datetime.now() - timedelta(hours=hours)
        cursor = self.db.col("bedside").find(
            {"pid": pid, "recordTime": {"$gte": since}},
            {"recordTime": 1, "params": 1},
        ).sort("recordTime", 1)
        points = []
        async for doc in cursor:
            v = _extract_param(doc, code)
            if v is not None:
                points.append({"time": doc.get("recordTime"), "value": v})
        return points

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

        cursor = self.db.col("bedside").find(
            {"pid": pid, "recordTime": {"$gte": start, "$lte": end}},
            {"recordTime": 1, "params": 1},
        ).sort("recordTime", -1).limit(50)
        async for doc in cursor:
            v = _extract_param(doc, code)
            if v is not None:
                return v
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
        doc = await self.db.col("bedside").find_one({"pid": pid}, sort=[("recordTime", -1)])
        if not doc:
            return None
        params = doc.get("params", {})
        left = params.get("param_左瞳孔/光反射") or params.get("左瞳孔") or params.get("pupil_left")
        right = params.get("param_右瞳孔/光反射") or params.get("右瞳孔") or params.get("pupil_right")
        abnormal = False
        text = f"{left} {right}"
        if "不等" in text or "散大" in text or "固定" in text or "迟钝" in text:
            abnormal = True
        if left and right and str(left) != str(right):
            abnormal = True
        return {"left": left, "right": right, "abnormal": abnormal, "time": doc.get("recordTime")}

    async def _get_latest_labs_map(self, his_pid, lookback_hours: int = 72) -> dict:
        since = datetime.now() - timedelta(hours=lookback_hours)
        cursor = self.db.dc_col("VI_ICU_EXAM_ITEM").find({"hisPid": his_pid}).sort("requestTime", -1).limit(300)
        results: dict = {}
        async for doc in cursor:
            t = _lab_time(doc)
            if t and t < since:
                continue
            name = doc.get("itemCnName") or doc.get("itemName") or doc.get("item")
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
                "raw_flag": doc.get("resultFlag") or doc.get("flag") or doc.get("abnormalFlag"),
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
        cursor = self.db.dc_col("VI_ICU_EXAM_ITEM").find({"hisPid": his_pid}).sort("requestTime", -1).limit(limit)
        series = []
        async for doc in cursor:
            t = _lab_time(doc)
            if not t or t < since:
                continue
            if end and t > end:
                continue
            name = doc.get("itemCnName") or doc.get("itemName") or doc.get("item")
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
        cursor = self.db.col("bedside").find(
            {"pid": pid, "recordTime": {"$gte": since}},
            {"recordTime": 1, "params": 1},
        ).sort("recordTime", 1)
        points = []
        async for doc in cursor:
            for code in codes:
                v = _extract_param(doc, code)
                if v is not None:
                    points.append({"time": doc.get("recordTime"), "value": v})
                    break
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
        cursor = self.db.col("drugExe").find(
            {"pid": pid},
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
        alert_doc = {
            "rule_id": f"NURSE_{reminder_doc.get('score_type')}",
            "name": f"{reminder_doc.get('score_type', '').upper()}评估超时",
            "category": "assessments",
            "parameter": reminder_doc.get("code"),
            "condition": {"operator": "overdue"},
            "severity": reminder_doc.get("severity", "warning"),
            "alert_type": "nurse_reminder",
            "patient_id": reminder_doc.get("patient_id"),
            "patient_name": reminder_doc.get("patient_name"),
            "bed": reminder_doc.get("bed"),
            "value": None,
            "source_time": reminder_doc.get("last_score_time"),
            "created_at": reminder_doc.get("created_at"),
            "is_active": True,
            "related_id": reminder_doc.get("_id"),
        }
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
        query = {"pid": {"$in": pid_candidates}, code: {"$exists": True}}
        doc = await self.db.col("bedside").find_one(query, sort=[("recordTime", -1)])
        if not doc:
            return None
        return _parse_dt(doc.get("recordTime"))
