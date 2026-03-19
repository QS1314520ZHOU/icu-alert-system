"""ICU multi-agent orchestration service."""
from __future__ import annotations

from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Any

from bson import ObjectId

from app.services.clinical_knowledge_graph import ClinicalKnowledgeGraph
from app.services.clinical_reasoning_agent import ClinicalReasoningAgent


@dataclass(frozen=True)
class SpecialistAssessment:
    agent: str
    domain: str
    summary: str
    concerns: list[str]
    recommendations: list[str]
    priority: str
    evidence: list[str]


class ICUMultiAgentOrchestrator:
    def __init__(self, *, db, config, alert_engine, rag_service=None, ai_monitor=None, ai_handoff_service=None) -> None:
        self.db = db
        self.config = config
        self.alert_engine = alert_engine
        self.rag_service = rag_service
        self.ai_monitor = ai_monitor
        self.ai_handoff_service = ai_handoff_service
        self.reasoning_agent = ClinicalReasoningAgent(
            db=db,
            config=config,
            alert_engine=alert_engine,
            rag_service=rag_service,
            ai_monitor=ai_monitor,
            ai_handoff_service=ai_handoff_service,
        )
        self.knowledge_graph = ClinicalKnowledgeGraph(
            db=db,
            config=config,
            alert_engine=alert_engine,
            rag_service=rag_service,
        )
        self.agents = {
            "hemodynamic_agent": self._assess_hemodynamic,
            "respiratory_agent": self._assess_respiratory,
            "infection_agent": self._assess_infection,
            "renal_agent": self._assess_renal,
            "neuro_agent": self._assess_neuro,
            "nutrition_agent": self._assess_nutrition,
            "pharmacy_agent": self._assess_pharmacy,
        }

    def _cfg(self) -> dict[str, Any]:
        cfg = (self.config.yaml_cfg or {}).get("ai_service", {}).get("multi_agent", {})
        return cfg if isinstance(cfg, dict) else {}

    def _digital_twin_cache_minutes(self) -> int:
        cfg = self._cfg()
        return max(5, int(cfg.get("digital_twin_cache_minutes", 90) or 90))

    async def _load_patient(self, patient_id: str) -> dict[str, Any] | None:
        try:
            return await self.db.col("patient").find_one({"_id": ObjectId(patient_id)})
        except Exception:
            return None

    def _labs(self, twin: dict[str, Any]) -> dict[str, Any]:
        facts = twin.get("facts") if isinstance(twin.get("facts"), dict) else {}
        labs = facts.get("labs") if isinstance(facts.get("labs"), dict) else {}
        return labs

    def _vitals(self, twin: dict[str, Any]) -> dict[str, Any]:
        facts = twin.get("facts") if isinstance(twin.get("facts"), dict) else {}
        vitals = facts.get("vitals") if isinstance(facts.get("vitals"), dict) else {}
        return vitals

    def _alerts(self, twin: dict[str, Any]) -> list[dict[str, Any]]:
        rows = twin.get("recent_alerts_24h")
        return rows if isinstance(rows, list) else []

    def _drug_names(self, twin: dict[str, Any]) -> str:
        handoff = twin.get("handoff_context") if isinstance(twin.get("handoff_context"), dict) else {}
        drugs = handoff.get("drugs_12h") if isinstance(handoff.get("drugs_12h"), list) else []
        return " ".join(str(item.get("drugName") or item.get("orderName") or "") for item in drugs).lower()

    def _priority_from_flags(self, critical: bool, high: bool) -> str:
        if critical:
            return "critical"
        if high:
            return "high"
        return "medium"

    def _assess_hemodynamic(self, twin: dict[str, Any]) -> SpecialistAssessment:
        vitals = self._vitals(twin)
        labs = self._labs(twin)
        concerns: list[str] = []
        evidence: list[str] = []
        recs: list[str] = []
        map_value = vitals.get("map")
        hr = vitals.get("hr")
        lactate = ((labs.get("lac") or labs.get("lactate") or {}) if isinstance(labs.get("lac") or labs.get("lactate"), dict) else {}).get("value")
        if map_value is not None and float(map_value) < 65:
            concerns.append("平均动脉压偏低，存在灌注不足风险")
            evidence.append(f"MAP {map_value} mmHg")
            recs.append("优先复核容量反应性、目标 MAP 与升压药需求")
        if hr is not None and float(hr) >= 120:
            concerns.append("心率明显增快，需警惕休克代偿或节律问题")
            evidence.append(f"HR {hr}/min")
        if lactate is not None and float(lactate) >= 2:
            concerns.append("乳酸升高提示低灌注或代谢应激")
            evidence.append(f"乳酸 {lactate}")
            recs.append("建议 2-4 小时内复查乳酸并联动尿量/末梢灌注评估")
        summary = concerns[0] if concerns else "当前未见明确血流动力学失代偿证据"
        return SpecialistAssessment("hemodynamic_agent", "hemodynamic", summary, concerns, recs or ["维持循环趋势监测"], self._priority_from_flags(bool(map_value is not None and float(map_value) < 60), bool(concerns)), evidence)

    def _assess_respiratory(self, twin: dict[str, Any]) -> SpecialistAssessment:
        vitals = self._vitals(twin)
        concerns: list[str] = []
        evidence: list[str] = []
        recs: list[str] = []
        spo2 = vitals.get("spo2")
        rr = vitals.get("rr")
        if spo2 is not None and float(spo2) < 92:
            concerns.append("氧合下降，需警惕呼吸衰竭进展")
            evidence.append(f"SpO2 {spo2}%")
            recs.append("复核氧疗/通气支持强度并评估血气")
        if rr is not None and float(rr) >= 28:
            concerns.append("呼吸频率增快，提示呼吸功增加")
            evidence.append(f"RR {rr}/min")
            recs.append("关注疲劳、痰液负荷及通气同步性")
        summary = concerns[0] if concerns else "当前呼吸状态相对平稳"
        return SpecialistAssessment("respiratory_agent", "respiratory", summary, concerns, recs or ["持续观察氧合与呼吸功"], self._priority_from_flags(bool(spo2 is not None and float(spo2) < 88), bool(concerns)), evidence)

    def _assess_infection(self, twin: dict[str, Any]) -> SpecialistAssessment:
        alerts = self._alerts(twin)
        labs = self._labs(twin)
        concerns: list[str] = []
        evidence: list[str] = []
        recs: list[str] = []
        wbc = ((labs.get("wbc") or {}) if isinstance(labs.get("wbc"), dict) else {}).get("value")
        pct = ((labs.get("pct") or {}) if isinstance(labs.get("pct"), dict) else {}).get("value")
        if any("sepsis" in " ".join(str(row.get(k) or "") for k in ("alert_type", "rule_id", "name")).lower() for row in alerts):
            concerns.append("存在感染/脓毒症相关信号")
            evidence.append("近24h存在 sepsis/qSOFA/SOFA 相关预警")
            recs.append("复核感染灶控制、培养送检与抗感染时效")
        if wbc is not None:
            evidence.append(f"WBC {wbc}")
        if pct is not None:
            evidence.append(f"PCT {pct}")
        summary = concerns[0] if concerns else "当前未见强感染失控证据"
        return SpecialistAssessment("infection_agent", "infection", summary, concerns, recs or ["结合培养与炎症趋势复评"], self._priority_from_flags(False, bool(concerns)), evidence)

    def _assess_renal(self, twin: dict[str, Any]) -> SpecialistAssessment:
        labs = self._labs(twin)
        alerts = self._alerts(twin)
        concerns: list[str] = []
        evidence: list[str] = []
        recs: list[str] = []
        cr = ((labs.get("cr") or {}) if isinstance(labs.get("cr"), dict) else {}).get("value")
        if cr is not None and float(cr) >= 150:
            concerns.append("肾功能恶化风险升高")
            evidence.append(f"肌酐 {cr}")
            recs.append("复核容量状态、肾毒性药物与剂量调整")
        if any("crrt" in " ".join(str(row.get(k) or "") for k in ("alert_type", "rule_id", "name")).lower() for row in alerts):
            concerns.append("患者处于 CRRT/肾脏支持相关情境")
            evidence.append("近24h存在 CRRT 相关记录/预警")
        summary = concerns[0] if concerns else "当前肾脏支持需求未见明显升级信号"
        return SpecialistAssessment("renal_agent", "renal", summary, concerns, recs or ["继续跟踪肾功能、电解质和液体平衡"], self._priority_from_flags(False, bool(concerns)), evidence)

    def _assess_neuro(self, twin: dict[str, Any]) -> SpecialistAssessment:
        facts = twin.get("facts") if isinstance(twin.get("facts"), dict) else {}
        concerns: list[str] = []
        evidence: list[str] = []
        recs: list[str] = []
        gcs = facts.get("gcs") if facts.get("gcs") is not None else None
        if gcs is None and isinstance(facts.get("vitals"), dict):
            gcs = None
        alerts = self._alerts(twin)
        if any(any(token in " ".join(str(row.get(k) or "") for k in ("alert_type", "rule_id", "name")).lower() for token in ["delirium", "pupil", "gcs", "tbi"]) for row in alerts):
            concerns.append("存在神经系统/镇静相关异常信号")
            evidence.append("近24h存在瞳孔、GCS、谵妄或神外相关预警")
            recs.append("复核 GCS/RASS/CAM-ICU 与镇静镇痛目标")
        summary = concerns[0] if concerns else "当前神经系统状态未见明显新增危险信号"
        return SpecialistAssessment("neuro_agent", "neuro", summary, concerns, recs or ["保持神经监测与镇静评估节律"], self._priority_from_flags(False, bool(concerns)), evidence)

    def _assess_nutrition(self, twin: dict[str, Any]) -> SpecialistAssessment:
        alerts = self._alerts(twin)
        labs = self._labs(twin)
        concerns: list[str] = []
        evidence: list[str] = []
        recs: list[str] = []
        po4 = ((labs.get("po4") or {}) if isinstance(labs.get("po4"), dict) else {}).get("value")
        if any("nutrition" in " ".join(str(row.get(k) or "") for k in ("alert_type", "rule_id", "name")).lower() for row in alerts):
            concerns.append("营养支持相关风险需继续闭环管理")
            evidence.append("近24h存在营养/再喂养相关预警")
            recs.append("复核热卡、蛋白供给及电解质补充策略")
        if po4 is not None:
            evidence.append(f"PO4 {po4}")
        summary = concerns[0] if concerns else "当前营养代谢风险未见突出升级"
        return SpecialistAssessment("nutrition_agent", "nutrition", summary, concerns, recs or ["持续监测热卡达标率和电解质"], self._priority_from_flags(False, bool(concerns)), evidence)

    async def _assess_pharmacy(self, twin: dict[str, Any]) -> SpecialistAssessment:
        drug_blob = self._drug_names(twin)
        concerns: list[str] = []
        evidence: list[str] = []
        recs: list[str] = []
        if any(token in drug_blob for token in ["vancomycin", "万古霉素", "linezolid", "利奈唑胺"]):
            concerns.append("存在高风险抗感染药物暴露，需关注毒性和疗效平衡")
            recs.append("复核 TDM、肾功能与药物相互作用")
        if any(token in drug_blob for token in ["heparin", "肝素"]):
            concerns.append("存在抗凝相关风险，需关注出血和 HIT 线索")
            recs.append("动态追踪血小板、凝血和出血征象")
        if any(token in drug_blob for token in ["propofol", "丙泊酚"]):
            evidence.append("近期使用丙泊酚")
        summary = concerns[0] if concerns else "当前药学风险未见明显升级信号"
        return SpecialistAssessment("pharmacy_agent", "pharmacy", summary, concerns, recs or ["继续做肾毒性/相互作用复核"], self._priority_from_flags(False, bool(concerns)), evidence)

    def detect_conflicts(self, assessments: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        conflicts: list[dict[str, Any]] = []
        renal_recs = " ".join(str(x) for x in (assessments.get("renal_agent", {}).get("recommendations") or []))
        hemo_recs = " ".join(str(x) for x in (assessments.get("hemodynamic_agent", {}).get("recommendations") or []))
        infect_recs = " ".join(str(x) for x in (assessments.get("infection_agent", {}).get("recommendations") or []))
        if ("容量" in hemo_recs or "补液" in hemo_recs) and ("液体平衡" in renal_recs or "限液" in renal_recs):
            conflicts.append({
                "type": "fluid_strategy_conflict",
                "agents": ["hemodynamic_agent", "renal_agent"],
                "summary": "血流动力学支持与肾脏/液体管理之间存在补液策略冲突",
                "resolution_focus": "需要结合容量反应性、氧合和肾功能动态综合决策",
            })
        if ("抗感染" in infect_recs) and ("肾功能" in renal_recs):
            conflicts.append({
                "type": "antiinfective_renal_conflict",
                "agents": ["infection_agent", "renal_agent", "pharmacy_agent"],
                "summary": "感染控制与肾脏保护之间存在药物剂量/毒性权衡",
                "resolution_focus": "需联动药学和肾功能做剂量个体化调整",
            })
        return conflicts

    async def _meta_synthesize(self, *, twin: dict[str, Any], assessments: dict[str, dict[str, Any]], conflicts: list[dict[str, Any]]) -> dict[str, Any]:
        priorities = sorted(
            assessments.values(),
            key=lambda row: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(str(row.get("priority") or "medium"), 9),
        )
        top_items = priorities[:3]
        summary = "；".join(str(item.get("summary") or "") for item in top_items if str(item.get("summary") or "").strip()) or "当前多学科评估未发现显著冲突。"
        final_actions = list(dict.fromkeys([rec for item in top_items for rec in (item.get("recommendations") or [])]))[:8]
        if conflicts:
            for conflict in conflicts:
                resolution = str(conflict.get("resolution_focus") or "").strip()
                if resolution and resolution not in final_actions:
                    final_actions.append(resolution)
        return {
            "summary": summary,
            "top_priorities": [
                {"agent": item.get("agent"), "domain": item.get("domain"), "summary": item.get("summary"), "priority": item.get("priority")}
                for item in top_items
            ],
            "final_actions": final_actions[:8],
            "conflict_resolution": conflicts,
            "source_problem_list": list(twin.get("problem_list") or [])[:10],
        }

    async def get_full_context(self, patient_id: str) -> dict[str, Any] | None:
        patient_doc = await self._load_patient(patient_id)
        if not patient_doc:
            return None
        cached_plan = await self.db.col("score_records").find_one(
            {
                "patient_id": patient_id,
                "score_type": "clinical_reasoning_plan",
                "calc_time": {"$gte": datetime.now() - timedelta(minutes=self._digital_twin_cache_minutes())},
                "digital_twin": {"$type": "object"},
            },
            sort=[("calc_time", -1)],
        )
        if isinstance(cached_plan, dict) and isinstance(cached_plan.get("digital_twin"), dict):
            return cached_plan["digital_twin"]
        return await self.reasoning_agent.build_digital_twin(patient_id, patient_doc)

    async def orchestrated_assessment(self, patient_id: str) -> dict[str, Any] | None:
        twin = await self.get_full_context(patient_id)
        if not twin:
            return None

        assessments: dict[str, dict[str, Any]] = {}
        for name, agent in self.agents.items():
            result = await agent(twin) if name == "pharmacy_agent" else agent(twin)
            assessments[name] = {
                "agent": result.agent,
                "domain": result.domain,
                "summary": result.summary,
                "concerns": result.concerns,
                "recommendations": result.recommendations,
                "priority": result.priority,
                "evidence": result.evidence,
            }

        conflicts = self.detect_conflicts(assessments)
        meta_plan = await self._meta_synthesize(twin=twin, assessments=assessments, conflicts=conflicts)

        result = {
            "patient_id": patient_id,
            "generated_at": datetime.now(),
            "assessments": assessments,
            "conflicts": conflicts,
            "meta_agent": meta_plan,
        }
        await self.db.col("score_records").insert_one(
            {
                "patient_id": patient_id,
                "score_type": "multi_agent_mdt_assessment",
                "summary": meta_plan.get("summary") or "",
                "result": result,
                "calc_time": datetime.now(),
                "updated_at": datetime.now(),
            }
        )
        return result
