"""AKI 电子表型计算 - KDIGO 2012 定义 (v1.2)。

KDIGO AKI 分期:
  Stage 1: SCr 1.5-1.9x baseline 或升高 >=0.3 mg/dL (26.5 umol/L)
  Stage 2: SCr 2.0-2.9x baseline
  Stage 3: SCr >=3.0x baseline 或 SCr >=4.0 mg/dL (353.6 umol/L) 或开始 RRT
参考: KDIGO Clinical Practice Guideline for Acute Kidney Injury. Kidney Int Suppl. 2012;2(1):1-138.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("icu-alert")

VERSION = "v1.2.0"
RULE_SOURCE = "KDIGO AKI Guideline 2012; Kidney Disease: Improving Global Outcomes"

# 单位转换常数
MG_DL_TO_UMOL_L = 88.4
UMOL_L_TO_MG_DL = 1.0 / 88.4


def _to_umol_l(value: float, unit: str = "") -> float:
    """将肌酐值统一转换为 umol/L。"""
    u = str(unit).strip().lower().replace("μ", "u").replace("µ", "u")
    if "mg/dl" in u:
        return value * MG_DL_TO_UMOL_L
    if "umol" in u or "μmol" in u:
        return value
    # 如果值 < 20，猜测是 mg/dL
    if value < 20:
        return value * MG_DL_TO_UMOL_L
    return value


def _extract_numeric_from_doc(doc: dict) -> tuple[float | None, str]:
    """从 labResult 文档提取肌酐数值和单位。"""
    unit = ""
    for key in ("unit", "units", "referenceUnit"):
        raw_unit = doc.get(key)
        if raw_unit:
            unit = str(raw_unit)
            break

    for key in ("result", "value", "val", "numResult"):
        raw = doc.get(key)
        if raw is None:
            continue
        if isinstance(raw, (int, float)):
            return float(raw), unit
        text = str(raw).strip()
        match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
        if match:
            try:
                return float(match.group(0)), unit
            except ValueError:
                continue
    return None, unit


class AKIPhenotypeCalculator:
    """KDIGO AKI 电子表型计算器。"""

    def __init__(self) -> None:
        self.version = VERSION
        self.rule_source = RULE_SOURCE

    async def calculate(
        self,
        db: Any,
        patient_id: str,
        patient_doc: dict[str, Any] | None = None,
        time_window_hours: int = 48,
    ) -> dict[str, Any]:
        """计算 AKI 电子表型。"""
        now = datetime.now(timezone.utc)
        evidence: list[dict[str, Any]] = []

        # 1. 获取患者文档
        if patient_doc is None:
            from bson import ObjectId
            try:
                patient_doc = await db.col("patient").find_one({"_id": ObjectId(patient_id)})
            except Exception:
                patient_doc = await db.col("patient").find_one({"_id": patient_id})
        if not patient_doc:
            return self._empty_result(now, evidence, "患者文档未找到")

        # 2. 计算基线肌酐
        baseline_cr, baseline_doc = await self._get_baseline_creatinine(db, patient_id, now)
        if baseline_doc:
            evidence.append({
                "component": "baseline_creatinine",
                "value": baseline_cr,
                "unit": "umol/L",
                "source": "labResult",
                "doc_id": str(baseline_doc.get("_id", "")),
                "report_time": str(baseline_doc.get("reportTime", "")),
            })

        # 3. 获取当前肌酐
        current_cr, current_doc = await self._get_current_creatinine(db, patient_id, now, time_window_hours)
        if current_doc:
            evidence.append({
                "component": "current_creatinine",
                "value": current_cr,
                "unit": "umol/L",
                "source": "labResult",
                "doc_id": str(current_doc.get("_id", "")),
                "report_time": str(current_doc.get("reportTime", "")),
            })

        # 4. 检查 CRRT
        has_crrt = await self._check_crrt_initiation(db, patient_id, now - timedelta(hours=time_window_hours), now)
        if has_crrt:
            evidence.append({"component": "crrt_initiated", "value": True, "source": "crrt"})

        # 5. KDIGO 分期
        aki_stage = 0
        creatinine_ratio = None
        aki_type = "none"

        if has_crrt:
            aki_stage = 3
            aki_type = "rrt"
        elif baseline_cr is not None and current_cr is not None:
            if baseline_cr > 0:
                creatinine_ratio = current_cr / baseline_cr
            else:
                creatinine_ratio = float("inf") if current_cr > 0 else 0

            # 48h 内绝对升高
            abs_increase_48h = await self._get_48h_increase(db, patient_id, current_cr, now)

            # Stage 3: >= 3x baseline 或 >= 353.6 umol/L (4.0 mg/dL)
            if (creatinine_ratio is not None and creatinine_ratio >= 3.0) or current_cr >= 353.6:
                aki_stage = 3
                aki_type = "creatinine"
            # Stage 2: 2.0-2.9x baseline
            elif creatinine_ratio is not None and creatinine_ratio >= 2.0:
                aki_stage = 2
                aki_type = "creatinine"
            # Stage 1: 1.5-1.9x baseline 或绝对升高 >= 26.5 umol/L
            elif (creatinine_ratio is not None and creatinine_ratio >= 1.5) or (abs_increase_48h is not None and abs_increase_48h >= 26.5):
                aki_stage = 1
                aki_type = "creatinine"

            evidence.append({
                "component": "kdigo_staging",
                "creatinine_ratio": creatinine_ratio,
                "abs_increase_48h": abs_increase_48h,
                "stage": aki_stage,
            })

        # 6. 计算尿量 AKI 分期（如果可用）
        uo_stage = await self._check_urine_output_aki(db, patient_id, now, time_window_hours)
        if uo_stage > aki_stage:
            aki_stage = uo_stage
            aki_type = "urine_output"
            evidence.append({"component": "urine_output_stage", "stage": uo_stage})

        return {
            "aki_stage": aki_stage,
            "creatinine_baseline": baseline_cr,
            "creatinine_current": current_cr,
            "creatinine_ratio": creatinine_ratio,
            "urine_output_ml_kg_h": None,  # 尿量需要体重，复杂处理在 _check_urine_output_aki 中
            "aki_type": aki_type,
            "calc_time": now,
            "version": self.version,
            "rule_source": self.rule_source,
            "evidence": evidence,
            "disclaimer": "电子表型计算结果基于规则引擎自动生成，需经临床医师人工复核后方可用于科研分析。",
        }

    async def _get_baseline_creatinine(
        self, db: Any, patient_id: str, now: datetime
    ) -> tuple[float | None, dict | None]:
        """获取基线肌酐：过去 7 天最低值。"""
        since = now - timedelta(days=7)
        cr_keys = ["cr", "肌酐", "creatinine", "scr", "CREA"]

        cursor = db.col("labResult").find(
            {
                "$or": [
                    {"patientId": patient_id},
                    {"patient_id": patient_id},
                ],
                "$or": [
                    {"test_code": {"$in": cr_keys}},
                    {"testName": {"$regex": "|".join(cr_keys), "$options": "i"}},
                    {"code": {"$in": cr_keys}},
                    {"name": {"$regex": "|".join(cr_keys), "$options": "i"}},
                ],
                "reportTime": {"$gte": since, "$lte": now},
            }
        ).sort("reportTime", -1)

        docs = await cursor.to_list(100)
        if not docs:
            return None, None

        min_cr = None
        min_doc = None
        for doc in docs:
            val, unit = _extract_numeric_from_doc(doc)
            if val is None:
                continue
            cr_umol = _to_umol_l(val, unit)
            if min_cr is None or cr_umol < min_cr:
                min_cr = cr_umol
                min_doc = doc

        return min_cr, min_doc

    async def _get_current_creatinine(
        self, db: Any, patient_id: str, now: datetime, window_hours: int
    ) -> tuple[float | None, dict | None]:
        """获取当前肌酐：时间窗内最新值。"""
        since = now - timedelta(hours=window_hours)
        cr_keys = ["cr", "肌酐", "creatinine", "scr", "CREA"]

        cursor = db.col("labResult").find(
            {
                "$or": [
                    {"patientId": patient_id},
                    {"patient_id": patient_id},
                ],
                "$or": [
                    {"test_code": {"$in": cr_keys}},
                    {"testName": {"$regex": "|".join(cr_keys), "$options": "i"}},
                    {"code": {"$in": cr_keys}},
                    {"name": {"$regex": "|".join(cr_keys), "$options": "i"}},
                ],
                "reportTime": {"$gte": since, "$lte": now},
            }
        ).sort("reportTime", -1).limit(1)

        docs = await cursor.to_list(1)
        if not docs:
            return None, None

        val, unit = _extract_numeric_from_doc(docs[0])
        if val is None:
            return None, None
        return _to_umol_l(val, unit), docs[0]

    async def _get_48h_increase(
        self, db: Any, patient_id: str, current_cr: float, now: datetime
    ) -> float | None:
        """获取 48 小时前的肌酐值，计算绝对升高。"""
        since_48h = now - timedelta(hours=48)
        since_7d = now - timedelta(days=7)
        cr_keys = ["cr", "肌酐", "creatinine", "scr", "CREA"]

        cursor = db.col("labResult").find(
            {
                "$or": [
                    {"patientId": patient_id},
                    {"patient_id": patient_id},
                ],
                "$or": [
                    {"test_code": {"$in": cr_keys}},
                    {"testName": {"$regex": "|".join(cr_keys), "$options": "i"}},
                    {"code": {"$in": cr_keys}},
                    {"name": {"$regex": "|".join(cr_keys), "$options": "i"}},
                ],
                "reportTime": {"$gte": since_7d, "$lte": since_48h},
            }
        ).sort("reportTime", -1).limit(1)

        docs = await cursor.to_list(1)
        if not docs:
            return None

        val, unit = _extract_numeric_from_doc(docs[0])
        if val is None:
            return None
        old_cr = _to_umol_l(val, unit)
        return current_cr - old_cr

    async def _check_crrt_initiation(
        self, db: Any, patient_id: str, since: datetime, until: datetime
    ) -> bool:
        """检查时间窗内是否开始 CRRT。"""
        cursor = db.col("crrt").find(
            {
                "$or": [
                    {"patientId": patient_id},
                    {"patient_id": patient_id},
                ],
                "startTime": {"$gte": since, "$lte": until},
            }
        ).limit(1)
        docs = await cursor.to_list(1)
        return len(docs) > 0

    async def _check_urine_output_aki(
        self, db: Any, patient_id: str, now: datetime, window_hours: int
    ) -> int:
        """检查尿量 AKI 分期（简化版，返回 0-3）。"""
        # 尿量 AKI 需要更复杂的数据（连续尿量监测），此处简化处理
        # 实际系统中需要从 nursing assessments 或 specific urine output collection 获取
        return 0

    def _empty_result(self, now: datetime, evidence: list, reason: str) -> dict[str, Any]:
        return {
            "aki_stage": 0,
            "creatinine_baseline": None,
            "creatinine_current": None,
            "creatinine_ratio": None,
            "urine_output_ml_kg_h": None,
            "aki_type": "none",
            "calc_time": now,
            "version": self.version,
            "rule_source": self.rule_source,
            "evidence": evidence,
            "error": reason,
        }
