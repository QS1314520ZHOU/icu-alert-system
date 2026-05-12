from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any, Literal

from bson import ObjectId

from app import runtime
from app.config import get_config
from app.services.vital_trajectory_forecaster import get_vital_trajectory_forecaster
from app.utils.serialization import serialize_doc

logger = logging.getLogger("icu-alert")

SectionType = Literal["overview", "respiratory", "hemodynamic", "neuro", "renal", "infection", "events", "trajectory"]
Severity = Literal["stable", "watch", "deteriorating", "improving"]


@dataclass
class NarrativeBullet:
    text: str
    data_refs: list[str] = field(default_factory=list)
    value_snapshot: dict[str, Any] = field(default_factory=dict)


@dataclass
class NarrativeSection:
    section_type: SectionType
    headline: str
    bullet_points: list[NarrativeBullet] = field(default_factory=list)
    severity: Severity = "stable"


@dataclass
class DailyNarrative:
    patient_id: str
    narrative_date: date
    sections: list[NarrativeSection]
    provenance: dict[str, list[str]]
    generated_at: datetime
    generator_version: str = "patient-narrative-rules-v1"


SECTION_ORDER: list[SectionType] = ["overview", "respiratory", "hemodynamic", "neuro", "renal", "infection", "events", "trajectory"]
SECTION_LABELS: dict[str, str] = {
    "overview": "总览",
    "respiratory": "呼吸",
    "hemodynamic": "循环",
    "neuro": "神经",
    "renal": "肾脏",
    "infection": "感染",
    "events": "事件",
    "trajectory": "轨迹",
}


def _as_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _as_date(value: Any) -> date:
    dt = _as_dt(value)
    return dt.date() if dt else datetime.now().date()


def _safe_text(value: Any, default: str = "") -> str:
    text = str(value or "").strip()
    return text if text else default


def _metric(value: Any, unit: str = "", digits: int = 0) -> str:
    if value is None or value == "":
        return "未记录"
    try:
        number = float(value)
        rendered = f"{number:.{digits}f}" if digits > 0 else str(int(round(number)))
        return f"{rendered}{unit}".strip()
    except Exception:
        return f"{value}{unit}".strip()


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        try:
            import re

            match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value))
            return float(match.group(0)) if match else None
        except Exception:
            return None


def _doc_ref(prefix: str, doc: dict[str, Any]) -> str:
    raw = doc.get("_id") or doc.get("id") or doc.get("record_id") or ""
    return f"{prefix}:{raw}" if raw else prefix


def _doc_time(doc: dict[str, Any]) -> datetime:
    for key in ("time", "recordTime", "executeTime", "startTime", "created_at", "source_time", "assessmentTime", "authTime", "reportTime"):
        dt = _as_dt(doc.get(key))
        if dt:
            return dt
    return datetime.min


def render_narrative_markdown(narrative: DailyNarrative) -> str:
    lines = [f"# 患者病程叙事 {narrative.narrative_date.isoformat()}", ""]
    for section in narrative.sections:
        lines.append(f"## {SECTION_LABELS.get(section.section_type, section.section_type)} · {section.severity}")
        lines.append(section.headline)
        for bullet in section.bullet_points:
            refs = f" [{', '.join(bullet.data_refs[:4])}]" if bullet.data_refs else ""
            lines.append(f"- {bullet.text}{refs}")
        lines.append("")
    return "\n".join(lines).strip()


class PatientNarrativeService:
    """Rule-based patient narrative memory. No LLM and no ai_* collection reads."""

    def __init__(self, *, db, config=None, alert_engine=None) -> None:
        self.db = db
        self.config = config or get_config()
        self.alert_engine = alert_engine

    def _col(self):
        return self.db.col("patient_narratives")

    def _cfg(self) -> dict[str, Any]:
        try:
            cfg = (self.config.yaml_cfg or {}).get("patient_narrative", {})
            return cfg if isinstance(cfg, dict) else {}
        except Exception:
            return {}

    def enabled(self) -> bool:
        return self._cfg().get("enabled", False) is True

    def _max_context_chars(self) -> int:
        return int(self._cfg().get("max_context_chars", 6000) or 6000)

    async def _load_patient(self, patient_id: str) -> dict[str, Any] | None:
        try:
            return await self.db.col("patient").find_one({"_id": ObjectId(patient_id)})
        except Exception:
            return await self.db.col("patient").find_one({"_id": patient_id})

    async def _collect_sources(self, patient_id: str, patient_doc: dict[str, Any], target_date: date) -> dict[str, Any]:
        start = datetime.combine(target_date, time.min)
        end = start + timedelta(days=1)
        his_pid = _safe_text(patient_doc.get("hisPid") or patient_doc.get("hisPID"))

        async def _find(collection: str, query: dict[str, Any], sort_key: str = "created_at", limit: int = 80) -> list[dict[str, Any]]:
            try:
                cursor = self.db.col(collection).find(query).sort(sort_key, -1).limit(limit)
                return [doc async for doc in cursor]
            except Exception as exc:
                logger.debug("patient narrative source %s unavailable: %s", collection, exc)
                return []

        vitals: list[dict[str, Any]] = []
        if his_pid:
            for code in ("param_HR", "param_SpO2", "param_RR", "param_T", "param_nibp_m", "param_ibp_m"):
                vitals.extend(await _find("paramData", {"pid": his_pid, "code": code, "time": {"$gte": start, "$lt": end}}, "time", 120))
        labs = await _find("labResult", {"$or": [{"patient_id": patient_id}, {"pid": his_pid}, {"hisPid": his_pid}], "authTime": {"$gte": start, "$lt": end}}, "authTime", 100) if his_pid else []
        drugs = await _find("drugExe", {"$or": [{"pid": patient_id}, {"pid": his_pid}, {"patient_id": patient_id}], "executeTime": {"$gte": start, "$lt": end}}, "executeTime", 100)
        alerts = await _find("alert_records", {"patient_id": patient_id, "created_at": {"$gte": start, "$lt": end}}, "created_at", 80)
        assessments = await _find("nursing_score", {"$or": [{"patient_id": patient_id}, {"pid": his_pid}], "created_at": {"$gte": start, "$lt": end}}, "created_at", 50) if his_pid else []
        workflow_events = await _find("workflow_events", {"patient_id": patient_id, "created_at": {"$gte": start, "$lt": end}}, "created_at", 50)
        scanner_outputs = await _find("score", {"patient_id": patient_id, "calc_time": {"$gte": start, "$lt": end}, "score_type": {"$not": {"$regex": "^ai_"}}}, "calc_time", 50)
        return {
            "vitals": vitals,
            "labs": labs,
            "drugs": drugs,
            "alerts": alerts,
            "assessments": assessments,
            "workflow_events": workflow_events,
            "scanner_outputs": scanner_outputs,
        }

    def _latest_vital(self, vitals: list[dict[str, Any]], code: str) -> dict[str, Any] | None:
        rows = [row for row in vitals if str(row.get("code") or "") == code]
        return max(rows, key=_doc_time) if rows else None

    def _latest_lab_by_keywords(self, labs: list[dict[str, Any]], keywords: list[str]) -> dict[str, Any] | None:
        lowered = [key.lower() for key in keywords]
        rows = []
        for row in labs:
            text = " ".join(str(row.get(key) or "") for key in ("itemName", "name", "code", "ename", "cname")).lower()
            if any(key in text for key in lowered):
                rows.append(row)
        return max(rows, key=_doc_time) if rows else None

    def _bullet(self, text: str, refs: list[str], snapshot: dict[str, Any]) -> NarrativeBullet:
        return NarrativeBullet(text=text, data_refs=refs, value_snapshot=serialize_doc(snapshot))

    async def _trajectory_bullet(self, patient_id: str) -> NarrativeBullet:
        try:
            service = get_vital_trajectory_forecaster(db=self.db, config=self.config, alert_engine=self.alert_engine)
            forecast = await service.forecast(patient_id, ["HR", "MAP", "SpO2"], horizon_hours=6)
            if not forecast.get("available"):
                return self._bullet(f"轨迹预测未就绪：{forecast.get('reason') or '模型不可用'}。", [], {"available": False, "reason": forecast.get("reason")})
            codes = ", ".join((forecast.get("series") or {}).keys())
            return self._bullet(f"已生成 6h 轨迹预测，覆盖 {codes or '关键生命体征'}。", ["trajectory:forecast"], {"available": True, "codes": list((forecast.get("series") or {}).keys())})
        except Exception as exc:
            return self._bullet(f"轨迹预测降级：{str(exc)[:80]}。", [], {"available": False, "reason": str(exc)[:160]})

    async def build_dataclass(self, patient_id: str, patient_doc: dict[str, Any], *, narrative_date: date | datetime | str | None = None) -> DailyNarrative:
        target_date = _as_date(narrative_date)
        sources = await self._collect_sources(patient_id, patient_doc, target_date)
        previous = await self._col().find_one({"patient_id": patient_id, "narrative_date": (target_date - timedelta(days=1)).isoformat()})
        previous_headline = ""
        try:
            previous_headline = ((previous.get("json") or {}).get("sections") or [{}])[0].get("headline") or ""
        except Exception:
            previous_headline = ""

        vitals = sources["vitals"]
        labs = sources["labs"]
        alerts = sources["alerts"]
        drugs = sources["drugs"]
        assessments = sources["assessments"]
        scanner_outputs = sources["scanner_outputs"]
        workflow_events = sources["workflow_events"]
        map_row = self._latest_vital(vitals, "param_ibp_m") or self._latest_vital(vitals, "param_nibp_m")
        spo2_row = self._latest_vital(vitals, "param_SpO2")
        hr_row = self._latest_vital(vitals, "param_HR")
        rr_row = self._latest_vital(vitals, "param_RR")
        temp_row = self._latest_vital(vitals, "param_T")
        lactate_row = self._latest_lab_by_keywords(labs, ["lactate", "lac", "乳酸"])
        cr_row = self._latest_lab_by_keywords(labs, ["creatinine", "cr", "肌酐"])
        wbc_row = self._latest_lab_by_keywords(labs, ["wbc", "白细胞"])
        pct_row = self._latest_lab_by_keywords(labs, ["pct", "降钙素原"])

        provenance = {
            "vitals": [_doc_ref("vital", row) for row in vitals[:30]],
            "labs": [_doc_ref("lab", row) for row in labs[:30]],
            "drugs": [_doc_ref("drug", row) for row in drugs[:30]],
            "alerts": [_doc_ref("alert", row) for row in alerts[:30]],
            "scanner_outputs": [_doc_ref("scanner", row) for row in scanner_outputs[:30]],
            "workflow_events": [_doc_ref("workflow", row) for row in workflow_events[:30]],
            "assessments": [_doc_ref("assessment", row) for row in assessments[:30]],
        }

        high_alerts = [row for row in alerts if str(row.get("severity") or "").lower() in {"high", "critical"}]
        sections: list[NarrativeSection] = []
        overview_bullets = [
            self._bullet(
                f"{_safe_text(patient_doc.get('name') or patient_doc.get('hisName'), '患者')}，{_safe_text(patient_doc.get('hisBed') or patient_doc.get('bed'), '床位未知')}，主要诊断：{_safe_text(patient_doc.get('clinicalDiagnosis') or patient_doc.get('admissionDiagnosis'), '待补充')}。",
                ["patient:demographics"],
                {"bed": patient_doc.get("hisBed") or patient_doc.get("bed"), "diagnosis": patient_doc.get("clinicalDiagnosis") or patient_doc.get("admissionDiagnosis")},
            )
        ]
        if previous_headline:
            overview_bullets.append(self._bullet(f"昨日概要延续：{previous_headline}", ["narrative:yesterday"], {"previous_headline": previous_headline}))
        overview_bullets.append(self._bullet(f"当日记录：生命体征 {len(vitals)} 条、检验 {len(labs)} 条、用药 {len(drugs)} 条、预警 {len(alerts)} 条。", [], {"source_counts": {key: len(value) for key, value in sources.items()}}))
        sections.append(NarrativeSection("overview", f"当日结构化资料显示 {len(high_alerts)} 条高危/危急预警。", overview_bullets, "watch" if high_alerts else "stable"))

        respiratory_bullets = [
            self._bullet(f"SpO2 最新 {_metric(spo2_row.get('value') if spo2_row else None, '%')}，RR 最新 {_metric(rr_row.get('value') if rr_row else None, '/min')}。", [_doc_ref("vital", row) for row in (spo2_row, rr_row) if row], {"spo2": (spo2_row or {}).get("value"), "rr": (rr_row or {}).get("value")})
        ]
        spo2_value = _to_float(spo2_row.get("value") if spo2_row else None)
        resp_sev: Severity = "watch" if (spo2_value is not None and spo2_value < 92) else "stable"
        sections.append(NarrativeSection("respiratory", "氧合低于 92% 需重点复核。" if resp_sev == "watch" else "呼吸氧合暂无明显恶化信号。", respiratory_bullets, resp_sev))

        hemo_bullets = [
            self._bullet(f"MAP 最新 {_metric(map_row.get('value') if map_row else None, 'mmHg')}，HR 最新 {_metric(hr_row.get('value') if hr_row else None, 'bpm')}，乳酸 {_metric(lactate_row.get('value') if lactate_row else None, 'mmol/L', 1)}。", [_doc_ref("vital", row) for row in (map_row, hr_row) if row] + ([_doc_ref("lab", lactate_row)] if lactate_row else []), {"map": (map_row or {}).get("value"), "hr": (hr_row or {}).get("value"), "lactate": (lactate_row or {}).get("value")})
        ]
        map_value = _to_float(map_row.get("value") if map_row else None)
        lactate_value = _to_float(lactate_row.get("value") if lactate_row else None)
        hemo_sev: Severity = "watch" if ((map_value is not None and map_value < 65) or (lactate_value is not None and lactate_value >= 2.5)) else "stable"
        sections.append(NarrativeSection("hemodynamic", "存在低灌注/循环不稳线索。" if hemo_sev == "watch" else "循环指标未见明确低灌注触发。", hemo_bullets, hemo_sev))

        neuro_rows = [row for row in assessments if any(key in str(row).lower() for key in ("gcs", "rass", "delirium", "谵妄", "意识"))]
        sections.append(NarrativeSection("neuro", "神经评估记录可用于追踪意识/镇静变化。" if neuro_rows else "当日神经评估结构化记录不足。", [self._bullet(f"神经/镇静相关评估 {len(neuro_rows)} 条。", [_doc_ref("assessment", row) for row in neuro_rows[:5]], {"count": len(neuro_rows)})], "watch" if not neuro_rows else "stable"))

        renal_alerts = [row for row in alerts if "aki" in str(row.get("rule_id") or row.get("alert_type") or "").lower() or "肾" in str(row.get("name") or "")]
        renal_bullets = [self._bullet(f"肌酐最新 {_metric(cr_row.get('value') if cr_row else None, 'umol/L')}；肾相关预警 {len(renal_alerts)} 条。", ([_doc_ref("lab", cr_row)] if cr_row else []) + [_doc_ref("alert", row) for row in renal_alerts[:5]], {"creatinine": (cr_row or {}).get("value"), "renal_alerts": len(renal_alerts)})]
        sections.append(NarrativeSection("renal", "存在肾功能相关预警。" if renal_alerts else "肾功能暂无结构化高危触发。", renal_bullets, "watch" if renal_alerts else "stable"))

        infection_alerts = [row for row in alerts if any(key in str(row.get("rule_id") or row.get("alert_type") or row.get("name") or "").lower() for key in ("sepsis", "infection", "感染", "脓毒"))]
        infection_bullets = [self._bullet(f"WBC {_metric(wbc_row.get('value') if wbc_row else None, '10^9/L', 1)}，PCT {_metric(pct_row.get('value') if pct_row else None, 'ng/mL', 2)}；感染相关预警 {len(infection_alerts)} 条。", [_doc_ref("lab", row) for row in (wbc_row, pct_row) if row] + [_doc_ref("alert", row) for row in infection_alerts[:5]], {"wbc": (wbc_row or {}).get("value"), "pct": (pct_row or {}).get("value"), "infection_alerts": len(infection_alerts)})]
        sections.append(NarrativeSection("infection", "感染/脓毒症线索需继续核对。" if infection_alerts else "感染结构化线索未达预警阈值。", infection_bullets, "watch" if infection_alerts else "stable"))

        event_rows = sorted([*alerts[:8], *drugs[:8], *workflow_events[:8]], key=_doc_time, reverse=True)[:10]
        event_bullets = [self._bullet(f"{_doc_time(row).strftime('%H:%M') if _doc_time(row) != datetime.min else '时间未知'} {row.get('name') or row.get('drugName') or row.get('orderName') or row.get('event_type') or row.get('rule_id') or '事件'}", [_doc_ref("event", row)], {"source": row.get("score_type") or row.get("alert_type") or row.get("event_type")}) for row in event_rows]
        if not event_bullets:
            event_bullets = [self._bullet("当日暂无可结构化提取的关键事件。", [], {"count": 0})]
        sections.append(NarrativeSection("events", f"提取当日关键事件 {len(event_rows)} 条。", event_bullets, "watch" if high_alerts else "stable"))

        trajectory_bullet = await self._trajectory_bullet(patient_id)
        sections.append(NarrativeSection("trajectory", trajectory_bullet.text.replace("。", ""), [trajectory_bullet], "watch" if not trajectory_bullet.value_snapshot.get("available") else "stable"))

        return DailyNarrative(patient_id=patient_id, narrative_date=target_date, sections=sections, provenance=provenance, generated_at=datetime.now())

    def to_record(self, narrative: DailyNarrative) -> dict[str, Any]:
        data = asdict(narrative)
        data["narrative_date"] = narrative.narrative_date.isoformat()
        data["generated_at"] = narrative.generated_at
        markdown = render_narrative_markdown(narrative)
        context = markdown[: self._max_context_chars()]
        return {
            "patient_id": narrative.patient_id,
            "narrative_date": narrative.narrative_date.isoformat(),
            "json": data,
            "markdown": markdown,
            "llm_context_text": context,
            "sections": data["sections"],
            "provenance": data["provenance"],
            "generated_at": narrative.generated_at,
            "generator_version": narrative.generator_version,
            "updated_at": datetime.now(),
        }

    async def generate_daily(self, patient_id: str, patient_doc: dict[str, Any] | None = None, *, narrative_date: date | datetime | str | None = None, refresh: bool = True) -> dict[str, Any]:
        if not self.enabled():
            return {"available": False, "reason": "patient_narrative disabled", "patient_id": patient_id}
        patient_doc = patient_doc or await self._load_patient(patient_id)
        if not patient_doc:
            return {"available": False, "reason": "patient not found", "patient_id": patient_id}
        target = _as_date(narrative_date).isoformat()
        if not refresh:
            cached = await self._col().find_one({"patient_id": patient_id, "narrative_date": target})
            if cached:
                return cached
        narrative = await self.build_dataclass(patient_id, patient_doc, narrative_date=target)
        record = self.to_record(narrative)
        await self._col().update_one({"patient_id": patient_id, "narrative_date": target}, {"$set": record, "$setOnInsert": {"created_at": datetime.now()}}, upsert=True)
        return await self._col().find_one({"patient_id": patient_id, "narrative_date": target}) or record

    async def list_recent(self, patient_id: str, *, days: int = 7) -> list[dict[str, Any]]:
        days = max(1, min(int(days or 7), 30))
        since = (datetime.now().date() - timedelta(days=days - 1)).isoformat()
        cursor = self._col().find({"patient_id": patient_id, "narrative_date": {"$gte": since}}).sort("narrative_date", -1).limit(days)
        return [doc async for doc in cursor]

    async def latest_context_text(self, patient_id: str, *, days: int = 7, max_chars: int | None = None) -> str:
        if not self.enabled():
            return ""
        rows = await self.list_recent(patient_id, days=days)
        rows = sorted(rows, key=lambda row: str(row.get("narrative_date") or ""))
        text = "\n\n".join(str(row.get("llm_context_text") or row.get("markdown") or "").strip() for row in rows if row.get("llm_context_text") or row.get("markdown")).strip()
        limit = int(max_chars or self._max_context_chars())
        return text[-limit:] if len(text) > limit else text


async def _dry_run(patient_id: str, narrative_date: str | None = None) -> None:
    service = PatientNarrativeService(db=runtime.db, config=get_config(), alert_engine=runtime.alert_engine)
    patient = await service._load_patient(patient_id)
    record = await service.generate_daily(patient_id, patient, narrative_date=narrative_date, refresh=True)
    print(json.dumps(serialize_doc(record), ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Dry-run PatientNarrativeService for one patient")
    parser.add_argument("--patient-id", required=True)
    parser.add_argument("--date", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.dry_run:
        parser.error("Only --dry-run is supported")
    asyncio.run(_dry_run(args.patient_id, args.date))


if __name__ == "__main__":
    main()
