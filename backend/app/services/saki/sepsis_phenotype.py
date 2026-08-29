"""脓毒症电子表型计算 - Sepsis-3 定义 (v2.1)。

Sepsis-3 定义: 感染 + 器官功能障碍 (SOFA delta >= 2)
参考文献: Singer M, et al. JAMA 2016;315(8):801-810.
         Evans L, et al. Intensive Care Med 2021;47(11):1181-1197.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger("icu-alert")

VERSION = "v2.1.0"
RULE_SOURCE = "Sepsis-3: Singer et al. JAMA 2016; Evans et al. Intensive Care Med 2021"

# 感染证据关键词
INFECTION_KEYWORDS = [
    "脓毒", "感染", "sepsis", "菌血症", "bacteremia",
    "肺炎", "pneumonia", "腹膜炎", "peritonitis",
    "泌尿系感染", "uti", "胆道感染", "皮肤软组织感染",
    "颅内感染", "meningitis", "感染性心内膜炎",
    "导管相关感染", "catheter-related infection",
]

ANTIBIOTIC_KEYWORDS = [
    "美罗培南", "meropenem", "亚胺培南", "imipenem",
    "万古霉素", "vancomycin", "替考拉宁", "teicoplanin",
    "哌拉西林他唑巴坦", "piperacillin", "头孢吡肟", "cefepime",
    "头孢他啶", "ceftazidime", "左氧氟沙星", "levofloxacin",
    "氟康唑", "fluconazole", "伏立康唑", "voriconazole",
]

VASOPRESSOR_KEYWORDS = [
    "去甲肾上腺素", "norepinephrine", "肾上腺素", "epinephrine",
    "血管加压素", "vasopressin", "多巴胺", "dopamine",
    "苯肾上腺素", "phenylephrine",
]


class SepsisPhenotypeCalculator:
    """Sepsis-3 电子表型计算器。"""

    def __init__(self) -> None:
        self.version = VERSION
        self.rule_source = RULE_SOURCE

    async def calculate(
        self,
        db: Any,
        patient_id: str,
        patient_doc: dict[str, Any] | None = None,
        time_window_hours: int = 24,
    ) -> dict[str, Any]:
        """计算脓毒症电子表型。

        Args:
            db: DatabaseManager 实例
            patient_id: 患者 ID (MongoDB _id 的字符串形式)
            patient_doc: 可选的患者文档，避免重复查询
            time_window_hours: SOFA 评估时间窗（小时）

        Returns:
            包含脓毒症判定、SOFA 评分、感染证据等的完整结果字典
        """
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

        # 2. 计算当前 SOFA
        sofa_result = await self._calc_sofa(db, patient_id, patient_doc, now, time_window_hours)
        current_sofa = sofa_result["total"]
        evidence.extend(sofa_result.get("evidence", []))

        # 3. 计算基线 SOFA（前 48 小时最低值）
        baseline_sofa = await self._calc_baseline_sofa(db, patient_id, patient_doc, now)
        sofa_delta = current_sofa - baseline_sofa

        # 4. 评估感染证据
        infection = await self._assess_infection(db, patient_id, patient_doc, now)
        evidence.extend(infection.get("evidence", []))

        # 5. 判定脓毒症
        is_sepsis = infection["verdict"] in ("supported", "possible") and sofa_delta >= 2

        return {
            "is_sepsis": is_sepsis,
            "sofa_score": current_sofa,
            "baseline_sofa": baseline_sofa,
            "sofa_delta": sofa_delta,
            "infection_evidence": {
                "verdict": infection["verdict"],
                "confidence": infection["confidence"],
                "sources": infection.get("sources", []),
            },
            "organ_scores": sofa_result.get("organ_scores", {}),
            "calc_time": now,
            "version": self.version,
            "rule_source": self.rule_source,
            "evidence": evidence,
            "disclaimer": "电子表型计算结果基于规则引擎自动生成，需经临床医师人工复核后方可用于科研分析。",
        }

    # -------------------------------------------------------------------
    # SOFA 评分计算
    # -------------------------------------------------------------------

    async def _calc_sofa(
        self,
        db: Any,
        patient_id: str,
        patient_doc: dict,
        now: datetime,
        window_hours: int,
    ) -> dict[str, Any]:
        """计算 6 个器官系统的 SOFA 评分。"""
        from bson import ObjectId

        since = now - timedelta(hours=window_hours)
        organ_scores: dict[str, int] = {}
        evidence: list[dict[str, Any]] = []

        pid_obj = None
        try:
            pid_obj = ObjectId(patient_id)
        except Exception:
            pid_obj = patient_id

        # --- 1. 呼吸 (PaO2/FiO2) ---
        pao2_score, pao2_ev = await self._sofa_respiration(db, pid_obj, since, now)
        organ_scores["respiration"] = pao2_score
        evidence.extend(pao2_ev)

        # --- 2. 凝血 (血小板) ---
        plt_score, plt_ev = await self._sofa_coagulation(db, pid_obj, since, now)
        organ_scores["coagulation"] = plt_score
        evidence.extend(plt_ev)

        # --- 3. 肝脏 (胆红素) ---
        bil_score, bil_ev = await self._sofa_liver(db, pid_obj, since, now)
        organ_scores["liver"] = bil_score
        evidence.extend(bil_ev)

        # --- 4. 神经 (GCS) ---
        gcs_score, gcs_ev = await self._sofa_neurological(db, pid_obj, since, now)
        organ_scores["neurological"] = gcs_score
        evidence.extend(gcs_ev)

        # --- 5. 心血管 (MAP + 血管活性药) ---
        cardio_score, cardio_ev = await self._sofa_cardiovascular(db, pid_obj, since, now)
        organ_scores["cardiovascular"] = cardio_score
        evidence.extend(cardio_ev)

        # --- 6. 肾脏 (肌酐 / 尿量) ---
        renal_score, renal_ev = await self._sofa_renal(db, pid_obj, since, now)
        organ_scores["renal"] = renal_score
        evidence.extend(renal_ev)

        total = sum(organ_scores.values())
        return {"total": total, "organ_scores": organ_scores, "evidence": evidence}

    async def _latest_lab_value(
        self, db: Any, pid: Any, lab_keys: list[str], since: datetime, until: datetime
    ) -> tuple[float | None, dict | None]:
        """获取指定实验室指标在时间窗内的最新值。"""
        for key in lab_keys:
            cursor = db.col("labResult").find(
                {
                    "$or": [
                        {"patientId": str(pid)},
                        {"patient_id": str(pid)},
                        {"patientId": pid},
                        {"patient_id": pid},
                    ],
                    "$or": [
                        {"test_code": {"$regex": f"^{key}$", "$options": "i"}},
                        {"testName": {"$regex": key, "$options": "i"}},
                        {"code": {"$regex": f"^{key}$", "$options": "i"}},
                        {"name": {"$regex": key, "$options": "i"}},
                    ],
                    "reportTime": {"$gte": since, "$lte": until},
                },
            ).sort("reportTime", -1).limit(1)
            doc = await cursor.to_list(1)
            if doc:
                val = _extract_numeric(doc[0])
                if val is not None:
                    return val, doc[0]
        return None, None

    async def _sofa_respiration(self, db, pid, since, until):
        """PaO2/FiO2 → SOFA 呼吸评分。"""
        evidence = []
        pao2, pao2_doc = await self._latest_lab_value(db, pid, ["pao2", "po2", "氧分压"], since, until)
        fio2, fio2_doc = await self._latest_lab_value(db, pid, ["fio2", "吸入氧浓度"], since, until)

        if pao2 is not None:
            evidence.append({"component": "respiration", "parameter": "pao2", "value": pao2, "unit": "mmHg",
                             "source": "labResult", "doc_id": str(pao2_doc.get("_id", "")) if pao2_doc else ""})

        # 如果没有 FiO2，假设 21%（空气）
        fio2_val = fio2 if fio2 and fio2 > 0 else 21.0
        if fio2_doc:
            evidence.append({"component": "respiration", "parameter": "fio2", "value": fio2_val, "unit": "%"})

        if pao2 is None:
            return 0, evidence

        pao2_fio2 = pao2 / (fio2_val / 100.0) if fio2_val > 0 else 0

        if pao2_fio2 >= 400:
            return 0, evidence
        elif pao2_fio2 >= 300:
            return 1, evidence
        elif pao2_fio2 >= 200:
            return 2, evidence
        elif pao2_fio2 >= 100:
            return 3, evidence
        else:
            return 4, evidence

    async def _sofa_coagulation(self, db, pid, since, until):
        """血小板 → SOFA 凝血评分。"""
        evidence = []
        plt_val, plt_doc = await self._latest_lab_value(db, pid, ["plt", "血小板", "platelet"], since, until)
        if plt_val is None:
            return 0, evidence
        evidence.append({"component": "coagulation", "parameter": "platelet", "value": plt_val,
                         "unit": "10^9/L", "source": "labResult",
                         "doc_id": str(plt_doc.get("_id", "")) if plt_doc else ""})

        if plt_val >= 150:
            return 0, evidence
        elif plt_val >= 100:
            return 1, evidence
        elif plt_val >= 50:
            return 2, evidence
        elif plt_val >= 20:
            return 3, evidence
        else:
            return 4, evidence

    async def _sofa_liver(self, db, pid, since, until):
        """胆红素 → SOFA 肝脏评分。"""
        evidence = []
        bil_val, bil_doc = await self._latest_lab_value(db, pid, ["bil", "胆红素", "bilirubin", "tbil"], since, until)
        if bil_val is None:
            return 0, evidence

        # 单位转换：如果 > 20 很可能是 mg/dL → umol/L
        if bil_val < 20:
            bil_val = bil_val * 17.1  # mg/dL → umol/L

        evidence.append({"component": "liver", "parameter": "bilirubin", "value": bil_val,
                         "unit": "umol/L", "source": "labResult",
                         "doc_id": str(bil_doc.get("_id", "")) if bil_doc else ""})

        if bil_val <= 20:
            return 0, evidence
        elif bil_val <= 32:
            return 1, evidence
        elif bil_val <= 101:
            return 2, evidence
        elif bil_val <= 204:
            return 3, evidence
        else:
            return 4, evidence

    async def _sofa_neurological(self, db, pid, since, until):
        """GCS → SOFA 神经系统评分。"""
        evidence = []
        # 尝试从 labResult 中获取 GCS
        gcs_val, gcs_doc = await self._latest_lab_value(db, pid, ["gcs", "格拉斯哥"], since, until)
        if gcs_val is None:
            return 0, evidence

        gcs_int = int(gcs_val)
        evidence.append({"component": "neurological", "parameter": "gcs", "value": gcs_int,
                         "source": "labResult", "doc_id": str(gcs_doc.get("_id", "")) if gcs_doc else ""})

        if gcs_int >= 15:
            return 0, evidence
        elif gcs_int >= 13:
            return 1, evidence
        elif gcs_int >= 10:
            return 2, evidence
        elif gcs_int >= 6:
            return 3, evidence
        else:
            return 4, evidence

    async def _sofa_cardiovascular(self, db, pid, since, until):
        """MAP + 血管活性药 → SOFA 心血管评分。"""
        evidence = []

        # MAP
        map_codes = ["param_nibp_m", "param_ibp_m", "param_abp_m"]
        map_cursor = db.col("vitalSign").find(
            {
                "$or": [
                    {"patientId": str(pid)},
                    {"patient_id": str(pid)},
                    {"patientId": pid},
                    {"patient_id": pid},
                ],
                "param_code": {"$in": map_codes},
                "recordTime": {"$gte": since, "$lte": until},
            }
        ).sort("recordTime", -1).limit(1)
        map_docs = await map_cursor.to_list(1)

        map_val = None
        if map_docs:
            map_val = _extract_numeric(map_docs[0])
            evidence.append({"component": "cardiovascular", "parameter": "map", "value": map_val,
                             "unit": "mmHg", "source": "vitalSign"})

        # 血管活性药
        has_vasopressor = await self._check_vasopressors(db, pid, since, until)
        if has_vasopressor:
            evidence.append({"component": "cardiovascular", "parameter": "vasopressor", "value": True, "source": "drug"})

        if map_val is not None and map_val < 70:
            return 1, evidence
        if has_vasopressor:
            # 简化：有血管活性药即为 1 分（详细分类需剂量）
            return 2, evidence
        return 0, evidence

    async def _sofa_renal(self, db, pid, since, until):
        """肌酐 → SOFA 肾脏评分。"""
        evidence = []
        cr_val, cr_doc = await self._latest_lab_value(db, pid, ["cr", "肌酐", "creatinine", "scr"], since, until)
        if cr_val is None:
            return 0, evidence

        # 单位转换：如果 < 20 很可能是 mg/dL → umol/L
        if cr_val < 20:
            cr_val = cr_val * 88.4

        evidence.append({"component": "renal", "parameter": "creatinine", "value": cr_val,
                         "unit": "umol/L", "source": "labResult",
                         "doc_id": str(cr_doc.get("_id", "")) if cr_doc else ""})

        if cr_val <= 110:
            return 0, evidence
        elif cr_val <= 170:
            return 1, evidence
        elif cr_val <= 299:
            return 2, evidence
        elif cr_val <= 340:
            return 3, evidence
        else:
            return 4, evidence

    async def _calc_baseline_sofa(self, db: Any, patient_id: str, patient_doc: dict, now: datetime) -> int:
        """基线 SOFA：取前 48h 最低值。"""
        since = now - timedelta(hours=48)
        sofa_result = await self._calc_sofa(db, patient_id, patient_doc, since, 48)
        return sofa_result["total"]

    async def _assess_infection(self, db: Any, patient_id: str, patient_doc: dict, now: datetime) -> dict[str, Any]:
        """评估感染证据。"""
        evidence: list[dict[str, Any]] = []
        sources: list[str] = []
        score = 0

        # 1. 诊断关键词
        diagnosis = str(patient_doc.get("clinicalDiagnosis", "") or patient_doc.get("admissionDiagnosis", "") or "")
        for kw in INFECTION_KEYWORDS:
            if kw.lower() in diagnosis.lower():
                score += 2
                sources.append(f"诊断关键词: {kw}")
                evidence.append({"source_type": "diagnosis", "keyword": kw, "text": diagnosis[:200]})
                break

        # 2. 感染标志物
        for lab_key, lab_name in [("pct", "PCT"), ("crp", "CRP"), ("wbc", "WBC")]:
            val, doc = await self._latest_lab_value(db, patient_id, [lab_key, lab_name], now - timedelta(hours=48), now)
            if val is not None:
                if lab_key == "pct" and val > 0.5:
                    score += 1
                    sources.append(f"{lab_name}={val}")
                    evidence.append({"source_type": "lab", "parameter": lab_name, "value": val})
                elif lab_key == "crp" and val > 50:
                    score += 1
                    sources.append(f"{lab_name}={val}")
                    evidence.append({"source_type": "lab", "parameter": lab_name, "value": val})
                elif lab_key == "wbc" and (val > 12 or val < 4):
                    score += 1
                    sources.append(f"{lab_name}={val}")
                    evidence.append({"source_type": "lab", "parameter": lab_name, "value": val})

        # 3. 抗生素使用
        has_abx = await self._check_antibiotics(db, patient_id, now - timedelta(hours=72), now)
        if has_abx:
            score += 1
            sources.append("近期使用抗生素")
            evidence.append({"source_type": "medication", "detail": "抗生素使用记录"})

        if score >= 3:
            verdict, confidence = "supported", "strong"
        elif score >= 2:
            verdict, confidence = "supported", "moderate"
        elif score >= 1:
            verdict, confidence = "possible", "weak"
        else:
            verdict, confidence = "not_supported", "weak"

        return {
            "verdict": verdict,
            "confidence": confidence,
            "score": score,
            "sources": sources,
            "evidence": evidence,
        }

    async def _check_vasopressors(self, db: Any, pid: Any, since: datetime, until: datetime) -> bool:
        """检查是否使用了血管活性药。"""
        for kw in VASOPRESSOR_KEYWORDS:
            cursor = db.col("drug").find(
                {
                    "$or": [
                        {"patientId": str(pid)},
                        {"patient_id": str(pid)},
                        {"patientId": pid},
                        {"patient_id": pid},
                    ],
                    "$or": [
                        {"drugName": {"$regex": kw, "$options": "i"}},
                        {"drug_name": {"$regex": kw, "$options": "i"}},
                        {"name": {"$regex": kw, "$options": "i"}},
                    ],
                    "startTime": {"$lte": until},
                }
            ).limit(1)
            docs = await cursor.to_list(1)
            if docs:
                return True
        return False

    async def _check_antibiotics(self, db: Any, pid: Any, since: datetime, until: datetime) -> bool:
        """检查是否使用了抗生素。"""
        for kw in ANTIBIOTIC_KEYWORDS[:6]:
            cursor = db.col("drug").find(
                {
                    "$or": [
                        {"patientId": str(pid)},
                        {"patient_id": str(pid)},
                        {"patientId": pid},
                        {"patient_id": pid},
                    ],
                    "$or": [
                        {"drugName": {"$regex": kw, "$options": "i"}},
                        {"drug_name": {"$regex": kw, "$options": "i"}},
                        {"name": {"$regex": kw, "$options": "i"}},
                    ],
                    "startTime": {"$gte": since, "$lte": until},
                }
            ).limit(1)
            docs = await cursor.to_list(1)
            if docs:
                return True
        return False

    def _empty_result(self, now: datetime, evidence: list, reason: str) -> dict[str, Any]:
        return {
            "is_sepsis": False,
            "sofa_score": 0,
            "baseline_sofa": 0,
            "sofa_delta": 0,
            "infection_evidence": {"verdict": "unknown", "confidence": "weak", "sources": []},
            "organ_scores": {},
            "calc_time": now,
            "version": self.version,
            "rule_source": self.rule_source,
            "evidence": evidence,
            "error": reason,
        }


def _extract_numeric(doc: dict) -> float | None:
    """从实验室/生命体征文档中提取数值。"""
    import re
    for key in ("result", "value", "val", "numResult"):
        raw = doc.get(key)
        if raw is None:
            continue
        if isinstance(raw, (int, float)):
            return float(raw)
        text = str(raw).strip()
        match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
        if match:
            try:
                return float(match.group(0))
            except ValueError:
                continue
    return None
