"""Six-section daily ICU progress note renderer.

The renderer is intentionally deterministic: every numeric value it writes must
come from the structured context supplied by upstream collectors.
"""
from __future__ import annotations

from typing import Any


SECTION_HEADINGS = ["患者概况", "病情变化", "今日评估", "处理经过", "后续计划", "安全提示"]


def _text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text or default


def _num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _fmt_num(value: Any, digits: int = 0) -> str:
    num = _num(value)
    if num is None:
        return ""
    if digits <= 0:
        return str(int(round(num)))
    text = f"{num:.{digits}f}"
    return text.rstrip("0").rstrip(".")


def _latest_from_range(stat: Any) -> float | None:
    if isinstance(stat, dict):
        for key in ("latest", "value", "max", "curr", "current"):
            val = _num(stat.get(key))
            if val is not None:
                return val
        return _num(stat.get("min"))
    return _num(stat)


def _vitals_from_structured(sd: dict[str, Any]) -> dict[str, float | None]:
    vitals = sd.get("latest_vitals") if isinstance(sd.get("latest_vitals"), dict) else {}
    out: dict[str, float | None] = {}
    aliases = {
        "map": ("map", "MAP", "mean_arterial_pressure"),
        "hr": ("hr", "HR", "heart_rate"),
        "spo2": ("spo2", "SpO2", "spo2_percent"),
        "rr": ("rr", "RR", "respiratory_rate"),
        "temp": ("temp", "temperature", "T"),
    }
    for key, names in aliases.items():
        out[key] = None
        for name in names:
            if name in vitals:
                out[key] = _latest_from_range(vitals.get(name))
                break
    return out


def _vitals_from_workbench(draft: dict[str, Any]) -> dict[str, float | None]:
    rows: dict[str, float | None] = {"map": None, "hr": None, "spo2": None, "rr": None, "temp": None}
    for event in draft.get("timeline") or []:
        title = _text(event.get("title") or event.get("type")).lower()
        desc = _text(event.get("description") or event.get("value"))
        val = _num(desc)
        if "map" in title and rows["map"] is None:
            rows["map"] = val
        elif ("hr" in title or "心率" in title) and rows["hr"] is None:
            rows["hr"] = val
        elif "spo2" in title and rows["spo2"] is None:
            rows["spo2"] = val
        elif ("rr" in title or "呼吸" in title) and rows["rr"] is None:
            rows["rr"] = val
        elif ("temp" in title or "体温" in title) and rows["temp"] is None:
            rows["temp"] = val
    return rows


def _lab_name_value(row: Any) -> tuple[str, str, str]:
    if not isinstance(row, dict):
        return "", "", ""
    name = _text(row.get("itemName") or row.get("itemCnName") or row.get("name"))
    value = _text(row.get("result") or row.get("resultValue") or row.get("value") or row.get("curr"))
    unit = _text(row.get("unit"))
    return name, value, unit


def _find_lab(sd: dict[str, Any], keywords: tuple[str, ...]) -> tuple[str, str, str] | None:
    for row in sd.get("labs_24h") or []:
        name, value, unit = _lab_name_value(row)
        lowered = name.lower()
        if value and any(k.lower() in lowered or k in name for k in keywords):
            return name, value, unit
    return None


def _facts_push(facts: list[str], label: str, value: Any, unit: str = "") -> None:
    text = _text(value)
    if text:
        facts.append(f"{label} {text}{unit}")


def _alert_counts(alerts: list[Any]) -> tuple[int, int]:
    total = 0
    high = 0
    for row in alerts:
        if not isinstance(row, dict):
            continue
        total += 1
        sev = _text(row.get("severity")).lower()
        if sev in {"high", "critical", "危急", "高危"}:
            high += 1
    return total, high


def _drug_name(row: Any) -> str:
    if not isinstance(row, dict):
        return ""
    return _text(row.get("drugName") or row.get("orderName") or row.get("name") or row.get("itemName"))


def _is_vasopressor(name: str) -> bool:
    lowered = name.lower()
    return any(k in lowered or k in name for k in ("去甲", "肾上腺素", "norepi", "norad", "多巴胺", "dopamine", "血管活性", "升压"))


def _is_antibiotic(name: str) -> bool:
    lowered = name.lower()
    return any(k in lowered or k in name for k in ("美罗培南", "亚胺培南", "哌拉", "头孢", "万古", "抗感染", "抗菌", "meropenem", "imipenem", "vancomycin"))


def _is_prophylactic_antibiotic(name: str) -> bool:
    lowered = name.lower()
    return any(k in lowered or k in name for k in ("预防", "prophy", "prophylaxis"))


def _is_analgesic(name: str) -> bool:
    lowered = name.lower()
    return any(k in lowered or k in name for k in ("镇痛", "芬太尼", "瑞芬", "吗啡", "舒芬", "fentanyl", "morphine"))


def _treatment_text(drugs: list[Any]) -> str:
    names = [_drug_name(row) for row in drugs]
    names = list(dict.fromkeys([name for name in names if name]))[:8]
    if not names:
        return "暂无可用结构化治疗执行摘要，需医生补充。"
    parts: list[str] = []
    vaso = [name for name in names if _is_vasopressor(name)]
    abx = [name for name in names if _is_antibiotic(name)]
    analgesic = [name for name in names if _is_analgesic(name)]
    if vaso:
        parts.append(f"{vaso[0]}泵入")
    if abx:
        parts.append(f"{'、'.join(abx[:3])}抗感染")
    if analgesic:
        parts.append(f"{'、'.join(analgesic[:2])}镇痛")
    for name in names:
        if name not in "、".join(parts):
            parts.append(name)
        if len(parts) >= 5:
            break
    return "、".join(parts) + "。"


def _diagnosis_text(patient: dict[str, Any]) -> str:
    return _text(patient.get("diagnosis") or patient.get("primary_diagnosis") or patient.get("current_diagnosis"), "未提供")


def _previous_clause(sd: dict[str, Any]) -> str:
    prev = _text(sd.get("previous_daily_progress_summary") or sd.get("previous_assessment"))
    if not prev:
        return ""
    prev = prev.replace("\n", " ").strip("。；; ")
    if len(prev) > 42:
        prev = prev[:42] + "…"
    return f"延续昨日“{prev}”的判断，"


def _render_sections(
    *,
    patient: dict[str, Any],
    vitals: dict[str, float | None],
    labs: list[Any],
    drugs: list[Any],
    alerts: list[Any],
    plan_items: list[str],
    previous_clause: str = "",
) -> dict[str, Any]:
    facts: list[str] = []
    for label, key, unit, digits in (
        ("MAP", "map", "mmHg", 0),
        ("HR", "hr", "bpm", 0),
        ("SpO2", "spo2", "%", 0),
        ("RR", "rr", "/min", 0),
        ("体温", "temp", "℃", 1),
    ):
        if vitals.get(key) is not None:
            _facts_push(facts, label, _fmt_num(vitals.get(key), digits), unit)

    lactate = _find_lab({"labs_24h": labs}, ("乳酸", "lactate"))
    creatinine = _find_lab({"labs_24h": labs}, ("肌酐", "creatinine", "cr"))
    wbc = _find_lab({"labs_24h": labs}, ("WBC", "白细胞"))
    pct = _find_lab({"labs_24h": labs}, ("PCT", "降钙素原"))
    for item in (lactate, creatinine, wbc, pct):
        if item:
            _facts_push(facts, item[0], item[1], item[2])

    alert_total, alert_high = _alert_counts(alerts)
    drug_names = [_drug_name(row) for row in drugs]
    has_vaso = any(_is_vasopressor(name) for name in drug_names)
    has_abx = any(_is_antibiotic(name) for name in drug_names)
    has_therapeutic_abx = any(_is_antibiotic(name) and not _is_prophylactic_antibiotic(name) for name in drug_names)
    lactate_num = _num(lactate[1]) if lactate else None
    map_low = vitals.get("map") is not None and float(vitals["map"] or 0) < 65
    spo2_low = vitals.get("spo2") is not None and float(vitals["spo2"] or 0) < 92
    hr_high = vitals.get("hr") is not None and float(vitals["hr"] or 0) >= 120
    rr_high = vitals.get("rr") is not None and float(vitals["rr"] or 0) >= 28
    lactate_high = lactate_num is not None and lactate_num >= 2
    high_risk = any([map_low, spo2_low, hr_high, rr_high, lactate_high, has_vaso, alert_high > 0])
    stable = not high_risk and alert_high == 0 and any(v is not None for v in vitals.values())

    name = _text(patient.get("name"), "")
    bed = _text(patient.get("bed") or patient.get("bed_no"), "--")
    diagnosis = _diagnosis_text(patient)
    name_part = f"患者{name}" if name else "患者"
    patient_overview = f"{name_part}，{bed}床，主要诊断：{diagnosis}。"

    vital_parts = []
    for label, key, unit, digits in (
        ("MAP", "map", "mmHg", 0),
        ("HR", "hr", "bpm", 0),
        ("SpO2", "spo2", "%", 0),
        ("呼吸频率", "rr", "/min", 0),
        ("体温", "temp", "℃", 1),
    ):
        if vitals.get(key) is not None:
            vital_parts.append(f"{label} {_fmt_num(vitals.get(key), digits)}{unit}")
    if stable:
        change = f"近 24 小时生命体征平稳，最新{'，'.join(vital_parts)}。当日无高危/危急预警。"
    else:
        alert_sentence = f"当日触发高危/危急预警 {alert_high} 条" if alert_high else "当日未见高危/危急预警"
        change_bits = "，".join(vital_parts) if vital_parts else "结构化生命体征不足"
        vaso_text = "，存在升压药使用记录" if has_vaso else ""
        change = f"近 24 小时病情需重点复核，最新{change_bits}{vaso_text}。{alert_sentence}。"

    assessments: list[str] = []
    if map_low or lactate_high or has_vaso:
        details = []
        if map_low:
            details.append("MAP 低于 65")
        if lactate_high and lactate:
            details.append(f"乳酸 {lactate[1]}{lactate[2]}")
        if has_vaso:
            details.append("存在升压药使用")
        assessments.append("循环存在低灌注或循环不稳线索（" + "、".join(details) + "）")
    elif stable:
        assessments.append("循环指标未见明确低灌注触发")
    if spo2_low or rr_high:
        details = []
        if spo2_low:
            details.append("氧合低于 92%")
        if rr_high:
            details.append("呼吸频率增快")
        assessments.append("呼吸需重点复核氧合与通气（" + "、".join(details) + "）")
    elif stable:
        assessments.append("呼吸氧合暂无明显恶化信号")
    if creatinine:
        assessments.append(f"肾功能肌酐 {creatinine[1]}{creatinine[2]}，暂无结构化高危触发")
    elif stable:
        assessments.append("肾功能暂无结构化高危触发")
    if wbc or pct or (has_therapeutic_abx and not stable):
        inf = []
        if wbc:
            inf.append(f"{wbc[0]} {wbc[1]}{wbc[2]}")
        if pct:
            inf.append(f"{pct[0]} {pct[1]}{pct[2]}")
        if has_therapeutic_abx:
            inf.append("已有抗感染治疗记录")
        assessments.append("感染/脓毒症线索需继续核对：" + "、".join(inf))
    elif stable:
        assessments.append("感染结构化线索未达预警阈值")
    if not assessments:
        assessments.append("当前结构化数据不足，暂不强行判断平稳或恶化，需结合床旁查体补充。")
    trend_tail = ""
    if previous_clause:
        trend_tail = previous_clause + ("今日较前需重点复核。" if high_risk else "今日维持稳定。")
    assessment = "；".join(assessments) + ("。" if not trend_tail else f"。{trend_tail}")

    plan = "；".join([_text(item).strip("。") for item in plan_items if _text(item)][:20])
    if not plan:
        if high_risk:
            plan = "维持 MAP≥65 目标，动态复评乳酸清除与升压药需求；复查感染指标与病原学；评估氧合趋势，必要时调整呼吸支持；建议 6 小时内复评循环与感染状态"
        else:
            plan = "继续监测生命体征与出入量，关注切口、引流及感染指标；评估降阶护理与转出条件；按病情制定下一次复评计划"
    plan = plan.rstrip("。") + "。"

    sections = [
        {"heading": "患者概况", "content": patient_overview},
        {"heading": "病情变化", "content": change},
        {"heading": "今日评估", "content": assessment},
        {"heading": "处理经过", "content": _treatment_text(drugs)},
        {"heading": "后续计划", "content": plan},
        {"heading": "安全提示", "content": "本病程为结构化数据辅助草稿，须由医生审核确认后写入正式病历。"},
    ]
    return {
        "title": "日常病程记录",
        "sections": sections,
        "document_text": "\n\n".join(f"{row['heading']}：{row['content']}" for row in sections),
        "key_facts_used": facts[:12],
        "risk_profile": "high_risk" if high_risk else "stable" if stable else "uncertain",
    }


def render_daily_progress_from_structured(structured_data: dict[str, Any]) -> dict[str, Any]:
    patient = structured_data.get("patient") if isinstance(structured_data.get("patient"), dict) else {}
    reasoning = structured_data.get("clinical_reasoning") if isinstance(structured_data.get("clinical_reasoning"), dict) else {}
    proactive = structured_data.get("proactive_plan") if isinstance(structured_data.get("proactive_plan"), dict) else {}
    plan_items: list[str] = []
    for source in (reasoning.get("recommendations"), reasoning.get("action_items"), reasoning.get("plan"), proactive.get("recommendations"), proactive.get("action_items")):
        if isinstance(source, list):
            for item in source:
                if isinstance(item, dict):
                    plan_items.append(_text(item.get("action") or item.get("recommendation") or item.get("title")))
                else:
                    plan_items.append(_text(item))
        elif isinstance(source, str):
            plan_items.append(source)
    return _render_sections(
        patient=patient,
        vitals=_vitals_from_structured(structured_data),
        labs=structured_data.get("labs_24h") if isinstance(structured_data.get("labs_24h"), list) else [],
        drugs=structured_data.get("drugs_24h") if isinstance(structured_data.get("drugs_24h"), list) else [],
        alerts=structured_data.get("alerts_24h") if isinstance(structured_data.get("alerts_24h"), list) else [],
        plan_items=plan_items,
        previous_clause=_previous_clause(structured_data),
    )


def render_daily_progress_from_workbench(draft: dict[str, Any]) -> dict[str, Any]:
    banner = draft.get("patient_banner") if isinstance(draft.get("patient_banner"), dict) else {}
    patient = {
        "name": _text(banner.get("name")),
        "bed": banner.get("bed_no"),
        "diagnosis": banner.get("primary_diagnosis") or banner.get("current_diagnosis"),
    }
    alerts: list[dict[str, Any]] = []
    for idx, raw in enumerate(draft.get("raw_ai_tags") or [], start=1):
        alerts.append({"name": raw, "alert_type": raw, "severity": "high" if any(k in str(raw).lower() for k in ("sepsis", "shock", "critical", "high", "ards", "aki")) else "warning", "id": idx})
    plan_items: list[str] = []
    for goal in draft.get("daily_goals") or []:
        target = _text(goal.get("target") or goal.get("label"))
        if target:
            plan_items.append(target)
    for task in draft.get("risk_tasks") or []:
        title = _text(task.get("title"))
        if title:
            plan_items.append(title)
    for card in draft.get("system_ap") or []:
        if not isinstance(card, dict):
            continue
        for item in card.get("plan_items") or []:
            if isinstance(item, dict):
                text = _text(item.get("text") or item.get("action") or item.get("recommendation"))
            else:
                text = _text(item)
            if text:
                plan_items.append(text)
    drugs = [{"drugName": row.get("title") or row.get("name")} for row in draft.get("timeline") or [] if isinstance(row, dict) and any(k in _text(row.get("title") or row.get("description")) for k in ("抗", "美罗", "头孢", "去甲", "镇痛"))]
    result = _render_sections(
        patient=patient,
        vitals=_vitals_from_workbench(draft),
        labs=[],
        drugs=drugs,
        alerts=alerts,
        plan_items=plan_items,
        previous_clause=_previous_clause(draft),
    )
    return {
        "style": "DAILY_PROGRESS",
        "generated_text": result["document_text"],
        "sections": result["sections"],
        "key_facts_used": result["key_facts_used"],
        "risk_profile": result["risk_profile"],
    }
