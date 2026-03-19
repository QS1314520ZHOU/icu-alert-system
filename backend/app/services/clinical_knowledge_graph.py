"""Clinical knowledge graph + causal reasoning service."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId


@dataclass(frozen=True)
class EvidenceSpec:
    key: str
    label: str
    category: str
    positive_hint: str
    negative_hint: str


@dataclass(frozen=True)
class CauseNode:
    key: str
    label: str
    mechanism: str
    clinical_domain: str
    base_rate: float
    required_evidence: list[str]
    supportive_evidence: list[str]
    contraindicating_evidence: list[str]
    recommended_checks: list[str]
    initial_actions: list[str]
    rag_terms: list[str]


class ClinicalKnowledgeGraph:
    EVIDENCE_LIBRARY: dict[str, EvidenceSpec] = {
        "sepsis_signal": EvidenceSpec("sepsis_signal", "脓毒症相关信号", "alert", "近期存在 sepsis/qSOFA/SOFA/shock 相关预警", "近期未见明确脓毒症预警"),
        "shock_signal": EvidenceSpec("shock_signal", "休克/低灌注信号", "alert", "存在 shock/low perfusion/lactate 相关预警", "近期未见休克类预警"),
        "map_low": EvidenceSpec("map_low", "MAP < 65 mmHg", "vital", "平均动脉压偏低", "当前 MAP 未提示明显低灌注"),
        "sbp_low": EvidenceSpec("sbp_low", "SBP < 90 mmHg", "vital", "收缩压偏低", "当前 SBP 未明显降低"),
        "vasopressor_use": EvidenceSpec("vasopressor_use", "近期使用升压药", "drug", "近期存在去甲肾上腺素/血管加压素等暴露", "近期未见明确升压药暴露"),
        "tachycardia": EvidenceSpec("tachycardia", "HR >= 110 次/分", "vital", "心率增快", "心率未明显增快"),
        "perfusion_poor": EvidenceSpec("perfusion_poor", "末梢灌注/组织灌注差", "alert", "近期存在低灌注线索", "未见明确末梢灌注不良线索"),
        "lactate_high": EvidenceSpec("lactate_high", "乳酸升高", "lab", "乳酸高于正常范围", "乳酸未明显升高"),
        "lactate_very_high": EvidenceSpec("lactate_very_high", "乳酸 >= 4 mmol/L", "lab", "乳酸高度升高", "乳酸未达到重度升高"),
        "cr_high": EvidenceSpec("cr_high", "肌酐升高", "lab", "肌酐高于常见警戒阈值", "肌酐未明显升高"),
        "aki_alert": EvidenceSpec("aki_alert", "近期 AKI 预警", "alert", "近 72h 存在 AKI/KDIGO 相关预警", "近期未见 AKI 预警"),
        "drug_nephrotoxin": EvidenceSpec("drug_nephrotoxin", "肾毒性药物暴露", "drug", "近期存在万古霉素/造影剂/NSAIDs 等暴露", "近期未见明确肾毒性药物暴露"),
        "crrt_running": EvidenceSpec("crrt_running", "CRRT 场景", "therapy", "近期存在 CRRT 相关记录/诊断", "当前未见 CRRT 场景"),
        "hyperkalemia": EvidenceSpec("hyperkalemia", "高钾", "lab", "血钾升高", "血钾未明显升高"),
        "ddimer_high": EvidenceSpec("ddimer_high", "D-dimer 升高", "lab", "D-dimer 升高", "D-dimer 未明显升高"),
        "inr_high": EvidenceSpec("inr_high", "INR 升高", "lab", "INR 延长", "INR 未明显延长"),
        "platelet_low": EvidenceSpec("platelet_low", "血小板低", "lab", "血小板降低", "血小板未明显下降"),
        "platelet_drop_50pct": EvidenceSpec("platelet_drop_50pct", "血小板较基线下降 >= 50%", "trend", "血小板呈明显下降趋势", "未见血小板显著下降趋势"),
        "heparin_exposure": EvidenceSpec("heparin_exposure", "肝素暴露", "drug", "近期使用肝素或低分子肝素", "近期未见肝素暴露"),
        "heparin_exposure_5d": EvidenceSpec("heparin_exposure_5d", "肝素暴露时程匹配", "drug", "肝素暴露时间窗与 HIT 相符", "肝素暴露时间窗不典型"),
        "thrombosis_signal": EvidenceSpec("thrombosis_signal", "血栓/栓塞线索", "alert", "近期存在 DVT/PE/血栓相关线索", "近期未见明确血栓线索"),
        "drug_linezolid_or_vanco": EvidenceSpec("drug_linezolid_or_vanco", "利奈唑胺/万古霉素暴露", "drug", "近期存在骨髓抑制或 TDM 风险药物", "近期未见相关高风险抗感染药物"),
        "bleeding_signal": EvidenceSpec("bleeding_signal", "出血线索", "alert", "近期存在 bleeding/DIC/失血线索", "近期未见明确出血信号"),
        "hb_drop": EvidenceSpec("hb_drop", "Hb 下降", "trend", "近期 Hb 呈下降趋势", "Hb 未明显下降"),
        "spo2_low": EvidenceSpec("spo2_low", "SpO2 < 92%", "vital", "氧合下降", "当前 SpO2 尚可"),
        "resp_distress": EvidenceSpec("resp_distress", "呼吸频率增快/呼吸窘迫", "vital", "存在呼吸功增加证据", "未见明显呼吸窘迫"),
        "vent_support": EvidenceSpec("vent_support", "机械通气/高流量支持", "therapy", "当前存在高级呼吸支持", "当前未见高级呼吸支持"),
        "recent_transfusion": EvidenceSpec("recent_transfusion", "近期输血", "drug", "近期存在血制品或输血暴露", "近期未见输血记录"),
        "infection_signal": EvidenceSpec("infection_signal", "感染线索", "problem", "当前诊断或预警支持感染背景", "当前未见强感染背景"),
        "pe_signal": EvidenceSpec("pe_signal", "肺栓塞线索", "alert", "近期存在 PE/VTE 相关预警或诊断", "近期未见 PE 明确信号"),
        "wheeze_or_bronchospasm": EvidenceSpec("wheeze_or_bronchospasm", "支气管痉挛/气道阻力升高", "problem", "诊断或用药提示存在气道痉挛", "未见明确气道痉挛证据"),
        "bilirubin_high": EvidenceSpec("bilirubin_high", "胆红素升高", "lab", "总胆红素升高", "胆红素未明显升高"),
        "ast_alt_high": EvidenceSpec("ast_alt_high", "转氨酶升高", "lab", "肝细胞损伤指标升高", "转氨酶未明显升高"),
        "alp_or_ggt_high": EvidenceSpec("alp_or_ggt_high", "胆汁淤积指标升高", "lab", "ALP/GGT 升高", "未见明显胆汁淤积指标异常"),
        "tpn_running": EvidenceSpec("tpn_running", "TPN/静脉营养暴露", "drug", "近期存在 TPN/脂肪乳等支持", "近期未见明确 TPN 暴露"),
        "coagulopathy_signal": EvidenceSpec("coagulopathy_signal", "凝血功能障碍信号", "lab", "存在 INR/APTT/纤维蛋白原异常", "未见明确凝血功能障碍"),
    }

    FINDING_ALIASES: dict[str, str] = {
        "乳酸升高": "lactate_rise",
        "lactate": "lactate_rise",
        "lactate_rise": "lactate_rise",
        "高乳酸": "lactate_rise",
        "肌酐升高": "creatinine_rise",
        "cr": "creatinine_rise",
        "creatinine": "creatinine_rise",
        "creatinine_rise": "creatinine_rise",
        "低氧": "hypoxemia",
        "氧合下降": "hypoxemia",
        "hypoxemia": "hypoxemia",
        "spo2低": "hypoxemia",
        "低血压": "hypotension",
        "血压低": "hypotension",
        "hypotension": "hypotension",
        "血小板下降": "platelet_drop",
        "platelet": "platelet_drop",
        "plt": "platelet_drop",
        "platelet_drop": "platelet_drop",
        "胆红素升高": "bilirubin_rise",
        "bilirubin": "bilirubin_rise",
        "tbil": "bilirubin_rise",
        "bilirubin_rise": "bilirubin_rise",
        "凝血异常": "coagulopathy",
        "inr升高": "coagulopathy",
        "coagulopathy": "coagulopathy",
    }

    def __init__(self, *, db, config, alert_engine, rag_service=None) -> None:
        self.db = db
        self.config = config
        self.alert_engine = alert_engine
        self.rag_service = rag_service

    def _cfg(self) -> dict[str, Any]:
        cfg = (self.config.yaml_cfg or {}).get("ai_service", {}).get("knowledge_graph", {})
        return cfg if isinstance(cfg, dict) else {}

    def _cause_map(self) -> dict[str, list[CauseNode]]:
        return {
            "lactate_rise": [
                CauseNode("septic_shock", "脓毒性低灌注", "感染导致炎症级联与循环灌注不足，乳酸升高往往伴随脓毒症/休克线索。", "hemodynamic", 0.28, ["sepsis_signal", "map_low"], ["lactate_high", "vasopressor_use", "infection_signal"], [], ["复查乳酸清除与尿量", "评估感染灶控制与补液/升压目标", "必要时完善培养与再评估抗感染覆盖"], ["床旁复核灌注目标", "联动感染源控制"], ["sepsis", "shock", "lactate"]),
                CauseNode("hemorrhagic_hypovolemia", "失血/容量不足", "前负荷不足可导致乳酸升高，常伴低血压、Hb 下降或出血线索。", "hemodynamic", 0.16, ["map_low"], ["hb_drop", "tachycardia", "bleeding_signal"], [], ["复核 Hb 动态与可见/隐匿出血", "评估容量反应性和液体/输血指征"], ["优先排查失血与容量不足"], ["hemorrhage", "shock", "transfusion"]),
                CauseNode("vasopressor_or_low_flow", "药物/低流量灌注状态", "升压药升级或心排量不足时可出现灌注不足与乳酸升高。", "hemodynamic", 0.1, ["vasopressor_use"], ["perfusion_poor", "map_low", "lactate_high"], [], ["复核 MAP 目标与升压药剂量", "结合尿量、末梢灌注和超声评估低流量状态"], ["避免仅依赖 MAP 掩盖低流量"], ["vasopressor", "perfusion"]),
                CauseNode("mesenteric_or_occult_ischemia", "组织缺血/隐匿缺血", "重度乳酸升高而感染/失血证据不充分时，需警惕肠系膜或其他组织缺血。", "hemodynamic", 0.07, ["lactate_very_high"], ["shock_signal", "tachycardia"], ["infection_signal"], ["结合腹痛/腹胀/影像复核缺血可能", "必要时升级 CTA/外科会诊"], ["针对隐匿缺血做床旁再评估"], ["ischemia", "lactate"]),
            ],
            "creatinine_rise": [
                CauseNode("sepsis_aki", "脓毒症相关 AKI", "感染与低灌注背景下肾前性与炎症性损伤常共同推动肌酐升高。", "renal", 0.26, ["cr_high"], ["sepsis_signal", "map_low", "aki_alert"], [], ["复核感染控制、容量状态与血流动力学", "动态追踪肌酐、尿量与乳酸"], ["优先识别可逆性肾灌注因素"], ["aki", "sepsis", "renal"]),
                CauseNode("drug_induced_aki", "药物/造影剂相关肾损伤", "肾毒性暴露可直接推动肌酐升高，尤其在高龄、感染或休克背景下。", "renal", 0.18, ["drug_nephrotoxin"], ["cr_high", "aki_alert"], [], ["核对万古霉素/造影剂/NSAIDs 暴露", "尽快完成剂量调整或替代方案评估"], ["停评可疑肾毒性暴露"], ["aki", "contrast", "vancomycin"]),
                CauseNode("pre_renal_hypoperfusion", "肾前性低灌注", "低血压、休克、容量不足可导致肾前性损伤并快速拉高肌酐。", "renal", 0.2, ["map_low"], ["sbp_low", "tachycardia", "cr_high"], [], ["联合尿量、液体平衡和床旁超声复核容量反应性", "避免持续肾灌注不足"], ["优先恢复肾灌注"], ["renal perfusion", "aki", "shock"]),
                CauseNode("crrt_or_advanced_renal_failure", "CRRT 依赖/进展性肾衰竭", "已进入 CRRT 场景或伴高钾、严重 AKI 预警时，更提示进展性肾衰竭。", "renal", 0.12, ["crrt_running"], ["aki_alert", "hyperkalemia", "cr_high"], [], ["复核 CRRT 适应证、通路与处方目标", "评估电解质与容量控制是否达标"], ["确认肾脏支持治疗目标"], ["crrt", "aki", "electrolyte"]),
            ],
            "hypoxemia": [
                CauseNode("ards_progression", "ARDS/呼吸衰竭进展", "低氧合伴呼吸窘迫和高级呼吸支持时，最常见为肺实变或 ARDS 进展。", "respiratory", 0.24, ["spo2_low", "resp_distress"], ["vent_support", "infection_signal"], [], ["复核氧疗/通气参数", "必要时复查血气、胸片或肺超声"], ["及时再评估氧合策略"], ["ards", "hypoxemia", "ventilator"]),
                CauseNode("pe_or_embolism", "肺栓塞/急性栓塞事件", "低氧合伴呼吸窘迫、心率增快和 D-dimer 升高时需警惕栓塞事件。", "respiratory", 0.1, ["resp_distress"], ["ddimer_high", "tachycardia", "pe_signal"], [], ["评估 Wells/影像学指征", "结合循环状态复核是否需 CTA 或超声"], ["将栓塞纳入高优先级鉴别"], ["pulmonary embolism", "hypoxemia"]),
                CauseNode("transfusion_lung_injury_or_overload", "输血相关肺损伤/容量负荷", "近期输血后出现低氧合，应考虑 TRALI/TACO 或容量负荷相关问题。", "respiratory", 0.08, ["recent_transfusion"], ["spo2_low", "resp_distress"], [], ["核对近期输血时序", "评估容量状态、BNP 与影像变化"], ["复盘输血后氧合变化"], ["transfusion", "trali", "taco"]),
                CauseNode("bronchospasm_or_airway_obstruction", "支气管痉挛/气道阻力升高", "气道阻力上升或支气管痉挛可导致低氧与呼吸功增加。", "respiratory", 0.09, ["resp_distress"], ["wheeze_or_bronchospasm", "spo2_low"], [], ["复核雾化、支气管舒张剂和痰液清除策略", "评估是否存在气道阻塞或分泌物潴留"], ["先排查可逆气道因素"], ["bronchospasm", "airway obstruction"]),
            ],
            "hypotension": [
                CauseNode("septic_vasoplegia", "感染性血管扩张/脓毒性休克", "感染背景下低血压伴升压药需求，首先考虑脓毒性血管扩张与灌注不足。", "hemodynamic", 0.25, ["map_low"], ["sepsis_signal", "vasopressor_use", "lactate_high"], [], ["复核感染源控制、补液反应与升压目标", "动态追踪乳酸与末梢灌注"], ["优先按休克路径复评"], ["sepsis", "shock", "hypotension"]),
                CauseNode("hypovolemia", "容量不足", "容量丢失或第三间隙转移可直接造成低血压和器官灌注下降。", "hemodynamic", 0.18, ["sbp_low"], ["tachycardia", "hb_drop", "perfusion_poor"], [], ["评估液体反应性、尿量、出入量与失血线索", "结合超声复核前负荷"], ["先辨别是否需要补液/止血"], ["hypovolemia", "shock"]),
                CauseNode("obstructive_or_pe", "阻塞性休克/肺栓塞", "低血压合并呼吸负担或栓塞证据时，应提升阻塞性休克权重。", "hemodynamic", 0.08, ["sbp_low"], ["pe_signal", "ddimer_high", "resp_distress"], [], ["结合超声、D-dimer 与 CTA 指征评估阻塞性病因"], ["尽快完成床旁超声筛查"], ["obstructive shock", "pulmonary embolism"]),
                CauseNode("drug_related_vasodilation", "药物相关血管扩张/镇静相关低血压", "镇静镇痛或血管活性药调整后可出现药物相关低血压。", "hemodynamic", 0.1, ["sbp_low"], ["vasopressor_use"], ["lactate_very_high"], ["回顾镇静、镇痛和血管活性药调整时间点", "区分药物效应与真实循环恶化"], ["避免把药物性低压误判为纯感染性休克"], ["sedation", "vasodilation", "hypotension"]),
            ],
            "platelet_drop": [
                CauseNode("dic", "DIC/消耗性凝血障碍", "血小板下降并伴 D-dimer、INR 异常时，首先考虑 DIC 或凝血消耗。", "hematology", 0.18, ["ddimer_high", "inr_high"], ["sepsis_signal", "platelet_low", "bleeding_signal"], [], ["复查 PT/INR、纤维蛋白原和 D-dimer", "评估是否存在脓毒症或活动性出血"], ["把 DIC 纳入高优先级排查"], ["dic", "coagulopathy", "thrombocytopenia"]),
                CauseNode("hit", "HIT", "肝素暴露后血小板快速下降并伴血栓线索时，应高度警惕 HIT。", "hematology", 0.12, ["heparin_exposure_5d"], ["platelet_drop_50pct", "thrombosis_signal", "platelet_low"], ["inr_high"], ["计算 4T 评分", "复核 PF4 抗体/功能试验", "评估是否需停用肝素并替代抗凝"], ["先做 4T 快速分层"], ["hit", "heparin", "thrombocytopenia"]),
                CauseNode("drug_induced_thrombocytopenia", "药物相关血小板减少", "利奈唑胺、万古霉素等药物暴露时，药物性骨髓抑制需同步考虑。", "hematology", 0.16, ["drug_linezolid_or_vanco"], ["platelet_low", "platelet_drop_50pct"], [], ["复核利奈唑胺/万古霉素等暴露", "评估停药、减量或替代方案"], ["尽快回顾高风险药物时间窗"], ["drug-induced thrombocytopenia", "linezolid", "vancomycin"]),
                CauseNode("sepsis_consumption", "脓毒症相关消耗", "感染、炎症和微循环损伤常导致血小板消耗性下降。", "hematology", 0.22, ["sepsis_signal"], ["platelet_low", "lactate_high"], [], ["复核感染灶、培养结果与器官功能变化", "动态追踪乳酸和血小板趋势"], ["把感染控制与凝血监测并行推进"], ["sepsis", "platelet", "coagulopathy"]),
                CauseNode("crrt_consumption", "CRRT/滤器消耗", "CRRT 运行过程中的滤器消耗与抗凝方案可加重血小板下降。", "hematology", 0.08, ["crrt_running"], ["platelet_low", "heparin_exposure"], [], ["核对 CRRT 运行时长与滤器更换频率", "复核抗凝策略与出血风险"], ["结合 CRRT 场景重估血小板下降"], ["crrt", "platelet", "filter clotting"]),
            ],
            "bilirubin_rise": [
                CauseNode("sepsis_cholestasis", "脓毒症相关胆汁淤积", "感染重症状态下常出现胆红素升高和胆汁淤积样改变。", "hepatic", 0.18, ["bilirubin_high"], ["infection_signal", "sepsis_signal"], [], ["追踪胆红素、感染控制与器官功能", "结合血流动力学和肝胆影像排查可逆因素"], ["先区分感染性胆汁淤积与机械性梗阻"], ["liver", "cholestasis", "sepsis"]),
                CauseNode("ischemic_hepatopathy", "缺血性肝损伤", "休克或低灌注背景下肝细胞缺血可导致胆红素与转氨酶同步上升。", "hepatic", 0.12, ["bilirubin_high"], ["ast_alt_high", "map_low", "shock_signal"], [], ["复盘低血压/低灌注时程", "联动 AST/ALT、乳酸和循环复苏效果评估"], ["把缺血性损伤纳入时序分析"], ["ischemic hepatitis", "shock liver"]),
                CauseNode("obstructive_cholestasis", "机械性胆汁淤积/胆道梗阻", "胆红素升高伴 ALP/GGT 异常时，需关注机械性胆道问题。", "hepatic", 0.13, ["bilirubin_high"], ["alp_or_ggt_high"], [], ["完善肝胆超声或 CT", "结合腹痛、感染与胆道病史排查梗阻"], ["尽快补齐肝胆影像"], ["cholestasis", "biliary obstruction"]),
                CauseNode("tpn_or_drug_related_cholestasis", "TPN/药物相关胆汁淤积", "长期静脉营养或药物暴露可引起非梗阻性胆汁淤积。", "hepatic", 0.09, ["bilirubin_high"], ["tpn_running", "alp_or_ggt_high"], [], ["核对静脉营养时长与药物暴露", "评估是否需调整营养或可疑药物"], ["回顾静脉营养与药物时间窗"], ["tpn", "drug cholestasis"]),
            ],
            "coagulopathy": [
                CauseNode("dic_progression", "DIC 进展", "INR 延长、D-dimer 升高并伴脓毒症或出血时，需优先考虑 DIC。", "hematology", 0.2, ["inr_high"], ["ddimer_high", "sepsis_signal", "platelet_low"], [], ["复查凝血全套和纤维蛋白原", "评估是否存在脓毒症、失血和器官功能恶化"], ["以 DIC 路径做紧急分层"], ["dic", "coagulopathy"]),
                CauseNode("hepatic_synthetic_failure", "肝合成功能障碍", "胆红素升高或肝损伤背景下出现 INR 延长，需考虑肝源性凝血障碍。", "hepatic", 0.14, ["inr_high"], ["bilirubin_high", "ast_alt_high"], [], ["联动肝功能、INR 和影像评估肝源性因素", "复核肝毒性药物和休克时程"], ["同步评估肝脏与凝血"], ["liver failure", "coagulopathy"]),
                CauseNode("anticoagulant_effect", "抗凝药物效应", "存在肝素或其他抗凝暴露时，INR/APTT 异常需与药物效应区分。", "hematology", 0.12, ["inr_high"], ["heparin_exposure", "bleeding_signal"], ["ddimer_high"], ["核对抗凝药种类、剂量与最近给药时间", "必要时复查 APTT/抗 Xa/凝血酶时间"], ["先排除可解释的药物效应"], ["anticoagulation", "inr"]),
            ],
        }

    def _finding_labels(self) -> dict[str, str]:
        return {
            "lactate_rise": "乳酸升高",
            "creatinine_rise": "肌酐升高",
            "hypoxemia": "低氧",
            "hypotension": "低血压",
            "platelet_drop": "血小板下降",
            "bilirubin_rise": "胆红素升高",
            "coagulopathy": "凝血异常",
        }

    async def _load_patient(self, patient_id: str) -> dict[str, Any] | None:
        try:
            return await self.db.col("patient").find_one({"_id": ObjectId(patient_id)})
        except Exception:
            return None

    def _safe_float(self, value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except Exception:
            return None

    def _lab_value(self, labs: dict[str, Any], key: str) -> float | None:
        item = labs.get(key)
        if isinstance(item, dict):
            return self._safe_float(item.get("value"))
        return self._safe_float(item)

    def _has_alert(self, alerts: list[dict[str, Any]], keywords: list[str]) -> bool:
        for row in alerts:
            blob = " ".join(str(row.get(k) or "") for k in ("alert_type", "rule_id", "name", "category")).lower()
            if any(keyword in blob for keyword in keywords):
                return True
        return False

    def _drug_blob(self, drugs: list[dict[str, Any]]) -> str:
        return " ".join(self.alert_engine._drug_text(doc) for doc in drugs).lower()

    def _patient_blob(self, patient_doc: dict[str, Any]) -> str:
        return " ".join(
            str(patient_doc.get(key) or "")
            for key in ("clinicalDiagnosis", "admissionDiagnosis", "nursingLevel", "admissionType", "admissionPlan", "dept", "hisDept", "pastHistory")
        ).lower()

    def _trend_drop(self, rows: list[dict[str, Any]], threshold: float) -> bool:
        if len(rows) < 2:
            return False
        start = self._safe_float(rows[0].get("value"))
        end = self._safe_float(rows[-1].get("value"))
        if start is None or end is None:
            return False
        return end <= start - threshold

    def _trend_drop_ratio(self, rows: list[dict[str, Any]], ratio: float) -> bool:
        if len(rows) < 2:
            return False
        start = self._safe_float(rows[0].get("value"))
        end = self._safe_float(rows[-1].get("value"))
        if start is None or end is None or start <= 0:
            return False
        return end < start * ratio

    async def _patient_context(self, patient_id: str) -> dict[str, Any] | None:
        patient_doc = await self._load_patient(patient_id)
        if not patient_doc:
            return None
        pid = patient_doc.get("_id")
        his_pid = patient_doc.get("hisPid")
        facts = await self.alert_engine._collect_patient_facts(patient_doc, pid) if hasattr(self.alert_engine, "_collect_patient_facts") else {}
        labs = facts.get("labs") if isinstance(facts.get("labs"), dict) else {}
        vitals = facts.get("vitals") if isinstance(facts.get("vitals"), dict) else {}
        recent_alerts = await self.alert_engine._recent_alerts(patient_id, datetime.now() - timedelta(hours=72), max_records=80) if hasattr(self.alert_engine, "_recent_alerts") else []
        drugs = await self.alert_engine._get_recent_drug_docs_window(pid, hours=120, limit=400)
        plt_series = await self.alert_engine._get_lab_series(his_pid, "plt", datetime.now() - timedelta(days=7), limit=80) if his_pid else []
        hb_series = await self.alert_engine._get_lab_series(his_pid, "hb", datetime.now() - timedelta(days=3), limit=60) if his_pid else []
        cr_series = await self.alert_engine._get_lab_series(his_pid, "cr", datetime.now() - timedelta(days=3), limit=60) if his_pid else []
        tbil_series = await self.alert_engine._get_lab_series(his_pid, "tbil", datetime.now() - timedelta(days=5), limit=60) if his_pid else []
        return {
            "patient": patient_doc,
            "facts": facts,
            "labs": labs,
            "vitals": vitals,
            "recent_alerts": recent_alerts,
            "drugs": drugs,
            "plt_series": plt_series,
            "hb_series": hb_series,
            "cr_series": cr_series,
            "tbil_series": tbil_series,
        }

    def get_supporting_evidence(self, context: dict[str, Any], cause: CauseNode) -> dict[str, bool]:
        labs = context.get("labs") if isinstance(context.get("labs"), dict) else {}
        alerts = context.get("recent_alerts") if isinstance(context.get("recent_alerts"), list) else []
        drugs = context.get("drugs") if isinstance(context.get("drugs"), list) else []
        vitals = context.get("vitals") if isinstance(context.get("vitals"), dict) else {}
        patient_doc = context.get("patient") if isinstance(context.get("patient"), dict) else {}
        plt_series = context.get("plt_series") if isinstance(context.get("plt_series"), list) else []
        hb_series = context.get("hb_series") if isinstance(context.get("hb_series"), list) else []
        drug_blob = self._drug_blob(drugs)
        patient_blob = self._patient_blob(patient_doc)

        map_value = self._safe_float(vitals.get("map"))
        sbp = self._safe_float(vitals.get("sbp"))
        hr = self._safe_float(vitals.get("hr"))
        rr = self._safe_float(vitals.get("rr"))
        spo2 = self._safe_float(vitals.get("spo2"))
        lactate = self._lab_value(labs, "lac") or self._lab_value(labs, "lactate")
        cr = self._lab_value(labs, "cr")
        ddimer = self._lab_value(labs, "ddimer")
        inr = self._lab_value(labs, "inr")
        plt = self._lab_value(labs, "plt")
        k = self._lab_value(labs, "k")
        bilirubin = self._lab_value(labs, "tbil") or self._lab_value(labs, "bilirubin")
        ast = self._lab_value(labs, "ast")
        alt = self._lab_value(labs, "alt")
        alp = self._lab_value(labs, "alp")
        ggt = self._lab_value(labs, "ggt")

        evidence = {
            "sepsis_signal": self._has_alert(alerts, ["sepsis", "qsofa", "sofa", "septic_shock", "shock"]),
            "shock_signal": self._has_alert(alerts, ["shock", "low_perfusion", "lactate"]),
            "map_low": map_value is not None and map_value < 65,
            "sbp_low": sbp is not None and sbp < 90,
            "vasopressor_use": any(token in drug_blob for token in ["去甲", "norepinephrine", "血管加压素", "vasopressin", "肾上腺素", "epinephrine", "多巴胺", "dobutamine"]),
            "tachycardia": hr is not None and hr >= 110,
            "perfusion_poor": self._has_alert(alerts, ["low_perfusion", "shock", "lactate"]) or "灌注" in patient_blob,
            "lactate_high": lactate is not None and lactate >= 2.0,
            "lactate_very_high": lactate is not None and lactate >= 4.0,
            "cr_high": cr is not None and cr >= 133,
            "aki_alert": self._has_alert(alerts, ["aki", "kdigo", "renal"]),
            "drug_nephrotoxin": any(token in drug_blob for token in ["万古霉素", "vancomycin", "造影", "contrast", "布洛芬", "双氯芬酸", "amikacin", "庆大霉素"]),
            "crrt_running": self._has_alert(alerts, ["crrt"]) or "crrt" in patient_blob or "血滤" in patient_blob,
            "hyperkalemia": k is not None and k >= 5.5,
            "ddimer_high": ddimer is not None and ddimer > 2.0,
            "inr_high": inr is not None and inr >= 1.5,
            "platelet_low": plt is not None and plt < 100,
            "platelet_drop_50pct": self._trend_drop_ratio(plt_series, 0.5),
            "heparin_exposure": ("肝素" in drug_blob or "heparin" in drug_blob or "低分子" in drug_blob),
            "heparin_exposure_5d": ("肝素" in drug_blob or "heparin" in drug_blob or "低分子" in drug_blob),
            "thrombosis_signal": self._has_alert(alerts, ["thrombosis", "pe_", "dvt", "vte", "embolism"]),
            "drug_linezolid_or_vanco": any(token in drug_blob for token in ["利奈唑胺", "linezolid", "万古霉素", "vancomycin"]),
            "bleeding_signal": self._has_alert(alerts, ["bleeding", "dic", "hemorrhage"]) or ("出血" in patient_blob),
            "hb_drop": self._trend_drop(hb_series, 20.0),
            "spo2_low": spo2 is not None and spo2 < 92,
            "resp_distress": rr is not None and rr >= 28,
            "vent_support": self._has_alert(alerts, ["ventilator", "weaning", "ards"]) or any(token in patient_blob for token in ["机械通气", "呼吸机", "高流量"]),
            "recent_transfusion": any(token in drug_blob for token in ["输血", "血浆", "红细胞", "platelet", "transfusion", "冷沉淀"]),
            "infection_signal": any(token in patient_blob for token in ["感染", "肺炎", "sepsis", "脓毒", "休克"]) or self._has_alert(alerts, ["sepsis", "infection"]),
            "pe_signal": self._has_alert(alerts, ["pe_", "vte", "dvt", "embolism"]) or any(token in patient_blob for token in ["肺栓塞", "静脉血栓"]),
            "wheeze_or_bronchospasm": any(token in patient_blob for token in ["哮喘", "支气管痉挛", "慢阻肺", "copd"]) or any(token in drug_blob for token in ["沙丁胺醇", "异丙托溴铵"]),
            "bilirubin_high": bilirubin is not None and bilirubin >= 34,
            "ast_alt_high": (ast is not None and ast >= 80) or (alt is not None and alt >= 80),
            "alp_or_ggt_high": (alp is not None and alp >= 180) or (ggt is not None and ggt >= 100),
            "tpn_running": any(token in drug_blob for token in ["tpn", "肠外营养", "脂肪乳", "氨基酸注射液"]),
            "coagulopathy_signal": (inr is not None and inr >= 1.5) or self._has_alert(alerts, ["dic", "coagul"]),
        }
        target_keys = set(cause.required_evidence + cause.supportive_evidence + cause.contraindicating_evidence)
        return {key: bool(evidence.get(key)) for key in target_keys}

    def bayesian_update(
        self,
        *,
        prior: float,
        evidence: dict[str, bool],
        required: list[str],
        supportive: list[str],
        contraindicating: list[str],
    ) -> float:
        prior = max(0.001, min(0.999, float(prior)))
        likelihood_ratio = 1.0
        for key in required:
            likelihood_ratio *= 4.4 if evidence.get(key) else 0.2
        for key in supportive:
            likelihood_ratio *= 1.8 if evidence.get(key) else 0.84
        for key in contraindicating:
            likelihood_ratio *= 0.42 if evidence.get(key) else 1.0
        posterior = (prior * likelihood_ratio) / ((prior * likelihood_ratio) + (1 - prior))
        return round(max(0.001, min(0.999, posterior)), 4)

    def _normalize_finding(self, abnormal_finding: str) -> str:
        raw = str(abnormal_finding or "").strip()
        lower = raw.lower()
        if lower in self.FINDING_ALIASES:
            return self.FINDING_ALIASES[lower]
        if raw in self.FINDING_ALIASES:
            return self.FINDING_ALIASES[raw]
        for alias, key in self.FINDING_ALIASES.items():
            if alias and alias in lower:
                return key
        return lower or "unknown"

    def _finding_label(self, finding_key: str, abnormal_finding: str) -> str:
        return self._finding_labels().get(finding_key) or str(abnormal_finding or finding_key)

    def _pathway_steps(self, finding_label: str, cause: CauseNode, evidence_labels: list[str]) -> list[str]:
        steps = [f"异常入口: {finding_label}"]
        if evidence_labels:
            steps.append(f"关键证据: {' / '.join(evidence_labels[:3])}")
        steps.append(f"病理机制: {cause.mechanism}")
        steps.append(f"候选病因: {cause.label}")
        return steps

    def _recommendation_union(self, rows: list[dict[str, Any]], key: str, limit: int) -> list[str]:
        seen: list[str] = []
        for row in rows:
            for item in row.get(key) or []:
                text = str(item or "").strip()
                if text and text not in seen:
                    seen.append(text)
        return seen[:limit]

    def _context_summary(self, context: dict[str, Any], finding_label: str) -> dict[str, Any]:
        patient = context.get("patient") if isinstance(context.get("patient"), dict) else {}
        vitals = context.get("vitals") if isinstance(context.get("vitals"), dict) else {}
        labs = context.get("labs") if isinstance(context.get("labs"), dict) else {}
        alerts = context.get("recent_alerts") if isinstance(context.get("recent_alerts"), list) else []
        summary_bits = [
            str(patient.get("clinicalDiagnosis") or patient.get("admissionDiagnosis") or "").strip(),
            f"MAP {vitals.get('map')}" if vitals.get("map") is not None else "",
            f"SpO2 {vitals.get('spo2')}" if vitals.get("spo2") is not None else "",
            f"乳酸 {self._lab_value(labs, 'lac') or self._lab_value(labs, 'lactate')}" if (self._lab_value(labs, "lac") or self._lab_value(labs, "lactate")) is not None else "",
            f"肌酐 {self._lab_value(labs, 'cr')}" if self._lab_value(labs, "cr") is not None else "",
        ]
        return {
            "patient_name": patient.get("name") or "未知患者",
            "bed": patient.get("hisBed") or patient.get("bed"),
            "dept": patient.get("dept") or patient.get("hisDept"),
            "finding_label": finding_label,
            "summary": "；".join(bit for bit in summary_bits if bit) or f"围绕 {finding_label} 做候选病因排序",
            "recent_alert_count": len(alerts),
        }

    def _guideline_query(self, finding_label: str, cause_rows: list[dict[str, Any]]) -> str:
        top_terms = []
        for row in cause_rows[:3]:
            top_terms.extend(row.get("rag_terms") or [])
        text = " ".join(dict.fromkeys([finding_label, *top_terms]))
        return text.strip()

    def _search_guidelines(self, finding_label: str, cause_rows: list[dict[str, Any]], patient_doc: dict[str, Any], facts: dict[str, Any]) -> list[dict[str, Any]]:
        if self.rag_service is None:
            return []
        query = self._guideline_query(finding_label, cause_rows)
        if not query:
            return []
        top_k = max(3, int(self._cfg().get("rag_top_k", 6) or 6))
        tags: list[str] = []
        if hasattr(self.alert_engine, "_infer_rag_tags"):
            try:
                tags = list(self.alert_engine._infer_rag_tags(patient_doc, facts))
            except Exception:
                tags = []
        try:
            hits = self.rag_service.search(query, top_k=top_k, tags=tags or None)
        except Exception:
            return []
        normalized = []
        for item in hits[:top_k]:
            normalized.append(
                {
                    "chunk_id": str(item.get("chunk_id") or ""),
                    "source": str(item.get("source") or ""),
                    "recommendation": str(item.get("recommendation") or ""),
                    "recommendation_grade": str(item.get("recommendation_grade") or ""),
                    "topic": str(item.get("topic") or ""),
                    "quote": str(item.get("content") or "")[:220],
                    "score": item.get("score"),
                }
            )
        return normalized

    def _evidence_profile(self, cause_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        keys = []
        for row in cause_rows[:5]:
            keys.extend(row.get("required_evidence") or [])
            keys.extend(row.get("supportive_evidence") or [])
            keys.extend(row.get("contraindicating_evidence") or [])
        unique_keys = list(dict.fromkeys(str(key) for key in keys if str(key)))
        profile: list[dict[str, Any]] = []
        for key in unique_keys:
            spec = self.EVIDENCE_LIBRARY.get(key)
            present = bool(any(key in (row.get("matched_evidence_keys") or []) for row in cause_rows))
            profile.append(
                {
                    "key": key,
                    "label": spec.label if spec else key,
                    "category": spec.category if spec else "derived",
                    "present": present,
                    "summary": (spec.positive_hint if present else spec.negative_hint) if spec else ("命中" if present else "未命中"),
                }
            )
        return profile

    async def _load_recent_cached_result(self, patient_id: str, finding_key: str) -> dict[str, Any] | None:
        window_minutes = max(5, int(self._cfg().get("persist_window_minutes", 60) or 60))
        since = datetime.now() - timedelta(minutes=window_minutes)
        doc = await self.db.col("score_records").find_one(
            {
                "patient_id": patient_id,
                "score_type": "knowledge_graph_causal_analysis",
                "finding_key": finding_key,
                "calc_time": {"$gte": since},
            },
            sort=[("calc_time", -1)],
        )
        if not doc:
            return None
        result = doc.get("result")
        return result if isinstance(result, dict) else None

    async def _persist_result(self, patient_id: str, finding_key: str, abnormal_finding: str, result: dict[str, Any]) -> None:
        now = datetime.now()
        await self.db.col("score_records").insert_one(
            {
                "patient_id": patient_id,
                "score_type": "knowledge_graph_causal_analysis",
                "finding_key": finding_key,
                "summary": f"{abnormal_finding} 的主要候选因果链已完成排序",
                "result": result,
                "calc_time": now,
                "updated_at": now,
            }
        )

    def _rank_causes(self, finding_label: str, context: dict[str, Any], causes: list[CauseNode]) -> list[dict[str, Any]]:
        ranked: list[dict[str, Any]] = []
        for cause in causes:
            evidence = self.get_supporting_evidence(context, cause)
            posterior = self.bayesian_update(
                prior=cause.base_rate,
                evidence=evidence,
                required=cause.required_evidence,
                supportive=cause.supportive_evidence,
                contraindicating=cause.contraindicating_evidence,
            )
            matched_keys = [key for key, value in evidence.items() if value]
            missing_keys = [key for key, value in evidence.items() if not value]
            matched_labels = [self.EVIDENCE_LIBRARY.get(key).label if self.EVIDENCE_LIBRARY.get(key) else key for key in matched_keys]
            missing_labels = [self.EVIDENCE_LIBRARY.get(key).label if self.EVIDENCE_LIBRARY.get(key) else key for key in missing_keys]
            ranked.append(
                {
                    "cause_key": cause.key,
                    "label": cause.label,
                    "mechanism": cause.mechanism,
                    "clinical_domain": cause.clinical_domain,
                    "prior": cause.base_rate,
                    "posterior": posterior,
                    "required_evidence": cause.required_evidence,
                    "supportive_evidence": cause.supportive_evidence,
                    "contraindicating_evidence": cause.contraindicating_evidence,
                    "matched_evidence": matched_labels,
                    "matched_evidence_keys": matched_keys,
                    "missing_evidence": missing_labels,
                    "recommended_checks": cause.recommended_checks,
                    "initial_actions": cause.initial_actions,
                    "rag_terms": cause.rag_terms,
                    "pathway_steps": self._pathway_steps(finding_label, cause, matched_labels),
                    "confidence_level": "high" if posterior >= 0.75 else ("medium" if posterior >= 0.45 else "low"),
                }
            )
        ranked.sort(key=lambda item: float(item.get("posterior") or 0), reverse=True)
        return ranked

    async def causal_chain_analysis(self, patient_id: str, abnormal_finding: str) -> dict[str, Any] | None:
        finding_key = self._normalize_finding(abnormal_finding)
        causes = self._cause_map().get(finding_key, [])
        if not causes:
            return {
                "patient_id": patient_id,
                "abnormal_finding": abnormal_finding,
                "finding_key": finding_key,
                "generated_at": datetime.now(),
                "candidate_causes": [],
                "context_summary": {"summary": f"当前知识图谱尚未覆盖 {abnormal_finding} 的因果模板"},
                "top_recommendations": [],
                "suggested_next_actions": [],
                "guideline_evidence": [],
                "graph_version": "kg-v2",
            }

        cached = await self._load_recent_cached_result(patient_id, finding_key)
        if cached:
            return cached

        context = await self._patient_context(patient_id)
        if context is None:
            return None

        finding_label = self._finding_label(finding_key, abnormal_finding)
        ranked = self._rank_causes(finding_label, context, causes)
        top_rows = ranked[:4]
        guideline_evidence = self._search_guidelines(
            finding_label,
            top_rows,
            context.get("patient") if isinstance(context.get("patient"), dict) else {},
            context.get("facts") if isinstance(context.get("facts"), dict) else {},
        )
        if guideline_evidence:
            chunk_ids = [str(item.get("chunk_id") or "") for item in guideline_evidence if item.get("chunk_id")]
            for row in top_rows:
                row["guideline_refs"] = chunk_ids[:3]

        result = {
            "patient_id": patient_id,
            "abnormal_finding": abnormal_finding,
            "finding_key": finding_key,
            "finding_label": finding_label,
            "generated_at": datetime.now(),
            "graph_version": "kg-v2",
            "context_summary": self._context_summary(context, finding_label),
            "candidate_causes": top_rows,
            "top_recommendations": self._recommendation_union(top_rows, "recommended_checks", 8),
            "suggested_next_actions": self._recommendation_union(top_rows, "initial_actions", 6),
            "evidence_profile": self._evidence_profile(top_rows),
            "guideline_evidence": guideline_evidence,
        }
        await self._persist_result(patient_id, finding_key, abnormal_finding, result)
        return result

    def _intervention_map(self) -> dict[str, dict[str, Any]]:
        return {
            "norepinephrine_high_dose": {
                "label": "开始/升级大剂量去甲肾上腺素",
                "expected_effects": [{"item": "MAP", "direction": "up", "window": "30min内"}],
                "monitoring": ["MAP", "HR", "乳酸", "末梢灌注", "尿量"],
                "risks": ["心律失常", "肢端缺血", "灌注不足被掩盖"],
                "interactions": ["与血管加压素存在协同", "需警惕同时使用正性肌力药的节律影响"],
            },
            "fluid_bolus": {
                "label": "快速补液",
                "expected_effects": [{"item": "MAP", "direction": "up", "window": "15-60min内"}, {"item": "乳酸", "direction": "down", "window": "2-6h"}],
                "monitoring": ["MAP", "肺部氧合", "尿量", "乳酸", "液体平衡"],
                "risks": ["液体过负荷", "肺水肿", "右心负荷增加"],
                "interactions": ["与去甲肾上腺素联用时需同步评估容量反应性"],
            },
            "broad_spectrum_antibiotics": {
                "label": "启动/升级广谱抗感染",
                "expected_effects": [{"item": "感染负荷", "direction": "down", "window": "24-72h"}, {"item": "乳酸", "direction": "down", "window": "6-24h"}],
                "monitoring": ["体温", "WBC/PCT", "乳酸", "培养结果", "肾功能"],
                "risks": ["肾毒性", "二重感染", "耐药压力"],
                "interactions": ["与万古霉素/造影剂/肾毒性药物联用需评估肾损伤风险"],
            },
        }

    async def predict_downstream_effects(self, intervention: str) -> dict[str, Any]:
        key = str(intervention or "").strip().lower()
        effect = self._intervention_map().get(key) or {
            "label": intervention,
            "expected_effects": [],
            "monitoring": ["生命体征", "器官灌注", "关键实验室复查"],
            "risks": ["需结合当前病情个体化评估"],
            "interactions": [],
        }
        return {
            "intervention": key,
            "label": effect.get("label"),
            "generated_at": datetime.now(),
            "expected_effects": effect.get("expected_effects") or [],
            "monitoring": effect.get("monitoring") or [],
            "risks": effect.get("risks") or [],
            "interactions": effect.get("interactions") or [],
        }
