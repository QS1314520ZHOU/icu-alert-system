"""病例AI服务测试。

验证：
1. 结构化输出模型验证
2. Evidence ID 验证（移除不属于当前case的ID）
3. JSON解析失败 → 规则回退
4. 规则回退生成有效输出
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_ai_insight_model_validation():
    """测试 AICaseInsight 模型验证。"""
    from app.services.case_ai_service import AICaseInsight, AIClaim, AIMissingItem, AISuggestedAssessment

    # 有效数据
    insight = AICaseInsight(
        summary="患者存在AKI",
        core_problems=[AIClaim(claim="血肌酐升高", evidence_ids=["ev-001"], confidence_level="high")],
        supporting_evidence=[AIClaim(claim="尿量减少", confidence_level="moderate")],
        contradicting_evidence=[],
        missing_information=[AIMissingItem(item="电解质数据", reason="需要评估酸碱平衡")],
        suggested_assessments=[AISuggestedAssessment(title="监测肾功能", reason="AKI进展风险")],
        risk_level="high",
        uncertainty="moderate",
        generation_mode="llm",
    )
    assert insight.summary == "患者存在AKI"
    assert len(insight.core_problems) == 1
    assert insight.core_problems[0].confidence_level == "high"
    assert insight.risk_level == "high"

    # 默认值
    minimal = AICaseInsight()
    assert minimal.risk_level == "unknown"
    assert minimal.uncertainty == "high"
    assert minimal.generation_mode == "llm"
    assert minimal.core_problems == []
    assert len(minimal.safety_notes) == 2  # 默认安全提示


@pytest.mark.asyncio
async def test_ai_insight_rejects_invalid_literal():
    """测试 AICaseInsight 拒绝无效的 Literal 值。"""
    from app.services.case_ai_service import AICaseInsight
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AICaseInsight(risk_level="invalid_level")

    with pytest.raises(ValidationError):
        AICaseInsight(uncertainty="invalid")

    with pytest.raises(ValidationError):
        AICaseInsight(generation_mode="invalid")


@pytest.mark.asyncio
async def test_validate_evidence_ids_removes_invalid():
    """测试 Evidence ID 验证移除不属于当前case的ID。"""
    from app.services.case_ai_service import _validate_evidence_ids

    ai_result = {
        "core_problems": [
            {"claim": "问题1", "evidence_ids": ["ev-valid-001", "ev-invalid-999"]},
            {"claim": "问题2", "evidence_ids": ["ev-valid-002"]},
        ],
        "supporting_evidence": [
            {"claim": "证据1", "evidence_ids": ["ev-invalid-888"]},
        ],
        "contradicting_evidence": [],
    }

    valid_evidence_ids = {"ev-valid-001", "ev-valid-002"}

    result, warnings = _validate_evidence_ids(ai_result, valid_evidence_ids)

    # 有效ID保留
    assert "ev-valid-001" in result["core_problems"][0]["evidence_ids"]
    assert "ev-valid-002" in result["core_problems"][1]["evidence_ids"]

    # 无效ID被移除
    assert "ev-invalid-999" not in result["core_problems"][0]["evidence_ids"]
    assert "ev-invalid-888" not in result["supporting_evidence"][0]["evidence_ids"]

    # 应该有警告
    assert len(warnings) > 0
    assert any("ev-invalid-999" in w for w in warnings)


@pytest.mark.asyncio
async def test_validate_evidence_ids_all_valid():
    """测试所有Evidence ID有效时无警告。"""
    from app.services.case_ai_service import _validate_evidence_ids

    ai_result = {
        "core_problems": [
            {"claim": "问题1", "evidence_ids": ["ev-001", "ev-002"]},
        ],
        "supporting_evidence": [],
        "contradicting_evidence": [],
    }

    result, warnings = _validate_evidence_ids(ai_result, {"ev-001", "ev-002"})

    # 所有ID保留
    assert result["core_problems"][0]["evidence_ids"] == ["ev-001", "ev-002"]
    # 无无效ID警告
    invalid_warnings = [w for w in warnings if "移除无效" in w]
    assert len(invalid_warnings) == 0


@pytest.mark.asyncio
async def test_build_rule_fallback_returns_valid_insight():
    """测试规则回退生成有效的 AICaseInsight。"""
    from app.services.case_ai_service import _build_rule_fallback

    case_data = {
        "id": "case-001",
        "disease_code": "AKI",
        "disease_name": "急性肾损伤",
        "risk_level": "high",
        "status": "confirmed",
    }

    evidence_list = [
        {"id": "ev-001", "evidence_type": "lab_result", "feature_name": "血肌酐", "raw_value": "2.5", "matched": True},
        {"id": "ev-002", "evidence_type": "vital_sign", "feature_name": "血压", "raw_value": "90", "matched": True},
    ]

    conclusions = [
        {"conclusion_label": "AKI 2期", "conclusion_code": "AKI-2", "supporting_evidence_ids": ["ev-001"]},
    ]

    result = _build_rule_fallback(case_data, evidence_list, conclusions)

    assert result.case_id == "case-001"
    assert result.risk_level == "high"
    assert result.generation_mode == "rule_fallback"
    assert result.uncertainty == "high"
    assert len(result.core_problems) > 0
    assert len(result.supporting_evidence) > 0


@pytest.mark.asyncio
async def test_build_rule_fallback_handles_empty_inputs():
    """测试规则回退处理空输入。"""
    from app.services.case_ai_service import _build_rule_fallback

    case_data = {"id": "case-002", "disease_code": "SEPSIS", "disease_name": "脓毒症", "risk_level": "low"}
    result = _build_rule_fallback(case_data, [], [])

    assert result.case_id == "case-002"
    assert result.generation_mode == "rule_fallback"
    assert result.risk_level == "low"
    assert result.uncertainty == "high"
    # 空结论时不生成core_problems
    assert len(result.core_problems) == 0


@pytest.mark.asyncio
async def test_generate_case_ai_summary_with_mock_llm():
    """测试 generate_case_ai_summary 完整流程（mock LLM）。"""
    from app.services.case_ai_service import generate_case_ai_summary

    case_data = {
        "id": "case-003",
        "disease_code": "AKI",
        "disease_name": "急性肾损伤",
        "risk_level": "medium",
        "status": "confirmed",
        "patient_id": "patient-003",
    }

    evidence_list = [
        {"id": "ev-001", "evidence_type": "lab_result", "feature_name": "血肌酐", "raw_value": "2.5", "raw_unit": "mg/dL", "matched": True, "observed_at": "2024-01-01T00:00:00Z"},
    ]

    conclusions = [
        {"conclusion_label": "AKI 1期", "conclusion_code": "AKI-1", "supporting_evidence_ids": ["ev-001"]},
    ]

    # Mock LLM 返回有效JSON
    mock_response = '{"summary": "患者存在AKI", "core_problems": [{"claim": "血肌酐升高", "evidence_ids": ["ev-001"], "confidence_level": "high"}], "supporting_evidence": [], "contradicting_evidence": [], "missing_information": [], "suggested_assessments": [], "risk_level": "high", "uncertainty": "moderate"}'

    with patch('app.services.case_ai_service.call_llm_chat', new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = {"content": mock_response, "model": "test-model"}

        result = await generate_case_ai_summary(case_data, evidence_list, conclusions)

        assert result["success"] is True
        assert result["data"] is not None
        assert result["data"]["summary"] == "患者存在AKI"
        assert result["data"]["generation_mode"] == "llm"


@pytest.mark.asyncio
async def test_generate_case_ai_summary_json_parse_failure_triggers_fallback():
    """测试JSON解析失败触发规则回退。"""
    from app.services.case_ai_service import generate_case_ai_summary

    case_data = {
        "id": "case-004",
        "disease_code": "AKI",
        "disease_name": "急性肾损伤",
        "risk_level": "medium",
        "status": "confirmed",
    }

    # Mock LLM 返回无效JSON
    with patch('app.services.case_ai_service.call_llm_chat', new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = {"content": "这不是一个有效的JSON响应", "model": "test-model"}

        result = await generate_case_ai_summary(case_data, [], [])

        # 应该使用规则回退
        assert result["success"] is True
        assert result["data"] is not None
        assert result["data"]["generation_mode"] == "rule_fallback"


@pytest.mark.asyncio
async def test_generate_case_ai_summary_empty_llm_response():
    """测试LLM返回空内容触发规则回退。"""
    from app.services.case_ai_service import generate_case_ai_summary

    case_data = {
        "id": "case-005",
        "disease_code": "AKI",
        "disease_name": "急性肾损伤",
        "risk_level": "low",
        "status": "screening",
    }

    with patch('app.services.case_ai_service.call_llm_chat', new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = {"content": "", "model": "test-model"}

        result = await generate_case_ai_summary(case_data, [], [])

        assert result["success"] is True
        assert result["data"]["generation_mode"] == "rule_fallback"
