"""患者授权测试。

验证：
- 科室匹配检查
- 默认拒绝策略
- admin 全院权限
- researcher 不能访问临床数据
"""

from __future__ import annotations

import pytest
from app.auth.dependencies import check_patient_access
from app.auth.iframe_auth import CurrentUser


def test_doctor_can_access_own_dept():
    """本科室医生可以访问本科室患者。"""
    user = CurrentUser(
        user_id="d1", roles=["doctor"], department_ids=["ICU"],
    )
    assert check_patient_access(user, "ICU") is True


def test_doctor_cannot_access_other_dept():
    """非本科室医生不能访问其他科室患者。"""
    user = CurrentUser(
        user_id="d1", roles=["doctor"], department_ids=["ICU"],
    )
    assert check_patient_access(user, "普通病房") is False


def test_admin_can_access_all():
    """admin 可以访问所有科室。"""
    user = CurrentUser(
        user_id="a1", roles=["admin"], department_ids=[],
    )
    assert check_patient_access(user, "ICU") is True
    assert check_patient_access(user, "普通病房") is True


def test_user_with_patient_read_any_permission():
    """拥有 patient:read:any 权限的用户可以访问所有。"""
    user = CurrentUser(
        user_id="u1", roles=["doctor"], department_ids=["ICU"],
        permissions=["patient:read:any"],
    )
    assert check_patient_access(user, "普通病房") is True


def test_empty_department_ids_denies_access():
    """department_ids 为空时拒绝访问。"""
    user = CurrentUser(
        user_id="d1", roles=["doctor"], department_ids=[],
    )
    assert check_patient_access(user, "ICU") is False


def test_researcher_cannot_access_clinical_data():
    """researcher 不能直接访问临床数据。"""
    user = CurrentUser(
        user_id="r1", roles=["researcher"], department_ids=[],
    )
    assert check_patient_access(user, "ICU") is False


def test_viewer_cannot_access_other_dept():
    """viewer 不能访问非本科室。"""
    user = CurrentUser(
        user_id="v1", roles=["viewer"], department_ids=["普通病房"],
    )
    assert check_patient_access(user, "ICU") is False


def test_multi_dept_user():
    """多科室用户可以访问所有配置科室。"""
    user = CurrentUser(
        user_id="d1", roles=["doctor"], department_ids=["ICU", "急诊"],
    )
    assert check_patient_access(user, "ICU") is True
    assert check_patient_access(user, "急诊") is True
    assert check_patient_access(user, "普通病房") is False
