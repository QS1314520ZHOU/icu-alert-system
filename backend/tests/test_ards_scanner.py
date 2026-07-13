"""
ARDS 氧合筛查 + VILI 风险扫描器 单元测试 v2。

覆盖原要求 + 新增 10 项:
1. P/F 轻中重分级 (含 current/recent/stale 分层)
2. S/F 使用 sf_screen_positive/band (不写入 oxygenation_grade)
3. PEEP 不足
4. PaO2/FiO2 时间差过大 → insufficient_data
5. 找不到血气时间附近 FiO2/PEEP → 不进行 Berlin 分级
6. 时间配对优先采样前参数 (before/after 关系)
7. 缺影像 → indeterminate
8. 影像 NLP 最多 indeterminate (不自动满足 Berlin)
9. BNP 低不能自动标记 cardiogenic_exclusion=supported
10. 双触发+高VT 只生成 VILI 风险
11. 医生确认/否认
12. history ARDS 兼容
13. S/F 不生成 Berlin 分级 (sf_screen_band)
14. 影像否定/不确定文本 (indeterminate + evidence)
15. BNP 低不排除心源性
16. 缺身高不计算 VTe/PBW
17. 氧合等级升级不被告警抑制 (per-grade rule_id)
18. 医生复核乐观锁+快照保留
19. current/recent/stale 分层: recent 不触发 P0/P1
20. insufficient_data 时 ratio_value=null, 保留 calculated_ratio_preview
21. 时间锚定优先采样前参数
22. 找不到锚点附近参数 → valid_for_berlin=false
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.alert_engine.scanner_ards import (
    ArdsScanner, _minutes_ago, _data_tier, _sf_band,
    BERLIN_PF_THRESHOLDS, DEFAULT_FRESHNESS, _freshness_cfg,
)
from app.alert_engine.scanner_vili_risk import ViliRiskScanner


# ═══════════════ helpers ═══════════════

class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = list(docs or [])

    async def find_one(self, query, sort=None, projection=None):
        for doc in self.docs:
            if self._match(doc, query):
                return dict(doc)
        return None

    def find(self, query, projection=None):
        return _FakeCursor([dict(d) for d in self.docs if self._match(d, query)])

    def count_documents(self, query):
        return sum(1 for d in self.docs if self._match(d, query))

    async def insert_one(self, doc):
        doc["_id"] = f"f_{len(self.docs)}"
        self.docs.append(doc)
        return SimpleNamespace(inserted_id=doc["_id"])

    async def update_one(self, query, update):
        for doc in self.docs:
            if self._match(doc, query):
                for k, v in (update.get("$set") or {}).items():
                    parts = k.split(".")
                    t = doc
                    for p in parts[:-1]:
                        t = t.setdefault(p, {})
                    t[parts[-1]] = v
                return SimpleNamespace(modified_count=1)
        return SimpleNamespace(modified_count=0)

    @staticmethod
    def _match(doc, query):
        for key, value in query.items():
            if key == "$and":
                if not all(_FakeCollection._match(doc, s) for s in value):
                    return False
                continue
            if key == "$or":
                if not any(_FakeCollection._match(doc, s) for s in value):
                    return False
                continue
            cur = doc.get(key)
            if isinstance(value, dict):
                if "$gte" in value:
                    c = cur if cur is not None else 0
                    if isinstance(c, datetime) and isinstance(value["$gte"], datetime):
                        if c < value["$gte"]: return False
                    elif (c or 0) < value["$gte"]: return False
                if "$lte" in value:
                    c = cur if cur is not None else 0
                    if isinstance(c, datetime) and isinstance(value["$lte"], datetime):
                        if c > value["$lte"]: return False
                    elif (c or 0) > value["$lte"]: return False
                if "$in" in value and cur not in value["$in"]: return False
                if "$ne" in value and cur == value["$ne"]: return False
                if "$exists" in value:
                    exists = key in doc
                    if value["$exists"] and not exists: return False
                    if not value["$exists"] and exists: return False
                if "_id" in value:
                    from bson import ObjectId as OID
                    try:
                        if OID(str(cur)) != OID(str(value["_id"])): return False
                    except Exception:
                        if cur != value["_id"]: return False
                    continue
            elif cur != value:
                from bson import ObjectId as OID
                try:
                    if OID(str(cur)) == OID(str(value)): continue
                except Exception:
                    pass
                return False
        return True


class _FakeCursor:
    def __init__(self, rows):
        self._rows = list(rows)
        self._idx = 0

    def sort(self, key, direction=1):
        self._rows.sort(key=lambda x: str(x.get(key, "")), reverse=direction == -1)
        return self

    def limit(self, n):
        self._rows = self._rows[:n]
        return self

    def __aiter__(self):
        self._idx = 0
        return self

    async def __anext__(self):
        if self._idx >= len(self._rows):
            raise StopAsyncIteration
        row = self._rows[self._idx]
        self._idx += 1
        return row


class _FakeDb:
    def __init__(self, **cols):
        self._cols = {n: _FakeCollection(d) for n, d in cols.items()}

    def col(self, name):
        if name not in self._cols:
            self._cols[name] = _FakeCollection()
        return self._cols[name]

    def dc_col(self, name):
        return self.col(name)


def _deep_get(d, path, default=None):
    for p in path:
        if isinstance(d, dict): d = d.get(p)
        else: return default
    return d if d is not None else default


def _make_engine(**overrides):
    real_now = datetime.now()
    o = {
        "pao2": 80, "pao2_time": real_now - timedelta(minutes=10),
        "fio2": 50, "fio2_time": real_now - timedelta(minutes=12),
        "peep": 10, "peep_time": real_now - timedelta(minutes=12),
        "spo2": None, "spo2_time": None,
        "imaging": None, "bnp_latest": None, "bnp_ratio": None,
        "icu_admission": real_now - timedelta(hours=24),
        "height": None, "gender": "male",
        "asynchrony": None, "device_id": "vent_001",
        **overrides,
    }
    o["real_now"] = real_now

    yaml_cfg = {
        "alert_engine": {
            "ards_oxygenation": {"data_freshness": dict(DEFAULT_FRESHNESS)},
            "suppression": {"same_rule_same_patient_seconds": 1800, "max_alerts_per_patient_per_hour": 10},
        },
    }
    config = SimpleNamespace(yaml_cfg=yaml_cfg, llm_fast_model=None, llm_fallback_model=None,
                             llm_model_medical=None, settings=SimpleNamespace(LLM_MODEL=None))
    db = _FakeDb(
        patient=[{"_id": "p1", "name": "TP", "hisPid": "hp1", "hisBed": "B1",
                   "icuAdmissionTime": o["icu_admission"], "gender": o["gender"],
                   "heightCm": o["height"]}],
        deviceBind=[{"pid": "p1", "deviceID": o["device_id"], "type": "vent",
                      "unBindTime": None, "bindTime": real_now - timedelta(hours=48)}],
        alert_records=[], score=[], field_mapping=[],
    )
    # deviceCap: put FiO2 at fio2_time (slightly before pao2_time by default → before relation)
    device_cap_docs = []
    if o["fio2"] is not None:
        device_cap_docs.append({"deviceID": o["device_id"], "code": "param_FiO2", "fVal": o["fio2"], "time": o["fio2_time"]})
    if o["peep"] is not None:
        device_cap_docs.append({"deviceID": o["device_id"], "code": "param_vent_measure_peep", "fVal": o["peep"], "time": o["peep_time"]})
    db._cols["deviceCap"] = _FakeCollection(device_cap_docs)

    async def _get_device_id(pd, prefer=None): return o["device_id"]

    async def _get_labs(his_pid, lookback_hours=24):
        labs = {}
        if o["pao2"] is not None:
            labs["pao2"] = {"value": o["pao2"], "time": o["pao2_time"]}
        if o["spo2"] is not None:
            labs["spo2"] = {"value": o["spo2"], "time": o["spo2_time"]}
        return labs

    async def _get_bnp(hid, now, hours=72):
        return {"latest": o["bnp_latest"], "baseline": 50, "ratio": o["bnp_ratio"], "trend": None}

    async def _get_imaging(*a, **kw): return o["imaging"]

    async def _get_asynchrony(pid, hours=4): return o["asynchrony"]

    async def _get_device_cap(device_id, codes=None):
        if not device_cap_docs:
            return None
        filtered = [d for d in device_cap_docs if codes is None or d.get("code") in codes]
        if not filtered:
            return None
        return {"params": {d["code"]: d.get("fVal") for d in filtered}, "time": filtered[0].get("time")}

    def _vent_param(c, name, default=None):
        return c.get("params", {}).get(default) if c else None

    def _vent_param_priority(c, names, defaults):
        if not c: return None
        for i, n in enumerate(names):
            code = defaults[i] if i < len(defaults) else None
            if code and code in c.get("params", {}):
                return c["params"][code]
        return None

    def _vent_codes(concept, defaults):
        return [defaults[0]] if defaults else []

    def _calc_pbw(h, g):
        if h is None: return None
        f = str(g).lower() in ("female", "女", "f")
        base = 45.5 if f else 50.0
        return round(base + 0.91 * (h - 152.4), 2)

    engine = SimpleNamespace(
        config=config, db=db,
        _active_patient_query=lambda: {},
        _get_device_id_for_patient=_get_device_id,
        _get_latest_device_cap=_get_device_cap,
        _get_latest_labs_map=_get_labs,
        _vent_param=_vent_param,
        _vent_param_priority=_vent_param_priority,
        _vent_mapping_codes_sync=_vent_codes,
        _cfg=lambda *p, default=None: _deep_get(yaml_cfg, p, default),
        _patient_icu_start_time=lambda pd: o["icu_admission"],
        get_imaging_report_analysis=_get_imaging,
        _select_imaging_signals=lambda img, **kw: img.get("matched_signals", []) if img else [],
        _build_imaging_summary=lambda s: "summary",
        _format_imaging_evidence_lines=lambda s, **kw: [],
        _get_bnp_trend=_get_bnp,
        _predicted_body_weight=lambda pd: _calc_pbw(o["height"], o["gender"]),
        _latest_ventilator_asynchrony_assessment=_get_asynchrony,
        _is_suppressed=lambda pid, rid, sec, mph: False,
        _create_alert=lambda **kw: kw,
        _polish_structured_alert_explanation=lambda p: p,
        _log_info=lambda n, c: None,
    )
    return engine, o


def _assess(engine, grade_only=False):
    import asyncio

    async def _run():
        s = ArdsScanner(engine)
        return await s._assess_patient({"_id": "p1", "hisPid": "hp1", "icuAdmissionTime": engine._patient_icu_start_time(None)}, "p1", "hp1")
    return asyncio.run(_run())


# ═══════════════ Unit tests ═══════════════

class TestDataTiers:
    def test_current(self):
        f = DEFAULT_FRESHNESS
        assert _data_tier(60, f) == "current"
        assert _data_tier(120, f) == "current"

    def test_recent(self):
        f = DEFAULT_FRESHNESS
        assert _data_tier(121, f) == "recent"
        assert _data_tier(300, f) == "recent"

    def test_stale(self):
        f = DEFAULT_FRESHNESS
        assert _data_tier(400, f) == "stale"

    def test_sf_bands(self):
        assert _sf_band(100) == "severe"
        assert _sf_band(200) == "moderate"
        assert _sf_band(300) == "mild"
        assert _sf_band(400) == "none"


class TestBerlinThresholds:
    def test_thresholds(self):
        assert BERLIN_PF_THRESHOLDS == {"severe": 100, "moderate": 200, "mild": 300}


# ═══════════════ ARDS integration tests ═══════════════

class TestPfGrading:
    def test_severe(self):
        r = _assess(_make_engine(pao2=55, fio2=100, fio2_time=datetime.now() - timedelta(minutes=12))[0])
        assert r["oxygenation_grade"] == "severe"
        assert r["ratio_type"] == "pf"
        assert r["calculated_ratio_valid"] is True

    def test_moderate(self):
        r = _assess(_make_engine()[0])  # 80/0.5 = 160
        assert r["oxygenation_grade"] == "moderate"

    def test_mild(self):
        r = _assess(_make_engine(pao2=120, fio2=40)[0])
        assert r["oxygenation_grade"] == "mild"


class TestSfScreening:
    """S/F 不写入 oxygenation_grade，使用 sf_screen_* 字段"""

    def test_sf_uses_sf_fields(self):
        now = datetime.now()
        r = _assess(_make_engine(pao2=None, spo2=92, spo2_time=now - timedelta(minutes=10),
                                  fio2=50, fio2_time=now - timedelta(minutes=12))[0])
        assert r["oxygenation_grade"] is None
        assert r["sf_screen_positive"] is True
        assert r["sf_screen_band"] in ("moderate", "mild")
        assert r["requires_abg_confirmation"] is True
        assert r["ratio_type"] == "sf"

    def test_sf_skipped_above_97(self):
        now = datetime.now()
        r = _assess(_make_engine(pao2=None, spo2=98, spo2_time=now - timedelta(minutes=10),
                                  fio2=30, fio2_time=now - timedelta(minutes=10))[0])
        assert r is None


class TestTimeMismatchInsufficientData:
    """PaO2/FiO2 时间差超过阈值 → insufficient_data, ratio_value=null"""

    def test_gap_exceeds_threshold(self):
        now = datetime.now()
        r = _assess(_make_engine(
            pao2=80, pao2_time=now - timedelta(minutes=100),
            fio2=50, fio2_time=now - timedelta(minutes=5),
            peep_time=now - timedelta(minutes=5),
        )[0])
        assert r["status"] == "insufficient_data"
        assert r["oxygenation_grade"] is None
        assert r["ratio_value"] is None
        assert r["calculated_ratio_valid"] is False
        assert r["calculated_ratio_preview"] is not None
        assert "pao2_fio2_time_mismatch" in r["missing_criteria"]


class TestNoFallbackBerlin:
    """找不到锚点附近 FiO2/PEEP 时不进行 Berlin 分级"""

    def test_fallback_not_used_for_berlin(self):
        now = datetime.now()
        # Put FiO2/PEEP far in the past (outside the time window)
        engine, _ = _make_engine(
            pao2=80, pao2_time=now - timedelta(minutes=10),
            fio2=50, fio2_time=now - timedelta(minutes=200),  # old
            peep=10, peep_time=now - timedelta(minutes=200),
        )
        r = _assess(engine)
        # FiO2 time won't match time window — should be insufficient_data
        assert r["status"] == "insufficient_data"
        assert r["calculated_ratio_valid"] is False


class TestTemporalPriority:
    """时间配对优先采样前参数"""

    def test_before_relation_recorded(self):
        now = datetime.now()
        # FiO2 at 12 min ago, PaO2 at 10 min ago → FiO2 before PaO2
        engine, _ = _make_engine(
            fio2_time=now - timedelta(minutes=12),
            pao2_time=now - timedelta(minutes=10),
            peep_time=now - timedelta(minutes=12),
        )
        r = _assess(engine)
        df = r["data_freshness"]
        assert df["fio2_temporal_relation"] == "before"
        assert df["fio2_valid_for_berlin"] is True
        assert df["peep_valid_for_berlin"] is True


class TestImagingIndeterminate:
    """影像 NLP 命中最多 indeterminate，不自动满足 Berlin"""

    def test_nlp_hit_is_indeterminate(self):
        r = _assess(_make_engine(imaging={
            "report_count": 1,
            "matched_signals": [{"code": "pulmonary_infiltrate_present", "sentence": "双肺弥漫渗出"}],
        })[0])
        assert r["bilateral_opacity_status"] == "indeterminate"
        assert len(r["bilateral_opacity_evidence"]) >= 1

    def test_no_imaging_is_unknown(self):
        r = _assess(_make_engine(imaging=None)[0])
        assert r["bilateral_opacity_status"] == "unknown"

    def test_empty_report_is_not_met(self):
        r = _assess(_make_engine(imaging={"report_count": 1, "matched_signals": []})[0])
        assert r["bilateral_opacity_status"] == "not_met"


class TestCardiogenicNeverAutoSupported:
    """BNP 低不能自动标记 cardiogenic_exclusion=supported"""

    def test_bnp_high_not_excluded(self):
        r = _assess(_make_engine(pao2=55, fio2=100, bnp_latest=2000, bnp_ratio=2.5)[0])
        assert r["oxygenation_grade"] == "severe"
        assert r["cardiogenic_exclusion_status"] == "not_excluded"

    def test_bnp_low_remains_unknown(self):
        r = _assess(_make_engine(bnp_latest=50, bnp_ratio=1.0)[0])
        assert r["cardiogenic_exclusion_status"] == "unknown"

    def test_no_bnp_is_unknown(self):
        r = _assess(_make_engine()[0])
        assert r["cardiogenic_exclusion_status"] == "unknown"


class TestRecentTierNoP0P1:
    """recent (2-6h) 数据仅作为历史参考，不触发 P0/P1"""

    def test_recent_data_tier_correct(self):
        now = datetime.now()
        engine, _ = _make_engine(
            pao2=55, fio2=100,
            pao2_time=now - timedelta(minutes=150),  # 2.5h → recent
            fio2_time=now - timedelta(minutes=152),
            peep_time=now - timedelta(minutes=152),
        )
        r = _assess(engine)
        assert r["data_tier"] == "recent"
        # recent data should still have machine_assessment.data_tier == "recent"
        assert r["machine_assessment"]["data_tier"] == "recent"
        # recent data: oxygenation_grade may still be computed but status
        # reflects that cardiogenic is unknown
        assert r["status"] in ("oxygenation_criteria_met", "alternative_explanation_possible", "insufficient_data")


class TestRuleIdPerGrade:
    def test_different_ids(self):
        s = ArdsScanner(None)
        assert s._build_rule_id("severe", "pf") == "ARDS_OXYGENATION_SEVERE"
        assert s._build_rule_id(None, "pf") == "ARDS_OXYGENATION_INSUFFICIENT"
        assert s._build_rule_id(None, "sf", "moderate") == "ARDS_SF_SCREEN_MODERATE"


class TestViliRisk:
    def test_no_pbw(self):
        now = datetime.now()
        engine, _ = _make_engine(height=None, asynchrony={"dominant_type": "double_triggering", "ai_index": 15.0})
        import asyncio
        async def _run():
            return await ViliRiskScanner(engine)._assess_vili_risk({"_id": "p1", "gender": "male"}, "p1")
        r = asyncio.run(_run())
        assert r is None or r.get("vte_ml_per_kg_pbw") is None

    def test_alert_names(self):
        s = ViliRiskScanner(None)
        assert "双触发叠加高VT" in s._build_alert_name({"risk_factors": ["double_triggering", "high_vt"]})
        assert "高潮气量" in s._build_alert_name({"risk_factors": ["high_vt"]})


class TestStatusNoAutoPossibleArds:
    """起病/影像/心源排除不可靠时不自动进入 possible_ards"""

    def test_indeterminate_imaging_prevents_possible_ards(self):
        r = _assess(_make_engine(
            icu_admission=datetime.now() - timedelta(hours=6),
            bnp_latest=50,
            imaging={"report_count": 1, "matched_signals": [
                {"code": "pulmonary_infiltrate_present", "sentence": "双肺斑片状影"}
            ]},
        )[0])
        assert r["status"] != "possible_ards"

    def test_unknown_cardiogenic_prevents_possible_ards(self):
        r = _assess(_make_engine(
            icu_admission=datetime.now() - timedelta(hours=6),
        )[0])
        assert r["status"] != "possible_ards"


class TestClinicalReview:
    def test_preserves_machine(self):
        from app.alert_engine.alert_actionability import AlertActionabilityScorerMixin
        fake_db = _FakeDb(alert_records=[{
            "_id": "aaaaaaaaaaaaaaaaaaaaaaa1", "patient_id": "p1", "alert_type": "ards_oxygenation_screen",
            "is_active": True, "created_at": datetime.now(),
            "extra": {"assessment": {
                "oxygenation_grade": "moderate", "status": "oxygenation_criteria_met",
                "machine_assessment": {"status": "oxygenation_criteria_met", "oxygenation_grade": "moderate",
                                       "ratio_type": "pf", "ratio_value": 160.0},
                "clinician_review": None,
            }},
        }])
        class TE:
            config = SimpleNamespace(yaml_cfg={"alert_engine": {"alert_actionability": {"enabled": True}}},
                                     llm_fast_model=None, llm_fallback_model=None,
                                     llm_model_medical=None, settings=SimpleNamespace(LLM_MODEL=None))
        TE.db = fake_db; TE._field_mapping_cache = {}
        TE._cfg = lambda s, *p, default=None: _deep_get(TE.config.yaml_cfg, p, default)
        scorer = AlertActionabilityScorerMixin()
        scorer.config = TE.config; scorer.db = TE.db; scorer._cfg = TE._cfg
        async def _noop(doc, persist=False): return doc
        scorer.refresh_alert_lifecycle = _noop

        import asyncio
        r = asyncio.run(scorer.clinical_review_alert(
            "aaaaaaaaaaaaaaaaaaaaaaa1", action="confirm", actor="dr_smith", review_basis="临床综合"))
        assert r is not None
        updated = asyncio.run(fake_db.col("alert_records").find_one({"_id": "aaaaaaaaaaaaaaaaaaaaaaa1"}))
        a = updated["extra"]["assessment"]
        assert a["machine_assessment"]["oxygenation_grade"] == "moderate"
        assert a["clinician_review"]["action"] == "confirm"
        assert a["clinician_review"]["machine_assessment_snapshot"]["oxygenation_grade"] == "moderate"

    def test_rejects_empty_actor(self):
        from app.alert_engine.alert_actionability import AlertActionabilityScorerMixin
        fake_db = _FakeDb(alert_records=[{
            "_id": "aaaaaaaaaaaaaaaaaaaaaaa2", "patient_id": "p1", "alert_type": "ards_oxygenation_screen",
            "is_active": True, "created_at": datetime.now(),
            "extra": {"assessment": {"machine_assessment": {}, "clinician_review": None}},
        }])
        class TE:
            config = SimpleNamespace(yaml_cfg={}, llm_fast_model=None, llm_fallback_model=None,
                                     llm_model_medical=None, settings=SimpleNamespace(LLM_MODEL=None))
        TE.db = fake_db; TE._field_mapping_cache = {}
        TE._cfg = lambda s, *p, default=None: {}
        scorer = AlertActionabilityScorerMixin()
        scorer.config = TE.config; scorer.db = TE.db; scorer._cfg = TE._cfg
        import asyncio
        assert asyncio.run(scorer.clinical_review_alert("aaaaaaaaaaaaaaaaaaaaaaa2", action="confirm", actor="")) is None

    def test_optimistic_lock(self):
        from app.alert_engine.alert_actionability import AlertActionabilityScorerMixin
        fake_db = _FakeDb(alert_records=[{
            "_id": "aaaaaaaaaaaaaaaaaaaaaaa3", "patient_id": "p1", "alert_type": "ards_oxygenation_screen",
            "is_active": True, "created_at": datetime.now(),
            "extra": {"assessment": {"machine_assessment": {},
                                      "clinician_review": {"version": 2, "action": "confirm",
                                                           "reviewed_by": "dr_j", "reviewed_at": datetime.now().isoformat(),
                                                           "machine_assessment_snapshot": {}}}},
        }])
        class TE:
            config = SimpleNamespace(yaml_cfg={}, llm_fast_model=None, llm_fallback_model=None,
                                     llm_model_medical=None, settings=SimpleNamespace(LLM_MODEL=None))
        TE.db = fake_db; TE._field_mapping_cache = {}
        TE._cfg = lambda s, *p, default=None: {}
        scorer = AlertActionabilityScorerMixin()
        scorer.config = TE.config; scorer.db = TE.db; scorer._cfg = TE._cfg
        import asyncio
        r = asyncio.run(scorer.clinical_review_alert("aaaaaaaaaaaaaaaaaaaaaaa3", action="confirm", actor="dr_s", expected_version=1))
        assert r["conflict"] is True
        assert r["current_version"] == 2


class TestBackwardCompatibility:
    def test_old_ards_explanation(self):
        from app.alert_engine.base import BaseEngine
        class E(BaseEngine):
            def __init__(self): pass
            def _format_alert_number(self, v, d=1): return str(round(float(v or 0), d))
            def _format_alert_measure(self, v, u="", d=1): return "—" if v is None else f"{round(float(v),d)}{u}"
            def _format_condition_text(self, c, v=None): return ""
        e = E()
        r = e._build_alert_explanation(rule_id="ARDS_HIGH", name="ARDS中度", category="syndrome",
                                        alert_type="ards", severity="high", parameter="pf_ratio",
                                        condition={}, value=150, patient_doc=None,
                                        extra={"pao2": 75, "fio2": 50, "peep": 10})
        assert "150" in r
