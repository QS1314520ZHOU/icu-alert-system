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
        from .scanner_vte_prophylaxis import VteProphylaxisScanner

        await VteProphylaxisScanner(self).scan()
