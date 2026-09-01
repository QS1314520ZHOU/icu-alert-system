"""病种中心测试配置。

使用真实 MongoDB 测试实例。
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio

# 设置测试环境变量
os.environ.setdefault("JWT_SECRET_KEY", "test-key-for-unit-tests-only-min32chars")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("IFRAME_AUTH_DEV_MODE", "true")
os.environ.setdefault("IFRAME_AUTH_MOCK_USER_ID", "test-doctor-001")
os.environ.setdefault("IFRAME_AUTH_MOCK_USER_NAME", "测试医生")
os.environ.setdefault("IFRAME_AUTH_MOCK_ROLE", "doctor")


@pytest_asyncio.fixture
async def mongodb():
    """连接到测试 MongoDB。"""
    from motor.motor_asyncio import AsyncIOMotorClient

    mongo_url = os.environ.get("MONGO_TEST_URL", "mongodb://localhost:27017")
    db_name = f"icu_test_{uuid.uuid4().hex[:8]}"

    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    # 测试连接
    try:
        await client.admin.command("ping")
    except Exception as e:
        pytest.skip(f"MongoDB 不可用: {e}")

    # 设置全局数据库
    from app.repositories import mongodb as mongo_module
    old_client = mongo_module._client
    old_db = mongo_module._database
    mongo_module._client = client
    mongo_module._database = db

    yield db

    # 清理
    await client.drop_database(db_name)
    client.close()

    mongo_module._client = old_client
    mongo_module._database = old_db


@pytest.fixture
def sample_patient():
    """示例患者数据。"""
    return {
        "_id": "patient-001",
        "name": "张三",
        "hisPid": "his-pid-001",
        "hisBed": "5",
        "dept": "ICU",
        "hisDept": "ICU",
    }


@pytest.fixture
def mock_current_user():
    """模拟当前用户。"""
    from app.auth.iframe_auth import CurrentUser
    return CurrentUser(
        user_id="test-doctor-001",
        user_name="测试医生",
        roles=["doctor"],
        department_ids=["ICU"],
        permissions=[],
    )


@pytest.fixture
def mock_admin_user():
    """模拟管理员用户。"""
    from app.auth.iframe_auth import CurrentUser
    return CurrentUser(
        user_id="admin-001",
        user_name="管理员",
        roles=["admin"],
        department_ids=[],
        permissions=["patient:read:any", "case:manage:any"],
    )
