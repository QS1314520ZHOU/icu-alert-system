"""S-AKI 统计分析调用契约：曾因位置参数错误导致所有分析返回 error。"""
import asyncio

import numpy as np
import pandas as pd
import pytest

import app.services.research_analytics as ra
from app.services.saki import statistics as st


def _df(n: int = 120) -> pd.DataFrame:
    rng = np.random.default_rng(3)
    sofa = rng.integers(2, 18, n)
    lac = np.round(rng.gamma(2, 1.3, n), 1)
    dead = (rng.random(n) < 1 / (1 + np.exp(-(-5 + 0.25 * sofa + 0.3 * lac)))).astype(int)
    return pd.DataFrame({
        "patient_id": [f"p{i}" for i in range(n)], "age": rng.integers(25, 90, n),
        "sex": rng.choice(["M", "F"], n), "sofa_admission": sofa, "apache2": sofa * 2,
        "lactate_admission": lac, "creatinine_admission": rng.gamma(3, 50, n),
        "mechanical_ventilation": rng.integers(0, 2, n), "vasopressor": (sofa > 9).astype(int),
        "crrt": rng.integers(0, 2, n), "icu_mortality": dead, "los_icu_days": np.round(rng.gamma(2, 4, n), 1),
    })


@pytest.fixture
def stats(monkeypatch):
    df = _df()

    async def fake_load(ids, db, max_patients=5000, **kwargs):
        return df.copy()

    async def fake_ids(self, db, patient_ids, cohort_id):
        return list(df["patient_id"])

    monkeypatch.setattr(ra, "_load_patient_dataframe", fake_load)
    monkeypatch.setattr(st.SAKIStatistics, "_resolve_ids", fake_ids)
    return st.SAKIStatistics()


def test_all_analyses_run_without_error(stats):
    async def run():
        return {
            "table1": await stats.table1(None),
            "km": await stats.km_analysis(None, group_by="vasopressor"),
            "logistic": await stats.logistic_regression(None),
            "cox": await stats.cox_regression(None),
            "roc": await stats.roc_analysis(None),
        }

    out = asyncio.run(run())
    for key, value in out.items():
        assert "error" not in value, (key, value.get("error"))
    assert len(out["table1"]["rows"]) == len(st.DEFAULT_TABLE1_VARIABLES)
    assert out["logistic"]["univariate"], "默认预测变量应产生单因素结果"
    assert set(out["roc"]["curves"]) == set(st.DEFAULT_ROC_SCORES)
    assert set(out["km"]["kaplan_meier"]["curves"]) == {"0", "1"}


def test_categorical_missing_not_in_denominator():
    s = ra._categorical_strings(pd.Series([1, 0, None, 1.0]))
    assert ra._format_cat_cell(s, "1").startswith("2 (66.7%")
