"""病种管理服务测试。"""

import pytest
from app.services import disease_service
from app.models.disease_center import DiseaseDefinition, DiseaseStatus


class _MemoryRepo:
    """Generic in-memory mock repository."""

    def __init__(self):
        self._store: dict[str, dict] = {}

    async def create(self, doc: dict):
        oid = doc.get("id", "")
        self._store[oid] = doc

    async def find_by_id(self, oid: str):
        return self._store.get(oid)

    async def find_all(self, *args, **kwargs):
        return list(self._store.values())

    async def update(self, oid: str, updates: dict):
        if oid in self._store:
            self._store[oid].update(updates)

    async def delete(self, oid: str):
        if oid in self._store:
            del self._store[oid]
            return True
        return False

    async def delete_one(self, flt: dict):
        oid = flt.get("id")
        return await self.delete(oid) if oid else False

    # Specialty methods used by disease_service
    async def find_by_disease(self, disease_id: str):
        for doc in self._store.values():
            if doc.get("disease_id") == disease_id or doc.get("source_id") == disease_id:
                return doc
        return None


class _DiseaseRepo(_MemoryRepo):
    async def find_all(self, status=None, category=None, limit=100):
        results = list(self._store.values())
        if status:
            results = [r for r in results if r.get("status") == status]
        if category:
            results = [r for r in results if r.get("category_id") == category]
        return results[:limit]


class _ReviewRepo(_MemoryRepo):
    async def find_all(self, status=None):
        results = list(self._store.values())
        if status:
            results = [r for r in results if r.get("status") == status]
        return results


class _AuditRepo(_MemoryRepo):
    async def find_all(self, resource_type=None, resource_id=None, limit=100):
        results = list(self._store.values())
        if resource_type:
            results = [r for r in results if r.get("resource_type") == resource_type]
        if resource_id:
            results = [r for r in results if r.get("resource_id") == resource_id]
        return results[:limit]


class _RelationRepo(_MemoryRepo):
    async def find_by_disease(self, disease_id: str):
        return [r for r in self._store.values()
                if r.get("source_id") == disease_id or r.get("target_id") == disease_id]


@pytest.fixture(autouse=True)
def _mock_repos(monkeypatch):
    """Replace all MongoDB repositories with in-memory mocks."""
    disease_repo = _DiseaseRepo()
    review_repo = _ReviewRepo()
    audit_repo = _AuditRepo()
    relation_repo = _RelationRepo()
    pathway_repo = _MemoryRepo()

    monkeypatch.setattr(disease_service, "_disease_repo", disease_repo)
    monkeypatch.setattr(disease_service, "_review_repo", review_repo)
    monkeypatch.setattr(disease_service, "_audit_repo", audit_repo)
    monkeypatch.setattr(disease_service, "_relation_repo", relation_repo)
    monkeypatch.setattr(disease_service, "_pathway_repo", pathway_repo)


@pytest.fixture
def sample_disease():
    """示例病种数据。"""
    return DiseaseDefinition(
        name="测试病种",
        description="测试描述",
        category_id="test",
        icd_codes=["A00"]
    )


@pytest.mark.asyncio
async def test_create_disease(sample_disease):
    """测试创建病种。"""
    result = await disease_service.create_disease(sample_disease)

    assert result.id is not None
    assert result.name == "测试病种"
    assert result.status == DiseaseStatus.DRAFT
    assert result.revision == 1


@pytest.mark.asyncio
async def test_get_disease(sample_disease):
    """测试获取病种。"""
    created = await disease_service.create_disease(sample_disease)
    result = await disease_service.get_disease(created.id)

    assert result is not None
    assert result.id == created.id
    assert result.name == "测试病种"


@pytest.mark.asyncio
async def test_get_disease_not_found():
    """测试获取不存在的病种。"""
    result = await disease_service.get_disease("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_list_diseases(sample_disease):
    """测试获取病种列表。"""
    await disease_service.create_disease(sample_disease)
    await disease_service.create_disease(DiseaseDefinition(
        name="另一个病种",
        category_id="test2"
    ))

    result = await disease_service.list_diseases()
    assert len(result) == 2


@pytest.mark.asyncio
async def test_list_diseases_with_filters(sample_disease):
    """测试带过滤条件的病种列表。"""
    await disease_service.create_disease(sample_disease)
    await disease_service.create_disease(DiseaseDefinition(
        name="另一个病种",
        category_id="test2"
    ))

    result = await disease_service.list_diseases(category="test")
    assert len(result) == 1
    assert result[0].name == "测试病种"


@pytest.mark.asyncio
async def test_update_disease(sample_disease):
    """测试更新病种。"""
    created = await disease_service.create_disease(sample_disease)

    updates = {
        "name": "更新后的病种",
        "revision": created.revision
    }
    result = await disease_service.update_disease(created.id, updates)

    assert result is not None
    assert result.name == "更新后的病种"
    assert result.revision == 2


@pytest.mark.asyncio
async def test_update_disease_version_conflict(sample_disease):
    """测试版本冲突。"""
    created = await disease_service.create_disease(sample_disease)

    updates = {
        "name": "更新后的病种",
        "revision": 999  # 错误的版本号
    }

    with pytest.raises(ValueError, match="版本冲突"):
        await disease_service.update_disease(created.id, updates)


@pytest.mark.asyncio
async def test_delete_disease(sample_disease):
    """测试删除病种。"""
    created = await disease_service.create_disease(sample_disease)

    result = await disease_service.delete_disease(created.id)
    assert result is True

    # 验证已归档
    disease = await disease_service.get_disease(created.id)
    assert disease.status == DiseaseStatus.ARCHIVED


@pytest.mark.asyncio
async def test_delete_published_disease(sample_disease):
    """测试删除已发布病种。"""
    created = await disease_service.create_disease(sample_disease)
    # Directly update status in repo to simulate published state
    disease_service._disease_repo._store[created.id]["status"] = DiseaseStatus.PUBLISHED

    with pytest.raises(ValueError, match="已发布版本不能直接删除"):
        await disease_service.delete_disease(created.id)


@pytest.mark.asyncio
async def test_submit_review(sample_disease):
    """测试提交审核。"""
    created = await disease_service.create_disease(sample_disease)

    review = await disease_service.submit_review(created.id, "user1")

    assert review.id is not None
    assert review.resource_id == created.id
    assert review.submitter_id == "user1"

    # 验证病种状态已更新
    disease = await disease_service.get_disease(created.id)
    assert disease.status == DiseaseStatus.REVIEW_PENDING


@pytest.mark.asyncio
async def test_approve_review(sample_disease):
    """测试通过审核。"""
    created = await disease_service.create_disease(sample_disease)
    review = await disease_service.submit_review(created.id, "user1")

    result = await disease_service.approve_review(review.id, "reviewer1")

    assert result.status == "approved"
    assert result.reviewer_id == "reviewer1"

    # 验证病种状态已更新
    disease = await disease_service.get_disease(created.id)
    assert disease.status == DiseaseStatus.APPROVED


@pytest.mark.asyncio
async def test_reject_review(sample_disease):
    """测试拒绝审核。"""
    created = await disease_service.create_disease(sample_disease)
    review = await disease_service.submit_review(created.id, "user1")

    result = await disease_service.reject_review(review.id, "reviewer1", "需要修改")

    assert result.status == "rejected"
    assert result.review_comment == "需要修改"

    # 验证病种状态已更新
    disease = await disease_service.get_disease(created.id)
    assert disease.status == DiseaseStatus.CHANGES_REQUESTED


@pytest.mark.asyncio
async def test_create_relation(sample_disease):
    """测试创建病种关系。"""
    disease1 = await disease_service.create_disease(sample_disease)
    disease2 = await disease_service.create_disease(DiseaseDefinition(
        name="另一个病种",
        category_id="test"
    ))

    from app.models.disease_center import DiseaseRelation, RelationType
    relation = DiseaseRelation(
        source_id=disease1.id,
        target_id=disease2.id,
        relation_type=RelationType.RELATED_TO
    )

    result = await disease_service.create_relation(relation)
    assert result.id is not None


@pytest.mark.asyncio
async def test_list_relations(sample_disease):
    """测试获取病种关系列表。"""
    disease1 = await disease_service.create_disease(sample_disease)
    disease2 = await disease_service.create_disease(DiseaseDefinition(
        name="另一个病种",
        category_id="test"
    ))

    from app.models.disease_center import DiseaseRelation, RelationType
    relation = DiseaseRelation(
        source_id=disease1.id,
        target_id=disease2.id,
        relation_type=RelationType.RELATED_TO
    )
    await disease_service.create_relation(relation)

    relations = await disease_service.list_relations(disease1.id)
    assert len(relations) == 1


@pytest.mark.asyncio
async def test_list_audits(sample_disease):
    """测试获取审计事件列表。"""
    created = await disease_service.create_disease(sample_disease)
    await disease_service.update_disease(created.id, {"name": "更新", "revision": 1})

    audits = await disease_service.list_audits()
    assert len(audits) == 2  # 创建 + 更新
