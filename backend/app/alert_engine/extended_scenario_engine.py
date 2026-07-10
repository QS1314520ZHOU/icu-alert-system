"""Extended clinical scenario coverage engine."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


class ExtendedScenarioMixin:
    def _extended_scenarios_cfg(self) -> dict[str, list[str]]:
        cfg = self.config.yaml_cfg.get("extended_scenarios", {})
        return cfg if isinstance(cfg, dict) else {}

    def _extended_scenario_list(self) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []
        for group, scenarios in self._extended_scenarios_cfg().items():
            if not isinstance(scenarios, list):
                continue
            for item in scenarios:
                name = str(item).strip()
                if name:
                    rows.append((str(group).strip(), name))
        return rows

    def _extended_patient_text(self, patient_doc: dict[str, Any]) -> str:
        return " ".join(
            str(patient_doc.get(k) or "")
            for k in (
                "clinicalDiagnosis",
                "admissionDiagnosis",
                "history",
                "diagnosisHistory",
                "surgeryHistory",
                "operationHistory",
                "chiefComplaint",
                "presentIllness",
                "allDiagnosis",
                "pastHistory",
            )
        ).lower()

    def _contains_keywords(self, text: str, keywords: list[str]) -> bool:
        blob = str(text or "").lower()
        return any(str(keyword).strip().lower() in blob for keyword in keywords if str(keyword).strip())

    async def _extended_snapshot(self, patient_doc: dict[str, Any], pid) -> dict[str, Any]:
        his_pid = patient_doc.get("hisPid")
        device_id = await self._get_device_id_for_patient(patient_doc, ["monitor", "vent"])
        cap = await self._get_latest_param_snapshot_by_pid(
            pid,
            codes=["param_HR", "param_spo2", "param_resp", "param_nibp_s", "param_ibp_s", "param_nibp_m", "param_ibp_m", "param_T"],
        )
        if not cap and device_id:
            cap = await self._get_latest_device_cap(
                device_id,
                codes=["param_HR", "param_spo2", "param_resp", "param_nibp_s", "param_ibp_s", "param_nibp_m", "param_ibp_m", "param_T"],
            )
        params = cap.get("params", cap) if isinstance(cap, dict) else {}
        labs = await self._get_latest_labs_map(his_pid, lookback_hours=96) if his_pid else {}
        return {
            "device_id": device_id,
            "cap": cap,
            "params": params,
            "text": self._extended_patient_text(patient_doc),
            "labs": labs,
            "gcs": await self._get_latest_assessment(pid, "gcs"),
            "rass": await self._get_latest_assessment(pid, "rass"),
            "pupil": await self._get_pupil_status(pid),
            "drugs": await self._get_recent_drug_docs_window(pid, hours=96, limit=500),
            "active_alerts": await self._recent_alerts(self._pid_str(pid), datetime.now() - timedelta(hours=48), max_records=60) if hasattr(self, "_recent_alerts") else [],
            "vitals": {
                "hr": self._get_priority_param(params, ["param_HR"]) if params else None,
                "spo2": self._get_priority_param(params, ["param_spo2"]) if params else None,
                "rr": self._get_priority_param(params, ["param_resp"]) if params else None,
                "sbp": self._get_priority_param(params, ["param_nibp_s", "param_ibp_s"]) if params else None,
                "map": self._get_priority_param(params, ["param_nibp_m", "param_ibp_m"]) if params else None,
                "temp": self._get_priority_param(params, ["param_T"]) if params else None,
                "time": cap.get("time") if isinstance(cap, dict) else None,
            },
        }

    def _scenario_title(self, scenario: str) -> str:
        titles = {
            "tamponade_risk": "心包填塞风险",
            "sternal_wound_infection": "胸骨切口感染风险",
            "post_pump_syndrome": "体外循环后综合征风险",
            "cerebral_vasospasm": "脑血管痉挛风险",
            "hydrocephalus_acute": "急性脑积水风险",
            "seizure_prophylaxis": "癫痫预防评估提醒",
            "primary_graft_nonfunction": "移植物原发无功能风险",
            "hepatic_artery_thrombosis": "肝动脉血栓风险",
            "malignant_hyperthermia": "恶性高热风险",
            "transfusion_reaction": "输血反应风险",
            "adrenal_crisis": "肾上腺危象风险",
            "thyroid_storm": "甲状腺危象风险",
            "fat_embolism_syndrome": "脂肪栓塞综合征风险",
            "refeeding_syndrome": "再喂养综合征风险",
            "tumor_lysis_syndrome": "肿瘤溶解综合征风险",
            "heparin_induced_thrombocytopenia": "HIT 风险",
            "serotonin_syndrome": "5-羟色胺综合征风险",
            "neuroleptic_malignant_syndrome": "恶性综合征风险",
            "propofol_infusion_syndrome": "丙泊酚输注综合征风险",
            "contrast_nephropathy_risk": "造影剂肾病风险",
            "ventilator_auto_peep": "呼吸机 Auto-PEEP 风险",
            "iabp_timing_mismatch": "IABP 时相不匹配风险",
            "ecmo_circuit_thrombosis": "ECMO 回路血栓风险",
            "pacemaker_failure_to_capture": "起搏失夺获风险",
            "crrt_filter_clotting": "CRRT 滤器凝血风险",
            "central_line_dislodgement_risk": "中心静脉导管脱位风险",
            "arterial_line_failure": "动脉监测通路失效风险",
            "tracheostomy_obstruction": "气切套管阻塞风险",
            "urinary_catheter_obstruction": "导尿管阻塞风险",
            "septic_shock_escalation": "脓毒性休克升级风险",
            "septic_shock_refractory": "难治性脓毒性休克风险",
            "hemorrhagic_shock": "失血性休克风险",
            "cardiogenic_shock": "心源性休克风险",
            "obstructive_shock_pe": "阻塞性休克/肺栓塞风险",
            "vasoplegia_refractory": "顽固性血管麻痹风险",
            "hypertensive_emergency": "高血压急症风险",
            "refractory_hypoxemia": "难治性低氧血症风险",
            "hypercapnic_failure": "高碳酸血症呼衰风险",
            "pneumothorax_risk": "气胸风险",
            "aspiration_pneumonia": "误吸性肺炎风险",
            "mucus_plugging": "痰栓阻塞风险",
            "ventilator_asynchrony": "呼吸机不同步风险",
            "extubation_failure_risk": "拔管失败风险",
            "pulmonary_edema": "肺水肿风险",
            "aki_progression": "AKI 进展风险",
            "hyperkalemia_critical": "危重高钾血症风险",
            "severe_hyponatremia": "重度低钠血症风险",
            "severe_hypernatremia": "重度高钠血症风险",
            "metabolic_acidosis": "代谢性酸中毒风险",
            "lactic_acidosis_persistent": "持续高乳酸酸中毒风险",
            "uremic_complication": "尿毒症并发症风险",
            "rhabdomyolysis": "横纹肌溶解风险",
            "sepsis_escalation": "感染失控/脓毒症升级风险",
            "invasive_fungal_risk": "侵袭性真菌感染风险",
            "catheter_bloodstream_infection": "导管相关血流感染风险",
            "ventilator_associated_pneumonia": "呼吸机相关肺炎风险",
            "c_difficile_risk": "艰难梭菌感染风险",
            "neutropenic_sepsis_risk": "中性粒细胞减少性脓毒症风险",
            "delirium_hyperactive": "高活动型谵妄风险",
            "delirium_hypoactive": "低活动型谵妄风险",
            "status_epilepticus_risk": "癫痫持续状态风险",
            "elevated_icp_risk": "颅压升高风险",
            "acute_stroke_evolution": "急性卒中演变风险",
            "dic_progression": "DIC 进展风险",
            "active_bleeding_risk": "活动性出血风险",
            "coagulopathy_severe": "严重凝血障碍风险",
            "thrombocytopenia_severe": "重度血小板减少风险",
            "anemia_transfusion_trigger": "贫血输血阈值触发",
            "hypoglycemia_critical": "危重低血糖风险",
            "hyperglycemia_crisis": "高血糖危象风险",
            "starvation_ketosis_risk": "饥饿性酮症风险",
            "adrenal_insufficiency_risk": "肾上腺皮质功能不全风险",
            "anastomotic_leak_risk": "吻合口漏风险",
            "postop_bleeding_recurrence": "术后再出血风险",
            "ileus_risk": "肠麻痹风险",
            "abdominal_compartment_risk": "腹腔间隔室综合征风险",
        }
        return titles.get(scenario, scenario.replace("_", " ").title())

    def _scenario_severity(self, score: float) -> str:
        if score >= 8:
            return "critical"
        if score >= 5:
            return "high"
        return "warning"

    async def _evaluate_extended_scenario(
        self,
        *,
        group: str,
        scenario: str,
        patient_doc: dict[str, Any],
        context: dict[str, Any],
        now: datetime,
    ) -> dict[str, Any] | None:
        text = context.get("text") or ""
        vitals = context.get("vitals") if isinstance(context.get("vitals"), dict) else {}
        labs = context.get("labs") if isinstance(context.get("labs"), dict) else {}
        drugs = context.get("drugs") if isinstance(context.get("drugs"), list) else []
        alerts = context.get("active_alerts") if isinstance(context.get("active_alerts"), list) else []
        hr = vitals.get("hr")
        map_value = vitals.get("map")
        spo2 = vitals.get("spo2")
        rr = vitals.get("rr")
        temp = vitals.get("temp")
        gcs = context.get("gcs")
        pupil = context.get("pupil") if isinstance(context.get("pupil"), dict) else {}
        drug_blob = " ".join(self._drug_text(doc) for doc in drugs).lower()

        def lab_value(*keys: str) -> float | None:
            for key in keys:
                item = labs.get(key)
                if isinstance(item, dict) and item.get("value") is not None:
                    try:
                        return float(item.get("value"))
                    except Exception:
                        continue
            return None

        def recent_alert(keywords: list[str]) -> bool:
            for row in alerts:
                blob = " ".join(str(row.get(k) or "") for k in ("alert_type", "rule_id", "name")).lower()
                if any(keyword in blob for keyword in keywords):
                    return True
            return False

        wbc = lab_value("wbc")
        pct_value = lab_value("pct")
        lactate = lab_value("lac", "lactate")
        hb = lab_value("hb")
        plt = lab_value("plt")
        inr = lab_value("inr")
        na = lab_value("na")
        k = lab_value("k")
        cr = lab_value("cr")
        glu = lab_value("glu", "glucose")
        alb = lab_value("alb", "albumin")
        ddimer = lab_value("ddimer")
        po4 = lab_value("po4")
        mg = lab_value("mg")
        bil = lab_value("bil")
        ast = lab_value("ast")
        alt = lab_value("alt")
        vent_device = await self._get_device_id_for_patient(patient_doc, ["vent"])
        crrt_device = await self._get_device_id_for_patient(patient_doc, ["crrt"])

        if scenario == "septic_shock_escalation":
            if ((lactate is not None and lactate >= 2.5) or recent_alert(["sepsis", "qsofa", "sofa"])) and map_value is not None and float(map_value) < 65:
                score = 5 + (1 if lactate is not None and lactate >= 4 else 0) + (1 if self._contains_keywords(drug_blob, ["norepinephrine", "去甲"]) else 0)
                return {"score": score, "value": map_value, "extra": {"map": map_value, "lactate": lactate, "wbc": wbc, "pct": pct_value}}
        elif scenario == "septic_shock_refractory":
            if recent_alert(["sepsis"]) and map_value is not None and float(map_value) < 60 and self._contains_keywords(drug_blob, ["norepinephrine", "vasopressin", "去甲", "血管加压素"]):
                return {"score": 8, "value": map_value, "extra": {"map": map_value, "lactate": lactate}}
        elif scenario == "hemorrhagic_shock":
            if hb is not None and hb < 70 and ((map_value is not None and float(map_value) < 65) or (hr is not None and float(hr) >= 120)):
                return {"score": 7, "value": hb, "extra": {"hb": hb, "map": map_value, "hr": hr}}
        elif scenario == "cardiogenic_shock":
            if self._contains_keywords(text, ["心梗", "心衰", "cardiogenic", "heart failure", "acs"]) and map_value is not None and float(map_value) < 65:
                score = 5 + (1 if hr is not None and float(hr) >= 110 else 0) + (1 if recent_alert(["right_heart", "cardiac_arrest"]) else 0)
                return {"score": score, "value": map_value, "extra": {"map": map_value, "hr": hr, "lactate": lactate}}
        elif scenario == "obstructive_shock_pe":
            if recent_alert(["pe", "wells"]) and map_value is not None and float(map_value) < 65 and (spo2 is not None and float(spo2) < 92):
                return {"score": 7, "value": map_value, "extra": {"map": map_value, "spo2": spo2, "ddimer": ddimer}}
        elif scenario == "vasoplegia_refractory":
            if self._contains_keywords(drug_blob, ["norepinephrine", "vasopressin", "去甲", "血管加压素"]) and map_value is not None and float(map_value) < 65 and lactate is not None and lactate >= 2:
                return {"score": 6, "value": map_value, "extra": {"map": map_value, "lactate": lactate}}
        elif scenario == "hypertensive_emergency":
            if self._contains_keywords(text, ["高血压", "hypertension", "脑出血", "主动脉夹层"]) and hr is not None and map_value is not None and float(map_value) >= 120:
                return {"score": 5, "value": map_value, "extra": {"map": map_value, "hr": hr}}
        elif scenario == "refractory_hypoxemia":
            if spo2 is not None and float(spo2) < 88 and vent_device:
                return {"score": 7, "value": spo2, "extra": {"spo2": spo2, "rr": rr, "on_vent": True}}
        elif scenario == "hypercapnic_failure":
            if self._contains_keywords(text, ["copd", "慢阻肺", "二氧化碳潴留", "hypercapnia"]) and rr is not None and float(rr) >= 28:
                return {"score": 5, "value": rr, "extra": {"rr": rr, "spo2": spo2}}
        elif scenario == "pneumothorax_risk":
            if vent_device and ((spo2 is not None and float(spo2) < 90) and (map_value is not None and float(map_value) < 65)):
                return {"score": 6, "value": spo2, "extra": {"spo2": spo2, "map": map_value}}
        elif scenario == "aspiration_pneumonia":
            if self._contains_keywords(text, ["误吸", "aspiration", "呕吐", "吞咽障碍"]) and ((temp is not None and float(temp) >= 38) or (wbc is not None and wbc >= 12)):
                return {"score": 5, "value": temp or wbc, "extra": {"temp": temp, "wbc": wbc, "spo2": spo2}}
        elif scenario == "mucus_plugging":
            if vent_device and spo2 is not None and rr is not None and float(spo2) < 90 and float(rr) >= 28:
                return {"score": 5, "value": spo2, "extra": {"spo2": spo2, "rr": rr}}
        elif scenario == "ventilator_asynchrony":
            if vent_device and rr is not None and float(rr) >= 30 and (context.get("rass") is not None and float(context.get("rass")) >= 1):
                return {"score": 5, "value": rr, "extra": {"rr": rr, "rass": context.get("rass")}}
        elif scenario == "extubation_failure_risk":
            if recent_alert(["post_extubation", "reintubation", "weaning"]) and spo2 is not None and float(spo2) < 92:
                return {"score": 6, "value": spo2, "extra": {"spo2": spo2, "rr": rr}}
        elif scenario == "pulmonary_edema":
            if self._contains_keywords(text, ["心衰", "肺水肿", "pulmonary edema"]) and ((spo2 is not None and float(spo2) < 92) or recent_alert(["fluid_balance"])):
                return {"score": 5, "value": spo2 or rr, "extra": {"spo2": spo2, "rr": rr}}
        elif scenario == "aki_progression":
            if cr is not None and recent_alert(["aki"]) and cr >= 177:
                return {"score": 6, "value": cr, "extra": {"cr": cr, "k": k}}
        elif scenario == "hyperkalemia_critical":
            if k is not None and k >= 6.0:
                return {"score": 8, "value": k, "extra": {"k": k, "cr": cr}}
        elif scenario == "severe_hyponatremia":
            if na is not None and na < 125:
                return {"score": 6, "value": na, "extra": {"na": na, "gcs": gcs}}
        elif scenario == "severe_hypernatremia":
            if na is not None and na >= 155:
                return {"score": 6, "value": na, "extra": {"na": na}}
        elif scenario == "metabolic_acidosis":
            if lactate is not None and lactate >= 3:
                return {"score": 5 + (1 if lactate >= 4 else 0), "value": lactate, "extra": {"lactate": lactate, "k": k}}
        elif scenario == "lactic_acidosis_persistent":
            if patient_doc.get("hisPid"):
                lac_series = await self._get_lab_series(patient_doc.get("hisPid"), "lac", now - timedelta(hours=12), limit=60)
                if len(lac_series) >= 2 and float(lac_series[-1]["value"]) >= 4 and float(lac_series[0]["value"]) >= 4:
                    return {"score": 7, "value": float(lac_series[-1]["value"]), "extra": {"lactate_start": float(lac_series[0]["value"]), "lactate_latest": float(lac_series[-1]["value"])}}
        elif scenario == "uremic_complication":
            if cr is not None and cr >= 300 and (k is not None and k >= 5.5):
                return {"score": 7, "value": cr, "extra": {"cr": cr, "k": k, "crrt": bool(crrt_device)}}
        elif scenario == "rhabdomyolysis":
            if self._contains_keywords(text, ["横纹肌溶解", "rhabdomyolysis", "挤压伤", "癫痫持续"]) and (cr is not None and cr >= 150):
                return {"score": 6, "value": cr, "extra": {"cr": cr, "k": k}}
        elif scenario == "sepsis_escalation":
            if recent_alert(["sepsis", "qsofa", "sofa"]) and ((wbc is not None and wbc >= 12) or (pct_value is not None and pct_value >= 2) or (lactate is not None and lactate >= 2)):
                return {"score": 6, "value": pct_value or lactate or wbc, "extra": {"wbc": wbc, "pct": pct_value, "lactate": lactate}}
        elif scenario == "invasive_fungal_risk":
            if self._contains_keywords(text, ["移植", "粒缺", "免疫抑制", "fungal", "真菌"]) and ((temp is not None and float(temp) >= 38) or recent_alert(["immunocompromised"])):
                return {"score": 5, "value": temp or 1, "extra": {"temp": temp, "wbc": wbc}}
        elif scenario == "catheter_bloodstream_infection":
            if self._contains_keywords(text, ["中心静脉", "picc", "cvc", "导管"]) and ((temp is not None and float(temp) >= 38) and (wbc is not None and wbc >= 12)):
                return {"score": 5, "value": temp, "extra": {"temp": temp, "wbc": wbc}}
        elif scenario == "ventilator_associated_pneumonia":
            if vent_device and ((temp is not None and float(temp) >= 38) and (wbc is not None and wbc >= 12)):
                return {"score": 5, "value": temp, "extra": {"temp": temp, "wbc": wbc, "spo2": spo2}}
        elif scenario == "c_difficile_risk":
            if self._contains_keywords(drug_blob, ["meropenem", "piperacillin", "头孢", "clindamycin", "抗生素"]) and self._contains_keywords(text, ["腹泻", "水样便", "c. difficile", "艰难梭菌"]):
                return {"score": 5, "value": wbc or 1, "extra": {"wbc": wbc, "albumin": alb}}
        elif scenario == "neutropenic_sepsis_risk":
            if wbc is not None and wbc < 1.0 and (temp is not None and float(temp) >= 38):
                return {"score": 7, "value": wbc, "extra": {"wbc": wbc, "temp": temp}}
        elif scenario == "delirium_hyperactive":
            if recent_alert(["delirium"]) and context.get("rass") is not None and float(context.get("rass")) >= 1:
                return {"score": 5, "value": context.get("rass"), "extra": {"rass": context.get("rass"), "gcs": gcs}}
        elif scenario == "delirium_hypoactive":
            if recent_alert(["delirium"]) and context.get("rass") is not None and float(context.get("rass")) <= -2:
                return {"score": 5, "value": context.get("rass"), "extra": {"rass": context.get("rass"), "gcs": gcs}}
        elif scenario == "status_epilepticus_risk":
            if self._contains_keywords(text, ["癫痫", "惊厥", "seizure"]) and ((gcs is not None and gcs < 10) or recent_alert(["tbi", "neuro"])):
                return {"score": 6, "value": gcs, "extra": {"gcs": gcs, "pupil": pupil}}
        elif scenario == "elevated_icp_risk":
            if self._contains_keywords(text, ["颅压", "脑外伤", "脑出血", "神外"]) and ((gcs is not None and gcs <= 10) or pupil.get("abnormal")):
                return {"score": 7, "value": gcs, "extra": {"gcs": gcs, "pupil": pupil}}
        elif scenario == "acute_stroke_evolution":
            if self._contains_keywords(text, ["卒中", "脑梗", "脑出血", "stroke"]) and ((gcs is not None and gcs < 13) or recent_alert(["pupil", "gcs_drop"])):
                return {"score": 6, "value": gcs, "extra": {"gcs": gcs, "map": map_value}}
        elif scenario == "dic_progression":
            if plt is not None and plt < 100 and inr is not None and inr >= 1.5:
                return {"score": 6, "value": plt, "extra": {"plt": plt, "inr": inr}}
        elif scenario == "active_bleeding_risk":
            if hb is not None and hb < 80 and ((plt is not None and plt < 80) or (inr is not None and inr >= 1.5)):
                return {"score": 6, "value": hb, "extra": {"hb": hb, "plt": plt, "inr": inr}}
        elif scenario == "coagulopathy_severe":
            if inr is not None and inr >= 2.0:
                return {"score": 6, "value": inr, "extra": {"inr": inr, "plt": plt}}
        elif scenario == "thrombocytopenia_severe":
            if plt is not None and plt < 50:
                return {"score": 6, "value": plt, "extra": {"plt": plt}}
        elif scenario == "anemia_transfusion_trigger":
            if hb is not None and hb < 70:
                return {"score": 5, "value": hb, "extra": {"hb": hb}}
        elif scenario == "hypoglycemia_critical":
            if glu is not None and glu < 3.0:
                return {"score": 8, "value": glu, "extra": {"glucose": glu, "gcs": gcs}}
        elif scenario == "hyperglycemia_crisis":
            if glu is not None and glu >= 16.7:
                return {"score": 6, "value": glu, "extra": {"glucose": glu, "k": k}}
        elif scenario == "starvation_ketosis_risk":
            if alb is not None and alb < 30 and recent_alert(["nutrition", "refeeding"]):
                return {"score": 5, "value": alb, "extra": {"albumin": alb, "glucose": glu}}
        elif scenario == "adrenal_insufficiency_risk":
            if self._contains_keywords(text, ["长期激素", "adrenal", "肾上腺"]) and map_value is not None and float(map_value) < 65 and (na is not None and na < 130):
                return {"score": 6, "value": map_value, "extra": {"map": map_value, "na": na, "k": k}}
        elif scenario == "crrt_filter_clotting":
            if crrt_device and ((ddimer is not None and ddimer >= 5) or (plt is not None and plt < 80)):
                return {"score": 5, "value": ddimer or plt, "extra": {"ddimer": ddimer, "plt": plt}}
        elif scenario == "central_line_dislodgement_risk":
            if self._contains_keywords(text, ["中心静脉", "cvc", "picc", "导管"]) and recent_alert(["device", "line"]) and (hr is not None and float(hr) >= 110):
                return {"score": 5, "value": hr, "extra": {"hr": hr}}
        elif scenario == "arterial_line_failure":
            if self._contains_keywords(text, ["动脉置管", "arterial line"]) and map_value is not None and float(map_value) < 60:
                return {"score": 4, "value": map_value, "extra": {"map": map_value}}
        elif scenario == "tracheostomy_obstruction":
            if self._contains_keywords(text, ["气切", "tracheostomy"]) and ((spo2 is not None and float(spo2) < 90) or (rr is not None and float(rr) >= 28)):
                return {"score": 6, "value": spo2 or rr, "extra": {"spo2": spo2, "rr": rr}}
        elif scenario == "urinary_catheter_obstruction":
            if self._contains_keywords(text, ["导尿", "尿管", "catheter"]) and cr is not None and cr >= 150:
                return {"score": 4, "value": cr, "extra": {"cr": cr}}
        elif scenario == "anastomotic_leak_risk":
            if self._contains_keywords(text, ["吻合口", "胃肠手术", "消化道术后", "anastomosis"]) and ((temp is not None and float(temp) >= 38) or (wbc is not None and wbc >= 12) or (lactate is not None and lactate >= 2)):
                return {"score": 6, "value": temp or wbc or lactate, "extra": {"temp": temp, "wbc": wbc, "lactate": lactate}}
        elif scenario == "postop_bleeding_recurrence":
            if self._contains_keywords(text, ["术后", "postop", "引流"]) and hb is not None and hb < 80:
                return {"score": 5, "value": hb, "extra": {"hb": hb, "inr": inr}}
        elif scenario == "ileus_risk":
            if self._contains_keywords(text, ["腹部手术", "肠梗阻", "ileus", "腹胀"]) and recent_alert(["nutrition"]) and k is not None and k < 3.5:
                return {"score": 4, "value": k, "extra": {"k": k}}
        elif scenario == "abdominal_compartment_risk":
            if self._contains_keywords(text, ["腹压", "腹腔间隔室", "大量补液", "abdominal compartment"]) and ((map_value is not None and float(map_value) < 65) or (cr is not None and cr >= 150)):
                return {"score": 6, "value": map_value or cr, "extra": {"map": map_value, "cr": cr}}

        if scenario == "tamponade_risk":
            if self._contains_keywords(text, ["cardiac surgery", "cabg", "瓣膜", "搭桥", "开胸", "心脏术后"]) and map_value is not None and hr is not None:
                score = (3 if float(map_value) < 65 else 0) + (2 if float(hr) > 110 else 0) + (2 if self._contains_keywords(drug_blob, ["norepinephrine", "去甲"]) else 0)
                if score >= 5:
                    return {"score": score, "value": map_value, "extra": {"map": map_value, "hr": hr}}
        elif scenario == "sternal_wound_infection":
            wbc = lab_value("wbc")
            if self._contains_keywords(text, ["cardiac surgery", "sternotomy", "开胸", "胸骨"]) and temp is not None and float(temp) >= 38 and wbc is not None and wbc >= 12:
                return {"score": 5, "value": temp, "extra": {"temp": temp, "wbc": wbc}}
        elif scenario == "post_pump_syndrome":
            lactate = lab_value("lac", "lactate")
            if self._contains_keywords(text, ["cardiac surgery", "cpb", "体外循环", "开胸"]) and ((lactate is not None and lactate >= 3) or self._contains_keywords(drug_blob, ["norepinephrine", "去甲"])):
                return {"score": 5 + (2 if lactate is not None and lactate >= 4 else 0), "value": lactate or map_value, "extra": {"lactate": lactate, "map": map_value}}
        elif scenario == "cerebral_vasospasm":
            if self._contains_keywords(text, ["subarachnoid", "蛛网膜下腔", "脑动脉瘤", "神外", "neurosurgery"]) and ((gcs is not None and gcs < 13) or recent_alert(["tbi", "pupil", "gcs_drop"])):
                return {"score": 6, "value": gcs, "extra": {"gcs": gcs, "pupil": pupil}}
        elif scenario == "hydrocephalus_acute":
            if self._contains_keywords(text, ["神外", "脑室", "脑出血", "hydrocephalus", "颅脑"]) and (pupil.get("abnormal") or (gcs is not None and gcs <= 10)):
                return {"score": 7, "value": gcs, "extra": {"gcs": gcs, "pupil": pupil}}
        elif scenario == "seizure_prophylaxis":
            if self._contains_keywords(text, ["神外", "脑膜瘤", "颅脑", "epilepsy", "seizure", "癫痫"]) and not self._contains_keywords(drug_blob, ["左乙拉西坦", "丙戊酸", "levetiracetam", "valproate"]):
                return {"score": 4, "value": 1, "extra": {"antiepileptic_detected": False}}
        elif scenario == "primary_graft_nonfunction":
            bil = lab_value("bil")
            inr = lab_value("inr")
            lactate = lab_value("lac", "lactate")
            if self._contains_keywords(text, ["liver transplant", "肝移植"]) and ((bil is not None and bil > 100) or (inr is not None and inr >= 2) or (lactate is not None and lactate >= 4)):
                return {"score": 8, "value": bil or inr or lactate, "extra": {"bilirubin": bil, "inr": inr, "lactate": lactate}}
        elif scenario == "hepatic_artery_thrombosis":
            ast = lab_value("ast")
            alt = lab_value("alt")
            if self._contains_keywords(text, ["liver transplant", "肝移植"]) and ((ast is not None and ast > 500) or (alt is not None and alt > 500)):
                return {"score": 7, "value": max(ast or 0, alt or 0), "extra": {"ast": ast, "alt": alt}}
        elif scenario == "malignant_hyperthermia":
            if self._contains_keywords(text, ["术后", "手术", "麻醉"]) and temp is not None and rr is not None and float(temp) >= 39 and float(rr) >= 28:
                return {"score": 8, "value": temp, "extra": {"temp": temp, "rr": rr}}
        elif scenario == "transfusion_reaction":
            if self._contains_keywords(drug_blob, ["悬浮红细胞", "血浆", "platelet", "transfusion", "输血"]) and spo2 is not None and float(spo2) < 92:
                return {"score": 6, "value": spo2, "extra": {"spo2": spo2, "rr": rr}}
        elif scenario == "adrenal_crisis":
            na = lab_value("na")
            k = lab_value("k")
            if self._contains_keywords(text, ["adrenal", "肾上腺", "长期激素"]) and map_value is not None and float(map_value) < 65:
                score = 5 + (1 if na is not None and na < 130 else 0) + (1 if k is not None and k > 5.2 else 0)
                return {"score": score, "value": map_value, "extra": {"map": map_value, "na": na, "k": k}}
        elif scenario == "thyroid_storm":
            if self._contains_keywords(text, ["甲亢", "thyroid", "graves"]) and hr is not None and temp is not None and float(hr) >= 130 and float(temp) >= 38.5:
                return {"score": 7, "value": hr, "extra": {"hr": hr, "temp": temp}}
        elif scenario == "fat_embolism_syndrome":
            if self._contains_keywords(text, ["骨折", "股骨", "创伤", "orthopedic", "脂肪栓塞"]) and spo2 is not None and ((float(spo2) < 90) or (gcs is not None and gcs < 13)):
                return {"score": 6, "value": spo2, "extra": {"spo2": spo2, "gcs": gcs}}
        elif scenario == "refeeding_syndrome":
            po4 = lab_value("po4")
            mg = lab_value("mg")
            if recent_alert(["nutrition_refeeding_risk"]) or ((po4 is not None and po4 < 0.8) and (mg is not None and mg < 0.7)):
                return {"score": 6, "value": po4 or mg, "extra": {"phosphate": po4, "magnesium": mg}}
        elif scenario == "tumor_lysis_syndrome":
            k = lab_value("k")
            po4 = lab_value("po4")
            cr = lab_value("cr")
            if self._contains_keywords(text, ["白血病", "淋巴瘤", "肿瘤", "chemotherapy", "肿瘤溶解"]) and ((k is not None and k >= 5.5) or (po4 is not None and po4 >= 1.6) or (cr is not None and cr >= 150)):
                return {"score": 7, "value": k or po4 or cr, "extra": {"k": k, "po4": po4, "cr": cr}}
        elif scenario == "heparin_induced_thrombocytopenia":
            plt_series = await self._get_lab_series(patient_doc.get("hisPid"), "plt", now - timedelta(days=7), limit=60) if patient_doc.get("hisPid") else []
            if self._contains_keywords(drug_blob, ["肝素", "heparin"]) and len(plt_series) >= 2:
                first = float(plt_series[0]["value"])
                last = float(plt_series[-1]["value"])
                if first > 0 and last < first * 0.5:
                    return {"score": 7, "value": last, "extra": {"plt_baseline": first, "plt_latest": last, "drop_ratio": round(last / first, 3)}}
        elif scenario == "serotonin_syndrome":
            if self._contains_keywords(drug_blob, ["舍曲林", "氟西汀", "linezolid", "曲马多", "sertraline", "fluoxetine", "tramadol"]) and temp is not None and hr is not None and float(temp) >= 38 and float(hr) >= 110:
                return {"score": 6, "value": temp, "extra": {"temp": temp, "hr": hr}}
        elif scenario == "neuroleptic_malignant_syndrome":
            if self._contains_keywords(drug_blob, ["氟哌啶醇", "奥氮平", "喹硫平", "haloperidol", "olanzapine", "quetiapine"]) and temp is not None and float(temp) >= 38.5:
                return {"score": 6, "value": temp, "extra": {"temp": temp, "rass": context.get("rass")}}
        elif scenario == "propofol_infusion_syndrome":
            lactate = lab_value("lac", "lactate")
            if self._contains_keywords(drug_blob, ["丙泊酚", "propofol"]) and lactate is not None and lactate >= 4:
                return {"score": 7, "value": lactate, "extra": {"lactate": lactate, "hr": hr}}
        elif scenario == "contrast_nephropathy_risk":
            cr_series = await self._get_lab_series(patient_doc.get("hisPid"), "cr", now - timedelta(days=3), limit=40) if patient_doc.get("hisPid") else []
            if self._contains_keywords(text, ["造影", "contrast", "cta", "pci"]) and len(cr_series) >= 2:
                first = float(cr_series[0]["value"])
                last = float(cr_series[-1]["value"])
                if last >= first + 26.5 or (first > 0 and last >= first * 1.25):
                    return {"score": 5, "value": last, "extra": {"cr_baseline": first, "cr_latest": last}}
        elif scenario == "ventilator_auto_peep":
            if await self._get_device_id_for_patient(patient_doc, ["vent"]) and rr is not None and float(rr) >= 30 and recent_alert(["weaning", "ventilator"]):
                return {"score": 5, "value": rr, "extra": {"rr": rr, "on_vent": True}}
        elif scenario == "iabp_timing_mismatch":
            if self._contains_keywords(text, ["iabp", "主动脉球囊"]) and map_value is not None and float(map_value) < 65:
                return {"score": 5, "value": map_value, "extra": {"map": map_value}}
        elif scenario == "ecmo_circuit_thrombosis":
            ddimer = lab_value("ddimer")
            if self._contains_keywords(text, ["ecmo"]) and ((ddimer is not None and ddimer > 5) or self._contains_keywords(drug_blob, ["肝素", "heparin"])):
                return {"score": 6, "value": ddimer or 1, "extra": {"ddimer": ddimer}}
        elif scenario == "pacemaker_failure_to_capture":
            if self._contains_keywords(text, ["pacemaker", "起搏器"]) and hr is not None and float(hr) < 50:
                return {"score": 6, "value": hr, "extra": {"hr": hr}}
        return None

    async def scan_extended_scenarios(self) -> None:
        from .scanner_extended_scenarios import ExtendedScenariosScanner

        await ExtendedScenariosScanner(self).scan()
