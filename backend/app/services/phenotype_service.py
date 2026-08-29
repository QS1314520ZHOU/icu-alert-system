"""表型规则管理服务 - MongoDB 实现。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.models.disease_center import (
    PhenotypeRule,
    PhenotypeRuleStatus,
)
from app.repositories import PhenotypeRepository


# 仓储实例
_repo = PhenotypeRepository()


def _generate_id() -> str:
    """生成唯一ID。"""
    import uuid
    return str(uuid.uuid4())


async def list_phenotypes(
    disease_id: Optional[str] = None,
    status: Optional[str] = None,
    phenotype_type: Optional[str] = None,
    limit: int = 100,
) -> list[PhenotypeRule]:
    """获取表型规则列表。"""
    phenotypes = await _repo.find_all(disease_id, status, limit)
    return [PhenotypeRule(**p) for p in phenotypes]


async def get_phenotype(phenotype_id: str) -> Optional[PhenotypeRule]:
    """获取表型规则详情。"""
    phenotype = await _repo.find_by_id(phenotype_id)
    if phenotype:
        return PhenotypeRule(**phenotype)
    return None


async def create_phenotype(phenotype: PhenotypeRule) -> PhenotypeRule:
    """创建表型规则。"""
    phenotype.id = _generate_id()
    phenotype.created_at = datetime.utcnow()
    phenotype.updated_at = datetime.utcnow()
    phenotype.status = PhenotypeRuleStatus.DRAFT
    phenotype.version = 1

    await _repo.create(phenotype.model_dump())
    return phenotype


async def update_phenotype(
    phenotype_id: str,
    updates: dict[str, Any]
) -> Optional[PhenotypeRule]:
    """更新表型规则。"""
    phenotype = await get_phenotype(phenotype_id)
    if not phenotype:
        return None

    for key, value in updates.items():
        if hasattr(phenotype, key):
            setattr(phenotype, key, value)

    phenotype.updated_at = datetime.utcnow()
    await _repo.update(phenotype_id, phenotype.model_dump())
    return phenotype


async def delete_phenotype(phenotype_id: str) -> bool:
    """删除表型规则。"""
    return await _repo.delete_one({"id": phenotype_id})


async def get_phenotype_stats() -> dict[str, Any]:
    """获取表型规则统计。"""
    return await _repo.get_stats()


async def validate_logic(phenotype: PhenotypeRule) -> dict[str, Any]:
    """验证表型规则逻辑。"""
    errors = []
    warnings = []

    # 验证 DSL
    if not phenotype.dsl:
        errors.append("缺少 DSL 定义")
    elif "operator" not in phenotype.dsl:
        errors.append("DSL 缺少 operator 字段")
    elif "conditions" not in phenotype.dsl:
        errors.append("DSL 缺少 conditions 字段")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
    }
