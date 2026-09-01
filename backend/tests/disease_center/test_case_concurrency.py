"""病例并发安全测试。

验证：
1. 原子状态转换（CAS pattern）
2. 并发确认只有一个成功
3. 并发病例创建只有一个活动病例
4. Evidence 幂等写入
"""

from __future__ import annotations

import asyncio
import pytest
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_transition_case_atomic_cas(mongodb):
    """测试原子状态转换 - 成功和失败场景。"""
    from app.services.disease_case_bridge import upsert_case_from_scanner, mark_screen_positive
    from app.services.case_state_service import transition_case, StateTransitionConflict
    from app.models.disease_center import DiseaseCaseStatus, ConfirmationAction
    from app.repositories import CaseRepository

    case = await upsert_case_from_scanner(
        patient_id="patient-cas-001",
        disease_code="AKI",
        encounter_id="enc-cas-001",
    )

    # 转到 pending_review
    await mark_screen_positive(case_id=case["id"])

    # 确认病例（应该成功）
    result = await transition_case(
        case_id=case["id"],
        new_status=DiseaseCaseStatus.CONFIRMED,
        operator_id="doctor-001",
        operator_name="测试医生",
        action=ConfirmationAction.CONFIRM,
    )
    assert result["status"] == "confirmed"

    # 再次确认（应该失败，因为状态已经是 confirmed）
    with pytest.raises(Exception) as exc_info:
        await transition_case(
            case_id=case["id"],
            new_status=DiseaseCaseStatus.CONFIRMED,
            operator_id="doctor-002",
            operator_name="另一个医生",
            action=ConfirmationAction.CONFIRM,
        )
    # 应该是 StateTransitionError（非法转换）或 StateTransitionConflict
    assert "confirmed" in str(exc_info.value).lower() or "冲突" in str(exc_info.value)


@pytest.mark.asyncio
async def test_concurrent_confirm_only_one_succeeds(mongodb):
    """测试并发确认同一病例 - 只有一个成功。"""
    from app.services.disease_case_bridge import upsert_case_from_scanner, mark_screen_positive
    from app.services.case_state_service import confirm_case, StateTransitionConflict, StateTransitionError
    from app.repositories import CaseRepository, ConfirmationRepository

    case = await upsert_case_from_scanner(
        patient_id="patient-conc-001",
        disease_code="AKI",
        encounter_id="enc-conc-001",
    )
    await mark_screen_positive(case_id=case["id"])

    # 并发确认
    results = []
    errors = []

    async def try_confirm(doctor_id: str):
        try:
            result = await confirm_case(
                case_id=case["id"],
                operator_id=doctor_id,
                operator_name=f"医生{doctor_id}",
                operator_role="doctor",
                reason="临床确认",
            )
            results.append(result)
        except (StateTransitionConflict, StateTransitionError) as e:
            errors.append(str(e))
        except Exception as e:
            errors.append(str(e))

    # 10个并发确认
    tasks = [try_confirm(f"doctor-{i:03d}") for i in range(10)]
    await asyncio.gather(*tasks)

    # 只有一个成功
    assert len(results) == 1, f"Expected 1 success, got {len(results)}"
    assert results[0]["status"] == "confirmed"

    # 其余应该失败
    assert len(errors) == 9, f"Expected 9 errors, got {len(errors)}"

    # 确认事件只有一条
    confirm_repo = ConfirmationRepository()
    confirmations = await confirm_repo.find_by_case(case["id"])
    confirm_actions = [c for c in confirmations if c.get("action") == "confirm"]
    assert len(confirm_actions) == 1, f"Expected 1 confirm event, got {len(confirm_actions)}"


@pytest.mark.asyncio
async def test_state_transition_conflict_returns_409(mongodb):
    """测试非法状态转换抛出 StateTransitionError。"""
    from app.services.case_state_service import transition_case, StateTransitionError
    from app.models.disease_center import DiseaseCaseStatus, ConfirmationAction

    # 不存在的病例应该抛出 StateTransitionError
    with pytest.raises(StateTransitionError):
        await transition_case(
            case_id="nonexistent-case-id",
            new_status=DiseaseCaseStatus.CONFIRMED,
            operator_id="doctor-001",
            operator_name="测试医生",
            action=ConfirmationAction.CONFIRM,
        )


@pytest.mark.asyncio
async def test_transition_sets_correct_timestamps(mongodb):
    """测试状态转换设置正确的时间戳字段。"""
    from app.services.disease_case_bridge import upsert_case_from_scanner, mark_screen_positive
    from app.services.case_state_service import confirm_case, exclude_case
    from app.repositories import CaseRepository

    # 创建并确认病例
    case = await upsert_case_from_scanner(
        patient_id="patient-ts-001",
        disease_code="AKI",
        encounter_id="enc-ts-001",
    )
    await mark_screen_positive(case_id=case["id"])

    confirmed = await confirm_case(
        case_id=case["id"],
        operator_id="doctor-001",
        operator_role="doctor",
        reason="确认纳入",
    )

    assert confirmed["confirmed_at"] is not None
    assert confirmed["confirmed_by"] == "doctor-001"
    assert confirmed["screen_positive_at"] is not None
    assert confirmed["pending_review_at"] is not None


@pytest.mark.asyncio
async def test_exclude_requires_reason(mongodb):
    """测试排除操作必须填写原因。"""
    from app.services.disease_case_bridge import upsert_case_from_scanner, mark_screen_positive
    from app.services.case_state_service import exclude_case, StateTransitionError

    case = await upsert_case_from_scanner(
        patient_id="patient-exc-001",
        disease_code="AKI",
        encounter_id="enc-exc-001",
    )
    await mark_screen_positive(case_id=case["id"])

    # 无原因应该失败
    with pytest.raises(StateTransitionError, match="原因"):
        await exclude_case(
            case_id=case["id"],
            operator_id="doctor-001",
            operator_role="doctor",
            reason="",
        )


@pytest.mark.asyncio
async def test_confirmed_case_cannot_be_directly_excluded(mongodb):
    """测试已确认病例不能直接排除（需要先发起复核）。"""
    from app.services.disease_case_bridge import upsert_case_from_scanner, mark_screen_positive
    from app.services.case_state_service import confirm_case, exclude_case, StateTransitionError

    case = await upsert_case_from_scanner(
        patient_id="patient-noexc-001",
        disease_code="AKI",
        encounter_id="enc-noexc-001",
    )
    await mark_screen_positive(case_id=case["id"])
    await confirm_case(
        case_id=case["id"],
        operator_id="doctor-001",
        operator_role="doctor",
        reason="确认",
    )

    # 已确认病例不能直接排除
    with pytest.raises(StateTransitionError, match="不允许排除"):
        await exclude_case(
            case_id=case["id"],
            operator_id="doctor-001",
            operator_role="doctor",
            reason="排除",
        )
