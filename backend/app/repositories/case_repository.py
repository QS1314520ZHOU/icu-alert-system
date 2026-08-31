"""病例和证据仓储 - MongoDB 实现。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.repositories.mongodb import MongoRepository


class CaseRepository(MongoRepository):
    """病种病例仓储。"""

    def __init__(self):
        super().__init__("disease_cases")

    async def find_by_id(self, case_id: str) -> Optional[dict[str, Any]]:
        """根据 ID 查询病例。"""
        return await self.find_one({"id": case_id})

    async def find_active_by_patient_disease(
        self, patient_id: str, disease_code: str
    ) -> Optional[dict[str, Any]]:
        """查找患者的活动病例（去重）。

        同一患者 + 同一病种 = 同一活动病例。
        排除已终结状态：completed, transferred, deceased。
        """
        return await self.find_one({
            "patient_id": patient_id,
            "disease_code": disease_code,
            "status": {"$nin": ["completed", "transferred", "deceased"]},
        })

    async def find_all(
        self,
        disease_id: Optional[str] = None,
        disease_code: Optional[str] = None,
        status: Optional[str] = None,
        patient_id: Optional[str] = None,
        dept: Optional[str] = None,
        risk_level: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 50,
        sort_by: str = "last_evaluated_at",
        sort_order: int = -1,
    ) -> list[dict[str, Any]]:
        """查询病例列表（支持分页、筛选、排序）。"""
        query: dict[str, Any] = {}
        if disease_id:
            query["disease_id"] = disease_id
        if disease_code:
            query["disease_code"] = disease_code
        if status:
            query["status"] = status
        if patient_id:
            query["patient_id"] = patient_id
        if dept:
            query["dept"] = dept
        if risk_level:
            query["risk_level"] = risk_level
        if date_from or date_to:
            time_query: dict[str, Any] = {}
            if date_from:
                time_query["$gte"] = date_from
            if date_to:
                time_query["$lte"] = date_to
            query["first_detected_at"] = time_query

        return await self.find_many(
            query,
            skip=skip,
            limit=limit,
            sort=[(sort_by, sort_order)],
        )

    async def count_by_filters(
        self,
        disease_id: Optional[str] = None,
        status: Optional[str] = None,
        patient_id: Optional[str] = None,
    ) -> int:
        """统计病例数量。"""
        query: dict[str, Any] = {}
        if disease_id:
            query["disease_id"] = disease_id
        if status:
            query["status"] = status
        if patient_id:
            query["patient_id"] = patient_id
        return await self.count(query)

    async def create(self, case: dict[str, Any]) -> str:
        """创建病例。"""
        case["created_at"] = datetime.utcnow()
        case["updated_at"] = datetime.utcnow()
        return await self.insert_one(case)

    async def update(self, case_id: str, updates: dict[str, Any]) -> bool:
        """更新病例。"""
        updates["updated_at"] = datetime.utcnow()
        return await self.update_one({"id": case_id}, updates)

    async def update_status(
        self, case_id: str, new_status: str, extra: Optional[dict[str, Any]] = None
    ) -> bool:
        """更新病例状态。"""
        updates: dict[str, Any] = {
            "status": new_status,
            "updated_at": datetime.utcnow(),
        }
        if extra:
            updates.update(extra)
        return await self.update_one({"id": case_id}, updates)

    async def count_by_status(self, disease_id: Optional[str] = None) -> dict[str, int]:
        """按状态统计病例数。"""
        match_stage: dict[str, Any] = {}
        if disease_id:
            match_stage["disease_id"] = disease_id

        pipeline = [
            {"$match": match_stage} if match_stage else {"$match": {}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]
        results = await self.aggregate(pipeline)
        return {r["_id"]: r["count"] for r in results if r["_id"]}

    async def count_today_new(self, disease_id: Optional[str] = None) -> int:
        """统计今日新增病例。"""
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        query: dict[str, Any] = {"created_at": {"$gte": today_start}}
        if disease_id:
            query["disease_id"] = disease_id
        return await self.count(query)

    async def count_pending_review(self, disease_id: Optional[str] = None) -> int:
        """统计待医生确认病例数。"""
        query: dict[str, Any] = {"status": "pending_review"}
        if disease_id:
            query["disease_id"] = disease_id
        return await self.count(query)

    async def get_risk_distribution(self, disease_id: Optional[str] = None) -> list[dict[str, Any]]:
        """获取风险等级分布。"""
        match_stage: dict[str, Any] = {"status": {"$nin": ["completed", "transferred", "deceased"]}}
        if disease_id:
            match_stage["disease_id"] = disease_id

        pipeline = [
            {"$match": match_stage},
            {"$group": {"_id": "$risk_level", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        return await self.aggregate(pipeline)

    async def get_case_trend(
        self,
        disease_id: Optional[str] = None,
        days: int = 30,
    ) -> list[dict[str, Any]]:
        """获取近 N 天病例识别趋势。"""
        from datetime import timedelta
        start = datetime.utcnow() - timedelta(days=days)

        match_stage: dict[str, Any] = {"created_at": {"$gte": start}}
        if disease_id:
            match_stage["disease_id"] = disease_id

        pipeline = [
            {"$match": match_stage},
            {
                "$group": {
                    "_id": {
                        "$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}
                    },
                    "total": {"$sum": 1},
                    "confirmed": {
                        "$sum": {"$cond": [{"$eq": ["$status", "confirmed"]}, 1, 0]}
                    },
                    "excluded": {
                        "$sum": {"$cond": [{"$eq": ["$status", "excluded"]}, 1, 0]}
                    },
                }
            },
            {"$sort": {"_id": 1}},
        ]
        return await self.aggregate(pipeline)


class EvidenceRepository(MongoRepository):
    """病例证据仓储。"""

    def __init__(self):
        super().__init__("case_evidence")

    async def find_by_id(self, evidence_id: str) -> Optional[dict[str, Any]]:
        """根据 ID 查询证据。"""
        return await self.find_one({"id": evidence_id})

    async def find_by_case(
        self,
        case_id: str,
        evidence_type: Optional[str] = None,
        matched: Optional[bool] = None,
        skip: int = 0,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """查询病例的所有证据。"""
        query: dict[str, Any] = {"case_id": case_id}
        if evidence_type:
            query["evidence_type"] = evidence_type
        if matched is not None:
            query["matched"] = matched
        return await self.find_many(
            query,
            skip=skip,
            limit=limit,
            sort=[("observed_at", -1)],
        )

    async def find_by_patient(
        self,
        patient_id: str,
        disease_code: Optional[str] = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """查询患者的所有证据。"""
        query: dict[str, Any] = {"patient_id": patient_id}
        if disease_code:
            query["disease_code"] = disease_code
        return await self.find_many(query, limit=limit, sort=[("observed_at", -1)])

    async def create(self, evidence: dict[str, Any]) -> str:
        """创建证据。"""
        evidence["created_at"] = datetime.utcnow()
        return await self.insert_one(evidence)

    async def create_many(self, evidences: list[dict[str, Any]]) -> list[str]:
        """批量创建证据。"""
        now = datetime.utcnow()
        for e in evidences:
            e["created_at"] = now
        return await self.insert_many(evidences)

    async def count_by_case(self, case_id: str) -> int:
        """统计病例证据数量。"""
        return await self.count({"case_id": case_id})

    async def count_matched_by_case(self, case_id: str) -> int:
        """统计病例命中证据数量。"""
        return await self.count({"case_id": case_id, "matched": True})

    async def get_evidence_completeness(self, case_id: str) -> dict[str, Any]:
        """获取证据完整度统计。"""
        pipeline = [
            {"$match": {"case_id": case_id}},
            {
                "$group": {
                    "_id": "$evidence_type",
                    "total": {"$sum": 1},
                    "matched": {"$sum": {"$cond": ["$matched", 1, 0]}},
                    "with_quality_flag": {
                        "$sum": {
                            "$cond": [
                                {"$gt": [{"$size": {"$ifNull": ["$quality_flags", []]}}, 0]},
                                1,
                                0,
                            ]
                        }
                    },
                }
            },
            {"$sort": {"_id": 1}},
        ]
        results = await self.aggregate(pipeline)

        total = sum(r["total"] for r in results)
        matched = sum(r["matched"] for r in results)

        return {
            "total_evidence": total,
            "matched_evidence": matched,
            "completeness_ratio": round(matched / total, 4) if total > 0 else None,
            "by_type": {
                r["_id"]: {
                    "total": r["total"],
                    "matched": r["matched"],
                    "quality_issues": r["with_quality_flag"],
                }
                for r in results
            },
        }

    async def get_timeline(self, case_id: str) -> list[dict[str, Any]]:
        """获取证据时间线（按观测时间排序）。"""
        return await self.find_many(
            {"case_id": case_id},
            limit=500,
            sort=[("observed_at", 1)],
        )


class ConfirmationRepository(MongoRepository):
    """临床确认记录仓储（不可变审计日志）。"""

    def __init__(self):
        super().__init__("clinical_confirmations")

    async def find_by_case(
        self, case_id: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        """查询病例的确认记录。"""
        return await self.find_many(
            {"case_id": case_id},
            limit=limit,
            sort=[("created_at", -1)],
        )

    async def create(self, confirmation: dict[str, Any]) -> str:
        """创建确认记录（不可变）。"""
        confirmation["created_at"] = datetime.utcnow()
        return await self.insert_one(confirmation)


class PathwayInstanceRepository(MongoRepository):
    """路径实例仓储。"""

    def __init__(self):
        super().__init__("pathway_instances")

    async def find_by_id(self, instance_id: str) -> Optional[dict[str, Any]]:
        """根据 ID 查询路径实例。"""
        return await self.find_one({"id": instance_id})

    async def find_by_case(self, case_id: str) -> Optional[dict[str, Any]]:
        """根据病例查询路径实例。"""
        return await self.find_one({"case_id": case_id})

    async def find_active_by_patient(
        self, patient_id: str
    ) -> list[dict[str, Any]]:
        """查询患者的活动路径实例。"""
        return await self.find_many(
            {"patient_id": patient_id, "status": "active"},
            sort=[("started_at", -1)],
        )

    async def create(self, instance: dict[str, Any]) -> str:
        """创建路径实例。"""
        instance["created_at"] = datetime.utcnow()
        instance["updated_at"] = datetime.utcnow()
        return await self.insert_one(instance)

    async def update(self, instance_id: str, updates: dict[str, Any]) -> bool:
        """更新路径实例。"""
        updates["updated_at"] = datetime.utcnow()
        return await self.update_one({"id": instance_id}, updates)

    async def count_active_overdue(self, disease_id: Optional[str] = None) -> int:
        """统计超时的活动路径实例数。"""
        now = datetime.utcnow()
        query: dict[str, Any] = {
            "status": "active",
            "deadline_1h": {"$lt": now},
        }
        if disease_id:
            query["disease_id"] = disease_id
        return await self.count(query)


class PathwayTaskRepository(MongoRepository):
    """路径任务仓储。"""

    def __init__(self):
        super().__init__("pathway_tasks")

    async def find_by_id(self, task_id: str) -> Optional[dict[str, Any]]:
        """根据 ID 查询任务。"""
        return await self.find_one({"id": task_id})

    async def find_by_instance(
        self, instance_id: str
    ) -> list[dict[str, Any]]:
        """查询路径实例的所有任务。"""
        return await self.find_many(
            {"instance_id": instance_id},
            sort=[("created_at", 1)],
        )

    async def find_by_case(self, case_id: str) -> list[dict[str, Any]]:
        """查询病例的所有任务。"""
        return await self.find_many(
            {"case_id": case_id},
            sort=[("created_at", 1)],
        )

    async def create(self, task: dict[str, Any]) -> str:
        """创建任务。"""
        task["created_at"] = datetime.utcnow()
        task["updated_at"] = datetime.utcnow()
        return await self.insert_one(task)

    async def create_many(self, tasks: list[dict[str, Any]]) -> list[str]:
        """批量创建任务。"""
        now = datetime.utcnow()
        for t in tasks:
            t["created_at"] = now
            t["updated_at"] = now
        return await self.insert_many(tasks)

    async def update(self, task_id: str, updates: dict[str, Any]) -> bool:
        """更新任务。"""
        updates["updated_at"] = datetime.utcnow()
        return await self.update_one({"id": task_id}, updates)

    async def complete_task(
        self,
        task_id: str,
        completed_by: str,
        actual_value: Optional[float] = None,
        note: str = "",
    ) -> bool:
        """完成任务。"""
        now = datetime.utcnow()
        updates: dict[str, Any] = {
            "execution_status": "completed",
            "completed_at": now,
            "completed_by": completed_by,
            "updated_at": now,
        }
        if actual_value is not None:
            updates["actual_value"] = actual_value
        if note:
            updates["review_note"] = note
        return await self.update_one({"id": task_id}, updates)
