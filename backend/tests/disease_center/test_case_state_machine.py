"""病例状态机测试。

验证所有合法和非法状态转换。
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_screening_to_screen_positive(mongodb):
    """screening → screen_positive 合法。"""
    from app.services.disease_case_bridge import upsert_case_from_scanner
    from app.services.case_state_service import transition_case
    from app.models.disease_center import DiseaseCaseStatus, ConfirmationAction

    case = await upsert_case_from_scanner(
        patient_id="p1", disease_code="AKI", encounter_id="e1",
    )

    result = await transition_case(
        case_id=case["id"],
        new_status=DiseaseCaseStatus.SCREEN_POSITIVE,
        operator_id="system",
        operator_name="扫描器",
        action=ConfirmationAction.STATUS_CHANGE,
    )

    assert result["status"] == DiseaseCaseStatus.SCREEN_POSITIVE


@pytest.mark.asyncio
async def test_screen_positive_to_pending_review(mongodb):
    """screen_positive → pending_review 合法。"""
    from app.services.disease_case_bridge import upsert_case_from_scanner
    from app.services.case_state_service import transition_case
    from app.models.disease_center import DiseaseCaseStatus, ConfirmationAction

    case = await upsert_case_from_scanner(
        patient_id="p1", disease_code="AKI", encounter_id="e1",
    )

    await transition_case(
        case_id=case["id"],
        new_status=DiseaseCaseStatus.SCREEN_POSITIVE,
        operator_id="system",
        action=ConfirmationAction.STATUS_CHANGE,
    )

    result = await transition_case(
        case_id=case["id"],
        new_status=DiseaseCaseStatus.PENDING_REVIEW,
        operator_id="system",
        action=ConfirmationAction.STATUS_CHANGE,
    )

    assert result["status"] == DiseaseCaseStatus.PENDING_REVIEW


@pytest.mark.asyncio
async def test_pending_review_to_confirmed(mongodb):
    """pending_review → confirmed 合法。"""
    from app.services.disease_case_bridge import upsert_case_from_scanner
    from app.services.case_state_service import transition_case
    from app.models.disease_center import DiseaseCaseStatus, ConfirmationAction

    case = await upsert_case_from_scanner(
        patient_id="p1", disease_code="AKI", encounter_id="e1",
    )

    await transition_case(case_id=case["id"], new_status=DiseaseCaseStatus.SCREEN_POSITIVE, operator_id="system", action=ConfirmationAction.STATUS_CHANGE)
    await transition_case(case_id=case["id"], new_status=DiseaseCaseStatus.PENDING_REVIEW, operator_id="system", action=ConfirmationAction.STATUS_CHANGE)

    result = await transition_case(
        case_id=case["id"],
        new_status=DiseaseCaseStatus.CONFIRMED,
        operator_id="doctor-001",
        operator_role="doctor",
        action=ConfirmationAction.CONFIRM,
    )

    assert result["status"] == DiseaseCaseStatus.CONFIRMED


@pytest.mark.asyncio
async def test_pending_review_to_excluded(mongodb):
    """pending_review → excluded 合法。"""
    from app.services.disease_case_bridge import upsert_case_from_scanner
    from app.services.case_state_service import transition_case
    from app.models.disease_center import DiseaseCaseStatus, ConfirmationAction

    case = await upsert_case_from_scanner(
        patient_id="p1", disease_code="AKI", encounter_id="e1",
    )

    await transition_case(case_id=case["id"], new_status=DiseaseCaseStatus.SCREEN_POSITIVE, operator_id="system", action=ConfirmationAction.STATUS_CHANGE)
    await transition_case(case_id=case["id"], new_status=DiseaseCaseStatus.PENDING_REVIEW, operator_id="system", action=ConfirmationAction.STATUS_CHANGE)

    result = await transition_case(
        case_id=case["id"],
        new_status=DiseaseCaseStatus.EXCLUDED,
        operator_id="doctor-001",
        operator_role="doctor",
        action=ConfirmationAction.EXCLUDE,
        reason="误报",
    )

    assert result["status"] == DiseaseCaseStatus.EXCLUDED


@pytest.mark.asyncio
async def test_excluded_to_confirmed_is_illegal(mongodb):
    """excluded → confirmed 非法（必须先 reopened）。"""
    from app.services.disease_case_bridge import upsert_case_from_scanner
    from app.services.case_state_service import transition_case, StateTransitionError
    from app.models.disease_center import DiseaseCaseStatus, ConfirmationAction

    case = await upsert_case_from_scanner(
        patient_id="p1", disease_code="AKI", encounter_id="e1",
    )

    await transition_case(case_id=case["id"], new_status=DiseaseCaseStatus.SCREEN_POSITIVE, operator_id="system", action=ConfirmationAction.STATUS_CHANGE)
    await transition_case(case_id=case["id"], new_status=DiseaseCaseStatus.PENDING_REVIEW, operator_id="system", action=ConfirmationAction.STATUS_CHANGE)
    await transition_case(case_id=case["id"], new_status=DiseaseCaseStatus.EXCLUDED, operator_id="d1", operator_role="doctor", action=ConfirmationAction.EXCLUDE, reason="误报")

    with pytest.raises(StateTransitionError):
        await transition_case(
            case_id=case["id"],
            new_status=DiseaseCaseStatus.CONFIRMED,
            operator_id="d1",
            operator_role="doctor",
            action=ConfirmationAction.CONFIRM,
        )


@pytest.mark.asyncio
async def test_excluded_to_reopened_then_confirmed(mongodb):
    """excluded → reopened → screening → screen_positive → pending_review → confirmed 合法。"""
    from app.services.disease_case_bridge import upsert_case_from_scanner
    from app.services.case_state_service import transition_case
    from app.models.disease_center import DiseaseCaseStatus, ConfirmationAction

    case = await upsert_case_from_scanner(
        patient_id="p1", disease_code="AKI", encounter_id="e1",
    )

    # 排除
    await transition_case(case_id=case["id"], new_status=DiseaseCaseStatus.SCREEN_POSITIVE, operator_id="system", action=ConfirmationAction.STATUS_CHANGE)
    await transition_case(case_id=case["id"], new_status=DiseaseCaseStatus.PENDING_REVIEW, operator_id="system", action=ConfirmationAction.STATUS_CHANGE)
    await transition_case(case_id=case["id"], new_status=DiseaseCaseStatus.EXCLUDED, operator_id="d1", operator_role="doctor", action=ConfirmationAction.EXCLUDE, reason="误报")

    # 重开
    await transition_case(case_id=case["id"], new_status=DiseaseCaseStatus.REOPENED, operator_id="system", action=ConfirmationAction.STATUS_CHANGE)

    # 重新筛查
    await transition_case(case_id=case["id"], new_status=DiseaseCaseStatus.SCREENING, operator_id="system", action=ConfirmationAction.RECALCULATE)
    await transition_case(case_id=case["id"], new_status=DiseaseCaseStatus.SCREEN_POSITIVE, operator_id="system", action=ConfirmationAction.STATUS_CHANGE)
    await transition_case(case_id=case["id"], new_status=DiseaseCaseStatus.PENDING_REVIEW, operator_id="system", action=ConfirmationAction.STATUS_CHANGE)

    # 确认
    result = await transition_case(
        case_id=case["id"],
        new_status=DiseaseCaseStatus.CONFIRMED,
        operator_id="d1",
        operator_role="doctor",
        action=ConfirmationAction.CONFIRM,
    )

    assert result["status"] == DiseaseCaseStatus.CONFIRMED


@pytest.mark.asyncio
async def test_nurse_cannot_confirm(mongodb):
    """nurse 角色不能执行 confirm 操作。"""
    from app.services.disease_case_bridge import upsert_case_from_scanner
    from app.services.case_state_service import transition_case, PermissionDeniedError
    from app.models.disease_center import DiseaseCaseStatus, ConfirmationAction

    case = await upsert_case_from_scanner(
        patient_id="p1", disease_code="AKI", encounter_id="e1",
    )

    await transition_case(case_id=case["id"], new_status=DiseaseCaseStatus.SCREEN_POSITIVE, operator_id="system", action=ConfirmationAction.STATUS_CHANGE)
    await transition_case(case_id=case["id"], new_status=DiseaseCaseStatus.PENDING_REVIEW, operator_id="system", action=ConfirmationAction.STATUS_CHANGE)

    with pytest.raises(PermissionDeniedError):
        await transition_case(
            case_id=case["id"],
            new_status=DiseaseCaseStatus.CONFIRMED,
            operator_id="nurse-001",
            operator_role="nurse",
            action=ConfirmationAction.CONFIRM,
        )


@pytest.mark.asyncio
async def test_viewer_cannot_exclude(mongodb):
    """viewer 角色不能执行 exclude 操作。"""
    from app.services.disease_case_bridge import upsert_case_from_scanner
    from app.services.case_state_service import transition_case, PermissionDeniedError
    from app.models.disease_center import DiseaseCaseStatus, ConfirmationAction

    case = await upsert_case_from_scanner(
        patient_id="p1", disease_code="AKI", encounter_id="e1",
    )

    await transition_case(case_id=case["id"], new_status=DiseaseCaseStatus.SCREEN_POSITIVE, operator_id="system", action=ConfirmationAction.STATUS_CHANGE)
    await transition_case(case_id=case["id"], new_status=DiseaseCaseStatus.PENDING_REVIEW, operator_id="system", action=ConfirmationAction.STATUS_CHANGE)

    with pytest.raises(PermissionDeniedError):
        await transition_case(
            case_id=case["id"],
            new_status=DiseaseCaseStatus.EXCLUDED,
            operator_id="viewer-001",
            operator_role="viewer",
            action=ConfirmationAction.EXCLUDE,
            reason="误报",
        )


@pytest.mark.asyncio
async def test_concurrent_transition_only_one_succeeds(mongodb):
    """并发状态转换只能成功一次。"""
    import asyncio
    from app.services.disease_case_bridge import upsert_case_from_scanner
    from app.services.case_state_service import transition_case, StateTransitionError
    from app.models.disease_center import DiseaseCaseStatus, ConfirmationAction

    case = await upsert_case_from_scanner(
        patient_id="p1", disease_code="AKI", encounter_id="e1",
    )

    await transition_case(case_id=case["id"], new_status=DiseaseCaseStatus.SCREEN_POSITIVE, operator_id="system", action=ConfirmationAction.STATUS_CHANGE)
    await transition_case(case_id=case["id"], new_status=DiseaseCaseStatus.PENDING_REVIEW, operator_id="system", action=ConfirmationAction.STATUS_CHANGE)

    # 并发确认
    results = await asyncio.gather(
        transition_case(
            case_id=case["id"],
            new_status=DiseaseCaseStatus.CONFIRMED,
            operator_id="d1",
            operator_role="doctor",
            action=ConfirmationAction.CONFIRM,
        ),
        transition_case(
            case_id=case["id"],
            new_status=DiseaseCaseStatus.CONFIRMED,
            operator_id="d2",
            operator_role="doctor",
            action=ConfirmationAction.CONFIRM,
        ),
        return_exceptions=True,
    )

    # 一个成功，一个失败
    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, Exception)]

    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], StateTransitionError)
