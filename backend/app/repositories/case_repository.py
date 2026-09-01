"""病例和证据仓储 - MongoDB 实现。

去重维度：patient_id + encounter_id + disease_code + episode_no
使用 MongoDB 原子 upsert 防止并发重复。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from app.repositories.mongodb import MongoRepository


def _now() -> datetime:
    return datetime.now(timezone.utc)


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
        """查找患者的活动病例（兼容旧去重逻辑）。

        同一患者 + 同一病种 = 同一活动病例。
        排除已终结状态：completed, transferred, deceased。
        """
        return await self.find_one({
            "patient_id": patient_id,
            "disease_code": disease_code,
            "status": {"$nin": ["completed", "transferred", "deceased"]},
        })

    async def find_active_by_dedup_key(
        self,
        patient_id: str,
        encounter_id: str,
        disease_code: str,
        episode_no: int = 1,
    ) -> Optional[dict[str, Any]]:
        """根据完整去重键查找活动病例。"""
        return await self.find_one({
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "disease_code": disease_code,
            "episode_no": episode_no,
            "status": {"$nin": ["completed", "transferred", "deceased"]},
        })

    async def upsert_case(
        self,
        patient_id: str,
        encounter_id: str,
        disease_code: str,
        episode_no: int,
        create_fields: dict[str, Any],
        update_fields: dict[str, Any],
    ) -> dict[str, Any]:
        """原子 upsert 病例，防止并发重复创建。

        使用 findOneAndUpdate 实现原子操作：
        - 如果存在匹配的活动病例，更新并返回
        - 如果不存在，创建新病例
        """
        now = _now()
        filter_query = {
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "disease_code": disease_code,
            "episode_no": episode_no,
            "status": {"$nin": ["completed", "transferred", "deceased"]},
        }

        update_ops = {
            "$set": {
                **update_fields,
                "updated_at": now,
                "last_evaluated_at": now,
            },
            "$setOnInsert": {
                **create_fields,
                "patient_id": patient_id,
                "encounter_id": encounter_id,
                "disease_code": disease_code,
                "episode_no": episode_no,
                "created_at": now,
                "first_detected_at": now,
            },
        }

        collection = await self.get_collection()
        result = await collection.find_one_and_update(
            filter_query,
            update_ops,
            upsert=True,
            return_document=True,
        )
        return result

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
        now = _now()
        case["created_at"] = now
        case["updated_at"] = now
        return await self.insert_one(case)

    async def update(self, case_id: str, updates: dict[str, Any]) -> bool:
        """更新病例。"""
        updates["updated_at"] = _now()
        return await self.update_one({"id": case_id}, updates)

    async def update_status(
        self, case_id: str, new_status: str, extra: Optional[dict[str, Any]] = None
    ) -> bool:
        """更新病例状态。"""
        updates: dict[str, Any] = {
            "status": new_status,
            "updated_at": _now(),
        }
        if extra:
            updates.update(extra)
        return await self.update_one({"id": case_id}, updates)

    async def transition_status_atomic(
        self,
        case_id: str,
        expected_status: str,
        new_status: str,
        extra_updates: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        """原子状态转换（Compare-And-Set）。

        只有当病例当前状态等于 expected_status 时才更新为 new_status。
        返回更新后的病例文档，如果状态不匹配则返回 None。

        这保证了并发安全：两个并发请求只有一个能成功。
        """
        now = _now()
        updates: dict[str, Any] = {
            "status": new_status,
            "updated_at": now,
        }
        if extra_updates:
            updates.update(extra_updates)

        collection = await self.get_collection()
        from pymongo import ReturnDocument
        result = await collection.find_one_and_update(
            {
                "id": case_id,
                "status": expected_status,
            },
            {"$set": updates},
            return_document=ReturnDocument.AFTER,
        )
        return result

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
        """统计今日新增病例（按医院本地时区）。"""
        from app.config import get_config
        import zoneinfo

        cfg = get_config()
        tz_name = cfg.hospital_timezone if hasattr(cfg, 'hospital_timezone') else "Asia/Shanghai"
        tz = zoneinfo.ZoneInfo(tz_name)
        now_local = datetime.now(tz)
        today_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        today_start_utc = today_start_local.astimezone(timezone.utc)

        query: dict[str, Any] = {"created_at": {"$gte": today_start_utc}}
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
        """获取近 N 天病例趋势（按医院本地时区统计）。"""
        from datetime import timedelta
        import zoneinfo
        from app.config import get_config

        cfg = get_config()
        tz_name = cfg.hospital_timezone if hasattr(cfg, 'hospital_timezone') else "Asia/Shanghai"
        tz = zoneinfo.ZoneInfo(tz_name)

        start = _now() - timedelta(days=days)

        match_stage: dict[str, Any] = {"created_at": {"$gte": start}}
        if disease_id:
            match_stage["disease_id"] = disease_id

        pipeline = [
            {"$match": match_stage},
            {
                "$group": {
                    "_id": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": "$created_at",
                            "timezone": tz_name,
                        }
                    },
                    "total": {"$sum": 1},
                    "screen_positive": {
                        "$sum": {"$cond": [
                            {"$ne": ["$screen_positive_at", None]}, 1, 0
                        ]}
                    },
                    "confirmed": {
                        "$sum": {"$cond": [
                            {"$ne": ["$confirmed_at", None]}, 1, 0
                        ]}
                    },
                    "excluded": {
                        "$sum": {"$cond": [
                            {"$ne": ["$excluded_at", None]}, 1, 0
                        ]}
                    },
                    "pathway_started": {
                        "$sum": {"$cond": [
                            {"$ne": ["$pathway_instance_id", ""]}, 1, 0
                        ]}
                    },
                }
            },
            {"$sort": {"_id": 1}},
        ]
        return await self.aggregate(pipeline)

    async def get_funnel_data(
        self,
        disease_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """获取筛查漏斗数据（按"曾到达该阶段"统计）。

        不是当前状态计数，而是检查时间戳字段是否存在。
        """
        match_stage: dict[str, Any] = {}
        if disease_id:
            match_stage["disease_id"] = disease_id

        pipeline = [
            {"$match": match_stage},
            {
                "$group": {
                    "_id": None,
                    "total_screened": {"$sum": 1},
                    "ever_screen_positive": {
                        "$sum": {"$cond": [
                            {"$ne": ["$screen_positive_at", None]}, 1, 0
                        ]}
                    },
                    "ever_pending_review": {
                        "$sum": {"$cond": [
                            {"$in": ["$status", ["pending_review", "confirmed", "pathway_active", "completed", "reconsideration_pending"]]}, 1, 0
                        ]}
                    },
                    "ever_confirmed": {
                        "$sum": {"$cond": [
                            {"$ne": ["$confirmed_at", None]}, 1, 0
                        ]}
                    },
                    "ever_pathway_active": {
                        "$sum": {"$cond": [
                            {"$ne": ["$pathway_instance_id", ""]}, 1, 0
                        ]}
                    },
                    "ever_completed": {
                        "$sum": {"$cond": [
                            {"$ne": ["$resolved_at", None]}, 1, 0
                        ]}
                    },
                    "ever_excluded": {
                        "$sum": {"$cond": [
                            {"$ne": ["$excluded_at", None]}, 1, 0
                        ]}
                    },
                }
            },
        ]

        results = await self.aggregate(pipeline)
        if not results:
            return {
                "total_screened": 0,
                "screen_positive": 0,
                "pending_review": 0,
                "confirmed": 0,
                "pathway_active": 0,
                "completed": 0,
                "excluded": 0,
                "stages": [],
            }

        r = results[0]
        return {
            "total_screened": r["total_screened"],
            "screen_positive": r["ever_screen_positive"],
            "pending_review": r["ever_pending_review"],
            "confirmed": r["ever_confirmed"],
            "pathway_active": r["ever_pathway_active"],
            "completed": r["ever_completed"],
            "excluded": r["ever_excluded"],
            "stages": [
                {"label": "已筛查", "count": r["total_screened"]},
                {"label": "筛查阳性", "count": r["ever_screen_positive"]},
                {"label": "待临床确认", "count": r["ever_pending_review"]},
                {"label": "临床已确认", "count": r["ever_confirmed"]},
                {"label": "路径已启动", "count": r["ever_pathway_active"]},
                {"label": "路径已完成", "count": r["ever_completed"]},
            ],
        }

    async def get_quality_metrics(
        self,
        disease_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """获取质量指标。"""
        match_stage: dict[str, Any] = {}
        if disease_id:
            match_stage["disease_id"] = disease_id

        pipeline = [
            {"$match": match_stage},
            {
                "$group": {
                    "_id": None,
                    "total": {"$sum": 1},
                    "ever_screen_positive": {
                        "$sum": {"$cond": [{"$ne": ["$screen_positive_at", None]}, 1, 0]}
                    },
                    "ever_confirmed": {
                        "$sum": {"$cond": [{"$ne": ["$confirmed_at", None]}, 1, 0]}
                    },
                    "ever_excluded": {
                        "$sum": {"$cond": [{"$ne": ["$excluded_at", None]}, 1, 0]}
                    },
                    "ever_pathway": {
                        "$sum": {"$cond": [{"$ne": ["$pathway_instance_id", ""]}, 1, 0]}
                    },
                    "ever_completed": {
                        "$sum": {"$cond": [{"$ne": ["$resolved_at", None]}, 1, 0]}
                    },
                }
            },
        ]

        results = await self.aggregate(pipeline)
        if not results:
            return {}

        r = results[0]
        total = r["total"]
        screen_positive = r["ever_screen_positive"]
        confirmed = r["ever_confirmed"]
        excluded = r["ever_excluded"]

        def _metric(numerator: int, denominator: int, definition: str) -> dict:
            return {
                "numerator": numerator,
                "denominator": denominator,
                "value": round(numerator / denominator * 100, 1) if denominator > 0 else 0,
                "unit": "%",
                "definition": definition,
            }

        return {
            "confirmation_rate": _metric(
                confirmed, screen_positive, "临床确认病例/筛查阳性病例"
            ),
            "exclusion_rate": _metric(
                excluded, screen_positive, "排除病例/筛查阳性病例"
            ),
            "pathway_start_rate": _metric(
                r["ever_pathway"], confirmed, "路径启动/临床确认病例"
            ),
            "pathway_completion_rate": _metric(
                r["ever_completed"], r["ever_pathway"], "路径完成/路径启动病例"
            ),
        }


class EvidenceRepository(MongoRepository):
    """病例证据仓储。"""

    def __init__(self):
        super().__init__("case_evidence")

    async def find_by_id(self, evidence_id: str) -> Optional[dict[str, Any]]:
        """根据 ID 查询证据。"""
        return await self.find_one({"id": evidence_id})

    async def find_by_hash(self, evidence_hash: str) -> Optional[dict[str, Any]]:
        """根据哈希查询证据（幂等检查）。"""
        return await self.find_one({"evidence_hash": evidence_hash})

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
        evidence["created_at"] = _now()
        return await self.insert_one(evidence)

    async def upsert_by_hash(self, evidence: dict[str, Any]) -> str:
        """根据 evidence_hash 幂等写入证据。

        如果已存在相同 hash 的证据，更新；否则创建。
        使用 $setOnInsert 保护 id 和 created_at 不被覆盖。
        """
        evidence_hash = evidence.get("evidence_hash", "")
        if not evidence_hash:
            return await self.create(evidence)

        now = _now()
        evidence_id = evidence.get("id", "")

        # 分离 mutable 和 immutable 字段
        mutable_fields = {k: v for k, v in evidence.items() if k not in ("id", "evidence_hash", "created_at")}
        mutable_fields["updated_at"] = now

        collection = await self.get_collection()
        result = await collection.find_one_and_update(
            {"evidence_hash": evidence_hash},
            {
                "$set": mutable_fields,
                "$setOnInsert": {
                    "id": evidence_id,
                    "evidence_hash": evidence_hash,
                    "created_at": now,
                },
            },
            upsert=True,
            return_document=True,
        )
        return result.get("id", evidence_id)

    async def create_many(self, evidences: list[dict[str, Any]]) -> list[str]:
        """批量创建证据。"""
        now = _now()
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
        confirmation["created_at"] = confirmation.get("created_at", _now())
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
        now = _now()
        instance["created_at"] = now
        instance["updated_at"] = now
        return await self.insert_one(instance)

    async def update(self, instance_id: str, updates: dict[str, Any]) -> bool:
        """更新路径实例。"""
        updates["updated_at"] = _now()
        return await self.update_one({"id": instance_id}, updates)

    async def count_active_overdue(self, disease_id: Optional[str] = None) -> int:
        """统计超时的活动路径实例数。"""
        now = _now()
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
        now = _now()
        task["created_at"] = now
        task["updated_at"] = now
        return await self.insert_one(task)

    async def create_many(self, tasks: list[dict[str, Any]]) -> list[str]:
        """批量创建任务。"""
        now = _now()
        for t in tasks:
            t["created_at"] = now
            t["updated_at"] = now
        return await self.insert_many(tasks)

    async def update(self, task_id: str, updates: dict[str, Any]) -> bool:
        """更新任务。"""
        updates["updated_at"] = _now()
        return await self.update_one({"id": task_id}, updates)

    async def complete_task(
        self,
        task_id: str,
        completed_by: str,
        actual_value: Optional[float] = None,
        note: str = "",
    ) -> bool:
        """完成任务。"""
        now = _now()
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


class ConclusionRepository(MongoRepository):
    """临床结论仓储。"""

    def __init__(self):
        super().__init__("clinical_conclusions")

    async def find_by_case(
        self, case_id: str, current_only: bool = True
    ) -> list[dict[str, Any]]:
        """查询病例的临床结论。"""
        query: dict[str, Any] = {"case_id": case_id}
        if current_only:
            query["superseded_at"] = None
        return await self.find_many(query, sort=[("generated_at", -1)])

    async def create(self, conclusion: dict[str, Any]) -> str:
        """创建临床结论。"""
        conclusion["created_at"] = _now()
        return await self.insert_one(conclusion)

    async def supersede(self, conclusion_id: str, new_conclusion_id: str) -> bool:
        """标记旧结论被取代。"""
        return await self.update_one(
            {"id": conclusion_id},
            {"superseded_at": _now(), "superseded_by": new_conclusion_id},
        )
