"""S-AKI 统计分析引擎。委托 research_analytics 实现通用统计，增加 S-AKI 专有分析。"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("icu-alert")


class SAKIStatistics:
    """S-AKI 统计分析。"""

    async def table1(
        self, db: Any, patient_ids: list[str] | None = None, cohort_id: str | None = None,
        group_by: str = "aki_stage", variables: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """基线特征表 (Table 1)。"""
        ids = await self._resolve_ids(db, patient_ids, cohort_id)
        if not ids:
            return {"error": "无可用患者", "table": {}}
        try:
            from app.services.research_analytics import generate_table1
            return await generate_table1(db, patient_ids=ids, group_by=group_by, variables=variables or [])
        except Exception as exc:
            logger.warning("Table1 生成失败: %s", exc)
            return await self._fallback_table1(db, ids, group_by)

    async def km_analysis(
        self, db: Any, patient_ids: list[str] | None = None, cohort_id: str | None = None,
        time_field: str = "los_icu_days", event_field: str = "icu_mortality",
        group_by: str | None = None, max_time: int = 28,
    ) -> dict[str, Any]:
        """Kaplan-Meier 生存分析。"""
        ids = await self._resolve_ids(db, patient_ids, cohort_id)
        if not ids:
            return {"error": "无可用患者"}
        try:
            from app.services.research_analytics import survival_analysis
            return await survival_analysis(db, patient_ids=ids, time_field=time_field,
                                           event_field=event_field, group_by=group_by, max_time=max_time)
        except Exception as exc:
            logger.warning("KM 分析失败: %s", exc)
            return {"error": str(exc)}

    async def logistic_regression(
        self, db: Any, patient_ids: list[str] | None = None, cohort_id: str | None = None,
        outcome: str = "icu_mortality", predictors: list[str] | None = None,
    ) -> dict[str, Any]:
        """Logistic 回归分析。"""
        ids = await self._resolve_ids(db, patient_ids, cohort_id)
        if not ids:
            return {"error": "无可用患者"}
        try:
            from app.services.research_analytics import regression_analysis
            return await regression_analysis(db, patient_ids=ids, outcome=outcome, predictors=predictors or [], model_type="logistic")
        except Exception as exc:
            logger.warning("Logistic 回归失败: %s", exc)
            return {"error": str(exc)}

    async def cox_regression(
        self, db: Any, patient_ids: list[str] | None = None, cohort_id: str | None = None,
        time_field: str = "los_icu_days", event_field: str = "icu_mortality",
        predictors: list[str] | None = None, max_time: int = 28,
    ) -> dict[str, Any]:
        """Cox 比例风险回归。"""
        ids = await self._resolve_ids(db, patient_ids, cohort_id)
        if not ids:
            return {"error": "无可用患者"}
        try:
            from app.services.research_analytics import regression_analysis
            return await regression_analysis(db, patient_ids=ids, outcome=event_field, predictors=predictors or [],
                                             model_type="cox", time_field=time_field, max_time=max_time)
        except Exception as exc:
            logger.warning("Cox 回归失败: %s", exc)
            return {"error": str(exc)}

    async def roc_analysis(
        self, db: Any, patient_ids: list[str] | None = None, cohort_id: str | None = None,
        outcome: str = "icu_mortality", predictors: list[str] | None = None,
    ) -> dict[str, Any]:
        """ROC 曲线分析。"""
        ids = await self._resolve_ids(db, patient_ids, cohort_id)
        if not ids:
            return {"error": "无可用患者"}
        try:
            from app.services.research_analytics import roc_analysis as _roc
            return await _roc(db, patient_ids=ids, outcome=outcome, predictors=predictors or [])
        except Exception as exc:
            logger.warning("ROC 分析失败: %s", exc)
            return {"error": str(exc)}

    async def creatinine_trajectory(
        self, db: Any, patient_ids: list[str] | None = None, cohort_id: str | None = None,
        hours: int = 168,
    ) -> dict[str, Any]:
        """肌酐轨迹分析（S-AKI 专有）。"""
        ids = await self._resolve_ids(db, patient_ids, cohort_id)
        if not ids:
            return {"error": "无可用患者", "trajectories": []}

        cr_keys = ["cr", "肌酐", "creatinine", "scr", "CREA"]
        trajectories: list[dict[str, Any]] = []

        for pid in ids[:200]:
            cursor = db.col("labResult").find(
                {
                    "$or": [{"patientId": pid}, {"patient_id": pid}],
                    "$or": [
                        {"test_code": {"$in": cr_keys}},
                        {"testName": {"$regex": "|".join(cr_keys), "$options": "i"}},
                        {"code": {"$in": cr_keys}},
                    ],
                }
            ).sort("reportTime", 1)
            docs = await cursor.to_list(200)
            points = []
            for doc in docs:
                val = self._extract_val(doc)
                t = doc.get("reportTime")
                if val is not None and t is not None:
                    points.append({"time": t.isoformat() if hasattr(t, "isoformat") else str(t), "value": val})
            if points:
                trajectories.append({"patient_id": pid, "points": points})

        return {
            "patient_count": len(trajectories),
            "trajectories": trajectories,
            "hours": hours,
            "disclaimer": "统计分析结果基于观察性数据，仅提示关联性，不可作为因果推断依据。",
        }

    async def forest_plot_data(
        self, db: Any, patient_ids: list[str] | None = None, cohort_id: str | None = None,
        outcome: str = "icu_mortality", factors: list[str] | None = None,
    ) -> dict[str, Any]:
        """森林图数据。"""
        result = await self.logistic_regression(db, patient_ids, cohort_id, outcome, factors)
        return {"forest_data": result.get("coefficients", []), "error": result.get("error")}

    async def hospital_outcomes(
        self, db: Any, patient_ids: list[str] | None = None, cohort_id: str | None = None,
    ) -> dict[str, Any]:
        """住院结局汇总。"""
        ids = await self._resolve_ids(db, patient_ids, cohort_id)
        if not ids:
            return {"error": "无可用患者"}

        cases = []
        for pid in ids[:500]:
            doc = await db.col("saki_cases").find_one({"patient_id": pid})
            if doc:
                cases.append(doc)

        total = len(cases)
        if total == 0:
            return {"total": 0, "mortality_rate": 0, "dialysis_rate": 0}

        mortality = sum(1 for c in cases if c.get("aki_stage", 0) >= 3)
        saki_count = sum(1 for c in cases if c.get("is_saki"))
        stage_dist = {}
        for s in range(4):
            stage_dist[str(s)] = sum(1 for c in cases if c.get("aki_stage") == s)

        return {
            "total": total,
            "saki_positive": saki_count,
            "stage_distribution": stage_dist,
            "severe_aki_rate": round(mortality / total, 4) if total > 0 else 0,
            "disclaimer": "统计分析结果基于观察性数据，仅提示关联性，不可作为因果推断依据。",
        }

    async def _resolve_ids(self, db: Any, patient_ids: list[str] | None, cohort_id: str | None) -> list[str]:
        if patient_ids:
            return patient_ids
        if cohort_id:
            try:
                from bson import ObjectId
                cohort = await db.col("saki_cohorts").find_one({"_id": ObjectId(cohort_id)})
            except Exception:
                cohort = await db.col("saki_cohorts").find_one({"cohort_id": cohort_id})
            if cohort:
                from .cohort_builder import SAKICohortBuilder
                builder = SAKICohortBuilder()
                patients = await builder.get_cohort_patients(db, cohort_id, page=1, page_size=10000)
                return [c.get("patient_id", "") for c in patients.get("cases", []) if c.get("patient_id")]
        return []

    async def _fallback_table1(self, db: Any, ids: list[str], group_by: str) -> dict[str, Any]:
        """回退的 Table1（不依赖 research_analytics）。"""
        import re
        rows = []
        for pid in ids[:500]:
            case = await db.col("saki_cases").find_one({"patient_id": pid})
            if case:
                row = {
                    "patient_id": pid,
                    "aki_stage": case.get("aki_stage", 0),
                    "is_saki": case.get("is_saki", False),
                    "sofa_score": case.get("sepsis_phenotype", {}).get("sofa_score", 0),
                    "sofa_delta": case.get("sepsis_phenotype", {}).get("sofa_delta", 0),
                }
                rows.append(row)
        return {"table": {"rows": rows, "columns": list(rows[0].keys()) if rows else []}, "n": len(rows)}

    @staticmethod
    def _extract_val(doc: dict) -> float | None:
        import re
        for key in ("result", "value", "val"):
            raw = doc.get(key)
            if raw is None:
                continue
            if isinstance(raw, (int, float)):
                return float(raw)
            match = re.search(r"[-+]?\d+(?:\.\d+)?", str(raw))
            if match:
                try:
                    return float(match.group(0))
                except ValueError:
                    continue
        return None
