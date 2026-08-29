"""S-AKI 科研队列构建器。"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("icu-alert")


class SAKICohortBuilder:
    """S-AKI 研究队列构建器。"""

    async def build_cohort(
        self,
        db: Any,
        filters: dict[str, Any],
        name: str = "未命名S-AKI队列",
        created_by: str = "system",
    ) -> dict[str, Any]:
        """根据条件构建队列并持久化。"""
        now = datetime.now(timezone.utc)
        case_query = self._build_query(filters)
        col = db.col("saki_cases")
        total = await col.count_documents(case_query)

        cohort_id = str(uuid.uuid4())
        cohort = {
            "cohort_id": cohort_id,
            "name": name,
            "filters": filters,
            "patient_count": total,
            "created_by": created_by,
            "created_at": now,
            "updated_at": now,
        }
        await db.col("saki_cohorts").insert_one(cohort)
        logger.info("S-AKI 队列已创建: %s (%d 例)", name, total)
        return cohort

    async def generate_snapshot(self, db: Any, cohort_id: str) -> dict[str, Any]:
        """生成队列快照。"""
        now = datetime.now(timezone.utc)
        cohort_col = db.col("saki_cohorts")
        try:
            from bson import ObjectId
            cohort = await cohort_col.find_one({"_id": ObjectId(cohort_id)})
        except Exception:
            cohort = await cohort_col.find_one({"cohort_id": cohort_id})
        if not cohort:
            raise ValueError(f"队列 {cohort_id} 不存在")

        filters = cohort.get("filters", {})
        query = self._build_query(filters)
        cursor = db.col("saki_cases").find(query).limit(10000)
        cases = []
        async for doc in cursor:
            doc.pop("_id", None)
            cases.append(doc)

        snapshot = {
            "snapshot_id": str(uuid.uuid4()),
            "cohort_id": cohort_id,
            "name": cohort.get("name", ""),
            "patient_count": len(cases),
            "cases": cases,
            "created_at": now,
        }
        await db.col("saki_snapshots").insert_one(snapshot)
        return {"snapshot_id": snapshot["snapshot_id"], "patient_count": len(cases), "created_at": now.isoformat()}

    async def list_cohorts(self, db: Any, user_id: str | None = None) -> list[dict[str, Any]]:
        """列出队列。"""
        query = {}
        if user_id:
            query["created_by"] = user_id
        cursor = db.col("saki_cohorts").find(query).sort("created_at", -1).limit(200)
        result = []
        async for doc in cursor:
            doc.pop("_id", None)
            result.append(doc)
        return result

    async def delete_cohort(self, db: Any, cohort_id: str) -> bool:
        """删除队列。"""
        result = await db.col("saki_cohorts").delete_one({"cohort_id": cohort_id})
        return result.deleted_count > 0

    async def get_cohort_patients(
        self, db: Any, cohort_id: str, page: int = 1, page_size: int = 20
    ) -> dict[str, Any]:
        """获取队列中的患者列表（分页）。"""
        try:
            from bson import ObjectId
            cohort = await db.col("saki_cohorts").find_one({"_id": ObjectId(cohort_id)})
        except Exception:
            cohort = await db.col("saki_cohorts").find_one({"cohort_id": cohort_id})
        if not cohort:
            return {"cases": [], "total": 0, "page": page, "page_size": page_size}

        filters = cohort.get("filters", {})
        query = self._build_query(filters)
        total = await db.col("saki_cases").count_documents(query)
        skip = max(0, (page - 1) * page_size)
        cursor = db.col("saki_cases").find(query).skip(skip).limit(page_size)
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

    def _build_query(self, filters: dict[str, Any]) -> dict[str, Any]:
        """构建 MongoDB 查询条件。"""
        q: dict[str, Any] = {}
        if "is_saki" in filters:
            q["is_saki"] = bool(filters["is_saki"])
        if "aki_stage" in filters:
            stage = filters["aki_stage"]
            if isinstance(stage, list):
                q["aki_stage"] = {"$in": [int(s) for s in stage]}
            else:
                q["aki_stage"] = int(stage)
        if "department" in filters and filters["department"]:
            q["department"] = {"$regex": str(filters["department"]), "$options": "i"}
        if "date_from" in filters or "date_to" in filters:
            date_q: dict[str, Any] = {}
            if filters.get("date_from"):
                date_q["$gte"] = datetime.fromisoformat(str(filters["date_from"]))
            if filters.get("date_to"):
                date_q["$lte"] = datetime.fromisoformat(str(filters["date_to"]))
            if date_q:
                q["created_at"] = date_q
        return q
