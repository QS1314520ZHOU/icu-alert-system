"""MongoDB 数据库连接和仓储层。"""

from __future__ import annotations

import logging
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

# 全局数据库连接
_client: Optional[AsyncIOMotorClient] = None
_database: Optional[AsyncIOMotorDatabase] = None


async def connect(mongodb_url: str = "mongodb://localhost:27017", database_name: str = "icu_alert"):
    """连接到 MongoDB。"""
    global _client, _database

    try:
        _client = AsyncIOMotorClient(mongodb_url)
        _database = _client[database_name]

        # 测试连接
        await _client.admin.command('ping')
        logger.info(f"成功连接到 MongoDB: {mongodb_url}/{database_name}")

        # 创建索引
        await _create_indexes()

    except Exception as e:
        logger.error(f"连接 MongoDB 失败: {e}")
        raise


async def disconnect():
    """断开 MongoDB 连接。"""
    global _client, _database

    if _client:
        _client.close()
        _client = None
        _database = None
        logger.info("已断开 MongoDB 连接")


async def get_database() -> AsyncIOMotorDatabase:
    """获取数据库实例。"""
    if _database is None:
        raise RuntimeError("数据库未连接，请先调用 connect()")
    return _database


async def _create_indexes():
    """创建数据库索引。"""
    db = await get_database()

    # 病种集合索引
    await db.diseases.create_index("name")
    await db.diseases.create_index("status")
    await db.diseases.create_index("category_id")
    await db.diseases.create_index("icd_codes")

    # 术语集合索引
    await db.terminologies.create_index("standard_name")
    await db.terminologies.create_index("abbreviation")
    await db.terminologies.create_index("category")
    await db.terminologies.create_index("status")

    # 表型规则集合索引
    await db.phenotypes.create_index("disease_id")
    await db.phenotypes.create_index("status")

    # 审核任务集合索引
    await db.reviews.create_index("resource_type")
    await db.reviews.create_index("resource_id")
    await db.reviews.create_index("status")

    # 离线包集合索引
    await db.offline_packages.create_index("status")
    await db.offline_packages.create_index("target_device")

    # 质量快照集合索引
    await db.quality_snapshots.create_index("disease_id")
    await db.quality_snapshots.create_index("generated_at")

    # AI 提案集合索引
    await db.ai_proposals.create_index("disease_id")
    await db.ai_proposals.create_index("status")

    # 审计事件集合索引
    await db.audit_events.create_index("resource_type")
    await db.audit_events.create_index("resource_id")
    await db.audit_events.create_index("timestamp")

    # 病种病例集合索引
    await db.disease_cases.create_index("patient_id")
    await db.disease_cases.create_index("disease_id")
    await db.disease_cases.create_index("disease_code")
    await db.disease_cases.create_index("status")
    await db.disease_cases.create_index("created_at")
    await db.disease_cases.create_index("encounter_id")
    await db.disease_cases.create_index("source_alert_ids")
    # 去重索引：同一患者+同一病种的活动病例唯一（兼容旧逻辑）
    await db.disease_cases.create_index(
        [("patient_id", 1), ("disease_code", 1), ("status", 1)],
        name="idx_patient_disease_active",
    )
    # 新去重索引：patient_id + encounter_id + disease_code + episode_no
    await db.disease_cases.create_index(
        [("patient_id", 1), ("encounter_id", 1), ("disease_code", 1), ("episode_no", 1)],
        name="idx_dedup_key",
    )
    # 活动病例唯一键：防止并发创建重复活动病例
    await db.disease_cases.create_index(
        [("active_case_key", 1)],
        unique=True,
        sparse=True,
        name="uq_disease_case_active_key",
    )

    # 病例证据集合索引
    await db.case_evidence.create_index("case_id")
    await db.case_evidence.create_index("patient_id")
    await db.case_evidence.create_index("evidence_type")
    await db.case_evidence.create_index("observed_at")
    await db.case_evidence.create_index("evidence_hash", unique=True, sparse=True)

    # 临床结论集合索引
    await db.clinical_conclusions.create_index("case_id")
    await db.clinical_conclusions.create_index("patient_id")
    await db.clinical_conclusions.create_index("conclusion_code")
    await db.clinical_conclusions.create_index([("case_id", 1), ("superseded_at", 1)])

    # 临床确认记录集合索引
    await db.clinical_confirmations.create_index("case_id")
    await db.clinical_confirmations.create_index("patient_id")
    await db.clinical_confirmations.create_index("created_at")

    # 路径实例集合索引
    await db.pathway_instances.create_index("case_id")
    await db.pathway_instances.create_index("patient_id")
    await db.pathway_instances.create_index("disease_id")
    await db.pathway_instances.create_index("status")

    # 路径任务集合索引
    await db.pathway_tasks.create_index("instance_id")
    await db.pathway_tasks.create_index("case_id")
    await db.pathway_tasks.create_index("execution_status")

    # 病种关系集合索引
    await db.disease_relations.create_index("source_id")
    await db.disease_relations.create_index("target_id")

    # 临床路径定义集合索引
    await db.clinical_pathways.create_index("disease_id")
    await db.clinical_pathways.create_index("status")

    # AI 病例洞察集合索引
    await db.case_ai_insights.create_index("case_id")
    await db.case_ai_insights.create_index("generated_at")

    logger.info("数据库索引创建完成")


class MongoRepository:
    """MongoDB 仓储基类。"""

    def __init__(self, collection_name: str):
        self.collection_name = collection_name

    async def get_collection(self):
        """获取集合。"""
        db = await get_database()
        return db[self.collection_name]

    async def find_one(self, query: dict[str, Any]) -> Optional[dict[str, Any]]:
        """查询单个文档。"""
        collection = await self.get_collection()
        return await collection.find_one(query)

    async def find_many(
        self,
        query: dict[str, Any],
        skip: int = 0,
        limit: int = 100,
        sort: Optional[list[tuple[str, int]]] = None
    ) -> list[dict[str, Any]]:
        """查询多个文档。"""
        collection = await self.get_collection()
        cursor = collection.find(query).skip(skip).limit(limit)

        if sort:
            cursor = cursor.sort(sort)

        return await cursor.to_list(length=limit)

    async def insert_one(self, document: dict[str, Any]) -> str:
        """插入单个文档。"""
        collection = await self.get_collection()
        result = await collection.insert_one(document)
        return str(result.inserted_id)

    async def insert_many(self, documents: list[dict[str, Any]]) -> list[str]:
        """插入多个文档。"""
        collection = await self.get_collection()
        result = await collection.insert_many(documents)
        return [str(id) for id in result.inserted_ids]

    async def update_one(
        self,
        query: dict[str, Any],
        update: dict[str, Any],
        upsert: bool = False
    ) -> bool:
        """更新单个文档。"""
        collection = await self.get_collection()
        result = await collection.update_one(query, {"$set": update}, upsert=upsert)
        return result.modified_count > 0

    async def delete_one(self, query: dict[str, Any]) -> bool:
        """删除单个文档。"""
        collection = await self.get_collection()
        result = await collection.delete_one(query)
        return result.deleted_count > 0

    async def count(self, query: dict[str, Any]) -> int:
        """统计文档数量。"""
        collection = await self.get_collection()
        return await collection.count_documents(query)

    async def aggregate(self, pipeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """聚合查询。"""
        collection = await self.get_collection()
        cursor = collection.aggregate(pipeline)
        return await cursor.to_list(length=1000)
