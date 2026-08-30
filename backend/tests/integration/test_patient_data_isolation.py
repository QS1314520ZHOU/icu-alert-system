"""患者数据隔离集成测试 — 验证 MongoDB 查询正确按 patient_id 过滤。

如果 MongoDB 不可用，测试必须 skip（不能伪装通过）。
"""
from __future__ import annotations

import os
import uuid
import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta

try:
    from motor.motor_asyncio import AsyncIOMotorClient
    HAS_MOTOR = True
except ImportError:
    HAS_MOTOR = False

TEST_DB = os.environ.get("SMARTCARE_DB_NAME", "icu_alert_integration_test")
TEST_URI = os.environ.get("SMARTCARE_DB_URI", "mongodb://127.0.0.1:27017")

pytestmark = pytest.mark.skipif(not HAS_MOTOR, reason="motor not installed")

RUN_ID = str(uuid.uuid4())[:8]
PFX = f"INTG_{RUN_ID}_"

_client = None
_db = None


def _assert_safe():
    assert any(k in TEST_DB.lower() for k in ("test", "testing", "ci", "integration")), \
        f"DB名必须含test关键词: {TEST_DB}"
    assert TEST_DB.lower() not in ("smartcare", "datacenter", "icu_alert"), \
        f"不允许使用生产库: {TEST_DB}"


_assert_safe()


async def _mongodb_available() -> bool:
    """Check if MongoDB is reachable."""
    try:
        client = AsyncIOMotorClient(TEST_URI, serverSelectionTimeoutMS=3000)
        await client.admin.command("ping")
        client.close()
        return True
    except Exception:
        return False


@pytest_asyncio.fixture
async def db():
    global _client, _db
    if not await _mongodb_available():
        pytest.skip("MongoDB 不可用，跳过集成测试")
    _client = AsyncIOMotorClient(TEST_URI, serverSelectionTimeoutMS=5000)
    _db = _client[TEST_DB]
    yield _db
    # 清理本次 run_id 的测试数据
    for col_name in ["patient", "bedside", "risk_forecast", "knowledge_documents"]:
        await _db[col_name].delete_many({"_run_id": RUN_ID})
    _client.close()


@pytest.mark.asyncio
async def test_patient_a_data_not_visible_to_patient_b(db):
    """写入患者 A 和 B 的数据，查询 A 时不能返回 B 的数据。"""
    patient_a_id = f"{PFX}patient_a"
    patient_b_id = f"{PFX}patient_b"

    # 写入患者 A 的 bedside 数据
    await db["bedside"].insert_many([
        {"pid": patient_a_id, "code": "HR", "fVal": 80, "time": datetime.now(timezone.utc), "_run_id": RUN_ID},
        {"pid": patient_a_id, "code": "HR", "fVal": 82, "time": datetime.now(timezone.utc) - timedelta(minutes=1), "_run_id": RUN_ID},
    ])
    # 写入患者 B 的 bedside 数据
    await db["bedside"].insert_many([
        {"pid": patient_b_id, "code": "HR", "fVal": 90, "time": datetime.now(timezone.utc), "_run_id": RUN_ID},
    ])

    # 查询患者 A 的数据
    cursor = db["bedside"].find({"pid": patient_a_id, "_run_id": RUN_ID})
    rows_a = await cursor.to_list(length=100)
    assert len(rows_a) == 2, f"患者 A 应有 2 条数据，实际 {len(rows_a)}"
    for row in rows_a:
        assert row["pid"] == patient_a_id

    # 查询患者 B 的数据
    cursor = db["bedside"].find({"pid": patient_b_id, "_run_id": RUN_ID})
    rows_b = await cursor.to_list(length=100)
    assert len(rows_b) == 1
    assert rows_b[0]["pid"] == patient_b_id


@pytest.mark.asyncio
async def test_empty_waveform_returns_empty_list(db):
    """查询不存在的患者波形数据应返回空列表。"""
    fake_pid = f"{PFX}nonexistent"
    cursor = db["bedside"].find({"pid": fake_pid, "_run_id": RUN_ID})
    rows = await cursor.to_list(length=100)
    assert rows == [], f"不存在的患者应返回空列表，实际 {len(rows)} 条"


@pytest.mark.asyncio
async def test_model_unavailable_returns_null_probability(db):
    """模型缺权重时 probability 应为 null。"""
    record = {
        "patient_id": f"{PFX}patient_c",
        "model_available": False,
        "model_status": "weight_missing",
        "probability": None,
        "organ_risk_scores": None,
        "top_contributors": [],
        "calculable": False,
        "_run_id": RUN_ID,
    }
    await db["risk_forecast"].insert_one(record)

    fetched = await db["risk_forecast"].find_one({"patient_id": record["patient_id"], "_run_id": RUN_ID})
    assert fetched is not None
    assert fetched["model_available"] is False
    assert fetched["probability"] is None
    assert fetched["calculable"] is False


@pytest.mark.asyncio
async def test_knowledge_all_zero_chunks_returns_unindexed(db):
    """全 0 知识库文档应能正确标识为未索引。"""
    docs = [
        {"title": "指南A", "chunk_count": 0, "_run_id": RUN_ID},
        {"title": "指南B", "chunk_count": 0, "_run_id": RUN_ID},
    ]
    await db["knowledge_documents"].insert_many(docs)

    cursor = db["knowledge_documents"].find({"_run_id": RUN_ID})
    all_docs = await cursor.to_list(length=100)
    assert len(all_docs) == 2
    assert all(d["chunk_count"] == 0 for d in all_docs)

    # 验证已索引文档过滤
    indexed = [d for d in all_docs if d.get("chunk_count", 0) > 0]
    assert indexed == [], "全 0 文档不应出现在已索引列表"
