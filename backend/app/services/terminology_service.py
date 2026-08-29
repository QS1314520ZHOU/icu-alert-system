"""术语管理服务 - MongoDB 实现。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from app.models.disease_center import (
    Terminology,
    TerminologyStatus,
)
from app.repositories import TerminologyRepository


# 仓储实例
_repo = TerminologyRepository()


def _generate_id() -> str:
    """生成唯一ID。"""
    import uuid
    return str(uuid.uuid4())


async def list_terminologies(
    category: Optional[str] = None,
    status: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = 100,
) -> list[Terminology]:
    """获取术语列表。"""
    terms = await _repo.find_all(category, status, keyword, limit)
    return [Terminology(**t) for t in terms]


async def get_terminology(term_id: str) -> Optional[Terminology]:
    """获取术语详情。"""
    term = await _repo.find_by_id(term_id)
    if term:
        return Terminology(**term)
    return None


async def create_terminology(terminology: Terminology) -> Terminology:
    """创建术语。"""
    terminology.id = _generate_id()
    terminology.created_at = datetime.utcnow()
    terminology.updated_at = datetime.utcnow()
    terminology.status = TerminologyStatus.DRAFT
    terminology.version = 1

    await _repo.create(terminology.model_dump())
    return terminology


async def update_terminology(
    term_id: str,
    updates: dict[str, Any]
) -> Optional[Terminology]:
    """更新术语。"""
    term = await get_terminology(term_id)
    if not term:
        return None

    for key, value in updates.items():
        if hasattr(term, key):
            setattr(term, key, value)

    term.updated_at = datetime.utcnow()
    await _repo.update(term_id, term.model_dump())
    return term


async def delete_terminology(term_id: str) -> bool:
    """删除术语。"""
    return await _repo.delete_one({"id": term_id})


async def get_categories() -> list[dict[str, Any]]:
    """获取术语分类列表。"""
    return await _repo.get_categories()


async def import_batch(terms: list[dict[str, Any]]) -> dict[str, int]:
    """批量导入术语。"""
    success = 0
    failed = 0

    for term_data in terms:
        try:
            terminology = Terminology(**term_data)
            await create_terminology(terminology)
            success += 1
        except Exception:
            failed += 1

    return {"total": len(terms), "success": success, "failed": failed}
