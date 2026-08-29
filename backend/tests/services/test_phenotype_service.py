"""表型规则服务测试。"""

import pytest
from app.services import phenotype_service
from app.models.disease_center import PhenotypeRule, PhenotypeRuleStatus


@pytest.fixture(autouse=True)
async def clear_storage():
    """每个测试前清空存储。"""
    phenotype_service._phenotypes.clear()
    yield


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
