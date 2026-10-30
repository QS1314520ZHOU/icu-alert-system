"""出入量与血管活性药负荷（纯计算，无数据库依赖）。

借鉴 icu-sepsis-intelligence（ICU-05 v3）的判定原则：
- 缺失即未知：无记录不当 0；部分记录无量时累计量标记为"不完整"，不据此判"不足"。
- 血管活性药按执行动作序列（开始/暂停/恢复/停止）判断是否在用，三态：在用 / 已停 / 无法判断。
- 药名关键词严格匹配，排除常见误分类（氯化钾、氯化钠、胺碘酮）；晶体液不匹配裸"氯化钠"（会误中 10% 浓钠）。

剂量换算：
- 去甲肾上腺素当量 NEE（Goradia 2021）：NE×1 + 肾上腺素×1 + 多巴胺/100 + 去氧肾上腺素/10 + 血管加压素(U/min)×2.5；
  其他药物（间羟胺、特利加压素、正性肌力药）不计入 NEE，单列。
- 血管活性-正性肌力评分 VIS（Gaies 2010）：多巴胺 + 多巴酚丁胺 + 100×肾上腺素 + 100×去甲肾上腺素
  + 10×米力农 + 10000×血管加压素(U/kg/min)。
任何一项剂量无法换算时，对应合计标记为不完整（给出已知部分的下限），不补零。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Iterable

# ── 字典 ──────────────────────────────────────────────────────────────
# 顺序重要：长名优先，避免"肾上腺素"误中"去甲肾上腺素/去氧肾上腺素/异丙肾上腺素"
VASO_AGENTS: list[tuple[str, str, tuple[str, ...]]] = [
    ("ne", "去甲肾上腺素", ("去甲肾上腺素", "重酒石酸去甲", "norepinephrine", "noradrenaline")),
    ("phenylephrine", "去氧肾上腺素", ("去氧肾上腺素", "苯肾上腺素", "苯福林", "phenylephrine")),
    ("isoproterenol", "异丙肾上腺素", ("异丙肾上腺素", "isoproterenol", "isoprenaline")),
    ("epi", "肾上腺素", ("肾上腺素", "epinephrine", "adrenaline")),
    ("dobutamine", "多巴酚丁胺", ("多巴酚丁胺", "dobutamine")),
    ("dopamine", "多巴胺", ("多巴胺", "dopamine")),
    ("terlipressin", "特利加压素", ("特利加压素", "terlipressin")),
    ("vasopressin", "血管加压素", ("血管加压素", "垂体后叶", "加压素", "vasopressin", "pitressin")),
    ("metaraminol", "间羟胺", ("间羟胺", "阿拉明", "metaraminol")),
    ("milrinone", "米力农", ("米力农", "milrinone")),
    ("levosimendan", "左西孟旦", ("左西孟旦", "levosimendan")),
]
VASO_EXCLUDE = ("氯化钾", "氯化钠注射液", "胺碘酮", "利多卡因")  # 局麻药含肾上腺素的复方也排除
LOCAL_ANESTHETIC_HINT = ("利多卡因", "阿替卡因", "罗哌卡因")
UNIT_AGENTS = {"vasopressin", "terlipressin"}  # 剂量单位为 U
NEE_FACTOR = {"ne": 1.0, "epi": 1.0, "dopamine": 0.01, "phenylephrine": 0.1}
VIS_FACTOR = {"dopamine": 1.0, "dobutamine": 1.0, "epi": 100.0, "ne": 100.0, "milrinone": 10.0}

CRYSTALLOID = ("生理盐水", "0.9%氯化钠", "0.9％氯化钠", "normal saline", "乳酸林格", "醋酸林格", "林格", "lactated ringer",
               "plasmalyte", "勃脉力", "复方氯化钠", "复方电解质")
COLLOID = ("白蛋白", "albumin", "羟乙基淀粉", "万汶", "voluven", "琥珀酰明胶", "明胶", "gelatin", "右旋糖酐", "dextran")
BLOOD = ("红细胞", "血浆", "血小板", "冷沉淀", "全血")
NUTRITION = ("脂肪乳", "氨基酸", "卡文", "肠内营养", "能全", "瑞素", "瑞代", "百普力", "葡萄糖")
STOP_ACTIONS = {"stop", "cancel", "停止", "取消", "停用", "结束", "end", "finish"}
PAUSE_ACTIONS = {"pause", "暂停"}
RESUME_ACTIONS = {"recovery", "resume", "恢复", "继续"}

URINE_CODES = {"param_niaoLiang", "param_niaoLiang_pure", "param_udd_urine_cur", "param_udd_urine_1h",
               "param_urine", "param_尿量", "urine_output", "urine_ml_h"}
OUTPUT_CODES = {
    "drainage": {"param_drainage", "param_引流量", "drainage_output"},
    "ultrafiltration": {"param_uf", "param_超滤量", "ultrafiltration_output"},
    "gi": {"param_gi_decompression", "param_胃肠减压", "gi_decompression_output"},
    "other_out": {"param_out_other", "param_呕吐量", "param_大便量"},
}
INTAKE_CODES = {
    "enteral": {"param_enteral_in", "param_鼻饲量", "param_肠内营养"},
    "oral": {"param_oral_in", "param_饮水量", "param_口服量"},
    "iv_manual": {"param_iv_in", "param_入量", "param_静脉入量"},
}
OUTPUT_LABEL = {"urine": "尿量", "drainage": "引流", "ultrafiltration": "超滤", "gi": "胃肠减压", "other_out": "其他出量"}
INTAKE_LABEL = {"crystalloid": "晶体液", "colloid": "胶体", "blood": "血制品", "nutrition": "营养液",
                "iv_other": "其他静脉", "enteral": "肠内", "oral": "口服", "iv_manual": "护理记录静脉入量"}


def _norm(text: Any) -> str:
    return re.sub(r"^[\s*★☆#※\-·•]+", "", str(text or "")).strip().lower()


def to_float(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"-?\d+(?:\.\d+)?", str(v))
    return float(m.group(0)) if m else None


def parse_dt(v: Any) -> datetime | None:
    if isinstance(v, datetime):
        return v.replace(tzinfo=None) if v.tzinfo else v
    if not v:
        return None
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d.replace(tzinfo=None) if d.tzinfo else d
    except Exception:
        return None


def classify_vasoactive(name: Any) -> tuple[str, str] | None:
    n = _norm(name)
    if not n:
        return None
    if any(k in n for k in LOCAL_ANESTHETIC_HINT):
        return None
    for key, label, kws in VASO_AGENTS:
        if any(k.lower() in n for k in kws):
            return key, label
    return None


def fluid_type(name: Any) -> str | None:
    n = _norm(name)
    if not n:
        return None
    if any(k.lower() in n for k in BLOOD):
        return "blood"
    if any(k.lower() in n for k in COLLOID):
        return "colloid"
    if any(k.lower() in n for k in CRYSTALLOID):
        return "crystalloid"
    if any(k.lower() in n for k in NUTRITION):
        return "nutrition"
    return None


# ── 输入模型 ──────────────────────────────────────────────────────────
@dataclass
class Action:
    time: datetime | None
    action: str = ""
    speed_ml_h: float | None = None


@dataclass
class Item:
    name: str
    liquid_ml: float | None = None
    liquid_unit_known: bool = True
    dose: float | None = None
    dose_unit: str = ""


@dataclass
class Infusion:
    start: datetime | None
    items: list[Item] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    route: str = ""
    explicit_rate: float | None = None  # 医嘱直接给出的速度值
    explicit_rate_unit: str = ""
    source_id: str = ""


def infusion_from_doc(doc: dict) -> Infusion:
    """兼容两种 drugExe 结构：SmartCare 原生 drugList/drugActionList；以及扁平 drugName/dose/volume。"""
    start = parse_dt(doc.get("startTime")) or parse_dt(doc.get("executeTime")) or parse_dt(doc.get("orderTime"))
    parent_unit = str(doc.get("liquidAmountUnit") or "").strip().lower()
    parent_ml = parent_unit in ("", "ml", "毫升")
    items: list[Item] = []
    for it in doc.get("drugList") or []:
        if not isinstance(it, dict):
            continue
        unit = it.get("liquidUnit")
        known = parent_ml if unit is None else str(unit).strip().lower() in ("", "ml", "毫升")
        items.append(Item(
            name=str(it.get("name") or it.get("drugName") or ""),
            liquid_ml=to_float(it.get("liquidAmount")),
            liquid_unit_known=known,
            dose=to_float(it.get("dose") if it.get("dose") is not None else it.get("amount")),
            dose_unit=str(it.get("doseUnit") or it.get("unit") or ""),
        ))
    if not items:
        name = str(doc.get("drugName") or doc.get("orderName") or "")
        vol = None
        for k in ("volume", "totalVolume", "inputVolume", "infusionVolume"):
            vol = to_float(doc.get(k))
            if vol:
                break
        vunit = str(doc.get("volumeUnit") or "ml").strip().lower()
        dose_unit = str(doc.get("doseUnit") or doc.get("unit") or "")
        dose = to_float(doc.get("dose"))
        if vol is None and dose is not None and dose_unit.strip().lower() in ("ml", "毫升"):
            vol, dose = dose, None
        items.append(Item(name=name, liquid_ml=vol, liquid_unit_known=vunit in ("ml", "毫升", ""), dose=dose, dose_unit=dose_unit))
    actions: list[Action] = []
    for a in doc.get("drugActionList") or []:
        if not isinstance(a, dict):
            continue
        sp = None
        for k in ("speed", "dripSpeed", "rate"):
            sp = to_float(a.get(k))
            if sp is not None:
                break
        act = a.get("action") if a.get("action") is not None else a.get("type")
        actions.append(Action(time=parse_dt(a.get("time")), action=str(act or ""), speed_ml_h=sp))
    rate, rate_unit = None, ""
    for vk, uk in (("rate", "rateUnit"), ("speed", "speedUnit"), ("flowRate", "flowRateUnit")):
        if doc.get(vk) is not None:
            rate, rate_unit = to_float(doc.get(vk)), str(doc.get(uk) or "")
            break
    return Infusion(start=start, items=items, actions=actions, route=str(doc.get("routeName") or doc.get("route") or ""),
                    explicit_rate=rate, explicit_rate_unit=rate_unit, source_id=str(doc.get("_id") or ""))


# ── 在用状态（三态） ──────────────────────────────────────────────────
def _act_kind(raw: str) -> str:
    r = (raw or "").strip().lower()
    if r in STOP_ACTIONS:
        return "stop"
    if r in PAUSE_ACTIONS:
        return "pause"
    if r in RESUME_ACTIONS:
        return "resume"
    return "keep"


def running_at(inf: Infusion, at: datetime) -> bool | None:
    """TRUE/FALSE/None。无执行动作且开始于 at 之前 → None（泵可能已静默结束）。"""
    if inf.start is None:
        return None
    if inf.start > at:
        return False
    acts = sorted([a for a in inf.actions if a.time], key=lambda a: a.time)  # type: ignore[arg-type,return-value]
    if not acts:
        return None
    on = True
    for a in acts:
        if a.time > at:  # type: ignore[operator]
            break
        k = _act_kind(a.action)
        if k in ("stop", "pause"):
            on = False
        elif k == "resume":
            on = True
        if a.speed_ml_h is not None and a.speed_ml_h <= 0:
            on = False
        elif a.speed_ml_h is not None and a.speed_ml_h > 0 and k == "keep":
            on = True
    return on


def speed_at(inf: Infusion, at: datetime) -> float | None:
    speed = None
    for a in sorted([a for a in inf.actions if a.time], key=lambda a: a.time):  # type: ignore[arg-type,return-value]
        if a.time > at:  # type: ignore[operator]
            break
        if a.speed_ml_h is not None:
            speed = a.speed_ml_h
    return speed


# ── 剂量换算 ──────────────────────────────────────────────────────────
def _amount_in_ug_or_u(dose: float | None, unit: str, unit_agent: bool) -> float | None:
    if dose is None or dose <= 0:
        return None
    u = unit.strip().lower().replace("μ", "u").replace("µ", "u")
    if unit_agent:
        if u in ("u", "iu", "单位", "units", "unit"):
            return dose
        return None
    if u in ("mg", "毫克"):
        return dose * 1000.0
    if u in ("ug", "mcg", "微克"):
        return dose
    if u in ("g", "克"):
        return dose * 1e6
    return None


def rate_from_text(value: float | None, unit: str, weight: float | None) -> float | None:
    """显式速度单位 → μg/kg/min（血管加压素为 U/min，另行处理）。"""
    if value is None or value <= 0:
        return None
    u = unit.lower().replace(" ", "").replace("μ", "u").replace("µ", "u")
    if "ug/kg/min" in u or "mcg/kg/min" in u:
        return value
    if "mg/kg/h" in u:
        return value * 1000 / 60
    if weight is None or weight <= 0:
        return None
    if "mg/h" in u:
        return value * 1000 / 60 / weight
    if "ug/min" in u or "mcg/min" in u:
        return value / weight
    if "ug/h" in u or "mcg/h" in u:
        return value / 60 / weight
    return None


@dataclass
class DoseResult:
    value: float | None
    unit: str
    reason: str | None = None  # 无法换算的原因


def vaso_dose(inf: Infusion, agent: str, at: datetime, weight: float | None) -> DoseResult:
    unit_agent = agent in UNIT_AGENTS
    unit_label = "U/min" if unit_agent else "μg/kg/min"
    if inf.explicit_rate is not None and not unit_agent:
        r = rate_from_text(inf.explicit_rate, inf.explicit_rate_unit, weight)
        if r is not None:
            return DoseResult(round(r, 4), unit_label)
    speed = speed_at(inf, at)
    if speed is None:
        return DoseResult(None, unit_label, "无泵速记录")
    if speed <= 0:
        return DoseResult(0.0, unit_label)
    drug_item = next((it for it in inf.items if classify_vasoactive(it.name) and classify_vasoactive(it.name)[0] == agent), None)  # type: ignore[index]
    amount = _amount_in_ug_or_u(drug_item.dose if drug_item else None, drug_item.dose_unit if drug_item else "", unit_agent)
    if amount is None:
        return DoseResult(None, unit_label, "药量或单位缺失，无法计算浓度")
    total_ml = 0.0
    for it in inf.items:
        if it.liquid_ml is None or not it.liquid_unit_known:
            return DoseResult(None, unit_label, "配液总量缺失")
        total_ml += it.liquid_ml
    if total_ml <= 0:
        return DoseResult(None, unit_label, "配液总量缺失")
    per_min = amount / total_ml * speed / 60.0  # μg/min 或 U/min
    if unit_agent:
        return DoseResult(round(per_min, 4), unit_label)
    if weight is None or weight <= 0:
        return DoseResult(None, unit_label, "缺体重")
    return DoseResult(round(per_min / weight, 4), unit_label)


def nee_of(doses: dict[str, float | None]) -> tuple[float | None, bool]:
    """返回 (NEE, 是否完整)。只要有一项计入 NEE 的药剂量未知 → 不完整，值为已知部分下限。"""
    total, complete, any_known = 0.0, True, False
    for agent, v in doses.items():
        if agent in NEE_FACTOR:
            if v is None:
                complete = False
            else:
                total += v * NEE_FACTOR[agent]
                any_known = True
        elif agent == "vasopressin":
            if v is None:
                complete = False
            else:
                total += v * 2.5
                any_known = True
    if not any_known and not complete:
        return None, False
    return round(total, 3), complete


def vis_of(doses: dict[str, float | None], weight: float | None) -> tuple[float | None, bool]:
    total, complete, any_known = 0.0, True, False
    for agent, v in doses.items():
        if agent in VIS_FACTOR:
            if v is None:
                complete = False
                continue
            total += v * VIS_FACTOR[agent]
            any_known = True
        elif agent == "vasopressin":
            if v is None or not weight:
                complete = False
                continue
            total += 10000.0 * v / weight
            any_known = True
    if not any_known and not complete:
        return None, False
    return round(total, 1), complete


# ── 汇总 ──────────────────────────────────────────────────────────────
@dataclass
class Observation:
    time: datetime
    code: str
    value: float


def _hour_floor(t: datetime) -> datetime:
    return t.replace(minute=0, second=0, microsecond=0)


def compute(
    *,
    infusion_docs: Iterable[dict],
    bedside: Iterable[Observation],
    weight_kg: float | None,
    now: datetime,
    hours: int = 24,
    urine_codes: set[str] | None = None,
) -> dict[str, Any]:
    hours = max(6, min(int(hours or 24), 72))
    end = _hour_floor(now) + timedelta(hours=1)
    start = end - timedelta(hours=hours)
    buckets = [start + timedelta(hours=i) for i in range(hours)]
    urine_codes = urine_codes or URINE_CODES
    infusions = [infusion_from_doc(d) for d in infusion_docs]

    # ---- 入量（输液执行记录，按开始时间整袋计入） ----
    intake = {b: {} for b in buckets}
    intake_incomplete = 0
    resus = {"crystalloid": 0.0, "colloid": 0.0}
    resus_incomplete = False
    for inf in infusions:
        if inf.start is None or inf.start < start or inf.start >= end:
            continue
        if any(classify_vasoactive(it.name) for it in inf.items):
            # 血管活性药泵入液量小，且速度可变，按泵速积分不可靠时不计入（单独提示）
            continue
        b = _hour_floor(inf.start)
        cat = None
        vol, missing = 0.0, False
        for it in inf.items:
            ft = fluid_type(it.name)
            if ft and (cat is None or ft in ("crystalloid", "colloid", "blood")):
                cat = ft if cat not in ("crystalloid", "colloid", "blood") else cat
            if it.liquid_ml is None or not it.liquid_unit_known:
                missing = True
            else:
                vol += it.liquid_ml
        cat = cat or "iv_other"
        route = inf.route.lower()
        if any(k in route for k in ("鼻饲", "胃管", "肠内", "enteral")):
            cat = "enteral"
        elif any(k in route for k in ("口服", "oral", "po")) and "pump" not in route:
            cat = "oral"
        if missing:
            intake_incomplete += 1
        if vol > 0:
            intake[b][cat] = intake[b].get(cat, 0.0) + vol
        if cat in resus:
            if missing:
                resus_incomplete = True
            resus[cat] += vol

    # ---- 出量 & 护理记录入量 ----
    output = {b: {} for b in buckets}
    urine_hours: set[datetime] = set()
    for ob in bedside:
        if ob.time < start or ob.time >= end or ob.value is None or ob.value < 0:
            continue
        b = _hour_floor(ob.time)
        if ob.code in urine_codes:
            output[b]["urine"] = output[b].get("urine", 0.0) + ob.value
            urine_hours.add(b)
            continue
        for cat, codes in OUTPUT_CODES.items():
            if ob.code in codes:
                output[b][cat] = output[b].get(cat, 0.0) + ob.value
                break
        else:
            for cat, codes in INTAKE_CODES.items():
                if ob.code in codes:
                    intake[b][cat] = intake[b].get(cat, 0.0) + ob.value
                    break

    rows = []
    cum = 0.0
    for b in buckets:
        i_sum = sum(intake[b].values())
        o_sum = sum(output[b].values())
        cum += i_sum - o_sum
        rows.append({
            "hour": b.isoformat(),
            "intake_ml": round(i_sum, 1),
            "output_ml": round(o_sum, 1),
            "urine_ml": round(output[b]["urine"], 1) if b in urine_hours else None,
            "net_ml": round(i_sum - o_sum, 1),
            "cumulative_ml": round(cum, 1),
            "intake_by": {k: round(v, 1) for k, v in intake[b].items()},
            "output_by": {k: round(v, 1) for k, v in output[b].items()},
        })

    def _window(h: int) -> dict[str, Any]:
        sub = rows[-h:]
        i_ = sum(r["intake_ml"] for r in sub)
        o_ = sum(r["output_ml"] for r in sub)
        urine_vals = [r["urine_ml"] for r in sub if r["urine_ml"] is not None]
        recorded = len(urine_vals)
        urine_total = sum(urine_vals) if urine_vals else None
        # 尿量常按 2-4 小时汇总记录：只要窗口内有记录，用"总量/窗口小时"；完全无记录 → 未知
        rate = (urine_total / h / weight_kg) if (urine_total is not None and weight_kg) else None
        return {
            "hours": h, "intake_ml": round(i_, 1), "output_ml": round(o_, 1), "net_ml": round(i_ - o_, 1),
            "urine_ml": round(urine_total, 1) if urine_total is not None else None,
            "urine_ml_kg_h": round(rate, 2) if rate is not None else None,
            "urine_hours_recorded": recorded,
        }

    windows = {f"{h}h": _window(h) for h in (6, 12, 24) if h <= hours}
    totals = {"intake_ml": round(sum(r["intake_ml"] for r in rows), 1), "output_ml": round(sum(r["output_ml"] for r in rows), 1)}
    totals["net_ml"] = round(totals["intake_ml"] - totals["output_ml"], 1)
    intake_by: dict[str, float] = {}
    output_by: dict[str, float] = {}
    for r in rows:
        for k, v in r["intake_by"].items():
            intake_by[k] = round(intake_by.get(k, 0.0) + v, 1)
        for k, v in r["output_by"].items():
            output_by[k] = round(output_by.get(k, 0.0) + v, 1)
    overload_pct = round(totals["net_ml"] / 1000.0 / weight_kg * 100, 1) if weight_kg else None
    last_urine = max(urine_hours) if urine_hours else None
    hours_since_urine = round((now - last_urine).total_seconds() / 3600, 1) if last_urine else None

    # ---- 血管活性药 ----
    agents: dict[str, dict[str, Any]] = {}
    for inf in infusions:
        if inf.start is None or inf.start >= end:
            continue
        for it in inf.items:
            c = classify_vasoactive(it.name)
            if not c:
                continue
            key, label = c
            a = agents.setdefault(key, {"agent": key, "label": label, "infusions": []})
            a["infusions"].append(inf)
    hourly_dose: list[dict[str, Any]] = []
    sample_times = [min(b + timedelta(minutes=59), now) for b in buckets if b <= now] + [now]
    for at in sample_times:
        doses: dict[str, float | None] = {}
        for key, a in agents.items():
            best: DoseResult | None = None
            state_unknown = False
            for inf in a["infusions"]:
                st = running_at(inf, at)
                if st is None:
                    state_unknown = True
                    continue
                if not st:
                    continue
                d = vaso_dose(inf, key, at, weight_kg)
                if best is None or (d.value or 0) > (best.value or 0):
                    best = d
            if best is not None:
                doses[key] = best.value
            elif state_unknown:
                doses[key] = None
        hourly_dose.append({"time": at.isoformat(), "doses": doses})
    current = hourly_dose[-1]["doses"] if hourly_dose else {}
    agent_rows = []
    for key, a in agents.items():
        states = [running_at(inf, now) for inf in a["infusions"]]
        starts = [inf.start for inf in a["infusions"] if inf.start]
        latest_start = max(starts) if starts else None
        state = "running" if any(x is True for x in states) else "unknown" if any(x is None for x in states) else "stopped"
        latest_reason = None
        if state == "running":
            for inf, st in zip(a["infusions"], states):
                if st:
                    latest_reason = vaso_dose(inf, key, now, weight_kg).reason
                    if latest_reason is None:
                        break
        series = [{"time": h["time"], "dose": h["doses"].get(key)} for h in hourly_dose if key in h["doses"]]
        agent_rows.append({
            "agent": key, "label": a["label"],
            "unit": "U/min" if key in UNIT_AGENTS else "μg/kg/min",
            "state": state,
            "current_dose": current.get(key) if state == "running" else None,
            "dose_unknown_reason": latest_reason if current.get(key) is None and state == "running" else None,
            "started_at": latest_start.isoformat() if latest_start else None,
            "series": series,
            "in_nee": key in NEE_FACTOR or key == "vasopressin",
        })
    agent_rows.sort(key=lambda r: (r["state"] != "running", r["label"]))
    running_doses = {r["agent"]: r["current_dose"] for r in agent_rows if r["state"] == "running"}
    nee, nee_complete = nee_of(running_doses) if running_doses else (0.0, True)
    vis, vis_complete = vis_of(running_doses, weight_kg) if running_doses else (0.0, True)
    unknown_agents = {r["agent"] for r in agent_rows if r["state"] == "unknown"}
    if unknown_agents & (set(NEE_FACTOR) | {"vasopressin"}):
        nee_complete = False
    if unknown_agents & (set(VIS_FACTOR) | {"vasopressin"}):
        vis_complete = False
    nee_series = []
    for h in hourly_dose:
        running = {k: v for k, v in h["doses"].items()}
        v, c = nee_of(running) if running else (0.0, True)
        nee_series.append({"time": h["time"], "nee": v, "complete": c})
    nee_6h_ago = next((p for p in reversed(nee_series[:-6]) if p["nee"] is not None), None) if len(nee_series) > 6 else None

    # ---- 结论 ----
    findings: list[dict[str, str]] = []
    w = windows.get("6h") or {}
    if w.get("urine_ml_kg_h") is not None and w["urine_ml_kg_h"] < 0.5:
        findings.append({"level": "critical" if w["urine_ml_kg_h"] < 0.3 else "warning",
                         "text": f"近6h尿量 {w['urine_ml_kg_h']} ml/kg/h（<0.5，KDIGO 少尿标准）"})
    if hours_since_urine is not None and hours_since_urine >= 4:
        findings.append({"level": "warning", "text": f"距上次尿量记录已 {hours_since_urine} 小时"})
    if not urine_hours:
        findings.append({"level": "warning", "text": f"近{hours}h 无尿量记录（未知，不按 0 计）"})
    if overload_pct is not None and overload_pct >= 10:
        findings.append({"level": "critical", "text": f"{hours}h 累计正平衡 {totals['net_ml']:.0f} ml，约占体重 {overload_pct}%（≥10% 液体过负荷）"})
    elif overload_pct is not None and overload_pct >= 5:
        findings.append({"level": "warning", "text": f"{hours}h 累计正平衡 {totals['net_ml']:.0f} ml，约占体重 {overload_pct}%"})
    if nee is not None and running_doses:
        lvl = "critical" if nee >= 0.5 else "warning" if nee >= 0.25 else "info"
        txt = f"当前去甲肾上腺素当量 {'≥' if not nee_complete else ''}{nee} μg/kg/min"
        if nee >= 0.25:
            txt += "（≥0.25，已联用血管加压素）" if "vasopressin" in running_doses else "（≥0.25，SSC 建议考虑加用血管加压素/评估激素）"
        findings.append({"level": lvl, "text": txt})
        if nee_6h_ago and nee_6h_ago["nee"] is not None and nee_complete:
            diff = round(nee - nee_6h_ago["nee"], 3)
            if abs(diff) >= 0.05:
                findings.append({"level": "warning" if diff > 0 else "info", "text": f"较6小时前{'上调' if diff > 0 else '下调'} {abs(diff)} μg/kg/min"})
    for r in agent_rows:
        if r["state"] == "running" and r["current_dose"] is None:
            findings.append({"level": "warning", "text": f"{r['label']}在用但剂量无法换算：{r['dose_unknown_reason'] or '数据不足'}"})
        if r["state"] == "unknown":
            findings.append({"level": "info", "text": f"{r['label']}有执行记录，但缺少执行动作，无法判断是否仍在泵入"})
    if intake_incomplete:
        findings.append({"level": "info", "text": f"{intake_incomplete} 条输液记录无液量/单位非 ml，入量为下限"})

    resus_total = resus["crystalloid"] + resus["colloid"]
    target = round(30 * weight_kg) if weight_kg else None
    return {
        "window_hours": hours,
        "generated_at": now.isoformat(),
        "weight_kg": weight_kg,
        "fluid": {
            "rows": rows,
            "windows": windows,
            "totals": totals,
            "intake_by": [{"key": k, "label": INTAKE_LABEL.get(k, k), "ml": v} for k, v in sorted(intake_by.items(), key=lambda x: -x[1])],
            "output_by": [{"key": k, "label": OUTPUT_LABEL.get(k, k), "ml": v} for k, v in sorted(output_by.items(), key=lambda x: -x[1])],
            "fluid_overload_pct": overload_pct,
            "intake_incomplete_records": intake_incomplete,
            "hours_since_urine": hours_since_urine,
            "resuscitation": {
                "crystalloid_ml": round(resus["crystalloid"], 1), "colloid_ml": round(resus["colloid"], 1),
                "total_ml": round(resus_total, 1), "target_30ml_kg": target,
                "met": (True if target and resus_total >= target else (None if resus_incomplete or not target else False)),
                "incomplete": resus_incomplete,
            },
            "method": "入量=输液执行记录（按开始时间整袋计入，血管活性药泵液不计）+ 护理记录入量；出量=护理记录。尿量无记录的小时为空，不按 0 计。",
        },
        "vasoactive": {
            "agents": agent_rows,
            "nee": nee,
            "nee_complete": nee_complete,
            "vis": vis,
            "vis_complete": vis_complete,
            "nee_series": nee_series,
            "method": "NEE=NE+肾上腺素+多巴胺/100+去氧肾上腺素/10+血管加压素(U/min)×2.5；VIS=多巴胺+多巴酚丁胺+100×(肾上腺素+NE)+10×米力农+10000×加压素(U/kg/min)。剂量=药量/配液总量×泵速/体重；任一项缺失时显示为下限（≥）。",
        },
        "findings": findings,
        "data_gaps": [x for x in [None if weight_kg else "缺体重：无法计算 ml/kg/h、μg/kg/min 与 30 ml/kg 目标"] if x],
    }
