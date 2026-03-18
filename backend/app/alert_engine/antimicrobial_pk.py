
"""抗菌药物药代动力学 / ARC / TDM 闭环。"""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from typing import Any


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    m = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group(0))
    except Exception:
        return None


class AntimicrobialPKMixin:
    def _antimicrobial_pk_cfg(self) -> dict:
        cfg = self._cfg("alert_engine", "antimicrobial_pk", default={}) or {}
        return cfg if isinstance(cfg, dict) else {}

    def _arc_cfg(self) -> dict:
        cfg = self._antimicrobial_pk_cfg().get("arc", {})
        return cfg if isinstance(cfg, dict) else {}

    def _pop_pk_cfg(self) -> dict:
        cfg = self._antimicrobial_pk_cfg().get("pop_pk", {})
        return cfg if isinstance(cfg, dict) else {}

    def _tdm_cfg(self) -> dict:
        cfg = self._antimicrobial_pk_cfg().get("tdm", {})
        return cfg if isinstance(cfg, dict) else {}

    def _drug_rule_cfg(self, drug_key: str) -> dict:
        cfg = self._pop_pk_cfg().get(drug_key, {})
        return cfg if isinstance(cfg, dict) else {}

    def _patient_age(self, patient_doc: dict | None) -> float | None:
        raw = (patient_doc or {}).get("age")
        if isinstance(raw, (int, float)):
            return float(raw)
        m = re.search(r"\d+(?:\.\d+)?", str(raw or ""))
        return float(m.group(0)) if m else None

    def _diagnosis_text(self, patient_doc: dict | None) -> str:
        return " ".join(str((patient_doc or {}).get(k) or "") for k in ("clinicalDiagnosis", "admissionDiagnosis", "diagnosis", "remark")).lower()

    def _match_any_text(self, text: str, keywords: list[str]) -> bool:
        t = str(text or "").lower()
        return any(str(k).strip().lower() in t for k in keywords if str(k).strip())

    def _is_trauma_or_neuro(self, patient_doc: dict | None) -> bool:
        keywords = self._arc_cfg().get("trauma_neuro_keywords", ["外伤", "创伤", "脑外伤", "tbi", "sah", "神经外科", "颅脑", "神外"])
        return self._match_any_text(self._diagnosis_text(patient_doc), keywords if isinstance(keywords, list) else [])

    async def _has_active_alert_type(self, pid_str: str, alert_types: list[str], hours: int = 48) -> bool:
        since = datetime.now() - timedelta(hours=max(hours, 1))
        cnt = await self.db.col("alert_records").count_documents({"patient_id": pid_str, "alert_type": {"$in": alert_types}, "created_at": {"$gte": since}})
        return cnt > 0

    async def _is_on_crrt(self, pid) -> bool:
        pid_str = self._pid_str(pid)
        doc = await self.db.col("deviceBind").find_one({"pid": pid_str, "unBindTime": None, "type": {"$in": ["crrt", "CRRT"]}}, {"_id": 1})
        return bool(doc)

    async def _latest_lab_value(self, his_pid: str | None, test_key: str, hours: int = 72) -> tuple[float | None, datetime | None]:
        if not his_pid:
            return None, None
        series = await self._get_lab_series(his_pid, test_key, datetime.now() - timedelta(hours=max(hours, 1)), limit=60)
        if not series:
            return None, None
        latest = series[-1]
        return _to_float(latest.get("value")), latest.get("time")

    async def _urine_ml_h(self, pid_str: str, now: datetime, hours: int = 6) -> float | None:
        since = now - timedelta(hours=max(hours, 1))
        configured_codes = self._cfg("alert_engine", "data_mapping", "urine_output", "codes", default=[]) or []
        codes = []
        seen: set[str] = set()
        for code in [
            *[str(x) for x in configured_codes if str(x).strip()],
            "param_niaoLiang",
            "param_niaoLiang_pure",
            "param_udd_urine_cur",
            "param_udd_urine_1h",
            "param_udd_urine_total",
            "param_udd_urine_24h",
            "param_out_hour",
            "param_out_hour_sum",
            "param_out_day",
        ]:
            if not code or code in seen:
                continue
            seen.add(code)
            codes.append(code)
        cursor = self.db.col("bedside").find({"pid": pid_str, "time": {"$gte": since}, "code": {"$in": codes}}, {"time": 1, "code": 1, "fVal": 1, "intVal": 1, "strVal": 1, "value": 1}).sort("time", 1)
        rows = [row async for row in cursor]
        if not rows:
            return None
        total = 0.0
        points = 0
        cum_total = []
        cum_24h = []
        out_vals = []
        for row in rows:
            code = str(row.get("code") or "")
            val = None
            for key in ("fVal", "intVal", "strVal", "value"):
                val = _to_float(row.get(key))
                if val is not None:
                    break
            if val is None or val < 0:
                continue
            if code in {"param_niaoLiang", "param_niaoLiang_pure", "param_udd_urine_cur", "param_udd_urine_1h"}:
                total += val
                points += 1
            elif code == "param_udd_urine_total":
                cum_total.append(val)
            elif code == "param_udd_urine_24h":
                cum_24h.append(val)
            else:
                out_vals.append(val)
        if points > 0:
            return round(total / max(hours, 1), 2)
        if len(cum_total) >= 2:
            return round(max(cum_total[-1] - cum_total[0], 0.0) / max(hours, 1), 2)
        if cum_24h:
            return round(max(cum_24h[-1], 0.0) / 24.0, 2)
        if len(out_vals) >= 2:
            return round(max(out_vals[-1] - out_vals[0], 0.0) / max(hours, 1), 2)
        return None

    async def assess_arc_risk(self, patient_doc: dict, now: datetime) -> dict:
        pid = patient_doc.get("_id")
        pid_str = self._pid_str(pid)
        his_pid = str(patient_doc.get("hisPid") or "").strip() or None
        age = self._patient_age(patient_doc)
        cr_value, cr_time = await self._latest_lab_value(his_pid, "cr", hours=24)
        crcl = self._estimate_crcl(patient_doc, cr_value)
        urine_ml_h = await self._urine_ml_h(pid_str, now, hours=6)
        on_crrt = await self._is_on_crrt(pid)
        has_aki = await self._has_active_alert_type(pid_str, ["aki"], hours=48)
        age_cutoff = float(self._arc_cfg().get("age_lt", 50))
        cr_cutoff = float(self._arc_cfg().get("creatinine_lt_umol_l", 60))
        crcl_cutoff = float(self._arc_cfg().get("crcl_threshold", 130))
        urine_cutoff = float(self._arc_cfg().get("urine_ml_h_gt", 100))
        score = 0
        features = {"age": age, "age_lt_threshold": bool(age is not None and age < age_cutoff), "trauma_or_neuro": self._is_trauma_or_neuro(patient_doc), "creatinine_umol_l": cr_value, "creatinine_low": bool(cr_value is not None and cr_value < cr_cutoff), "crcl_ml_min": crcl, "crcl_elevated": bool(crcl is not None and crcl > crcl_cutoff), "urine_ml_h": urine_ml_h, "urine_high": bool(urine_ml_h is not None and urine_ml_h > urine_cutoff), "on_crrt": on_crrt, "active_aki": has_aki, "creatinine_time": cr_time}
        if features["crcl_elevated"]:
            score += 3
        if features["age_lt_threshold"]:
            score += 2
        if features["trauma_or_neuro"]:
            score += 2
        if features["creatinine_low"]:
            score += 2
        if features["urine_high"]:
            score += 2
        if not on_crrt:
            score += 1
        if not has_aki:
            score += 1
        arc_risk = "high" if score >= 6 else "moderate" if score >= 3 else "low"
        suggestion = None
        if arc_risk == "high":
            suggestion = "ARC 风险高，关键抗菌药物可能暴露不足，建议考虑增量给药或延长输注并结合 TDM/PK 复核。"
        elif arc_risk == "moderate":
            suggestion = "ARC 风险中等，建议关注抗菌药物暴露不足，必要时复核给药方案。"
        evidence = []
        if features["age_lt_threshold"]:
            evidence.append("年龄偏轻")
        if features["trauma_or_neuro"]:
            evidence.append("外伤/神外背景")
        if features["crcl_elevated"]:
            evidence.append(f"CrCl 升高({crcl} mL/min)")
        if features["creatinine_low"]:
            evidence.append(f"肌酐偏低({cr_value})")
        if features["urine_high"]:
            evidence.append(f"尿量偏高({urine_ml_h} mL/h)")
        if not on_crrt:
            evidence.append("未在CRRT")
        if not has_aki:
            evidence.append("无活动性AKI")
        return {"arc_risk": arc_risk, "score": score, "features": features, "explanation": "，".join(evidence) if evidence else "ARC 证据不足", "suggested_pk_adjustment": suggestion}
    async def _persist_arc_risk(self, patient_doc: dict, result: dict, now: datetime) -> None:
        pid_str = self._pid_str(patient_doc.get("_id"))
        payload = {"patient_id": pid_str, "patient_name": patient_doc.get("name"), "bed": patient_doc.get("hisBed"), "dept": patient_doc.get("dept") or patient_doc.get("hisDept"), "score_type": "arc_risk", "score": result.get("score"), "arc_risk": result.get("arc_risk"), "features": result.get("features") or {}, "explanation": result.get("explanation"), "suggested_pk_adjustment": result.get("suggested_pk_adjustment"), "calc_time": now, "updated_at": now, "month": now.strftime("%Y-%m"), "day": now.strftime("%Y-%m-%d")}
        latest = await self.db.col("score_records").find_one({"patient_id": pid_str, "score_type": "arc_risk", "calc_time": {"$gte": now - timedelta(minutes=30)}}, sort=[("calc_time", -1)])
        if latest:
            await self.db.col("score_records").update_one({"_id": latest["_id"]}, {"$set": payload})
        else:
            payload["created_at"] = now
            await self.db.col("score_records").insert_one(payload)

    async def scan_arc_risk(self) -> None:
        from .scanner_arc_risk import ArcRiskScanner

        await ArcRiskScanner(self).scan()
    def _drugexe_names(self, doc: dict) -> list[str]:
        names = []
        for item in doc.get("drugList") or []:
            if isinstance(item, dict) and str(item.get("name") or "").strip():
                names.append(str(item.get("name") or "").strip())
        return names

    def _find_drug_list_entry(self, doc: dict, keywords: list[str]) -> dict | None:
        lowered = [str(k).strip().lower() for k in keywords if str(k).strip()]
        for item in doc.get("drugList") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").lower()
            if any(k in name for k in lowered):
                return item
        return None

    def _latest_action_speed(self, doc: dict) -> tuple[float | None, datetime | None]:
        valid = []
        positive = []
        for item in doc.get("drugActionList") or []:
            if not isinstance(item, dict):
                continue
            speed = _to_float(item.get("speed"))
            if speed is None:
                speed = _to_float(item.get("dripSpeed"))
            if speed is None:
                speed = _to_float(item.get("rate"))
            t = _parse_dt(item.get("time"))
            if speed is not None and t is not None:
                valid.append((t, speed))
                if speed > 0:
                    positive.append((t, speed))
        if positive:
            positive.sort(key=lambda x: x[0])
            return positive[-1][1], positive[-1][0]
        if not valid:
            return None, None
        valid.sort(key=lambda x: x[0])
        return valid[-1][1], valid[-1][0]

    async def _get_recent_drugexe_docs(self, pid, hours: int = 168, limit: int = 800) -> list[dict]:
        pid_str = self._pid_str(pid)
        if not pid_str:
            return []
        since = datetime.now() - timedelta(hours=max(hours, 1))
        cursor = self.db.col("drugExe").find(
            {"pid": pid_str},
            {
                "pid": 1,
                "startTime": 1,
                "orderTime": 1,
                "endTime": 1,
                "executeTime": 1,
                "orderType": 1,
                "liquidAmount": 1,
                "liquidAmountUnit": 1,
                "drugList": 1,
                "drugActionList": 1,
            },
        ).sort("startTime", -1).limit(limit)
        rows: list[dict] = []
        async for doc in cursor:
            latest_action_time = None
            _, latest_action_time = self._latest_action_speed(doc)
            event_time = (
                latest_action_time
                or _parse_dt(doc.get("endTime"))
                or _parse_dt(doc.get("startTime"))
                or _parse_dt(doc.get("orderTime"))
                or _parse_dt(doc.get("executeTime"))
            )
            if event_time and event_time < since:
                continue
            doc["_event_time"] = event_time
            rows.append(doc)
        rows.sort(key=lambda x: x.get("_event_time") or datetime.min)
        return rows

    def _estimate_crcl(self, patient_doc: dict | None, cr_umol_l: float | None) -> float | None:
        if cr_umol_l is None or cr_umol_l <= 0:
            return None
        age = self._patient_age(patient_doc)
        weight = self._get_patient_weight(patient_doc)
        if age is None or weight is None or weight <= 0:
            return None
        scr_mg_dl = cr_umol_l / 88.4
        if scr_mg_dl <= 0:
            return None
        sex_text = str((patient_doc or {}).get("gender") or (patient_doc or {}).get("hisSex") or "").lower()
        female_factor = 0.85 if any(k in sex_text for k in ["f", "female", "女"]) else 1.0
        crcl = ((140.0 - age) * weight * female_factor) / max(72.0 * scr_mg_dl, 1e-6)
        return round(max(crcl, 0.0), 2)

    async def _current_drug_regimen(self, pid, drug_key: str) -> dict | None:
        cfg = self._drug_rule_cfg(drug_key)
        keywords = cfg.get("keywords", []) if isinstance(cfg.get("keywords"), list) else []
        if not keywords:
            return None
        docs = await self._get_recent_drugexe_docs(pid, hours=int(cfg.get("lookback_hours", 168)), limit=800)
        matched = [doc for doc in docs if self._match_any_text(" ".join(self._drugexe_names(doc)), keywords)]
        if not matched:
            return None
        latest = matched[-1]
        main = self._find_drug_list_entry(latest, keywords)
        if not main:
            return None
        speed, speed_time = self._latest_action_speed(latest)
        start_time = speed_time or _parse_dt(latest.get("startTime")) or _parse_dt(latest.get("orderTime"))
        liquid_amount = _to_float(main.get("liquidAmount"))
        if liquid_amount is None:
            liquid_amount = _to_float(latest.get("liquidAmount"))
        return {"drug": drug_key, "display_name": str(main.get("name") or ""), "dose": _to_float(main.get("dose")), "dose_unit": str(main.get("unit") or ""), "liquid_amount_ml": liquid_amount, "speed_ml_h": speed, "start_time": start_time, "order_type": latest.get("orderType"), "doc_id": latest.get("_id"), "raw": latest}

    def _adjusted_cl(self, base_cl: float, *, crcl: float | None, weight: float | None, albumin: float | None, arc_risk: str, on_crrt: bool, drug_key: str) -> float:
        cl = max(base_cl, 0.1)
        if crcl is not None:
            # 这里是工程化的一室模型近似，不是逐篇文献原始 PopPK 公式。
            ref = float(self._drug_rule_cfg(drug_key).get("crcl_ref", 100.0))
            cl *= max((crcl / max(ref, 1e-6)) ** 0.5, 0.3)
        if weight is not None:
            ref_wt = float(self._drug_rule_cfg(drug_key).get("weight_ref", 70.0))
            cl *= max((weight / max(ref_wt, 1e-6)) ** 0.25, 0.5)
        if albumin is not None and albumin < 30:
            cl *= 1.1
        if arc_risk == "high":
            cl *= float(self._drug_rule_cfg(drug_key).get("arc_cl_multiplier_high", 1.25))
        elif arc_risk == "moderate":
            cl *= float(self._drug_rule_cfg(drug_key).get("arc_cl_multiplier_moderate", 1.1))
        if on_crrt:
            # 当前版本未读取 effluent_rate 做定量 CL_crrt 估算，仅作保守简化。
            cl *= float(self._drug_rule_cfg(drug_key).get("crrt_cl_multiplier", 0.8))
        return round(max(cl, 0.1), 3)

    def _adjusted_vd(self, base_vd: float, *, weight: float | None, albumin: float | None, drug_key: str) -> float:
        vd = max(base_vd, 0.1)
        if weight is not None:
            ref_wt = float(self._drug_rule_cfg(drug_key).get("weight_ref", 70.0))
            vd *= max(weight / max(ref_wt, 1e-6), 0.4)
        if albumin is not None and albumin < 30:
            vd *= float(self._drug_rule_cfg(drug_key).get("low_albumin_vd_multiplier", 1.15))
        return round(max(vd, 0.1), 3)

    def _predict_vanco_exposure(self, dose_mg: float | None, cl_l_h: float, vd_l: float) -> dict:
        if dose_mg is None or dose_mg <= 0:
            return {"trough": None, "auc24": None}
        tau_h = float(self._drug_rule_cfg("vancomycin").get("tau_h", 12.0))
        auc24 = (dose_mg * (24.0 / max(tau_h, 1e-6))) / max(cl_l_h, 1e-6)
        k = cl_l_h / max(vd_l, 1e-6)
        trough = (dose_mg / max(vd_l, 1e-6)) * math.exp(-k * tau_h)
        return {"trough": round(max(trough, 0.0), 2), "auc24": round(max(auc24, 0.0), 2)}

    def _predict_beta_lactam_exposure(self, dose: float | None, cl_l_h: float, vd_l: float, drug_key: str) -> dict:
        if dose is None or dose <= 0:
            return {"trough": None, "ft_above_mic": None}
        cfg = self._drug_rule_cfg(drug_key)
        tau_h = float(cfg.get("tau_h", 8.0))
        mic = float(cfg.get("mic", 1.0))
        k = cl_l_h / max(vd_l, 1e-6)
        trough = (dose / max(vd_l, 1e-6)) * math.exp(-k * tau_h)
        ft_mic = None
        if k > 0:
            try:
                c0 = dose / max(vd_l, 1e-6)
                ft_mic = max(0.0, min(1.0, math.log(c0 / mic) / k / tau_h)) if c0 > mic > 0 else 0.0
            except Exception:
                ft_mic = None
        return {"trough": round(max(trough, 0.0), 2), "ft_above_mic": round(ft_mic, 3) if ft_mic is not None else None}
    async def evaluate_antimicrobial_pk(self, patient_doc: dict, drug_name: str, now: datetime) -> dict | None:
        pid = patient_doc.get("_id")
        if not pid:
            return None
        his_pid = str(patient_doc.get("hisPid") or "").strip() or None
        regimen = await self._current_drug_regimen(pid, drug_name)
        if not regimen:
            return None
        arc = await self.assess_arc_risk(patient_doc, now)
        cr, _ = await self._latest_lab_value(his_pid, "cr", hours=48)
        albumin, _ = await self._latest_lab_value(his_pid, "albumin", hours=168)
        weight = self._get_patient_weight(patient_doc)
        crcl = self._estimate_crcl(patient_doc, cr)
        on_crrt = await self._is_on_crrt(pid)
        cfg = self._drug_rule_cfg(drug_name)
        if not cfg:
            return None
        cl = self._adjusted_cl(float(cfg.get("base_cl_l_h", 4.0)), crcl=crcl, weight=weight, albumin=albumin, arc_risk=arc.get("arc_risk"), on_crrt=on_crrt, drug_key=drug_name)
        vd = self._adjusted_vd(float(cfg.get("base_vd_l", 40.0)), weight=weight, albumin=albumin, drug_key=drug_name)
        dose = _to_float(regimen.get("dose"))
        dose_unit = str(regimen.get("dose_unit") or "").lower()
        if dose is not None and dose_unit == "g":
            dose *= 1000.0
        if drug_name == "vancomycin":
            predicted = self._predict_vanco_exposure(dose, cl, vd)
            mic = float(cfg.get("mic", 1.0))
            auc24 = predicted.get("auc24")
            attainment = bool(auc24 is not None and float(cfg.get("auc_mic_target_low", 400.0)) <= (auc24 / max(mic, 1e-6)) <= float(cfg.get("auc_mic_target_high", 600.0)))
            recommendation = "预计万古霉素暴露达标，建议维持并结合 TDM 复核。" if attainment else "预计万古霉素暴露不足，建议复核剂量/间隔并结合 TDM。"
        else:
            predicted = self._predict_beta_lactam_exposure(dose, cl, vd, drug_name)
            attainment = bool(predicted.get("ft_above_mic") is not None and predicted.get("ft_above_mic") >= float(cfg.get("ft_mic_target", 0.5)))
            recommendation = "预计目标暴露基本达标，建议维持当前方案。" if attainment else "预计暴露不足，建议复核剂量和输注策略。"
            if not attainment and arc.get("arc_risk") == "high":
                recommendation = "预计暴露不足且 ARC 风险高，建议考虑增加剂量或延长输注。"
        confidence = 0.5 + (0.15 if crcl is not None else 0) + (0.15 if weight is not None else 0) + (0.1 if albumin is not None else 0) + (0.1 if regimen.get("speed_ml_h") is not None else 0)
        return {"drug": drug_name, "regimen": {k: v for k, v in regimen.items() if k != "raw"}, "pk_params": {"cl": cl, "vd": vd, "crcl": crcl, "albumin": albumin, "on_crrt": on_crrt}, "arc_risk": arc.get("arc_risk"), "predicted_exposure": predicted, "target_attainment": attainment, "recommendation": recommendation, "confidence": round(min(confidence, 0.95), 3)}

    async def _persist_antimicrobial_pk(self, patient_doc: dict, result: dict, now: datetime) -> None:
        pid_str = self._pid_str(patient_doc.get("_id"))
        payload = {"patient_id": pid_str, "patient_name": patient_doc.get("name"), "bed": patient_doc.get("hisBed"), "dept": patient_doc.get("dept") or patient_doc.get("hisDept"), "score_type": "antimicrobial_pk", "drug": result.get("drug"), "regimen": result.get("regimen") or {}, "pk_params": result.get("pk_params") or {}, "predicted_exposure": result.get("predicted_exposure") or {}, "target_attainment": result.get("target_attainment"), "recommendation": result.get("recommendation"), "confidence": result.get("confidence"), "calc_time": now, "updated_at": now, "month": now.strftime("%Y-%m"), "day": now.strftime("%Y-%m-%d")}
        latest = await self.db.col("score_records").find_one({"patient_id": pid_str, "score_type": "antimicrobial_pk", "drug": result.get("drug"), "calc_time": {"$gte": now - timedelta(minutes=30)}}, sort=[("calc_time", -1)])
        if latest:
            await self.db.col("score_records").update_one({"_id": latest["_id"]}, {"$set": payload})
        else:
            payload["created_at"] = now
            await self.db.col("score_records").insert_one(payload)

    async def scan_antimicrobial_pk(self) -> None:
        from .scanner_antimicrobial_pk import AntimicrobialPkScanner

        await AntimicrobialPkScanner(self).scan()
    async def _find_latest_vanco_tdm(self, his_pid: str | None, since: datetime) -> dict | None:
        if not his_pid:
            return None
        keywords = self._tdm_cfg().get("vanco_keywords", ["万古霉素", "vancomycin", "vanco", "万古谷浓度"])
        cursor = self.db.dc_col("VI_ICU_EXAM_ITEM").find({"hisPid": his_pid}).sort("authTime", -1).limit(800)
        for doc in [d async for d in cursor]:
            t = _parse_dt(doc.get("authTime")) or _parse_dt(doc.get("collectTime")) or _parse_dt(doc.get("reportTime")) or _parse_dt(doc.get("time"))
            if not t or t < since:
                continue
            name = " ".join(str(doc.get(k) or "") for k in ("itemCnName", "itemName", "itemCode")).lower()
            if not any(str(k).strip().lower() in name for k in keywords if str(k).strip()):
                continue
            value = _to_float(doc.get("result") or doc.get("resultValue"))
            if value is None:
                continue
            return {"time": t, "value": value, "name": name, "raw": doc}
        return None

    async def update_vanco_tdm_state(self, patient_doc: dict, now: datetime) -> dict | None:
        pid = patient_doc.get("_id")
        if not pid:
            return None
        his_pid = str(patient_doc.get("hisPid") or "").strip() or None
        sample = await self._find_latest_vanco_tdm(his_pid, now - timedelta(days=7))
        if not sample:
            return None
        pop = await self.evaluate_antimicrobial_pk(patient_doc, "vancomycin", now)
        if not pop:
            return None
        sample_value = _to_float(sample.get("value"))
        predicted_trough = _to_float((pop.get("predicted_exposure") or {}).get("trough"))
        pop_cl = _to_float((pop.get("pk_params") or {}).get("cl")) or 4.0
        omega_sq = float(self._tdm_cfg().get("omega_cl_sq", 0.15))
        sigma_sq = float(self._tdm_cfg().get("sigma_sq", 0.04))
        if sample_value not in (None, 0) and predicted_trough not in (None, 0):
            log_ratio = math.log(max(predicted_trough, 0.01) / max(sample_value, 0.01))
            weight = omega_sq / max(omega_sq + sigma_sq, 1e-6)
            delta_cl = weight * log_ratio
            individual_cl = round(max(pop_cl * math.exp(delta_cl), 0.1), 3)
        else:
            log_ratio = None
            weight = None
            individual_cl = pop_cl
        vd = _to_float((pop.get("pk_params") or {}).get("vd")) or 40.0
        dose = _to_float((pop.get("regimen") or {}).get("dose"))
        dose_unit = str((pop.get("regimen") or {}).get("dose_unit") or "").lower()
        if dose is not None and dose_unit == "g":
            dose *= 1000.0
        adjusted = self._predict_vanco_exposure(dose, individual_cl, vd)
        auc24 = adjusted.get("auc24")
        mic = float(self._tdm_cfg().get("vanco_mic", 1.0))
        auc_mic = auc24 / max(mic, 1e-6) if auc24 is not None else None
        low = float(self._tdm_cfg().get("auc_mic_target_low", 400.0))
        high = float(self._tdm_cfg().get("auc_mic_target_high", 600.0))
        attainment = bool(auc_mic is not None and low <= auc_mic <= high)
        recommendation = "万古霉素 AUC/MIC 预计在目标范围内，建议维持并持续监测。"
        if auc_mic is None:
            recommendation = "万古霉素 TDM 数据不足，建议结合群体模型与临床复核。"
        elif auc_mic < low:
            recommendation = "万古霉素 AUC/MIC 预计不足，建议增加暴露并复核下一次浓度。"
        elif auc_mic > high:
            recommendation = "万古霉素 AUC/MIC 预计过高，建议降低暴露并警惕毒性。"
        return {"drug": "vancomycin", "sample_time": sample.get("time"), "sample_value": sample_value, "population_pk": pop.get("pk_params") or {}, "individual_pk": {"cl": individual_cl, "vd": vd}, "bayes_update": {"omega_cl_sq": omega_sq, "sigma_sq": sigma_sq, "shrinkage_weight": round(weight, 4) if weight is not None else None, "log_ratio": round(log_ratio, 4) if log_ratio is not None else None}, "auc24": auc24, "predicted_trough_next": adjusted.get("trough"), "target_attainment": attainment, "recommendation": recommendation}

    async def _persist_vanco_tdm(self, patient_doc: dict, result: dict, now: datetime) -> None:
        pid_str = self._pid_str(patient_doc.get("_id"))
        payload = {"patient_id": pid_str, "patient_name": patient_doc.get("name"), "bed": patient_doc.get("hisBed"), "dept": patient_doc.get("dept") or patient_doc.get("hisDept"), "score_type": "tdm_pk_state", "drug": "vancomycin", "sample_time": result.get("sample_time"), "sample_value": result.get("sample_value"), "population_pk": result.get("population_pk") or {}, "individual_pk": result.get("individual_pk") or {}, "auc24": result.get("auc24"), "predicted_trough_next": result.get("predicted_trough_next"), "target_attainment": result.get("target_attainment"), "recommendation": result.get("recommendation"), "calc_time": now, "updated_at": now, "month": now.strftime("%Y-%m"), "day": now.strftime("%Y-%m-%d")}
        latest = await self.db.col("score_records").find_one({"patient_id": pid_str, "score_type": "tdm_pk_state", "drug": "vancomycin", "calc_time": {"$gte": now - timedelta(hours=12)}}, sort=[("calc_time", -1)])
        if latest:
            await self.db.col("score_records").update_one({"_id": latest["_id"]}, {"$set": payload})
        else:
            payload["created_at"] = now
            await self.db.col("score_records").insert_one(payload)

    async def scan_vanco_tdm_closed_loop(self) -> None:
        from .scanner_vanco_tdm_closed_loop import VancoTdmClosedLoopScanner

        await VancoTdmClosedLoopScanner(self).scan()
