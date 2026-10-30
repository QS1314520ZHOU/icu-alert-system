from datetime import datetime, timedelta

from app.clinical_core.hemodynamic_load import (
    Observation, classify_vasoactive, compute, fluid_type, infusion_from_doc, nee_of, running_at, vis_of,
)

NOW = datetime(2026, 10, 30, 12, 30)


def ne_doc(start, actions, dose_mg=8, total_ml=50):
    return {
        "_id": "ne1", "startTime": start, "liquidAmountUnit": "ml",
        "drugList": [
            {"name": "重酒石酸去甲肾上腺素注射液", "dose": dose_mg, "doseUnit": "mg", "liquidAmount": 8},
            {"name": "0.9%氯化钠注射液", "liquidAmount": total_ml - 8},
        ],
        "drugActionList": actions,
    }


def test_classify_names():
    assert classify_vasoactive("重酒石酸去甲肾上腺素注射液")[0] == "ne"
    assert classify_vasoactive("盐酸肾上腺素注射液")[0] == "epi"
    assert classify_vasoactive("去氧肾上腺素")[0] == "phenylephrine"
    assert classify_vasoactive("垂体后叶注射液")[0] == "vasopressin"
    assert classify_vasoactive("利多卡因肾上腺素注射液") is None
    assert classify_vasoactive("氯化钾注射液") is None
    assert fluid_type("10%氯化钠注射液") is None  # 不匹配裸氯化钠
    assert fluid_type("0.9%氯化钠注射液") == "crystalloid"
    assert fluid_type("人血白蛋白") == "colloid"


def test_running_state_tristate():
    inf = infusion_from_doc(ne_doc(NOW - timedelta(hours=5), []))
    assert running_at(inf, NOW) is None  # 无执行动作 → 无法判断
    inf = infusion_from_doc(ne_doc(NOW - timedelta(hours=5), [
        {"time": NOW - timedelta(hours=5), "action": "start", "speed": 3},
        {"time": NOW - timedelta(hours=2), "action": "pause"},
        {"time": NOW - timedelta(hours=1), "action": "recovery", "speed": 6},
    ]))
    assert running_at(inf, NOW - timedelta(minutes=90)) is False
    assert running_at(inf, NOW) is True


def test_ne_dose_conversion_and_nee():
    # 8 mg / 50 ml = 160 μg/ml；6 ml/h → 16 μg/min；70 kg → 0.2286 μg/kg/min
    docs = [ne_doc(NOW - timedelta(hours=8), [
        {"time": NOW - timedelta(hours=8), "action": "start", "speed": 3},
        {"time": NOW - timedelta(hours=2), "action": "add", "speed": 6},
    ])]
    r = compute(infusion_docs=docs, bedside=[], weight_kg=70, now=NOW, hours=24)
    ag = r["vasoactive"]["agents"][0]
    assert ag["state"] == "running"
    assert abs(ag["current_dose"] - 0.2286) < 1e-3
    assert abs(r["vasoactive"]["nee"] - 0.229) < 1e-3
    assert r["vasoactive"]["nee_complete"] is True
    assert abs(r["vasoactive"]["vis"] - 22.9) < 0.1
    assert any("上调" in f["text"] for f in r["findings"])


def test_missing_weight_marks_unknown_not_zero():
    docs = [ne_doc(NOW - timedelta(hours=3), [{"time": NOW - timedelta(hours=3), "action": "start", "speed": 5}])]
    r = compute(infusion_docs=docs, bedside=[], weight_kg=None, now=NOW, hours=24)
    ag = r["vasoactive"]["agents"][0]
    assert ag["current_dose"] is None and ag["dose_unknown_reason"] == "缺体重"
    assert r["vasoactive"]["nee"] is None and r["vasoactive"]["nee_complete"] is False
    assert r["data_gaps"]


def test_nee_vis_partial():
    v, c = nee_of({"ne": 0.1, "epi": None})
    assert v == 0.1 and c is False
    v, c = vis_of({"ne": 0.1, "dobutamine": 5}, 70)
    assert v == 15.0 and c is True


def test_fluid_balance_and_urine_unknown():
    docs = [
        {"startTime": NOW - timedelta(hours=3), "drugList": [{"name": "乳酸林格液", "liquidAmount": 500}]},
        {"startTime": NOW - timedelta(hours=2), "drugList": [{"name": "人血白蛋白", "liquidAmount": 50}]},
        {"startTime": NOW - timedelta(hours=1), "drugList": [{"name": "头孢曲松", "liquidAmount": None}]},
    ]
    bedside = [Observation(NOW - timedelta(hours=2, minutes=10), "param_niaoLiang", 20),
               Observation(NOW - timedelta(hours=1, minutes=10), "param_niaoLiang", 15)]
    r = compute(infusion_docs=docs, bedside=bedside, weight_kg=70, now=NOW, hours=24)
    f = r["fluid"]
    assert f["totals"]["intake_ml"] == 550 and f["totals"]["output_ml"] == 35
    assert f["intake_incomplete_records"] == 1
    hours_with_urine = [row for row in f["rows"] if row["urine_ml"] is not None]
    assert len(hours_with_urine) == 2
    assert any(row["urine_ml"] is None for row in f["rows"])  # 无记录小时为空
    assert f["windows"]["6h"]["urine_ml_kg_h"] < 0.5
    assert any("少尿" in x["text"] for x in r["findings"])
    assert f["resuscitation"]["total_ml"] == 550 and f["resuscitation"]["met"] is False


def test_no_urine_records_flagged():
    r = compute(infusion_docs=[], bedside=[], weight_kg=70, now=NOW, hours=24)
    assert r["fluid"]["windows"]["6h"]["urine_ml"] is None
    assert any("无尿量记录" in x["text"] for x in r["findings"])
