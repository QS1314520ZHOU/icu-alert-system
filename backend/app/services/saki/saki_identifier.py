"""S-AKI 病例识别 - 脓毒症相关急性肾损伤。

时间关联逻辑: AKI 发生在脓毒症识别前后 [-24h, +168h] 窗口内。
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId

logger = logging.getLogger("icu-alert")

VERSION = "v1.0.0"
TEMPORAL_WINDOW_HOURS = 168  # 7 天
TEMPORAL_PRE_WINDOW_HOURS = 24  # AKI 可早于脓毒症识别 24h（数据滞后）

NEPHROTOXIC_DRUGS = [
    "万古霉素", "vancomycin", "氨基糖苷", "amikacin", "gentamicin",
    "两性霉素", "amphotericin", "NSAIDs", "布洛芬", "ibuprofen",
    "造影剂", "contrast", "顺铂", "cisplatin", "他克莫司", "tacrolimus",
]

RISK_FACTOR_KEYWORDS = {
    "diabetes": ["糖尿病", "diabetes", "DM"],
    "hypertension": ["高血压", "hypertension", "HTN"],
    "chronic_kidney_disease": ["慢性肾", "CKD", "chronic kidney"],
    "heart_failure": ["心衰", "heart failure", "HF"],
    "liver_disease": ["肝硬化", "cirrhosis", "肝病"],
    "immunocompromised": ["免疫抑制", "immunocompromised", "移植", "transplant"],
    "rhabdomyolysis": ["横纹肌溶解", "rhabdomyolysis"],
    "severe_sepsis": ["感染性休克", "septic shock"],
    "contrast_exposure": ["造影", "contrast"],
}


class SAKICaseIdentifier:
    """S-AKI 病例识别器。"""

    def __init__(self) -> None:
        self.version = VERSION

    async def identify(self, db: Any, patient_id: str) -> dict[str, Any]:
        """识别单个患者的 S-AKI。"""
        now = datetime.now(timezone.utc)
        from .sepsis_phenotype import SepsisPhenotypeCalculator
        from .aki_phenotype import AKIPhenotypeCalculator

        sepsis_calc = SepsisPhenotypeCalculator()
        aki_calc = AKIPhenotypeCalculator()

        # 获取患者文档
        try:
            patient_doc = await db.col("patient").find_one({"_id": ObjectId(patient_id)})
        except Exception:
            patient_doc = await db.col("patient").find_one({"_id": patient_id})
        if not patient_doc:
            return {"error": "患者未找到", "patient_id": patient_id}

        # 计算表型
        sepsis = await sepsis_calc.calculate(db, patient_id, patient_doc)
        aki = await aki_calc.calculate(db, patient_id, patient_doc)

        # 时间关联
        temporal = self._assess_temporal_association(sepsis, aki)

        # 风险因素
        risk_factors = await self._identify_risk_factors(db, patient_id, patient_doc)

        # S-AKI 判定
        is_saki = (
            sepsis.get("is_sepsis", False)
            and aki.get("aki_stage", 0) > 0
            and temporal["associated"]
        )

        probability = "none"
        if is_saki:
            if aki.get("aki_stage", 0) >= 2 and sepsis.get("sofa_delta", 0) >= 3:
                probability = "high"
            elif aki.get("aki_stage", 0) >= 1 and sepsis.get("sofa_delta", 0) >= 2:
                probability = "moderate"
            else:
                probability = "low"
        elif aki.get("aki_stage", 0) > 0 and sepsis.get("is_sepsis", False):
            probability = "low"

        # 组装结果
        case = {
            "patient_id": patient_id,
            "patient_name": patient_doc.get("name", ""),
            "department": patient_doc.get("hisDept", patient_doc.get("dept", "")),
            "dept_code": patient_doc.get("deptCode", ""),
            "is_saki": is_saki,
            "saki_probability": probability,
            "aki_stage": aki.get("aki_stage", 0),
            "sepsis_phenotype": sepsis,
            "aki_phenotype": aki,
            "temporal_association": temporal,
            "risk_factors": risk_factors,
            "review_status": "pending",
            "version": self.version,
            "calc_time": now,
            "created_at": now,
            "updated_at": now,
            "evidence": sepsis.get("evidence", []) + aki.get("evidence", []),
        }

        # 持久化
        try:
            col = db.col("saki_cases")
            existing = await col.find_one({"patient_id": patient_id})
            if existing:
                case["_id"] = existing["_id"]
                await col.update_one({"_id": existing["_id"]}, {"$set": case})
            else:
                await col.insert_one(case)
            logger.info("S-AKI 病例已保存: patient=%s is_saki=%s stage=%d", patient_id, is_saki, aki.get("aki_stage", 0))
        except Exception as exc:
            logger.warning("保存 S-AKI 病例失败: %s", exc)

        return case

    async def batch_identify(self, db: Any, patient_ids: list[str] | None = None) -> list[dict[str, Any]]:
        """批量识别 S-AKI。"""
        if patient_ids is None:
            cursor = db.col("patient").find(
                {"$or": [
                    {"status": {"$nin": ["discharged", "invalid", "invaild"]}},
                    {"status": {"$exists": False}},
                ]},
                {"_id": 1},
            )
            docs = await cursor.to_list(1000)
            patient_ids = [str(d["_id"]) for d in docs]

        results = []
        for pid in patient_ids:
            try:
                result = await self.identify(db, pid)
                results.append(result)
            except Exception as exc:
                logger.warning("识别 S-AKI 失败 patient=%s: %s", pid, exc)
                results.append({"patient_id": pid, "error": str(exc)})
        return results

    async def list_cases(
        self,
        db: Any,
        page: int = 1,
        page_size: int = 20,
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """分页查询 S-AKI 病例。"""
        col = db.col("saki_cases")
        query: dict[str, Any] = {}

        if filters:
            if "aki_stage" in filters and filters["aki_stage"] is not None:
                query["aki_stage"] = int(filters["aki_stage"])
            if "department" in filters and filters["department"]:
                query["department"] = {"$regex": str(filters["department"]), "$options": "i"}
            if "is_saki" in filters:
                query["is_saki"] = bool(filters["is_saki"])
            if "review_status" in filters and filters["review_status"]:
                query["review_status"] = filters["review_status"]
            if "date_from" in filters or "date_to" in filters:
                date_q: dict[str, Any] = {}
                if filters.get("date_from"):
                    date_q["$gte"] = datetime.fromisoformat(str(filters["date_from"]))
                if filters.get("date_to"):
                    date_q["$lte"] = datetime.fromisoformat(str(filters["date_to"]))
                if date_q:
                    query["created_at"] = date_q

        total = await col.count_documents(query)
        skip = max(0, (page - 1) * page_size)
        cursor = col.find(query).sort("created_at", -1).skip(skip).limit(page_size)
        cases = []
        async for doc in cursor:
            doc.pop("_id", None)
            cases.append(doc)

        return {
            "cases": cases,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }

    async def get_case_detail(self, db: Any, case_id: str) -> dict[str, Any] | None:
        """获取病例详情。"""
        col = db.col("saki_cases")
        try:
            doc = await col.find_one({"_id": ObjectId(case_id)})
        except Exception:
            doc = await col.find_one({"_id": case_id})
        if doc:
            doc.pop("_id", None)
        return doc

    async def review_case(
        self,
        db: Any,
        case_id: str,
        reviewer_id: str,
        result: str,
        notes: str = "",
    ) -> dict[str, Any]:
        """人工复核病例。"""
        col = db.col("saki_cases")
        now = datetime.now(timezone.utc)
        update = {
            "review_status": result,
            "reviewer_id": reviewer_id,
            "review_notes": notes,
            "reviewed_at": now,
            "updated_at": now,
        }
        try:
            await col.update_one({"_id": ObjectId(case_id)}, {"$set": update})
        except Exception:
            await col.update_one({"_id": case_id}, {"$set": update})
        return update

    async def get_statistics(self, db: Any) -> dict[str, Any]:
        """获取病例统计概览。"""
        col = db.col("saki_cases")
        total = await col.count_documents({})
        saki_positive = await col.count_documents({"is_saki": True})
        by_stage = {}
        for stage in range(4):
            by_stage[str(stage)] = await col.count_documents({"aki_stage": stage})
        by_review = {}
        for status in ("pending", "confirmed", "rejected", "modified"):
            by_review[status] = await col.count_documents({"review_status": status})
        return {
            "total_cases": total,
            "saki_positive": saki_positive,
            "saki_negative": total - saki_positive,
            "by_stage": by_stage,
            "by_review_status": by_review,
        }

    def _assess_temporal_association(
        self, sepsis: dict, aki: dict
    ) -> dict[str, Any]:
        """评估脓毒症与 AKI 的时间关联。"""
        sepsis_time = sepsis.get("calc_time")
        aki_time = aki.get("calc_time")

        if not sepsis_time or not aki_time:
            return {"associated": False, "reason": "缺少时间信息"}

        if isinstance(sepsis_time, str):
            sepsis_time = datetime.fromisoformat(sepsis_time.replace("Z", "+00:00"))
        if isinstance(aki_time, str):
            aki_time = datetime.fromisoformat(aki_time.replace("Z", "+00:00"))

        delta = (aki_time - sepsis_time).total_seconds() / 3600.0
        abs_delta = abs(delta)

        associated = abs_delta <= (TEMPORAL_WINDOW_HOURS + TEMPORAL_PRE_WINDOW_HOURS)
        return {
            "associated": associated,
            "sepsis_onset_time": sepsis_time.isoformat(),
            "aki_onset_time": aki_time.isoformat(),
            "time_delta_hours": round(delta, 1),
            "window_hours": TEMPORAL_WINDOW_HOURS,
        }

    async def _identify_risk_factors(
        self, db: Any, patient_id: str, patient_doc: dict
    ) -> list[dict[str, Any]]:
        """识别 S-AKI 危险因素。"""
        factors: list[dict[str, Any]] = []
        diagnosis = str(
            patient_doc.get("clinicalDiagnosis", "")
            or patient_doc.get("admissionDiagnosis", "")
            or ""
        ).lower()

        for factor_name, keywords in RISK_FACTOR_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in diagnosis:
                    factors.append({"factor": factor_name, "source": "diagnosis", "keyword": kw})
                    break

        # 肾毒性药物
        try:
            cursor = db.col("drug").find(
                {
                    "$or": [
                        {"patientId": patient_id},
                        {"patient_id": patient_id},
                    ],
                }
            ).limit(200)
            drugs = await cursor.to_list(200)
            for drug in drugs:
                drug_name = str(drug.get("drugName", "") or drug.get("drug_name", "") or drug.get("name", "")).lower()
                for nephro in NEPHROTOXIC_DRUGS:
                    if nephro.lower() in drug_name:
                        factors.append({"factor": "nephrotoxic_drug", "source": "drug", "keyword": nephro, "drug_name": drug_name})
                        break
        except Exception:
            pass

        return factors
