"""营养达标率：缺失即未知，不臆造已给予量。"""
from app.services.nutrition_service import _delivery_trend, _estimate_delivery, _nutrition_prescription, _risk_tags


def test_started_without_kcal_is_unknown_not_imputed():
    orders = [{"route": "EN", "time": "2026-10-30T08:00:00", "kcal": 0, "protein_g": 0, "source": "order"}]
    d = _estimate_delivery(orders, 70)
    assert d["kcal_achieved_pct"] is None and d["kcal_delivered"] is None and d["kcal_gap"] is None
    assert "无法计算" in d["delivery_source"]
    p = _nutrition_prescription(d, "EN", {}, {})
    assert p["level"] == "unknown" and p["suggestions"] == []
    tags = _risk_tags("EN", d, {}, 3, 4, 3)
    assert "达标率未知" in tags and "热量未达标" not in tags


def test_known_delivery_computes_pct():
    orders = [{"route": "EN", "time": "2026-10-30T08:00:00", "kcal": 875, "protein_g": 42, "source": "drugExe"}]
    d = _estimate_delivery(orders, 70)
    assert d["kcal_achieved_pct"] == 50 and d["kcal_gap"] == 875
    assert d["delivery_source"] == "实际执行"


def test_trend_days_without_orders_are_zero_and_unknown_days_none():
    orders = [{"route": "EN", "time": "2026-10-30T08:00:00", "kcal": 0, "protein_g": 0}]
    trend = _delivery_trend(orders, 70)
    assert trend[-1]["pct"] is None
    assert all(day["pct"] == 0 for day in trend[:-1])


def test_24h_window_excludes_same_time_previous_day():
    orders = [
        {"route": "EN", "time": "2026-10-29T08:00:00", "kcal": 1100, "protein_g": 44, "source": "drugExe"},
        {"route": "EN", "time": "2026-10-30T08:00:00", "kcal": 1200, "protein_g": 48, "source": "drugExe"},
    ]
    d = _estimate_delivery(orders, 60)
    assert d["kcal_delivered"] == 1200


def test_refeeding_unknown_without_scores():
    from app.services import nutrition_service as ns

    assert ns._refeeding_panel({}, None, None)["level"] == "unknown"
    assert ns._refeeding_panel({}, 4, None)["level"] == "warn"
    assert ns._refeeding_panel({}, 1, 1)["level"] == "stable"


def test_data_quality_flags_estimated_weight_and_unknown_kcal():
    from app.services import nutrition_service as ns

    row = {"weight": 60.0, "weight_estimated": True, "nrs2002": 3, "nutric": 2, "labs": {}, "orders": [{"route": "EN"}], "kcal_achieved_pct": None}
    missing = ns._data_quality(row)["missing"]
    assert "体重" in missing and "医嘱热量" in missing


def test_dashboard_stats_route_counts_and_unknown_average():
    from app.services import nutrition_service as ns

    rows = [{"route": "EN", "kcal_achieved_pct": None, "risk_tags": []}, {"route": "未开始", "kcal_achieved_pct": 0, "risk_tags": ["再喂养风险"]}]
    stats = ns._dashboard_stats(rows)
    assert stats["route_counts"] == {"EN": 1, "未开始": 1}
    assert stats["avg_kcal_pct"] == 0 and stats["kcal_known_count"] == 1
    assert ns._dashboard_stats([{"route": "EN", "kcal_achieved_pct": None}])["avg_kcal_pct"] is None
