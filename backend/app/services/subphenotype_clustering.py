from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any

from .counterfactual_model import _safe_float, _round, SemiMechanisticCounterfactualModel


def _softmax(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    peak = max(scores.values())
    weights = {key: math.exp(value - peak) for key, value in scores.items()}
    total = sum(weights.values()) or 1.0
    return {key: round(val / total, 4) for key, val in weights.items()}


class CohortSubphenotypeProfiler:
    def __init__(self, *, db, alert_engine) -> None:
        self.db = db
        self.alert_engine = alert_engine
        self.counterfactual_model = SemiMechanisticCounterfactualModel(db=db, alert_engine=alert_engine)

    def _syndrome_prototypes(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "sepsis": [
                {
                    "code": "shock_hyperinflammatory",
                    "label": "脓毒症高炎症/休克型",
                    "summary": "循环衰竭与高代谢压力并存，更接近高炎症/休克主导表型。",
                    "care_implications": ["优先按休克路径管理灌注目标、升压药和乳酸清除"],
                    "axes": {
                        "lactate": {"center": 4.5, "spread": 1.4, "weight": 1.5},
                        "map_inverse": {"center": 1.0, "spread": 0.5, "weight": 1.2},
                        "vaso_dose": {"center": 0.22, "spread": 0.12, "weight": 1.5},
                        "wbc": {"center": 18.0, "spread": 5.0, "weight": 0.8},
                        "platelet_inverse": {"center": 1.0, "spread": 0.7, "weight": 0.9},
                        "creatinine": {"center": 160.0, "spread": 60.0, "weight": 0.8},
                    },
                },
                {
                    "code": "organ_dysfunction_dominant",
                    "label": "脓毒症器官功能障碍主导型",
                    "summary": "炎症存在，但肾脏、凝血或胆红素等器官损伤信号更占主导。",
                    "care_implications": ["更需要器官保护与灌注支持并行"],
                    "axes": {
                        "lactate": {"center": 2.4, "spread": 1.0, "weight": 0.8},
                        "map_inverse": {"center": 0.4, "spread": 0.5, "weight": 0.8},
                        "creatinine": {"center": 220.0, "spread": 70.0, "weight": 1.4},
                        "bilirubin": {"center": 60.0, "spread": 26.0, "weight": 1.1},
                        "platelet_inverse": {"center": 1.2, "spread": 0.8, "weight": 1.0},
                        "sofa": {"center": 9.0, "spread": 2.5, "weight": 1.0},
                    },
                },
                {
                    "code": "moderate_inflammatory",
                    "label": "脓毒症中等炎症活动型",
                    "summary": "存在感染性炎症证据，但暂未进入明显休克或多器官障碍高负荷模式。",
                    "care_implications": ["强化早期趋势监测与证据闭环"],
                    "axes": {
                        "lactate": {"center": 2.0, "spread": 0.8, "weight": 1.0},
                        "map_inverse": {"center": 0.2, "spread": 0.3, "weight": 0.8},
                        "vaso_dose": {"center": 0.04, "spread": 0.05, "weight": 0.8},
                        "wbc": {"center": 13.0, "spread": 4.0, "weight": 0.8},
                        "sofa": {"center": 5.0, "spread": 2.0, "weight": 1.0},
                    },
                },
            ],
            "ards": [
                {
                    "code": "diffuse_recruitable",
                    "label": "ARDS 弥漫可复张型",
                    "summary": "FiO2/PEEP 需求较高，接近弥漫受累和较高复张潜力表型。",
                    "care_implications": ["持续评估俯卧位、PEEP 窗口和肺保护通气"],
                    "axes": {
                        "sf_inverse": {"center": 1.4, "spread": 0.5, "weight": 1.6},
                        "fio2_fraction": {"center": 0.7, "spread": 0.15, "weight": 1.2},
                        "peep": {"center": 12.0, "spread": 3.0, "weight": 1.0},
                        "vaso_dose": {"center": 0.12, "spread": 0.08, "weight": 0.6},
                    },
                },
                {
                    "code": "focal_less_recruitable",
                    "label": "ARDS 局灶/低复张型",
                    "summary": "氧合受损存在，但呼吸机需求不完全呈现弥漫重度复张模式。",
                    "care_implications": ["结合影像、体位反应和分泌物负荷判断局灶病灶"],
                    "axes": {
                        "sf_inverse": {"center": 0.9, "spread": 0.4, "weight": 1.2},
                        "fio2_fraction": {"center": 0.5, "spread": 0.12, "weight": 1.0},
                        "peep": {"center": 8.0, "spread": 2.0, "weight": 0.8},
                    },
                },
            ],
            "aki": [
                {
                    "code": "hypoperfusion_oliguric",
                    "label": "AKI 低灌注少尿型",
                    "summary": "少尿与低灌注并存，更接近肾前性/灌注不足驱动模式。",
                    "care_implications": ["优先复核灌注压、容量反应性与肾毒性暴露"],
                    "axes": {
                        "creatinine": {"center": 180.0, "spread": 70.0, "weight": 1.2},
                        "urine_inverse": {"center": 1.4, "spread": 0.6, "weight": 1.6},
                        "map_inverse": {"center": 0.8, "spread": 0.5, "weight": 1.0},
                        "lactate": {"center": 3.0, "spread": 1.3, "weight": 0.8},
                    },
                },
                {
                    "code": "nonoliguric_inflammatory",
                    "label": "AKI 非少尿/炎症负荷型",
                    "summary": "肌酐负荷升高，但并不完全由典型低灌注少尿解释。",
                    "care_implications": ["同时回顾感染、药物与容量管理对肾功能的共同影响"],
                    "axes": {
                        "creatinine": {"center": 200.0, "spread": 75.0, "weight": 1.4},
                        "urine_inverse": {"center": 0.4, "spread": 0.4, "weight": 0.8},
                        "wbc": {"center": 15.0, "spread": 4.0, "weight": 0.8},
                        "bilirubin": {"center": 30.0, "spread": 18.0, "weight": 0.7},
                    },
                },
            ],
        }

    def _diagnosis_text(self, patient: dict) -> str:
        return " ".join(str(patient.get(key) or "") for key in ("clinicalDiagnosis", "admissionDiagnosis", "diagnosis", "hisDiagnosis")).lower()

    def _is_syndrome_candidate(self, syndrome: str, diagnosis: str, features: dict[str, float]) -> bool:
        if syndrome == "sepsis":
            return any(token in diagnosis for token in ["脓毒", "sepsis", "感染", "肺炎", "菌血症"]) or (features.get("lactate", 0) >= 2 and (features.get("wbc", 0) >= 12 or features.get("vaso_dose", 0) > 0))
        if syndrome == "ards":
            return any(token in diagnosis for token in ["ards", "呼吸窘迫", "肺损伤"]) or features.get("sf_inverse", 0) > 0.2
        if syndrome == "aki":
            return features.get("creatinine", 0) >= 133 or features.get("urine_inverse", 0) > 0.5
        return False

    async def _feature_vector(self, patient: dict) -> tuple[dict[str, float], dict[str, Any]] | tuple[None, None]:
        pid = str(patient.get("_id") or "")
        if not pid:
            return None, None
        snapshot = await self.counterfactual_model.build_snapshot(pid, patient, hours=24)
        facts = await self.alert_engine._collect_patient_facts(patient, patient.get("_id")) if hasattr(self.alert_engine, "_collect_patient_facts") else {}
        labs = facts.get("labs") if isinstance(facts.get("labs"), dict) else {}
        his_pid = str(patient.get("hisPid") or "").strip() or None
        sofa = await self.alert_engine._calc_sofa(patient, patient.get("_id"), None, his_pid) if hasattr(self.alert_engine, "_calc_sofa") else {}
        lactate = _safe_float(((snapshot.get("lactate") or {}).get("current")))
        map_value = _safe_float(((snapshot.get("map") or {}).get("current")))
        spo2 = _safe_float(((snapshot.get("spo2") or {}).get("current")))
        fio2 = _safe_float(((snapshot.get("fio2") or {}).get("current")))
        peep = _safe_float(((snapshot.get("peep") or {}).get("current")))
        urine_rate = _safe_float(snapshot.get("urine_ml_kg_h_6h"))
        vaso_dose = _safe_float((((snapshot.get("vasoactive_support") or {}).get("current_dose_ug_kg_min"))))
        wbc = _safe_float(((labs.get("wbc") or {}) if isinstance(labs.get("wbc"), dict) else {}).get("value"))
        plt = _safe_float(((labs.get("plt") or {}) if isinstance(labs.get("plt"), dict) else {}).get("value"))
        cr = _safe_float(((labs.get("cr") or {}) if isinstance(labs.get("cr"), dict) else {}).get("value"))
        bili = _safe_float(((labs.get("bil") or labs.get("bilirubin") or {}) if isinstance(labs.get("bil") or labs.get("bilirubin"), dict) else {}).get("value"))
        sf_ratio = (spo2 / max((fio2 or 21.0) / 100.0, 0.21)) if spo2 is not None else None
        sofa_score = _safe_float((sofa or {}).get("score"))
        features = {
            "lactate": lactate or 1.5,
            "map_inverse": max(0.0, (65.0 - (map_value or 65.0)) / 10.0),
            "vaso_dose": vaso_dose or 0.0,
            "wbc": wbc or 10.0,
            "platelet_inverse": max(0.0, (150.0 - (plt or 150.0)) / 100.0),
            "creatinine": cr or 90.0,
            "bilirubin": bili or 18.0,
            "sofa": sofa_score or 4.0,
            "fio2_fraction": (fio2 or 21.0) / 100.0,
            "peep": peep or 5.0,
            "sf_inverse": max(0.0, (315.0 - ((sf_ratio or 3.15) * 100.0)) / 100.0),
            "urine_inverse": max(0.0, (0.8 - (urine_rate or 0.8)) / 0.4),
        }
        snapshot_payload = {
            "map": _round(map_value, 0),
            "lactate": _round(lactate, 1),
            "spo2": _round(spo2, 0),
            "fio2": _round(fio2, 0),
            "peep": _round(peep, 0),
            "sf_ratio": _round((sf_ratio * 100.0) if sf_ratio is not None else None, 1),
            "urine_ml_kg_h_6h": _round(urine_rate, 2),
            "vaso_dose_ug_kg_min": _round(vaso_dose, 3),
            "wbc": _round(wbc, 1),
            "plt": _round(plt, 0),
            "creatinine": _round(cr, 1),
            "bilirubin": _round(bili, 1),
            "sofa": _round(sofa_score, 0),
        }
        return features, snapshot_payload

    def _prototype_distance(self, features: dict[str, float], prototype: dict[str, Any]) -> float:
        axes = prototype.get("axes") if isinstance(prototype.get("axes"), dict) else {}
        if not axes:
            return 99.0
        total = 0.0
        weight_sum = 0.0
        for axis, spec in axes.items():
            if axis not in features:
                continue
            center = _safe_float((spec or {}).get("center"))
            spread = max(_safe_float((spec or {}).get("spread")) or 1.0, 1e-6)
            weight = max(_safe_float((spec or {}).get("weight")) or 1.0, 1e-6)
            if center is None:
                continue
            total += abs(features[axis] - center) / spread * weight
            weight_sum += weight
        if weight_sum <= 0:
            return 99.0
        return total / weight_sum

    def _prototype_center(self, prototype: dict[str, Any]) -> dict[str, float]:
        axes = prototype.get("axes") if isinstance(prototype.get("axes"), dict) else {}
        return {
            axis: round(float((spec or {}).get("center") or 0.0), 3)
            for axis, spec in axes.items()
        }

    async def profile(self, patient: dict) -> dict[str, Any]:
        features, supporting_snapshot = await self._feature_vector(patient)
        if not features:
            return {"summary": "缺少足够特征，无法完成亚表型聚类。", "primary_profile": None, "profiles": []}
        diagnosis = self._diagnosis_text(patient)
        matches: list[dict[str, Any]] = []
        for syndrome, prototypes in self._syndrome_prototypes().items():
            if not self._is_syndrome_candidate(syndrome, diagnosis, features):
                continue
            scores = {}
            distances: dict[str, float] = {}
            for proto in prototypes:
                distance = self._prototype_distance(features, proto)
                distances[proto["code"]] = distance
                scores[proto["code"]] = -distance
            probabilities = _softmax(scores)
            for proto in prototypes:
                code = proto["code"]
                evidence = []
                if syndrome == "sepsis":
                    if supporting_snapshot.get("lactate") is not None:
                        evidence.append(f"乳酸 {supporting_snapshot.get('lactate')}")
                    if supporting_snapshot.get("map") is not None:
                        evidence.append(f"MAP {supporting_snapshot.get('map')}")
                elif syndrome == "ards":
                    if supporting_snapshot.get("sf_ratio") is not None:
                        evidence.append(f"S/F {supporting_snapshot.get('sf_ratio')}")
                    if supporting_snapshot.get("peep") is not None:
                        evidence.append(f"PEEP {supporting_snapshot.get('peep')}")
                elif syndrome == "aki":
                    if supporting_snapshot.get("creatinine") is not None:
                        evidence.append(f"Cr {supporting_snapshot.get('creatinine')}")
                    if supporting_snapshot.get("urine_ml_kg_h_6h") is not None:
                        evidence.append(f"尿量 {supporting_snapshot.get('urine_ml_kg_h_6h')} mL/kg/h")
                matches.append(
                    {
                        "syndrome": syndrome,
                        "subtype_code": code,
                        "subtype_label": proto["label"],
                        "confidence": round(probabilities.get(code, 0.0), 3),
                        "summary": proto["summary"],
                        "evidence": evidence[:6],
                        "care_implications": proto["care_implications"],
                        "prototype_distance": round(distances.get(code, 99.0), 3),
                        "cohort_centroid": self._prototype_center(proto),
                    }
                )
        matches.sort(key=lambda item: float(item.get("confidence") or 0), reverse=True)
        primary = matches[0] if matches else None
        return {
            "summary": primary.get("summary") if primary else "当前未识别出高置信度综合征亚表型。",
            "primary_profile": primary,
            "profiles": matches[:6],
            "supporting_snapshot": supporting_snapshot,
            "feature_vector": {key: round(value, 3) for key, value in features.items()},
            "model_meta": {
                "kind": "prototype_soft_clustering",
                "generated_at": datetime.now(),
                "note": "当前采用原型中心快速软聚类分配，优先保证交互时延；如需论文级 cohort clustering，需要离线训练固定队列并做稳定性与外部验证。",
            },
        }
