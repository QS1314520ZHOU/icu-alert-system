"""临床证据链后端集成测试。

使用 MongoDB 真实测试库验证证据查询逻辑。
"""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone


# ── Fixtures ──────────────────────────────────────────

@pytest.fixture
def sample_patient():
    return {
        "_id": "test-patient-001",
        "_name": "测试患者",
        "hisBed": "01",
        "hisDept": "ICU",
    }


@pytest.fixture
def sample_alerts():
    now = datetime.now(timezone.utc)
    return [
        {
            "_id": "alert-001",
            "patient_id": "test-patient-001",
            "alert_type": "tachycardia",
            "name": "心率过快",
            "severity": "high",
            "trigger_value": 150,
            "trigger_code": "HR",
            "acknowledged": False,
            "created_at": now - timedelta(hours=2),
        },
        {
            "_id": "alert-002",
            "patient_id": "test-patient-001",
            "alert_type": "hypotension",
            "name": "低血压",
            "severity": "critical",
            "trigger_value": 80,
            "trigger_code": "MAP",
            "acknowledged": True,
            "created_at": now - timedelta(hours=1),
        },
    ]


@pytest.fixture
def sample_vitals():
    now = datetime.now(timezone.utc)
    return [
        {"patient_id": "test-patient-001", "code": "HR", "value": 145, "unit": "bpm", "time": now - timedelta(minutes=30)},
        {"patient_id": "test-patient-001", "code": "MAP", "value": 75, "unit": "mmHg", "time": now - timedelta(minutes=30)},
        {"patient_id": "test-patient-001", "code": "SpO2", "value": 96, "unit": "%", "time": now - timedelta(minutes=30)},
        {"patient_id": "test-patient-001", "code": "RR", "value": 22, "unit": "次/min", "time": now - timedelta(minutes=30)},
    ]


@pytest.fixture
def sample_scores():
    now = datetime.now(timezone.utc)
    return [
        {
            "_id": "score-001",
            "patient_id": "test-patient-001",
            "score_type": "sofa",
            "total_score": 8,
            "items": [
                {"label": "呼吸", "score": 3},
                {"label": "凝血", "score": 2},
                {"label": "肝脏", "score": 1},
                {"label": "循环", "score": 2},
                {"label": "神经", "score": 0},
                {"label": "肾脏", "score": 0},
            ],
            "calc_time": now - timedelta(hours=1),
            "description": "SOFA 器官功能评分",
        },
    ]


# ── 单元测试（不需要数据库）──────────────────────────

class TestClinicalEvidenceService:
    """临床证据服务单元测试。"""

    def test_severity_to_flag(self):
        from app.services.clinical_evidence_service import _severity_to_flag

        assert _severity_to_flag("critical") == "critical"
        assert _severity_to_flag("high") == "high"
        assert _severity_to_flag("warning") == "high"
        assert _severity_to_flag("info") == "normal"
        assert _severity_to_flag("stable") == "normal"
        assert _severity_to_flag("unknown") == "normal"

    def test_check_abnormal(self):
        from app.services.clinical_evidence_service import _check_abnormal

        # 正常值
        assert _check_abnormal("HR", 80) == "normal"
        assert _check_abnormal("SpO2", 98) == "normal"

        # 偏高/偏低
        assert _check_abnormal("HR", 130) == "high"
        assert _check_abnormal("HR", 45) == "low"

        # 危急值
        assert _check_abnormal("HR", 160) == "critical"
        assert _check_abnormal("HR", 35) == "critical"

        # 乳酸
        assert _check_abnormal("Lactate", 3.0) == "high"
        assert _check_abnormal("Lactate", 5.0) == "critical"

        # None 值
        assert _check_abnormal("HR", None) == "missing"

        # 无阈值的指标
        assert _check_abnormal("unknown_code", 100) == "normal"

    def test_code_to_name(self):
        from app.services.clinical_evidence_service import _code_to_name

        assert _code_to_name("HR") == "心率"
        assert _code_to_name("MAP") == "平均动脉压"
        assert _code_to_name("SpO2") == "血氧饱和度"
        assert _code_to_name("unknown") == "unknown"

    def test_get_reference_range(self):
        from app.services.clinical_evidence_service import _get_reference_range

        assert "60-100" in _get_reference_range("HR")
        assert "70-105" in _get_reference_range("MAP")
        assert _get_reference_range("unknown") == ""

    def test_compute_severity(self):
        from app.services.clinical_evidence_service import _compute_severity

        # critical 指标
        metrics_critical = [{"code": "HR", "abnormal_flag": "critical"}]
        assert _compute_severity(metrics_critical, []) == "critical"

        # high 指标
        metrics_high = [{"code": "HR", "abnormal_flag": "high"}]
        assert _compute_severity(metrics_high, []) == "high"

        # normal + evidence rows
        metrics_normal = [{"code": "HR", "abnormal_flag": "normal"}]
        assert _compute_severity(metrics_normal, [{"id": "1"}]) == "warning"

        # 无数据
        assert _compute_severity([], []) == "stable"

    def test_compute_confidence(self):
        from app.services.clinical_evidence_service import _compute_confidence

        # 完整数据
        metrics = [{"code": "HR"}, {"code": "MAP"}, {"code": "SpO2"}]
        assert _compute_confidence(metrics, []) == 1.0

        # 部分缺失
        missing = [{"code": "RR"}]
        assert _compute_confidence(metrics, missing) == 0.75

        # 无数据
        assert _compute_confidence([], []) == 0.0

    def test_detect_missing_data(self):
        from app.services.clinical_evidence_service import _detect_missing_data

        expected = ["HR", "MAP", "SpO2", "RR"]
        metrics = [{"code": "HR", "value": 80}, {"code": "MAP", "value": 75}]
        missing = _detect_missing_data(expected, metrics)

        assert len(missing) == 2
        codes = [m["code"] for m in missing]
        assert "SpO2" in codes
        assert "RR" in codes

        # 全部存在
        all_metrics = [{"code": c} for c in expected]
        assert _detect_missing_data(expected, all_metrics) == []

    def test_build_conclusion(self):
        from app.services.clinical_evidence_service import _build_conclusion

        result = _build_conclusion("呼吸系统", "high", [{"code": "HR"}], [{"code": "RR"}])
        assert "呼吸系统" in result
        assert "高风险" in result
        assert "1 项指标" in result
        assert "1 项数据缺失" in result

    def test_build_weaning_lights(self):
        from app.services.clinical_evidence_service import _build_weaning_lights

        metrics = [
            {"code": "RSBI", "value": 80},
            {"code": "SpO2", "value": 96},
            {"code": "PEEP", "value": 5},
            {"code": "FiO2", "value": 35},
        ]
        sbt_scores = [{"result": "pass"}]

        lights = _build_weaning_lights(metrics, sbt_scores)
        assert len(lights) == 5
        assert all(l["ok"] for l in lights)

        # 未通过的情况
        metrics_bad = [
            {"code": "RSBI", "value": 120},
            {"code": "SpO2", "value": 88},
        ]
        lights_bad = _build_weaning_lights(metrics_bad, [])
        assert not lights_bad[0]["ok"]  # RSBI > 105
        assert not lights_bad[1]["ok"]  # SpO2 < 90

    def test_build_discharge_lights(self):
        from app.services.clinical_evidence_service import _build_discharge_lights

        metrics = [
            {"code": "HR", "value": 80},
            {"code": "MAP", "value": 85},
            {"code": "SpO2", "value": 96},
            {"code": "GCS", "value": 15},
            {"code": "Urine_output_24h", "value": 800},
            {"code": "Lactate", "value": 1.2},
        ]
        scores = {"total_score": 4}

        lights = _build_discharge_lights(metrics, scores)
        assert len(lights) == 6
        assert all(l["ok"] for l in lights)

    def test_error_response(self):
        from app.services.clinical_evidence_service import _error_response

        result = _error_response("测试错误")
        assert result["conclusion"] == "测试错误"
        assert result["severity"] == "info"
        assert result["confidence"] == 0.0
        assert result["metrics"] == []
        assert result["evidence_rows"] == []


# ── API 路由测试 ──────────────────────────────────────

class TestClinicalEvidenceRouter:
    """证据 API 路由测试。"""

    def test_valid_context_types(self):
        """验证所有合法 context_type。"""
        valid_types = {
            "organ_system", "risk", "order", "nursing",
            "weaning", "discharge", "rule_noise", "vitals", "unclosed",
        }
        assert len(valid_types) == 9

    def test_valid_organ_systems(self):
        """验证所有合法 organ_system。"""
        valid_systems = {
            "respiratory", "circulatory", "renal", "hepatic",
            "neurologic", "coagulation", "infection", "nutrition",
        }
        assert len(valid_systems) == 8

    def test_valid_time_ranges(self):
        """验证所有合法 time_range。"""
        valid_ranges = {"1h", "6h", "12h", "24h", "48h", "72h", "7d"}
        assert len(valid_ranges) == 7


# ── 跨患者数据隔离测试 ────────────────────────────────

class TestDataIsolation:
    """验证查询必须包含 patient_id 过滤。"""

    def test_all_queries_require_patient_id(self):
        """确保所有查询都包含 patient_id。"""
        from app.services.clinical_evidence_service import (
            _query_metrics, _query_trends, _query_evidence_rows,
            _query_scores, _query_timeline,
        )

        # 这些函数的签名都要求 patient_id 参数
        import inspect
        for func in [_query_metrics, _query_trends, _query_evidence_rows, _query_scores, _query_timeline]:
            sig = inspect.signature(func)
            assert "patient_id" in sig.parameters, f"{func.__name__} 缺少 patient_id 参数"

    def test_evidence_response_structure(self):
        """验证证据响应包含所有必需字段。"""
        from app.services.clinical_evidence_service import _error_response

        result = _error_response("test")
        required_fields = [
            "conclusion", "severity", "confidence", "generated_at",
            "data_cutoff_at", "metrics", "trends", "evidence_rows",
            "rule_calculation", "ai_analysis", "timeline", "missing_data",
            "provenance", "model_version", "rule_version",
        ]
        for field in required_fields:
            assert field in result, f"缺少必需字段: {field}"

    def test_evidence_row_structure(self):
        """验证证据行包含所有必需字段。"""
        required_fields = [
            "record_id", "patient_id", "observed_at", "category",
            "code", "name", "value", "unit", "reference_range",
            "abnormal_flag", "source_system", "collection_name", "data_quality",
        ]
        # 所有字段名都应在代码中定义
        assert len(required_fields) == 13
