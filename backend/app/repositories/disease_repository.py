"""病种仓储 - MongoDB 实现。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.repositories.mongodb import MongoRepository


class DiseaseRepository(MongoRepository):
    """病种仓储。"""

    def __init__(self):
        super().__init__("diseases")

    async def find_by_id(self, disease_id: str) -> Optional[dict[str, Any]]:
        """根据 ID 查询病种。"""
        return await self.find_one({"id": disease_id})

    async def find_all(
        self,
        status: Optional[str] = None,
        category: Optional[str] = None,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """查询所有病种。"""
        query = {}
        if status:
            query["status"] = status
        if category:
            query["category_id"] = category

        return await self.find_many(query, limit=limit, sort=[("created_at", -1)])

    async def create(self, disease: dict[str, Any]) -> str:
        """创建病种。"""
        disease["created_at"] = datetime.utcnow()
        disease["updated_at"] = datetime.utcnow()
        disease["revision"] = 1
        return await self.insert_one(disease)

    async def update(self, disease_id: str, updates: dict[str, Any]) -> bool:
        """更新病种。"""
        updates["updated_at"] = datetime.utcnow()
        return await self.update_one({"id": disease_id}, updates)

    async def increment_revision(self, disease_id: str) -> bool:
        """增加版本号。"""
        collection = await self.get_collection()
        result = await collection.update_one(
            {"id": disease_id},
            {"$inc": {"revision": 1}, "$set": {"updated_at": datetime.utcnow()}}
        )
        return result.modified_count > 0

    async def find_by_status(self, status: str) -> list[dict[str, Any]]:
        """根据状态查询病种。"""
        return await self.find_many({"status": status})

    async def find_by_category(self, category_id: str) -> list[dict[str, Any]]:
        """根据分类查询病种。"""
        return await self.find_many({"category_id": category_id})

    async def find_by_icd_code(self, icd_code: str) -> list[dict[str, Any]]:
        """根据 ICD 编码查询病种。"""
        return await self.find_many({"icd_codes": icd_code})

    async def search(self, keyword: str, limit: int = 100) -> list[dict[str, Any]]:
        """搜索病种。"""
        query = {
            "$or": [
                {"name": {"$regex": keyword, "$options": "i"}},
                {"description": {"$regex": keyword, "$options": "i"}},
                {"icd_codes": {"$regex": keyword, "$options": "i"}}
            ]
        }
        return await self.find_many(query, limit=limit)


class TerminologyRepository(MongoRepository):
    """术语仓储。"""

    def __init__(self):
        super().__init__("terminologies")

    async def find_by_id(self, term_id: str) -> Optional[dict[str, Any]]:
        """根据 ID 查询术语。"""
        return await self.find_one({"id": term_id})

    async def find_all(
        self,
        category: Optional[str] = None,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """查询所有术语。"""
        query = {}
        if category:
            query["category"] = category
        if status:
            query["status"] = status
        if keyword:
            query["$or"] = [
                {"standard_name": {"$regex": keyword, "$options": "i"}},
                {"abbreviation": {"$regex": keyword, "$options": "i"}},
                {"english_name": {"$regex": keyword, "$options": "i"}}
            ]

        return await self.find_many(query, limit=limit, sort=[("standard_name", 1)])

    async def create(self, terminology: dict[str, Any]) -> str:
        """创建术语。"""
        terminology["created_at"] = datetime.utcnow()
        terminology["updated_at"] = datetime.utcnow()
        return await self.insert_one(terminology)

    async def update(self, term_id: str, updates: dict[str, Any]) -> bool:
        """更新术语。"""
        updates["updated_at"] = datetime.utcnow()
        return await self.update_one({"id": term_id}, updates)

    async def find_by_category(self, category: str) -> list[dict[str, Any]]:
        """根据分类查询术语。"""
        return await self.find_many({"category": category})

    async def get_categories(self) -> list[dict[str, Any]]:
        """获取术语分类统计。"""
        pipeline = [
            {"$group": {"_id": "$category", "count": {"$sum": 1}}},
            {"$sort": {"_id": 1}}
        ]
        results = await self.aggregate(pipeline)
        return [{"name": r["_id"], "count": r["count"]} for r in results if r["_id"]]


class PhenotypeRepository(MongoRepository):
    """表型规则仓储。"""

    def __init__(self):
        super().__init__("phenotypes")

    async def find_by_id(self, phenotype_id: str) -> Optional[dict[str, Any]]:
        """根据 ID 查询表型规则。"""
        return await self.find_one({"id": phenotype_id})

    async def find_all(
        self,
        disease_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """查询所有表型规则。"""
        query = {}
        if disease_id:
            query["disease_id"] = disease_id
        if status:
            query["status"] = status

        return await self.find_many(query, limit=limit, sort=[("created_at", -1)])

    async def create(self, phenotype: dict[str, Any]) -> str:
        """创建表型规则。"""
        phenotype["created_at"] = datetime.utcnow()
        phenotype["updated_at"] = datetime.utcnow()
        return await self.insert_one(phenotype)

    async def update(self, phenotype_id: str, updates: dict[str, Any]) -> bool:
        """更新表型规则。"""
        updates["updated_at"] = datetime.utcnow()
        return await self.update_one({"id": phenotype_id}, updates)

    async def find_by_disease(self, disease_id: str) -> list[dict[str, Any]]:
        """根据病种查询表型规则。"""
        return await self.find_many({"disease_id": disease_id})

    async def get_stats(self) -> dict[str, Any]:
        """获取表型规则统计。"""
        total = await self.count({})
        by_status = {}

        for status in ["draft", "active", "disabled", "deprecated"]:
            count = await self.count({"status": status})
            if count > 0:
                by_status[status] = count

        return {"total": total, "by_status": by_status}


class ReviewRepository(MongoRepository):
    """审核任务仓储。"""

    def __init__(self):
        super().__init__("reviews")

    async def find_by_id(self, review_id: str) -> Optional[dict[str, Any]]:
        """根据 ID 查询审核任务。"""
        return await self.find_one({"id": review_id})

    async def find_all(
        self,
        status: Optional[str] = None,
        resource_type: Optional[str] = None,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """查询所有审核任务。"""
        query = {}
        if status:
            query["status"] = status
        if resource_type:
            query["resource_type"] = resource_type

        return await self.find_many(query, limit=limit, sort=[("submitted_at", -1)])

    async def create(self, review: dict[str, Any]) -> str:
        """创建审核任务。"""
        review["submitted_at"] = datetime.utcnow()
        return await self.insert_one(review)

    async def update(self, review_id: str, updates: dict[str, Any]) -> bool:
        """更新审核任务。"""
        return await self.update_one({"id": review_id}, updates)

    async def find_by_resource(self, resource_type: str, resource_id: str) -> list[dict[str, Any]]:
        """根据资源查询审核任务。"""
        return await self.find_many({
            "resource_type": resource_type,
            "resource_id": resource_id
        })


class OfflinePackageRepository(MongoRepository):
    """离线包仓储。"""

    def __init__(self):
        super().__init__("offline_packages")

    async def find_by_id(self, package_id: str) -> Optional[dict[str, Any]]:
        """根据 ID 查询离线包。"""
        return await self.find_one({"id": package_id})

    async def find_all(
        self,
        status: Optional[str] = None,
        target_device: Optional[str] = None,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """查询所有离线包。"""
        query = {}
        if status:
            query["status"] = status
        if target_device:
            query["target_device"] = target_device

        return await self.find_many(query, limit=limit, sort=[("created_at", -1)])

    async def create(self, package: dict[str, Any]) -> str:
        """创建离线包。"""
        package["created_at"] = datetime.utcnow()
        package["updated_at"] = datetime.utcnow()
        return await self.insert_one(package)

    async def update(self, package_id: str, updates: dict[str, Any]) -> bool:
        """更新离线包。"""
        updates["updated_at"] = datetime.utcnow()
        return await self.update_one({"id": package_id}, updates)

    async def get_stats(self) -> dict[str, Any]:
        """获取离线包统计。"""
        total = await self.count({})
        by_status = {}
        total_size = 0.0

        for status in ["draft", "building", "built", "published", "archived"]:
            count = await self.count({"status": status})
            if count > 0:
                by_status[status] = count

        # 计算总大小
        pipeline = [
            {"$group": {"_id": None, "total_size": {"$sum": "$file_size_mb"}}}
        ]
        results = await self.aggregate(pipeline)
        if results:
            total_size = results[0].get("total_size", 0.0)

        return {"total": total, "by_status": by_status, "total_size_mb": total_size}


class QualityRepository(MongoRepository):
    """质量快照仓储。"""

    def __init__(self):
        super().__init__("quality_snapshots")

    async def find_by_id(self, snapshot_id: str) -> Optional[dict[str, Any]]:
        """根据 ID 查询质量快照。"""
        return await self.find_one({"id": snapshot_id})

    async def find_all(
        self,
        disease_id: Optional[str] = None,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """查询所有质量快照。"""
        query = {}
        if disease_id:
            query["disease_id"] = disease_id

        return await self.find_many(query, limit=limit, sort=[("generated_at", -1)])

    async def create(self, snapshot: dict[str, Any]) -> str:
        """创建质量快照。"""
        snapshot["generated_at"] = datetime.utcnow()
        return await self.insert_one(snapshot)

    async def find_by_disease(self, disease_id: str) -> list[dict[str, Any]]:
        """根据病种查询质量快照。"""
        return await self.find_many({"disease_id": disease_id}, sort=[("generated_at", -1)])

    async def get_latest(self, disease_id: str) -> Optional[dict[str, Any]]:
        """获取最新的质量快照。"""
        results = await self.find_many(
            {"disease_id": disease_id},
            limit=1,
            sort=[("generated_at", -1)]
        )
        return results[0] if results else None


class AiProposalRepository(MongoRepository):
    """AI 提案仓储。"""

    def __init__(self):
        super().__init__("ai_proposals")

    async def find_by_id(self, proposal_id: str) -> Optional[dict[str, Any]]:
        """根据 ID 查询 AI 提案。"""
        return await self.find_one({"id": proposal_id})

    async def find_all(
        self,
        disease_id: Optional[str] = None,
        proposal_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """查询所有 AI 提案。"""
        query = {}
        if disease_id:
            query["disease_id"] = disease_id
        if proposal_type:
            query["proposal_type"] = proposal_type
        if status:
            query["status"] = status

        return await self.find_many(query, limit=limit, sort=[("created_at", -1)])

    async def create(self, proposal: dict[str, Any]) -> str:
        """创建 AI 提案。"""
        proposal["created_at"] = datetime.utcnow()
        proposal["updated_at"] = datetime.utcnow()
        return await self.insert_one(proposal)

    async def update(self, proposal_id: str, updates: dict[str, Any]) -> bool:
        """更新 AI 提案。"""
        updates["updated_at"] = datetime.utcnow()
        return await self.update_one({"id": proposal_id}, updates)

    async def get_stats(self) -> dict[str, Any]:
        """获取 AI 提案统计。"""
        total = await self.count({})
        by_status = {}
        by_type = {}

        for status in ["pending", "approved", "rejected", "implemented"]:
            count = await self.count({"status": status})
            if count > 0:
                by_status[status] = count

        # 按类型统计
        pipeline = [
            {"$group": {"_id": "$proposal_type", "count": {"$sum": 1}}}
        ]
        results = await self.aggregate(pipeline)
        for r in results:
            if r["_id"]:
                by_type[r["_id"]] = r["count"]

        # 平均置信度
        pipeline = [
            {"$group": {"_id": None, "avg_confidence": {"$avg": "$confidence"}}}
        ]
        avg_results = await self.aggregate(pipeline)
        avg_confidence = avg_results[0]["avg_confidence"] if avg_results else 0.0

        return {
            "total": total,
            "by_status": by_status,
            "by_type": by_type,
            "average_confidence": avg_confidence
        }


class AuditRepository(MongoRepository):
    """审计事件仓储。"""

    def __init__(self):
        super().__init__("audit_events")

    async def find_all(
        self,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """查询所有审计事件。"""
        query = {}
        if resource_type:
            query["resource_type"] = resource_type
        if resource_id:
            query["resource_id"] = resource_id

        return await self.find_many(query, limit=limit, sort=[("timestamp", -1)])

    async def create(self, event: dict[str, Any]) -> str:
        """创建审计事件。"""
        event["timestamp"] = datetime.utcnow()
        return await self.insert_one(event)

    async def find_by_resource(self, resource_type: str, resource_id: str) -> list[dict[str, Any]]:
        """根据资源查询审计事件。"""
        return await self.find_many({
            "resource_type": resource_type,
            "resource_id": resource_id
        }, sort=[("timestamp", -1)])


class DiseaseRelationRepository(MongoRepository):
    """病种关系仓储。"""

    def __init__(self):
        super().__init__("disease_relations")

    async def find_by_id(self, relation_id: str) -> Optional[dict[str, Any]]:
        """根据 ID 查询关系。"""
        return await self.find_one({"id": relation_id})

    async def find_by_disease(self, disease_id: str) -> list[dict[str, Any]]:
        """查询病种的所有关系。"""
        return await self.find_many({
            "$or": [
                {"source_id": disease_id},
                {"target_id": disease_id},
            ]
        })

    async def create(self, relation: dict[str, Any]) -> str:
        """创建关系。"""
        relation["created_at"] = datetime.utcnow()
        return await self.insert_one(relation)

    async def delete(self, relation_id: str) -> bool:
        """删除关系。"""
        return await self.delete_one({"id": relation_id})


class PathwayRepository(MongoRepository):
    """临床路径定义仓储。"""

    def __init__(self):
        super().__init__("clinical_pathways")

    async def find_by_id(self, pathway_id: str) -> Optional[dict[str, Any]]:
        """根据 ID 查询路径。"""
        return await self.find_one({"id": pathway_id})

    async def find_by_disease(self, disease_id: str) -> Optional[dict[str, Any]]:
        """根据病种查询路径。"""
        return await self.find_one({"disease_id": disease_id})

    async def create(self, pathway: dict[str, Any]) -> str:
        """创建路径。"""
        pathway["created_at"] = datetime.utcnow()
        pathway["updated_at"] = datetime.utcnow()
        return await self.insert_one(pathway)

    async def update(self, pathway_id: str, updates: dict[str, Any]) -> bool:
        """更新路径。"""
        updates["updated_at"] = datetime.utcnow()
        return await self.update_one({"id": pathway_id}, updates)
