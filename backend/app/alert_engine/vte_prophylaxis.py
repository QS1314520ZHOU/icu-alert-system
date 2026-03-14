"""VTE 预防评估与遗漏监测"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _to_num(value: Any) -> float | None:
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


class VteProphylaxisMixin:
    def _parse_age_years(self, patient_doc: dict) -> float | None:
        for key in ("age", "hisAge"):
            raw = patient_doc.get(key)
            if raw is None:
                continue
            if isinstance(raw, (int, float)):
                return float(raw)
            s = str(raw).strip()
            if not s:
                continue
            if s.endswith("天"):
                d = _to_num(s)
                return d / 365.0 if d is not None else None
            if s.endswith("月"):
                m = _to_num(s)
                return m / 12.0 if m is not None else None
            n = _to_num(s)
            if n is not None:
                return n
        return None

    def _parse_bmi(self, patient_doc: dict) -> float | None:
        for key in ("bmi", "BMI", "bodyMassIndex"):
            n = _to_num(patient_doc.get(key))
            if n is not None and 10 <= n <= 80:
                return n
        weight = self._get_patient_weight(patient_doc)
        height = None
        for key in ("height", "bodyHeight", "heightCm", "height_cm"):
            h = _to_num(patient_doc.get(key))
            if h is not None:
                height = h
                break
        if weight is None or height is None:
            return None
        h_m = height / 100.0 if height > 3 else height
        if h_m <= 0:
            return None
        bmi = weight / (h_m * h_m)
        return round(bmi, 2) if 10 <= bmi <= 80 else None

    def _text_join(self, patient_doc: dict, keys: list[str]) -> str:
        return " ".join(str(patient_doc.get(k) or "") for k in keys).lower()

    def _contains_any(self, text: str, keywords: list[str]) -> bool:
        t = str(text or "").lower()
        return any(str(k).strip().lower() in t for k in keywords if str(k).strip())

    def _has_recent_surgery(self, patient_doc: dict, now: datetime, days: int = 30) -> bool:
        for key in ("surgeryTime", "operationTime", "lastOperationTime", "recentSurgeryTime"):
            t = _parse_dt(patient_doc.get(key))
            if t and (now - t).total_seconds() <= days * 24 * 3600:
                return True
        txt = self._text_join(
            patient_doc,
            [
                "clinicalDiagnosis", "admissionDiagnosis", "surgeryHistory",
                "operationHistory", "recentSurgery", "history", "diagnosisHistory",
            ],
        )
        kw = self._get_cfg_list(
            ("alert_engine", "vte_prophylaxis", "recent_surgery_keywords"),
            ["术后", "手术", "surgery", "trauma", "外伤", "骨折手术", "创伤"],
        )
        return self._contains_any(txt, kw)

    async def _get_recent_drug_docs(self, pid_str: str, since: datetime) -> list[dict]:
        cursor = self.db.col("drugExe").find(
            {"pid": pid_str},
            {
                "executeTime": 1, "startTime": 1, "orderTime": 1,
                "drugName": 1, "orderName": 1, "route": 1, "routeName": 1, "orderType": 1,
            },
        ).sort("executeTime", -1).limit(1200)
        docs: list[dict] = []
        async for doc in cursor:
            t = _parse_dt(doc.get("executeTime")) or _parse_dt(doc.get("startTime")) or _parse_dt(doc.get("orderTime"))
            if not t or t < since:
                continue
            doc["_event_time"] = t
            docs.append(doc)
        return docs

    def _drug_name_text(self, doc: dict) -> str:
        return " ".join(str(doc.get(k) or "") for k in ("drugName", "orderName", "route", "routeName", "orderType")).lower()

    def _has_drug_prophylaxis(self, docs: list[dict]) -> bool:
        lmwh_kw = self._get_cfg_list(
            ("alert_engine", "vte_prophylaxis", "pharm_prophylaxis_keywords"),
            ["依诺肝素", "那曲肝素", "达肝素", "低分子肝素", "普通肝素", "肝素", "fondaparinux", "依度沙班", "利伐沙班"],
        )
        return any(self._contains_any(self._drug_name_text(d), lmwh_kw) for d in docs)

    def _has_hormonal_tx(self, docs: list[dict]) -> bool:
        kw = self._get_cfg_list(
            ("alert_engine", "vte_prophylaxis", "hormonal_treatment_keywords"),
            ["雌激素", "孕激素", "激素替代", "tamoxifen", "他莫昔芬"],
        )
        return any(self._contains_any(self._drug_name_text(d), kw) for d in docs)

    async def _has_mechanical_prophylaxis(self, pid_str: str, since: datetime) -> bool:
        mech_kw = self._get_cfg_list(
            ("alert_engine", "vte_prophylaxis", "mechanical_prophylaxis_keywords"),
            ["间歇充气", "ipc", "scd", "气压治疗", "弹力袜", "机械预防", "下肢气压泵", "梯度压力袜"],
        )
        mech_order_kw = self._get_cfg_list(
            ("alert_engine", "vte_prophylaxis", "mechanical_order_keywords"),
            mech_kw,
        )
        neg_kw = self._get_cfg_list(
            ("alert_engine", "vte_prophylaxis", "mechanical_negative_keywords"),
            ["未做", "未行", "未实施", "none", "no", "否"],
        )

        # 1) 护理/床旁记录
        cursor = self.db.col("bedside").find(
            {"pid": pid_str, "time": {"$gte": since}},
            {"time": 1, "code": 1, "name": 1, "paramName": 1, "itemName": 1, "remark": 1, "strVal": 1},
        ).sort("time", -1).limit(2500)
        async for doc in cursor:
            text = " ".join(str(doc.get(k) or "") for k in ("code", "name", "paramName", "itemName", "remark", "strVal")).lower()
            if not text:
                continue
            if self._contains_any(text, mech_kw) and not self._contains_any(text, neg_kw):
                return True

        # 2) 医嘱/执行记录：扩大到 orderName/route/orderType 等文本
        drug_docs = await self._get_recent_drug_docs(pid_str, since)
        for doc in drug_docs:
            text = self._drug_name_text(doc)
            if self._contains_any(text, mech_order_kw) and not self._contains_any(text, neg_kw):
                return True

        # 3) 文本兜底（部分系统将护理措施写在自由文本中）
        text_events = await self._get_recent_text_events(pid_str, mech_kw, hours=max(1, int((datetime.now() - since).total_seconds() / 3600)), limit=800)
        for doc in text_events:
            text = " ".join(str(doc.get(k) or "") for k in ("code", "strVal", "value")).lower()
            if self._contains_any(text, mech_kw) and not self._contains_any(text, neg_kw):
                return True
        return False

    async def _has_active_bleeding_alert(self, pid_str: str, lookback_hours: int = 72) -> bool:
        since = datetime.now() - timedelta(hours=lookback_hours)
        bleed_types = self._get_cfg_list(
            ("alert_engine", "vte_prophylaxis", "active_bleeding_alert_types"),
            ["gi_bleeding"],
        )
        cnt = await self.db.col("alert_records").count_documents(
            {
                "patient_id": pid_str,
                "alert_type": {"$in": bleed_types},
                "created_at": {"$gte": since},
            }
        )
        return cnt > 0

    async def _immobility_hours(self, patient_doc: dict, pid, now: datetime) -> float:
        # 优先由床边记录判断，兜底用入科时长
        bedrest_kw = self._get_cfg_list(
            ("alert_engine", "vte_prophylaxis", "immobility_keywords"),
            ["卧床", "制动", "绝对卧床", "不能下床", "bed rest", "immobile", "paralysis", "瘫痪", "昏迷"],
        )
        mobile_kw = self._get_cfg_list(
            ("alert_engine", "vte_prophylaxis", "mobility_positive_keywords"),
            ["下床", "活动", "行走", "可活动", "ambulation", "walking"],
        )
        since = now - timedelta(hours=96)
        pid_str = str(pid)
        cursor = self.db.col("bedside").find(
            {"pid": pid_str, "time": {"$gte": since}},
            {"time": 1, "code": 1, "name": 1, "paramName": 1, "itemName": 1, "remark": 1, "strVal": 1},
        ).sort("time", -1).limit(800)

        latest_mobile: datetime | None = None
        latest_immobile: datetime | None = None
        async for doc in cursor:
            t = _parse_dt(doc.get("time"))
            if not t:
                continue
            text = " ".join(str(doc.get(k) or "") for k in ("code", "name", "paramName", "itemName", "remark", "strVal")).lower()
            if not text:
                continue
            if self._contains_any(text, mobile_kw):
                latest_mobile = t if latest_mobile is None else max(latest_mobile, t)
            if self._contains_any(text, bedrest_kw):
                latest_immobile = t if latest_immobile is None else max(latest_immobile, t)

        if latest_mobile and (not latest_immobile or latest_mobile >= latest_immobile):
            return 0.0

        if latest_immobile:
            # 向前追溯起点
            earliest = latest_immobile
            cursor2 = self.db.col("bedside").find(
                {"pid": pid_str, "time": {"$gte": since}},
                {"time": 1, "code": 1, "name": 1, "paramName": 1, "itemName": 1, "remark": 1, "strVal": 1},
            ).sort("time", 1).limit(800)
            async for doc in cursor2:
                t = _parse_dt(doc.get("time"))
                if not t:
                    continue
                text = " ".join(str(doc.get(k) or "") for k in ("code", "name", "paramName", "itemName", "remark", "strVal")).lower()
                if self._contains_any(text, bedrest_kw):
                    earliest = t
                    break
            return round(max(0.0, (now - earliest).total_seconds() / 3600.0), 2)

        # 兜底: 根据临床信息与入科时长估计
        rass = await self._get_latest_assessment(pid, "rass")
        clinical_txt = self._text_join(
            patient_doc,
            ["clinicalDiagnosis", "admissionDiagnosis", "nursingLevel", "status", "activityLevel"],
        )
        likely_immobile = (
            (rass is not None and rass <= -4)
            or self._contains_any(clinical_txt, bedrest_kw)
        )
        if not likely_immobile:
            return 0.0
        adm = _parse_dt(patient_doc.get("icuAdmissionTime"))
        if not adm:
            return 0.0
        return round(max(0.0, (now - adm).total_seconds() / 3600.0), 2)

    async def scan_vte_prophylaxis(self) -> None:
        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        cfg = self.config.yaml_cfg.get("alert_engine", {}).get("vte_prophylaxis", {})
        padua_high = float(cfg.get("padua_high_risk_score", 4))
        caprini_high = float(cfg.get("caprini_high_risk_score", 5))
        immobility_hours_threshold = float(cfg.get("immobility_hours_threshold", 48))
        prophylaxis_lookback_hours = float(cfg.get("prophylaxis_lookback_hours", 72))

        padua_w = cfg.get("padua_weights", {}) if isinstance(cfg, dict) else {}
        caprini_w = cfg.get("caprini_weights", {}) if isinstance(cfg, dict) else {}

        # 关键词
        kw_cancer = self._get_cfg_list(("alert_engine", "vte_prophylaxis", "cancer_keywords"), ["恶性肿瘤", "癌", "cancer", "肿瘤"])
        kw_prev_vte = self._get_cfg_list(("alert_engine", "vte_prophylaxis", "previous_vte_keywords"), ["静脉血栓", "肺栓塞", "dvt", "pe", "vte"])
        kw_thrombophilia = self._get_cfg_list(("alert_engine", "vte_prophylaxis", "thrombophilia_keywords"), ["易栓症", "抗磷脂", "thrombophilia"])
        kw_heart_resp_fail = self._get_cfg_list(("alert_engine", "vte_prophylaxis", "heart_resp_failure_keywords"), ["心衰", "呼衰", "heart failure", "respiratory failure"])
        kw_acute_mi_stroke = self._get_cfg_list(("alert_engine", "vte_prophylaxis", "acute_mi_stroke_keywords"), ["急性心梗", "脑卒中", "stroke", "mi"])
        kw_infection_rheum = self._get_cfg_list(("alert_engine", "vte_prophylaxis", "infection_rheum_keywords"), ["感染", "sepsis", "肺炎", "风湿", "rheum"])

        patient_cursor = self.db.col("patient").find(
            self._active_patient_query(),
            {
                "_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "deptCode": 1,
                "age": 1, "hisAge": 1, "weight": 1, "bodyWeight": 1, "body_weight": 1, "weightKg": 1, "weight_kg": 1,
                "height": 1, "heightCm": 1, "height_cm": 1, "bmi": 1, "BMI": 1,
                "clinicalDiagnosis": 1, "admissionDiagnosis": 1, "nursingLevel": 1, "icuAdmissionTime": 1,
                "surgeryHistory": 1, "operationHistory": 1, "recentSurgery": 1, "history": 1, "diagnosisHistory": 1,
                "surgeryTime": 1, "operationTime": 1,
            },
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        now = datetime.now()
        triggered = 0

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            his_pid = patient_doc.get("hisPid")

            age = self._parse_age_years(patient_doc)
            bmi = self._parse_bmi(patient_doc)
            txt = self._text_join(
                patient_doc,
                [
                    "clinicalDiagnosis", "admissionDiagnosis", "nursingLevel",
                    "surgeryHistory", "operationHistory", "recentSurgery", "history", "diagnosisHistory",
                ],
            )
            immobility_hours = await self._immobility_hours(patient_doc, pid, now)
            reduced_mobility = immobility_hours >= 24
            recent_surgery = self._has_recent_surgery(patient_doc, now, days=30)

            # 近72h用药与机械预防状态
            since_proph = now - timedelta(hours=prophylaxis_lookback_hours)
            drug_docs = await self._get_recent_drug_docs(pid_str, since_proph)
            has_drug_proph = self._has_drug_prophylaxis(drug_docs)
            has_mech_proph = await self._has_mechanical_prophylaxis(pid_str, since_proph)
            has_hormone_tx = self._has_hormonal_tx(drug_docs)

            # Padua score
            padua_items = {
                "active_cancer": self._contains_any(txt, kw_cancer),
                "previous_vte": self._contains_any(txt, kw_prev_vte),
                "reduced_mobility": reduced_mobility,
                "thrombophilia": self._contains_any(txt, kw_thrombophilia),
                "recent_trauma_surgery": recent_surgery,
                "age_ge_70": age is not None and age >= 70,
                "heart_or_resp_failure": self._contains_any(txt, kw_heart_resp_fail),
                "acute_mi_or_stroke": self._contains_any(txt, kw_acute_mi_stroke),
                "acute_infection_or_rheum": self._contains_any(txt, kw_infection_rheum),
                "obesity_bmi_ge_30": bmi is not None and bmi >= 30,
                "hormonal_treatment": has_hormone_tx,
            }
            padua_defaults = {
                "active_cancer": 3, "previous_vte": 3, "reduced_mobility": 3, "thrombophilia": 3,
                "recent_trauma_surgery": 2, "age_ge_70": 1, "heart_or_resp_failure": 1,
                "acute_mi_or_stroke": 1, "acute_infection_or_rheum": 1, "obesity_bmi_ge_30": 1,
                "hormonal_treatment": 1,
            }
            padua_score = 0.0
            for k, matched in padua_items.items():
                if matched:
                    padua_score += float(padua_w.get(k, padua_defaults.get(k, 0)))

            # Caprini score（简化版）
            caprini_score = 0.0
            caprini_details: list[str] = []
            if age is not None:
                if 41 <= age <= 60:
                    caprini_score += float(caprini_w.get("age_41_60", 1))
                    caprini_details.append("age_41_60")
                elif 61 <= age <= 74:
                    caprini_score += float(caprini_w.get("age_61_74", 2))
                    caprini_details.append("age_61_74")
                elif age >= 75:
                    caprini_score += float(caprini_w.get("age_ge_75", 3))
                    caprini_details.append("age_ge_75")
            if bmi is not None and bmi > 25:
                caprini_score += float(caprini_w.get("bmi_gt_25", 1))
                caprini_details.append("bmi_gt_25")
            if immobility_hours >= 72:
                caprini_score += float(caprini_w.get("bedrest_gt_72h", 1))
                caprini_details.append("bedrest_gt_72h")
            if recent_surgery:
                caprini_score += float(caprini_w.get("recent_surgery", 2))
                caprini_details.append("recent_surgery")
            if padua_items["active_cancer"]:
                caprini_score += float(caprini_w.get("active_cancer", 2))
                caprini_details.append("active_cancer")
            if padua_items["previous_vte"]:
                caprini_score += float(caprini_w.get("previous_vte", 3))
                caprini_details.append("previous_vte")
            if padua_items["thrombophilia"]:
                caprini_score += float(caprini_w.get("thrombophilia", 3))
                caprini_details.append("thrombophilia")
            if padua_items["acute_mi_or_stroke"]:
                caprini_score += float(caprini_w.get("acute_stroke_or_mi", 5))
                caprini_details.append("acute_stroke_or_mi")

            high_risk = (padua_score >= padua_high) or (caprini_score >= caprini_high)

            # 出血风险联动
            bleeding_alert = await self._has_active_bleeding_alert(pid_str, lookback_hours=72)
            labs = await self._get_latest_labs_map(his_pid, lookback_hours=72) if his_pid else {}
            plt = labs.get("plt", {}).get("value") if labs else None
            inr = labs.get("inr", {}).get("value") if labs else None
            bleeding_labs = (plt is not None and float(plt) < 50) or (inr is not None and float(inr) > 2)
            bleeding_risk = bleeding_alert or bleeding_labs

            # (2) 高风险 + 预防遗漏
            if high_risk:
                if bleeding_risk:
                    # 有出血风险时：建议仅机械预防
                    rule_id = "VTE_BLEEDING_LINKAGE"
                    if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        sev = "high" if has_drug_proph else "warning"
                        alert = await self._create_alert(
                            rule_id=rule_id,
                            name="VTE预防与出血风险联动建议",
                            category="vte_prophylaxis",
                            alert_type="vte_bleeding_linkage",
                            severity=sev,
                            parameter="vte_bleeding_balance",
                            condition={"bleeding_risk": True, "recommendation": "mechanical_only"},
                            value=padua_score,
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=None,
                            source_time=now,
                            extra={
                                "padua_score": round(padua_score, 2),
                                "caprini_score": round(caprini_score, 2),
                                "has_drug_prophylaxis": has_drug_proph,
                                "has_mechanical_prophylaxis": has_mech_proph,
                                "platelet": plt,
                                "inr": inr,
                                "active_bleeding_alert": bleeding_alert,
                                "advice": "建议仅机械预防，不建议药物预防。",
                            },
                        )
                        if alert:
                            triggered += 1

                    if not has_mech_proph:
                        rule_id = "VTE_PROPHYLAXIS_OMISSION_BLEED"
                        if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                            alert = await self._create_alert(
                                rule_id=rule_id,
                                name="VTE机械预防遗漏(出血风险患者)",
                                category="vte_prophylaxis",
                                alert_type="vte_prophylaxis_omission",
                                severity="high",
                                parameter="vte_prophylaxis",
                                condition={"padua_gte": padua_high, "mechanical_required": True},
                                value=padua_score,
                                patient_id=pid_str,
                                patient_doc=patient_doc,
                                device_id=None,
                                source_time=now,
                                extra={
                                    "padua_score": round(padua_score, 2),
                                    "caprini_score": round(caprini_score, 2),
                                    "has_drug_prophylaxis": has_drug_proph,
                                    "has_mechanical_prophylaxis": has_mech_proph,
                                    "bleeding_risk": True,
                                },
                            )
                            if alert:
                                triggered += 1
                else:
                    if not has_drug_proph and not has_mech_proph:
                        rule_id = "VTE_PROPHYLAXIS_OMISSION"
                        if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                            alert = await self._create_alert(
                                rule_id=rule_id,
                                name="VTE预防遗漏",
                                category="vte_prophylaxis",
                                alert_type="vte_prophylaxis_omission",
                                severity="high",
                                parameter="vte_prophylaxis",
                                condition={"padua_gte": padua_high, "no_pharm": True, "no_mechanical": True},
                                value=padua_score,
                                patient_id=pid_str,
                                patient_doc=patient_doc,
                                device_id=None,
                                source_time=now,
                                extra={
                                    "padua_score": round(padua_score, 2),
                                    "caprini_score": round(caprini_score, 2),
                                    "has_drug_prophylaxis": False,
                                    "has_mechanical_prophylaxis": False,
                                    "immobility_hours": immobility_hours,
                                },
                            )
                            if alert:
                                triggered += 1

            # (4) 完全卧床 >48h 且无任何预防措施
            if immobility_hours >= immobility_hours_threshold and (not has_drug_proph) and (not has_mech_proph):
                rule_id = "VTE_IMMOBILITY_NO_PROPHYLAXIS"
                if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    sev = "high" if high_risk else "warning"
                    alert = await self._create_alert(
                        rule_id=rule_id,
                        name="长期制动且未行VTE预防",
                        category="vte_prophylaxis",
                        alert_type="vte_immobility_no_prophylaxis",
                        severity=sev,
                        parameter="immobility_hours",
                        condition={"operator": ">=", "threshold_hours": immobility_hours_threshold},
                        value=immobility_hours,
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        device_id=None,
                        source_time=now,
                        extra={
                            "immobility_hours": immobility_hours,
                            "padua_score": round(padua_score, 2),
                            "caprini_score": round(caprini_score, 2),
                            "has_drug_prophylaxis": has_drug_proph,
                            "has_mechanical_prophylaxis": has_mech_proph,
                            "padua_items": padua_items,
                            "caprini_items": caprini_details,
                        },
                    )
                    if alert:
                        triggered += 1

        if triggered > 0:
            self._log_info("VTE预防", triggered)
