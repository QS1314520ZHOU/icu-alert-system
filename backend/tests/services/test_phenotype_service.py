"""表型规则服务测试。"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services import phenotype_service
from app.models.disease_center import PhenotypeRule, PhenotypeRuleStatus


class _MemoryRepo:
    """In-memory mock for PhenotypeRepository."""

    def __init__(self):
        self._store: dict[str, dict] = {}

    async def create(self, doc: dict):
        self._store[doc["id"]] = doc

    async def find_by_id(self, oid: str):
        return self._store.get(oid)

    async def find_all(self, disease_id=None, status=None, limit=100):
        results = list(self._store.values())
        if disease_id:
            results = [r for r in results if r.get("disease_id") == disease_id]
        if status:
            results = [r for r in results if r.get("status") == status]
        return results[:limit]

    async def update(self, oid: str, doc: dict):
        if oid in self._store:
            self._store[oid] = doc

    async def delete_one(self, flt: dict):
        oid = flt.get("id")
        if oid and oid in self._store:
            del self._store[oid]
            return True
        return False

    async def get_stats(self):
        total = len(self._store)
        by_status: dict[str, int] = {}
        for doc in self._store.values():
            s = doc.get("status", "unknown")
            by_status[s] = by_status.get(s, 0) + 1
        return {"total": total, "by_status": by_status}


@pytest.fixture(autouse=True)
def _mock_repo(monkeypatch):
    """Replace the MongoDB repository with an in-memory mock."""
    repo = _MemoryRepo()
    monkeypatch.setattr(phenotype_service, "_repo", repo)
    return repo


@pytest.fixture
def sample_phenotype():
    """示例表型规则数据。"""
    return PhenotypeRule(
        name="ARDS 表型",
        disease_id="disease-1",
        dsl={
            "operator": "AND",
            "conditions": [
                {"type": "lab", "field": "pa_fio2_ratio", "operator": "lt", "value": 200},
                {"type": "imaging", "field": "bilateral_infiltrates", "operator": "eq", "value": True}
            ]
        }
    )


@pytest.mark.asyncio
async def test_create_phenotype(sample_phenotype):
    """测试创建表型规则。"""
    result = await phenotype_service.create_phenotype(sample_phenotype)

    assert result.id is not None
    assert result.name == "ARDS 表型"
    assert result.status == PhenotypeRuleStatus.DRAFT


@pytest.mark.asyncio
async def test_get_phenotype(sample_phenotype):
    """测试获取表型规则。"""
    created = await phenotype_service.create_phenotype(sample_phenotype)
    result = await phenotype_service.get_phenotype(created.id)

    assert result is not None
    assert result.id == created.id


@pytest.mark.asyncio
async def test_list_phenotypes(sample_phenotype):
    """测试获取表型规则列表。"""
    await phenotype_service.create_phenotype(sample_phenotype)
    await phenotype_service.create_phenotype(PhenotypeRule(
        name="脓毒症表型",
        disease_id="disease-2",
        dsl={"operator": "OR", "conditions": []}
    ))

    result = await phenotype_service.list_phenotypes()
    assert len(result) == 2


@pytest.mark.asyncio
async def test_list_phenotypes_with_filters(sample_phenotype):
    """测试带过滤条件的表型规则列表。"""
    await phenotype_service.create_phenotype(sample_phenotype)
    await phenotype_service.create_phenotype(PhenotypeRule(
        name="脓毒症表型",
        disease_id="disease-2",
        dsl={"operator": "OR", "conditions": []}
    ))

    result = await phenotype_service.list_phenotypes(disease_id="disease-1")
    assert len(result) == 1
    assert result[0].name == "ARDS 表型"


@pytest.mark.asyncio
async def test_update_phenotype(sample_phenotype):
    """测试更新表型规则。"""
    created = await phenotype_service.create_phenotype(sample_phenotype)

    updates = {"name": "更新后的表型"}
    result = await phenotype_service.update_phenotype(created.id, updates)

    assert result is not None
    assert result.name == "更新后的表型"


@pytest.mark.asyncio
async def test_delete_phenotype(sample_phenotype):
    """测试删除表型规则。"""
    created = await phenotype_service.create_phenotype(sample_phenotype)

    result = await phenotype_service.delete_phenotype(created.id)
    assert result is True

    # 验证已删除
    phenotype = await phenotype_service.get_phenotype(created.id)
    assert phenotype is None


@pytest.mark.asyncio
async def test_get_phenotype_stats(sample_phenotype):
    """测试获取表型规则统计。"""
    await phenotype_service.create_phenotype(sample_phenotype)
    await phenotype_service.create_phenotype(PhenotypeRule(
        name="脓毒症表型",
        disease_id="disease-2",
        dsl={"operator": "OR", "conditions": []}
    ))

    stats = await phenotype_service.get_phenotype_stats()

    assert stats["total"] == 2
    assert stats["by_status"]["draft"] == 2


@pytest.mark.asyncio
async def test_validate_logic_valid(sample_phenotype):
    """测试验证有效逻辑。"""
    result = await phenotype_service.validate_logic(sample_phenotype)

    assert result["valid"] is True
    assert len(result["errors"]) == 0


@pytest.mark.asyncio
async def test_validate_logic_invalid():
    """测试验证无效逻辑。"""
    phenotype = PhenotypeRule(
        name="无效表型",
        disease_id="disease-1",
        dsl={}  # 空 DSL
    )

    result = await phenotype_service.validate_logic(phenotype)

    assert result["valid"] is False
    assert len(result["errors"]) > 0
