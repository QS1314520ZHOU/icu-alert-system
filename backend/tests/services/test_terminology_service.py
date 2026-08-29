"""术语管理服务测试。"""

import pytest
from app.services import terminology_service
from app.models.disease_center import Terminology


@pytest.fixture(autouse=True)
async def clear_storage():
    """每个测试前清空存储。"""
    terminology_service._terminologies.clear()
    yield


@pytest.fixture
def sample_terminology():
    """示例术语数据。"""
    return Terminology(
        standard_name="急性呼吸窘迫综合征",
        abbreviation="ARDS",
        category="disease",
        source="local"
    )


@pytest.mark.asyncio
async def test_create_terminology(sample_terminology):
    """测试创建术语。"""
    result = await terminology_service.create_terminology(sample_terminology)

    assert result.id is not None
    assert result.standard_name == "急性呼吸窘迫综合征"
    assert result.abbreviation == "ARDS"


@pytest.mark.asyncio
async def test_get_terminology(sample_terminology):
    """测试获取术语。"""
    created = await terminology_service.create_terminology(sample_terminology)
    result = await terminology_service.get_terminology(created.id)

    assert result is not None
    assert result.id == created.id


@pytest.mark.asyncio
async def test_list_terminologies(sample_terminology):
    """测试获取术语列表。"""
    await terminology_service.create_terminology(sample_terminology)
    await terminology_service.create_terminology(Terminology(
        standard_name="脓毒症",
        abbreviation="SEPSIS",
        category="disease",
        source="local"
    ))

    result = await terminology_service.list_terminologies()
    assert len(result) == 2


@pytest.mark.asyncio
async def test_list_terminologies_with_filters(sample_terminology):
    """测试带过滤条件的术语列表。"""
    await terminology_service.create_terminology(sample_terminology)
    await terminology_service.create_terminology(Terminology(
        standard_name="脓毒症",
        abbreviation="SEPSIS",
        category="disease",
        source="local"
    ))

    result = await terminology_service.list_terminologies(keyword="呼吸")
    assert len(result) == 1
    assert result[0].standard_name == "急性呼吸窘迫综合征"


@pytest.mark.asyncio
async def test_update_terminology(sample_terminology):
    """测试更新术语。"""
    created = await terminology_service.create_terminology(sample_terminology)

    updates = {"standard_name": "更新后的术语"}
    result = await terminology_service.update_terminology(created.id, updates)

    assert result is not None
    assert result.standard_name == "更新后的术语"


@pytest.mark.asyncio
async def test_delete_terminology(sample_terminology):
    """测试删除术语。"""
    created = await terminology_service.create_terminology(sample_terminology)

    result = await terminology_service.delete_terminology(created.id)
    assert result is True

    # 验证已删除
    term = await terminology_service.get_terminology(created.id)
    assert term is None


@pytest.mark.asyncio
async def test_get_categories(sample_terminology):
    """测试获取术语分类。"""
    await terminology_service.create_terminology(sample_terminology)
    await terminology_service.create_terminology(Terminology(
        standard_name="脓毒症",
        abbreviation="SEPSIS",
        category="disease",
        source="local"
    ))
    await terminology_service.create_terminology(Terminology(
        standard_name="机械通气",
        abbreviation="MV",
        category="procedure",
        source="local"
    ))

    categories = await terminology_service.get_categories()
    assert len(categories) == 2


@pytest.mark.asyncio
async def test_import_batch():
    """测试批量导入。"""
    terms = [
        {"standard_name": "术语1", "category": "test", "source": "local"},
        {"standard_name": "术语2", "category": "test", "source": "local"},
        {"standard_name": "术语3", "category": "test", "source": "local"},
    ]

    result = await terminology_service.import_batch(terms)

    assert result["total"] == 3
    assert result["success"] == 3
    assert result["failed"] == 0

    # 验证已导入
    all_terms = await terminology_service.list_terminologies()
    assert len(all_terms) == 3
