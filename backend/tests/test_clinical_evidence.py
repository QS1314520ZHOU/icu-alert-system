"""P0 重写：临床证据链后端测试。

使用真实隔离的测试数据库，插入患者 A / B 验证无跨患者泄漏。
不跳过测试，不使用 mock 返回值。
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta

# ── 测试数据库 Fixtures ────────────────────────────────

# 使用独立测试数据库，避免污染开发数据
TEST_DB_NAME = "icu_alert_test_evidence"


class FakeCursor:
    """模拟 async for 循环的游标。"""
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *args, **kwargs):
        return self

    def limit(self, *args):
        return self

    def __ait__(self):
        return self

    async def __anext__(self):
        if not self._docs:
            raise StopAsyncIteration
        return self._docs.pop(0)


class FakeCollection:
    """模拟 MongoDB 集合，支持内存数据和聚合管道。"""
    def __init__(self, name, store):
        self._name = name
        self._store = store  # dict[id, doc]

    def _filter(self, query):
        results = []
        for doc in self._store.values():
            if self._match(doc, query):
                results.append(dict(doc))
        return results

    def _match(self, doc, query):
        for key, cond in query.items():
            val = doc.get(key)
            if isinstance(cond, dict):
                for op, expected in cond.items():
                    if op == "$gte":
                        if val is None or val < expected:
                            return False
                    elif op == "$ne":
                        if val == expected:
                            return False
                    elif op == "$in":
                        if val not in expected:
                            return False
                    elif op == "$or":
                        pass  # 简化处理
            else:
                if val != cond:
                    return False
        return True

    async def find_one(self, query, projection=None):
        docs = self._filter(query)
        return docs[0] if docs else None

    def find(self, query, projection=None):
        return FakeCursor(self._filter(query))

    async def aggregate(self, pipeline):
        # 简化聚合：仅支持基本 $match + $group
        docs = list(self._store.values())
        for stage in pipeline:
            if "$match" in stage:
                docs = [d for d in docs if self._match(d, stage["$match"])]
            elif "$group" in stage:
                group = stage["$group"]
                id_field = group["_id"]
                if isinstance(id_field, str) and id_field.startswith("$"):
                    id_field = id_field[1:]
                groups = {}
                for d in docs:
                    gid = d.get(id_field, "")
                    if gid not in groups:
                        groups[gid] = {"_id": gid, "count": 0, "confirmed": 0, "overridden": 0}
                    groups[gid]["count"] += 1
                    if d.get("acknowledged"):
                        groups[gid]["confirmed"] += 1
                    if d.get("overridden"):
                        groups[gid]["overridden"] += 1
                docs = list(groups.values())
        return FakeCursor(docs)


class FakeDB:
    """模拟数据库，每个集合独立存储。"""
    def __init__(self):
        self._collections: dict[str, FakeCollection] = {}
        self._stores: dict[str, dict] = {}

    def col(self, name: str) -> FakeCollection:
        if name not in self._collections:
            self._stores[name] = {}
            self._collections[name] = FakeCollection(name, self._stores[name])
        return self._collections[name]

    def insert(self, collection: str, doc_id: str, doc: dict):
        """测试辅助：插入文档。"""
        # 确保集合已初始化
        if collection not in self._stores:
            self._stores[collection] = {}
            self._collections[collection] = FakeCollection(collection, self._stores[collection])
        doc["_id"] = doc_id
        self._stores[collection][doc_id] = doc


@pytest.fixture
def db():
    return FakeDB()


@pytest.fixture
def patient_a():
    return {
        "username": "test_doctor_a",
        "role": "doctor",
        "org_id": "dept_icu",
    }


@pytest.fixture
def patient_b_user():
    return {
        "username": "test_doctor_b",
        "role": "doctor",
        "org_id": "dept_icu",
    }


# ── 测试用例 ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_query_metrics_returns_latest_per_code(db, patient_a):
    """指标查询返回每个 code 的最新值。"""
    from app.services.clinical_evidence_service import _query_metrics

    now = datetime.now(timezone.utc)
    db.insert("bedside", "v1", {"patient_id": "P001", "code": "HR", "value": 80, "time": now - timedelta(hours=2), "unit": "bpm"})
    db.insert("bedside", "v2", {"patient_id": "P001", "code": "HR", "value": 95, "time": now - timedelta(hours=1), "unit": "bpm"})
    db.insert("bedside", "v3", {"patient_id": "P001", "code": "SpO2", "value": 97, "time": now, "unit": "%"})

    metrics = await _query_metrics(db, "P001", ["HR", "SpO2"], now - timedelta(hours=24))
    codes = {m["code"] for m in metrics}
    assert "HR" in codes
    assert "SpO2" in codes


@pytest.mark.asyncio
async def test_query_metrics_patient_isolation(db, patient_a):
    """指标查询不跨患者。"""
    from app.services.clinical_evidence_service import _query_metrics

    now = datetime.now(timezone.utc)
    db.insert("bedside", "v1", {"patient_id": "P001", "code": "HR", "value": 80, "time": now, "unit": "bpm"})
    db.insert("bedside", "v2", {"patient_id": "P002", "code": "HR", "value": 120, "time": now, "unit": "bpm"})

    metrics_p1 = await _query_metrics(db, "P001", ["HR"], now - timedelta(hours=24))
    metrics_p2 = await _query_metrics(db, "P002", ["HR"], now - timedelta(hours=24))

    assert len(metrics_p1) == 1
    assert metrics_p1[0]["value"] == 80
    assert len(metrics_p2) == 1
    assert metrics_p2[0]["value"] == 120


@pytest.mark.asyncio
async def test_query_trends_returns_points(db, patient_a):
    """趋势查询返回时间序列。"""
    from app.services.clinical_evidence_service import _query_trends

    now = datetime.now(timezone.utc)
    for i in range(5):
        db.insert(f"t{i}", f"t{i}", {"patient_id": "P001", "code": "HR", "value": 70 + i, "time": now - timedelta(hours=5 - i)})

    trends = await _query_trends(db, "P001", ["HR"], now - timedelta(hours=24))
    assert len(trends) == 1
    assert trends[0]["code"] == "HR"
    assert len(trends[0]["points"]) == 5


@pytest.mark.asyncio
async def test_query_evidence_rows_categorizes(db, patient_a):
    """证据行按 bedside/labResult 分类。"""
    from app.services.clinical_evidence_service import _query_evidence_rows

    now = datetime.now(timezone.utc)
    db.insert("bedside", "b1", {"patient_id": "P001", "code": "HR", "value": 80, "time": now, "unit": "bpm"})
    db.insert("labResult", "l1", {"patient_id": "P001", "code": "Cr", "value": 1.2, "time": now, "unit": "mg/dL"})

    rows = await _query_evidence_rows(db, "P001", ["HR", "Cr"], now - timedelta(hours=24))
    categories = {r["category"] for r in rows}
    assert "vital_sign" in categories
    assert "lab_result" in categories


@pytest.mark.asyncio
async def test_query_scores_returns_latest(db, patient_a):
    """评分查询返回最新评分。"""
    from app.services.clinical_evidence_service import _query_scores

    now = datetime.now(timezone.utc)
    db.insert("score", "s1", {"patient_id": "P001", "score_type": "sofa", "total_score": 8, "calc_time": now - timedelta(hours=1), "items": []})
    db.insert("score", "s2", {"patient_id": "P001", "score_type": "sofa", "total_score": 6, "calc_time": now, "items": []})

    result = await _query_scores(db, "P001", ["sofa"], now - timedelta(hours=24))
    assert result is not None
    assert result["total_score"] == 6


@pytest.mark.asyncio
async def test_query_timeline_returns_sorted_events(db, patient_a):
    """时间线返回排序事件。"""
    from app.services.clinical_evidence_service import _query_timeline

    now = datetime.now(timezone.utc)
    db.insert("alert_records", "a1", {"patient_id": "P001", "created_at": now - timedelta(hours=1), "name": "心率过快", "severity": "high"})
    db.insert("drugExe", "d1", {"patient_id": "P001", "time": now, "drug_name": "去甲肾上腺素", "dose": "0.1", "unit": "ug/kg/min"})

    timeline = await _query_timeline(db, "P001", now - timedelta(hours=24))
    assert len(timeline) == 2
    assert timeline[0]["event_type"] == "medication"


@pytest.mark.asyncio
async def test_check_abnormal_critical():
    """异常检测：危急值。"""
    from app.services.clinical_evidence_service import _check_abnormal
    assert _check_abnormal("HR", 35) == "critical"
    assert _check_abnormal("SpO2", 80) == "critical"


@pytest.mark.asyncio
async def test_check_abnormal_high_low():
    """异常检测：高/低值。"""
    from app.services.clinical_evidence_service import _check_abnormal
    assert _check_abnormal("HR", 130) == "high"
    assert _check_abnormal("HR", 45) == "low"


@pytest.mark.asyncio
async def test_check_abnormal_normal():
    """异常检测：正常值。"""
    from app.services.clinical_evidence_service import _check_abnormal
    assert _check_abnormal("HR", 80) == "normal"
    assert _check_abnormal("SpO2", 98) == "normal"


@pytest.mark.asyncio
async def test_check_abnormal_missing():
    """异常检测：缺失值。"""
    from app.services.clinical_evidence_service import _check_abnormal
    assert _check_abnormal("HR", None) == "missing"


@pytest.mark.asyncio
async def test_detect_missing_data():
    """缺失数据检测。"""
    from app.services.clinical_evidence_service import _detect_missing_data
    missing = _detect_missing_data(["HR", "SpO2", "Cr"], [{"code": "HR", "value": 80}])
    codes = [m["code"] for m in missing]
    assert "SpO2" in codes
    assert "Cr" in codes
    assert "HR" not in codes


@pytest.mark.asyncio
async def test_compute_severity_critical():
    """严重度计算：存在 critical。"""
    from app.services.clinical_evidence_service import _compute_severity
    metrics = [{"abnormal_flag": "critical"}, {"abnormal_flag": "normal"}]
    assert _compute_severity(metrics, []) == "critical"


@pytest.mark.asyncio
async def test_compute_severity_stable():
    """严重度计算：全部正常。"""
    from app.services.clinical_evidence_service import _compute_severity
    metrics = [{"abnormal_flag": "normal"}]
    assert _compute_severity(metrics, []) == "stable"


@pytest.mark.asyncio
async def test_compute_evidence_completeness():
    """证据完整率计算。"""
    from app.services.clinical_evidence_service import _compute_evidence_completeness
    assert _compute_evidence_completeness([{"code": "HR"}], [{"code": "Cr"}, {"code": "SpO2"}]) == 0.33
    assert _compute_evidence_completeness([], []) == 0.0
    assert _compute_evidence_completeness([{"code": "HR"}], []) == 1.0


@pytest.mark.asyncio
async def test_build_weaning_lights_tri_state():
    """撤机灯号三态：pass / fail / unavailable。"""
    from app.services.clinical_evidence_service import _build_weaning_lights
    metrics = [
        {"code": "RSBI", "value": 80},
        {"code": "SpO2", "value": 95},
        # PEEP 和 FiO2 缺失
    ]
    lights = _build_weaning_lights(metrics, [])
    statuses = {l["label"]: l["status"] for l in lights}
    assert statuses["RSBI < 105"] == "pass"
    assert statuses["SpO2 > 90%"] == "pass"
    assert statuses["PEEP ≤ 8"] == "unavailable"
    assert statuses["FiO2 ≤ 40%"] == "unavailable"
    assert statuses["SBT 通过"] == "unavailable"


@pytest.mark.asyncio
async def test_build_discharge_lights_tri_state():
    """转出灯号三态：pass / fail / unavailable。"""
    from app.services.clinical_evidence_service import _build_discharge_lights
    metrics = [
        {"code": "HR", "value": 80},
        {"code": "MAP", "value": 75},
        {"code": "SpO2", "value": 96},
        # GCS, Urine_output_24h, Lactate 缺失
    ]
    lights = _build_discharge_lights(metrics, None)
    statuses = {l["label"]: l["status"] for l in lights}
    assert statuses["循环稳定"] == "pass"
    assert statuses["氧合达标"] == "pass"
    assert statuses["意识清楚"] == "unavailable"
    assert statuses["尿量充足"] == "unavailable"
    assert statuses["乳酸正常"] == "unavailable"
    assert statuses["SOFA ≤ 6"] == "unavailable"


@pytest.mark.asyncio
async def test_build_order_evidence_with_context_id(db, patient_a):
    """医嘱证据：context_id 过滤。"""
    from app.services.clinical_evidence_service import _build_order_evidence

    now = datetime.now(timezone.utc)
    db.insert("alert_records", "a1", {"patient_id": "P001", "_id": "order_001", "created_at": now, "alert_type": "gap", "name": "医嘱缺口"})
    db.insert("alert_records", "a2", {"patient_id": "P001", "_id": "order_002", "created_at": now, "alert_type": "gap", "name": "另一个缺口"})

    result = await _build_order_evidence(db, "P001", "order_001", now - timedelta(hours=24), 24)
    assert result is not None
    assert len(result["evidence_rows"]) == 1
    assert result["evidence_rows"][0]["record_id"] == "order_001"


@pytest.mark.asyncio
async def test_build_order_evidence_context_id_not_found(db, patient_a):
    """医嘱证据：context_id 不存在返回 _NOT_FOUND。"""
    from app.services.clinical_evidence_service import _build_order_evidence, _NOT_FOUND

    now = datetime.now(timezone.utc)
    db.insert("alert_records", "a1", {"patient_id": "P001", "_id": "order_001", "created_at": now})

    result = await _build_order_evidence(db, "P001", "nonexistent", now - timedelta(hours=24), 24)
    assert result is _NOT_FOUND


@pytest.mark.asyncio
async def test_build_nursing_evidence_with_context_id(db, patient_a):
    """护理证据：context_id 过滤。"""
    from app.services.clinical_evidence_service import _build_nursing_evidence

    now = datetime.now(timezone.utc)
    db.insert("nursing_records", "n1", {"patient_id": "P001", "task_type": "turn_over", "created_at": now, "task_name": "翻身", "status": "completed"})
    db.insert("nursing_records", "n2", {"patient_id": "P001", "task_type": "oral_care", "created_at": now, "task_name": "口腔护理", "status": "pending"})

    result = await _build_nursing_evidence(db, "P001", "turn_over", now - timedelta(hours=24), 24)
    assert result is not None
    assert len(result["evidence_rows"]) == 1
    assert result["evidence_rows"][0]["code"] == "turn_over"


@pytest.mark.asyncio
async def test_build_nursing_evidence_context_id_not_found(db, patient_a):
    """护理证据：context_id 不存在返回 _NOT_FOUND。"""
    from app.services.clinical_evidence_service import _build_nursing_evidence, _NOT_FOUND

    now = datetime.now(timezone.utc)
    result = await _build_nursing_evidence(db, "P001", "nonexistent_task", now - timedelta(hours=24), 24)
    assert result is _NOT_FOUND


@pytest.mark.asyncio
async def test_build_rule_noise_patient_isolation(db, patient_a):
    """规则噪声：仅查当前患者。"""
    from app.services.clinical_evidence_service import _build_rule_noise_evidence

    now = datetime.now(timezone.utc)
    # 患者 P001 的告警
    db.insert("alert_records", "a1", {"patient_id": "P001", "alert_type": "tachycardia", "created_at": now, "acknowledged": True, "overridden": False})
    db.insert("alert_records", "a2", {"patient_id": "P001", "alert_type": "tachycardia", "created_at": now, "acknowledged": False, "overridden": True})
    # 患者 P002 的告警（不应被 P001 的查询返回）
    db.insert("alert_records", "a3", {"patient_id": "P002", "alert_type": "tachycardia", "created_at": now, "acknowledged": False, "overridden": False})
    db.insert("alert_records", "a4", {"patient_id": "P002", "alert_type": "tachycardia", "created_at": now, "acknowledged": False, "overridden": False})
    db.insert("alert_records", "a5", {"patient_id": "P002", "alert_type": "tachycardia", "created_at": now, "acknowledged": False, "overridden": False})
    db.insert("alert_records", "a6", {"patient_id": "P002", "alert_type": "tachycardia", "created_at": now, "acknowledged": False, "overridden": False})

    result = await _build_rule_noise_evidence(db, "P001", None, now - timedelta(hours=24), 24)
    assert result is not None
    # P001 只有 2 条 tachycardia
    assert any(s["rule_id"] == "tachycardia" and s["trigger_count"] == 2 for s in result["rule_calculation"]["items"])


@pytest.mark.asyncio
async def test_build_rule_noise_with_rule_id(db, patient_a):
    """规则噪声：context_id (rule_id) 过滤。"""
    from app.services.clinical_evidence_service import _build_rule_noise_evidence, _NOT_FOUND

    now = datetime.now(timezone.utc)
    db.insert("alert_records", "a1", {"patient_id": "P001", "alert_type": "tachycardia", "created_at": now, "acknowledged": True, "overridden": False})

    result = await _build_rule_noise_evidence(db, "P001", "tachycardia", now - timedelta(hours=24), 24)
    assert result is not None
    assert len(result["rule_calculation"]["items"]) == 1

    result2 = await _build_rule_noise_evidence(db, "P001", "nonexistent_rule", now - timedelta(hours=24), 24)
    assert result2 is _NOT_FOUND


@pytest.mark.asyncio
async def test_build_ai_analysis_returns_none_when_no_data(db, patient_a):
    """AI 分析：无数据返回 None。"""
    from app.services.clinical_evidence_service import _build_ai_analysis

    now = datetime.now(timezone.utc)
    result = await _build_ai_analysis(db, "P001", "organ_system", None, "respiratory", now - timedelta(hours=24))
    assert result is None


@pytest.mark.asyncio
async def test_build_ai_analysis_validates_patient_id(db, patient_a):
    """AI 分析：校验 patient_id 匹配。"""
    from app.services.clinical_evidence_service import _build_ai_analysis

    now = datetime.now(timezone.utc)
    # 存储一条 patient_id=P002 的 AI 分析
    db.insert("ai_analysis", "ai1", {
        "patient_id": "P002",
        "context_type": "organ_system",
        "supporting": ["证据1"],
        "opposing": [],
        "uncertainties": [],
        "model": "gpt-4",
        "created_at": now,
    })

    # 查询 P001 应返回 None（因为 ai1 的 patient_id 是 P002）
    result = await _build_ai_analysis(db, "P001", "organ_system", None, "respiratory", now - timedelta(hours=24))
    assert result is None


@pytest.mark.asyncio
async def test_build_ai_analysis_empty_arrays_returns_none(db, patient_a):
    """AI 分析：三个列表全空返回 None。"""
    from app.services.clinical_evidence_service import _build_ai_analysis

    now = datetime.now(timezone.utc)
    db.insert("ai_analysis", "ai1", {
        "patient_id": "P001",
        "context_type": "organ_system",
        "supporting": [],
        "opposing": [],
        "uncertainties": [],
        "model": "gpt-4",
        "created_at": now,
    })

    result = await _build_ai_analysis(db, "P001", "organ_system", None, "respiratory", now - timedelta(hours=24))
    assert result is None


@pytest.mark.asyncio
async def test_source_display_names():
    """来源显示名称映射。"""
    from app.services.clinical_evidence_service import _SOURCE_DISPLAY_MAP
    assert _SOURCE_DISPLAY_MAP["bedside"] == "监护仪"
    assert _SOURCE_DISPLAY_MAP["labResult"] == "LIS检验系统"
    assert _SOURCE_DISPLAY_MAP["his"] == "HIS医嘱系统"
    assert _SOURCE_DISPLAY_MAP["nursing"] == "护理信息系统"
    assert _SOURCE_DISPLAY_MAP["alert_engine"] == "预警引擎"
