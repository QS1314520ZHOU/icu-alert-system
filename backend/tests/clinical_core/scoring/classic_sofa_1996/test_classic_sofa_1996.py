"""经典 SOFA 1996 完整测试。

从 critical-care-alert-platform 迁移，导入路径已调整。
来源: Vincent JL et al. Intensive Care Med. 1996;22:707-710.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.clinical_core import (
    DataQuality,
    Observation,
    ObservationCategory,
    ScoreVariant,
)
from app.clinical_core.scoring.calculators.sofa import SOFACalculator
from app.clinical_core.scoring.rulepacks.loaded_rulepack import LoadedRulepack
from app.clinical_core.scoring.rulepacks.sofa_rulepack import get_classic_sofa_1996_rulepack
from app.clinical_core.scoring.sofa_router import (
    ProductionExecutionRejectedError,
    SOFAVersionMismatchError,
    calculate_sofa,
)
from app.clinical_core.scoring.window_spec import ScoreWindowSpec, WindowSpec

BASE = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)


def _obs(code: str, value: float, unit: str = "", hours_ago: float = 1.0) -> Observation:
    return Observation(
        category=ObservationCategory.LABORATORY,
        code=code,
        display_name=code,
        value_number=value,
        unit=unit,
        observed_at=BASE - timedelta(hours=hours_ago),
    )


def _make_spec() -> ScoreWindowSpec:
    return ScoreWindowSpec(
        spec_id="classic-sofa-1996-spec",
        score_name="SOFA",
        rulepack_version="classic-sofa-1996.1",
        components=[
            WindowSpec(
                component_name="respiratory",
                lookback_window=timedelta(hours=24),
                max_staleness=timedelta(hours=4),
                aggregation="worst",
            ),
            WindowSpec(
                component_name="coagulation",
                lookback_window=timedelta(hours=24),
                max_staleness=timedelta(hours=12),
                aggregation="worst",
            ),
            WindowSpec(
                component_name="liver",
                lookback_window=timedelta(hours=24),
                max_staleness=timedelta(hours=12),
                aggregation="worst",
            ),
            WindowSpec(
                component_name="cardiovascular",
                lookback_window=timedelta(hours=24),
                max_staleness=timedelta(hours=1),
                aggregation="worst",
            ),
            WindowSpec(
                component_name="central_nervous_system",
                lookback_window=timedelta(hours=24),
                max_staleness=timedelta(hours=8),
                aggregation="worst",
            ),
            WindowSpec(
                component_name="renal",
                lookback_window=timedelta(hours=24),
                max_staleness=timedelta(hours=12),
                aggregation="worst",
            ),
        ],
    )


@pytest.fixture
def rulepack() -> LoadedRulepack:
    return LoadedRulepack(get_classic_sofa_1996_rulepack())


class TestClassicSOFARespiratory:
    """经典 SOFA 呼吸分项完整边界测试。"""

    def test_score_0(self, rulepack):
        obs = [_obs("param_PaO2", 500), _obs("param_FiO2", 1.0)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        resp = [c for c in r.components if c.name == "respiratory"][0]
        assert resp.score_points == 0

    def test_score_0_exact_boundary(self, rulepack):
        obs = [_obs("param_PaO2", 400), _obs("param_FiO2", 1.0)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        resp = [c for c in r.components if c.name == "respiratory"][0]
        assert resp.score_points == 0

    def test_score_0_high_ratio(self, rulepack):
        obs = [_obs("param_PaO2", 300), _obs("param_FiO2", 0.5)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        resp = [c for c in r.components if c.name == "respiratory"][0]
        assert resp.score_points == 0

    def test_score_1(self, rulepack):
        obs = [_obs("param_PaO2", 350), _obs("param_FiO2", 1.0)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        resp = [c for c in r.components if c.name == "respiratory"][0]
        assert resp.score_points == 1

    def test_score_1_exact_300(self, rulepack):
        obs = [_obs("param_PaO2", 150), _obs("param_FiO2", 0.5)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        resp = [c for c in r.components if c.name == "respiratory"][0]
        assert resp.score_points == 1

    def test_score_1_just_below_400(self, rulepack):
        obs = [_obs("param_PaO2", 399), _obs("param_FiO2", 1.0)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        resp = [c for c in r.components if c.name == "respiratory"][0]
        assert resp.score_points == 1

    def test_score_2(self, rulepack):
        obs = [_obs("param_PaO2", 250), _obs("param_FiO2", 1.0)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        resp = [c for c in r.components if c.name == "respiratory"][0]
        assert resp.score_points == 2

    def test_score_2_exact_200(self, rulepack):
        obs = [_obs("param_PaO2", 100), _obs("param_FiO2", 0.5)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        resp = [c for c in r.components if c.name == "respiratory"][0]
        assert resp.score_points == 2

    def test_score_2_just_below_300(self, rulepack):
        obs = [_obs("param_PaO2", 299), _obs("param_FiO2", 1.0)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        resp = [c for c in r.components if c.name == "respiratory"][0]
        assert resp.score_points == 2

    def test_score_3(self, rulepack):
        obs = [_obs("param_PaO2", 150), _obs("param_FiO2", 1.0)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        resp = [c for c in r.components if c.name == "respiratory"][0]
        assert resp.score_points == 3

    def test_score_3_exact_100(self, rulepack):
        obs = [_obs("param_PaO2", 50), _obs("param_FiO2", 0.5)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        resp = [c for c in r.components if c.name == "respiratory"][0]
        assert resp.score_points == 3

    def test_score_3_just_below_200(self, rulepack):
        obs = [_obs("param_PaO2", 199), _obs("param_FiO2", 1.0)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        resp = [c for c in r.components if c.name == "respiratory"][0]
        assert resp.score_points == 3

    def test_score_4(self, rulepack):
        obs = [_obs("param_PaO2", 80), _obs("param_FiO2", 1.0)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        resp = [c for c in r.components if c.name == "respiratory"][0]
        assert resp.score_points == 4

    def test_score_4_just_below_100(self, rulepack):
        obs = [_obs("param_PaO2", 99), _obs("param_FiO2", 1.0)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        resp = [c for c in r.components if c.name == "respiratory"][0]
        assert resp.score_points == 4

    def test_score_4_very_low(self, rulepack):
        obs = [_obs("param_PaO2", 50), _obs("param_FiO2", 1.0)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        resp = [c for c in r.components if c.name == "respiratory"][0]
        assert resp.score_points == 4

    def test_pair_time_too_far(self, rulepack):
        obs = [
            Observation(
                category=ObservationCategory.LABORATORY,
                code="param_PaO2",
                display_name="PaO2",
                value_number=200,
                unit="mmHg",
                observed_at=BASE - timedelta(hours=2),
            ),
            Observation(
                category=ObservationCategory.DEVICE_PARAMETER,
                code="param_FiO2",
                display_name="FiO2",
                value_number=0.5,
                unit="fraction",
                observed_at=BASE - timedelta(minutes=5),
            ),
        ]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        assert "respiratory" in r.missing_items

    def test_missing_pao2(self, rulepack):
        obs = [_obs("param_FiO2", 1.0)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        assert "respiratory" in r.missing_items

    def test_missing_fio2(self, rulepack):
        obs = [_obs("param_PaO2", 200)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        assert "respiratory" in r.missing_items


class TestClassicSOFAUrine:
    """经典 SOFA 尿量路径测试。"""

    def test_urine_below_200_score_4(self, rulepack):
        obs = [_obs("urine_output", 150)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        renal = [c for c in r.components if c.name == "renal"][0]
        assert renal.score_points == 4

    def test_urine_200_score_3(self, rulepack):
        obs = [_obs("urine_output", 200)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        renal = [c for c in r.components if c.name == "renal"][0]
        assert renal.score_points == 3

    def test_urine_499_score_3(self, rulepack):
        obs = [_obs("urine_output", 499)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        renal = [c for c in r.components if c.name == "renal"][0]
        assert renal.score_points == 3

    def test_urine_500_score_0(self, rulepack):
        obs = [_obs("urine_output", 500)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        renal = [c for c in r.components if c.name == "renal"][0]
        assert renal.score_points == 0


class TestClassicSOFARenalCombination:
    """经典 SOFA 肾脏两路径组合测试。"""

    def test_urine_0_crea_1(self, rulepack):
        obs = [_obs("CREA", 150), _obs("urine_output", 800)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        renal = [c for c in r.components if c.name == "renal"][0]
        assert renal.score_points == 1

    def test_urine_0_crea_2(self, rulepack):
        obs = [_obs("CREA", 200), _obs("urine_output", 800)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        renal = [c for c in r.components if c.name == "renal"][0]
        assert renal.score_points == 2

    def test_urine_3_crea_1(self, rulepack):
        obs = [_obs("CREA", 150), _obs("urine_output", 300)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        renal = [c for c in r.components if c.name == "renal"][0]
        assert renal.score_points == 3

    def test_urine_3_crea_4(self, rulepack):
        obs = [_obs("CREA", 500), _obs("urine_output", 300)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        renal = [c for c in r.components if c.name == "renal"][0]
        assert renal.score_points == 4

    def test_only_creatinine(self, rulepack):
        obs = [_obs("CREA", 200)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        renal = [c for c in r.components if c.name == "renal"][0]
        assert renal.score_points == 2

    def test_only_urine(self, rulepack):
        obs = [_obs("urine_output", 150)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        renal = [c for c in r.components if c.name == "renal"][0]
        assert renal.score_points == 4

    def test_both_missing(self, rulepack):
        obs = [_obs("param_PaO2", 400), _obs("param_FiO2", 1.0)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        assert "renal" in r.missing_items

    def test_urine_500_does_not_zero_renal_when_crea_high(self, rulepack):
        obs = [_obs("CREA", 200), _obs("urine_output", 1000)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        renal = [c for c in r.components if c.name == "renal"][0]
        assert renal.score_points == 2


class TestClassicSOFAcoagulation:
    """经典 SOFA 凝血（血小板）分项边界测试。"""

    def test_plt_200_score_0(self, rulepack):
        obs = [_obs("PLT", 200)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        comp = [c for c in r.components if c.name == "coagulation"][0]
        assert comp.score_points == 0

    def test_plt_150_exact_score_0(self, rulepack):
        obs = [_obs("PLT", 150)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        comp = [c for c in r.components if c.name == "coagulation"][0]
        assert comp.score_points == 0

    def test_plt_149_score_1(self, rulepack):
        obs = [_obs("PLT", 149)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        comp = [c for c in r.components if c.name == "coagulation"][0]
        assert comp.score_points == 1

    def test_plt_100_exact_score_1(self, rulepack):
        obs = [_obs("PLT", 100)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        comp = [c for c in r.components if c.name == "coagulation"][0]
        assert comp.score_points == 1

    def test_plt_99_score_2(self, rulepack):
        obs = [_obs("PLT", 99)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        comp = [c for c in r.components if c.name == "coagulation"][0]
        assert comp.score_points == 2

    def test_plt_50_exact_score_2(self, rulepack):
        obs = [_obs("PLT", 50)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        comp = [c for c in r.components if c.name == "coagulation"][0]
        assert comp.score_points == 2

    def test_plt_49_score_3(self, rulepack):
        obs = [_obs("PLT", 49)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        comp = [c for c in r.components if c.name == "coagulation"][0]
        assert comp.score_points == 3

    def test_plt_20_exact_score_3(self, rulepack):
        obs = [_obs("PLT", 20)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        comp = [c for c in r.components if c.name == "coagulation"][0]
        assert comp.score_points == 3

    def test_plt_19_score_4(self, rulepack):
        obs = [_obs("PLT", 19)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        comp = [c for c in r.components if c.name == "coagulation"][0]
        assert comp.score_points == 4


class TestClassicSOFALiver:
    """经典 SOFA 肝脏（总胆红素）分项边界测试。"""

    def test_bili_10_score_0(self, rulepack):
        obs = [_obs("TBIL", 10)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        comp = [c for c in r.components if c.name == "liver"][0]
        assert comp.score_points == 0

    def test_bili_20_score_1(self, rulepack):
        obs = [_obs("TBIL", 20)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        comp = [c for c in r.components if c.name == "liver"][0]
        assert comp.score_points == 1

    def test_bili_33_score_2(self, rulepack):
        obs = [_obs("TBIL", 33)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        comp = [c for c in r.components if c.name == "liver"][0]
        assert comp.score_points == 2

    def test_bili_102_score_3(self, rulepack):
        obs = [_obs("TBIL", 102)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        comp = [c for c in r.components if c.name == "liver"][0]
        assert comp.score_points == 3

    def test_bili_204_score_4(self, rulepack):
        obs = [_obs("TBIL", 204)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        comp = [c for c in r.components if c.name == "liver"][0]
        assert comp.score_points == 4


class TestClassicSOFACardiovascular:
    """经典 SOFA 心血管分项边界测试。"""

    def test_no_pressors_score_0(self, rulepack):
        obs = [
            _obs("param_PaO2", 400), _obs("param_FiO2", 1.0),
            _obs("PLT", 200), _obs("TBIL", 10),
            _obs("CREA", 80), _obs("param_score_gcs_obs", 15),
        ]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        cv = [c for c in r.components if c.name == "cardiovascular"][0]
        assert cv.score_points == 0

    def test_dose_0_05_score_1(self, rulepack):
        obs = [_obs("vasopressor_dose", 0.05)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        cv = [c for c in r.components if c.name == "cardiovascular"][0]
        assert cv.score_points == 1

    def test_dose_0_1_score_2(self, rulepack):
        obs = [_obs("vasopressor_dose", 0.1)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        cv = [c for c in r.components if c.name == "cardiovascular"][0]
        assert cv.score_points == 2

    def test_dose_0_2_score_3(self, rulepack):
        obs = [_obs("vasopressor_dose", 0.2)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        cv = [c for c in r.components if c.name == "cardiovascular"][0]
        assert cv.score_points == 3

    def test_dose_0_5_score_4(self, rulepack):
        obs = [_obs("vasopressor_dose", 0.5)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        cv = [c for c in r.components if c.name == "cardiovascular"][0]
        assert cv.score_points == 4


class TestClassicSOFACNS:
    """经典 SOFA 中枢神经系统（GCS）分项边界测试。"""

    def test_gcs_15_score_0(self, rulepack):
        obs = [_obs("param_score_gcs_obs", 15)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        cns = [c for c in r.components if c.name == "central_nervous_system"][0]
        assert cns.score_points == 0

    def test_gcs_14_score_1(self, rulepack):
        obs = [_obs("param_score_gcs_obs", 14)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        cns = [c for c in r.components if c.name == "central_nervous_system"][0]
        assert cns.score_points == 1

    def test_gcs_13_score_1(self, rulepack):
        obs = [_obs("param_score_gcs_obs", 13)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        cns = [c for c in r.components if c.name == "central_nervous_system"][0]
        assert cns.score_points == 1

    def test_gcs_12_score_2(self, rulepack):
        obs = [_obs("param_score_gcs_obs", 12)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        cns = [c for c in r.components if c.name == "central_nervous_system"][0]
        assert cns.score_points == 2

    def test_gcs_10_score_2(self, rulepack):
        obs = [_obs("param_score_gcs_obs", 10)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        cns = [c for c in r.components if c.name == "central_nervous_system"][0]
        assert cns.score_points == 2

    def test_gcs_9_score_3(self, rulepack):
        obs = [_obs("param_score_gcs_obs", 9)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        cns = [c for c in r.components if c.name == "central_nervous_system"][0]
        assert cns.score_points == 3

    def test_gcs_6_score_3(self, rulepack):
        obs = [_obs("param_score_gcs_obs", 6)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        cns = [c for c in r.components if c.name == "central_nervous_system"][0]
        assert cns.score_points == 3

    def test_gcs_5_score_4(self, rulepack):
        obs = [_obs("param_score_gcs_obs", 5)]
        calc = SOFACalculator(rulepack=rulepack)
        r = calc.calculate(obs, evaluation_time=BASE, window_spec=_make_spec())
        cns = [c for c in r.components if c.name == "central_nervous_system"][0]
        assert cns.score_points == 4
