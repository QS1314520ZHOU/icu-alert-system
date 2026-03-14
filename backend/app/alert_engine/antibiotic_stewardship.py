"""抗菌药物管理（Antibiotic Stewardship）"""
from __future__ import annotations

import re
import time
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


def _hours_between(a: datetime | None, b: datetime | None) -> float:
    if not a or not b:
        return 0.0
    return max(0.0, (b - a).total_seconds() / 3600.0)


class AntibioticStewardshipMixin:
    def _ensure_abx_runtime_state(self) -> None:
        if not hasattr(self, "_abx_dictionary_cache"):
            self._abx_dictionary_cache = {
                "expires_at": 0.0,
                "antibiotic_names": [],
                "broad_spectrum_names": [],
            }

    def _get_rule_cfg_list(self, key: str, default: list[str]) -> list[str]:
        return self._get_cfg_list(("alert_engine", "antibiotic_stewardship", key), default)

    def _text_has_any(self, text: str, keywords: list[str]) -> bool:
        t = str(text or "").lower()
        return any(str(k).lower() in t for k in keywords if str(k).strip())

    def _event_time(self, doc: dict) -> datetime | None:
        return (
            _parse_dt(doc.get("executeTime"))
            or _parse_dt(doc.get("startTime"))
            or _parse_dt(doc.get("orderTime"))
        )

    async def _load_antibiotic_dictionary(self) -> tuple[list[str], list[str]]:
        self._ensure_abx_runtime_state()
        now_ts = time.time()
        cached = self._abx_dictionary_cache
        if cached.get("expires_at", 0.0) > now_ts:
            return cached.get("antibiotic_names", []), cached.get("broad_spectrum_names", [])

        abx_names: set[str] = set()
        broad_names: set[str] = set()

        antibiotic_type_keywords = self._get_rule_cfg_list(
            "antibiotic_type_keywords",
            ["抗生素", "抗菌", "抗感染", "antibiotic", "antimicrobial"],
        )
        broad_type_keywords = self._get_rule_cfg_list(
            "broad_type_keywords",
            ["广谱", "碳青霉烯", "三四代头孢", "高级别", "broad", "carbapenem"],
        )
        broad_name_keywords = self._get_rule_cfg_list(
            "broad_spectrum_keywords",
            ["美罗培南", "亚胺培南", "哌拉西林他唑巴坦", "头孢哌酮舒巴坦", "头孢吡肟", "替加环素"],
        )
        seeded_abx_keywords = self._get_rule_cfg_list(
            "antibiotic_keywords",
            ["万古霉素", "头孢", "青霉素", "美罗培南", "阿奇霉素", "左氧氟沙星", "替考拉宁"],
        )

        # 从 configDrug 自动识别抗生素词典
        try:
            cursor = self.db.col("configDrug").find(
                {},
                {
                    "name": 1, "drugName": 1, "genericName": 1, "tradeName": 1, "fullName": 1,
                    "drugType": 1, "category": 1, "classify": 1, "classifyName": 1, "tags": 1,
                },
            )
            async for doc in cursor:
                name = str(
                    doc.get("name")
                    or doc.get("drugName")
                    or doc.get("genericName")
                    or doc.get("tradeName")
                    or doc.get("fullName")
                    or ""
                ).strip()
                if not name:
                    continue
                type_text = " ".join(
                    str(doc.get(k) or "")
                    for k in ("drugType", "category", "classify", "classifyName", "tags")
                )
                if self._text_has_any(type_text, antibiotic_type_keywords):
                    abx_names.add(name)
                    if self._text_has_any(type_text, broad_type_keywords):
                        broad_names.add(name)
        except Exception:
            pass

        for kw in seeded_abx_keywords:
            if str(kw).strip():
                abx_names.add(str(kw).strip())
        for kw in broad_name_keywords:
            if str(kw).strip():
                broad_names.add(str(kw).strip())

        abx_list = sorted(abx_names)
        broad_list = sorted(broad_names)
        cached["antibiotic_names"] = abx_list
        cached["broad_spectrum_names"] = broad_list
        cached["expires_at"] = now_ts + 3600
        return abx_list, broad_list

    def _match_name_keywords(self, name: str, keywords: list[str]) -> bool:
        n = str(name or "").strip().lower()
        if not n:
            return False
        return any(str(k).strip().lower() in n for k in keywords if str(k).strip())

    def _extract_drug_name(self, doc: dict) -> str:
        return str(doc.get("drugName") or doc.get("orderName") or doc.get("drugSpec") or "").strip()

    async def _get_drug_events(self, pid_str: str, since: datetime) -> list[dict]:
        cursor = self.db.col("drugExe").find(
            {"pid": pid_str},
            {
                "executeTime": 1, "startTime": 1, "orderTime": 1,
                "drugName": 1, "orderName": 1, "drugSpec": 1,
                "route": 1, "routeName": 1, "orderType": 1,
            },
        ).sort("executeTime", -1).limit(3000)

        items: list[dict] = []
        async for doc in cursor:
            t = self._event_time(doc)
            if not t or t < since:
                continue
            name = self._extract_drug_name(doc)
            if not name:
                continue
            items.append({"time": t, "name": name, "doc": doc})
        items.sort(key=lambda x: x["time"])
        return items

    def _continuous_course(self, events: list[dict], now: datetime, max_gap_hours: float = 36.0) -> dict | None:
        if not events:
            return None
        times = sorted([e["time"] for e in events if isinstance(e.get("time"), datetime)])
        if not times:
            return None
        last_t = times[-1]
        # 近24h无执行视为疗程已结束
        if _hours_between(last_t, now) > 24:
            return None
        start_t = last_t
        prev = last_t
        for t in reversed(times[:-1]):
            if _hours_between(t, prev) <= max_gap_hours:
                start_t = t
                prev = t
            else:
                break
        return {
            "start": start_t,
            "last": last_t,
            "duration_hours": round(_hours_between(start_t, now), 2),
        }

    async def _get_culture_records(self, his_pid: str, since: datetime) -> list[dict]:
        if not his_pid:
            return []
        culture_keywords = self._get_rule_cfg_list(
            "culture_keywords",
            ["培养", "culture", "菌", "药敏", "blood culture", "sputum culture", "urine culture"],
        )
        pending_keywords = self._get_rule_cfg_list(
            "culture_pending_keywords",
            ["待报", "待回", "进行中", "pending", "preliminary", "未出"],
        )
        positive_keywords = self._get_rule_cfg_list(
            "culture_positive_keywords",
            ["阳性", "positive", "生长", "检出", "分离出", "susceptible", "resistant"],
        )

        cursor = self.db.dc_col("VI_ICU_EXAM_ITEM").find({"hisPid": his_pid}).sort("authTime", -1).limit(3000)
        records: list[dict] = []
        async for doc in cursor:
            t = (
                _parse_dt(doc.get("authTime"))
                or _parse_dt(doc.get("collectTime"))
                or _parse_dt(doc.get("reportTime"))
                or _parse_dt(doc.get("time"))
            )
            if not t or t < since:
                continue
            name = str(doc.get("itemCnName") or doc.get("itemName") or doc.get("itemCode") or "").strip()
            if not self._match_name_keywords(name, culture_keywords):
                continue
            result = str(doc.get("result") or doc.get("resultValue") or "").strip()
            flag = str(doc.get("resultFlag") or doc.get("seriousFlag") or "").strip()
            text = f"{result} {flag}".strip()
            is_final = bool(text) and (not self._match_name_keywords(text, pending_keywords))
            is_positive = bool(text) and self._match_name_keywords(text, positive_keywords)
            records.append(
                {
                    "time": t,
                    "name": name,
                    "result": result,
                    "flag": flag,
                    "is_final": is_final,
                    "is_positive": is_positive,
                }
            )
        records.sort(key=lambda x: x["time"])
        return records

    async def _has_tdm_result(self, his_pid: str, since: datetime, keywords: list[str]) -> bool:
        if not his_pid or not keywords:
            return False
        cursor = self.db.dc_col("VI_ICU_EXAM_ITEM").find({"hisPid": his_pid}).sort("authTime", -1).limit(2000)
        for doc in [d async for d in cursor]:
            t = (
                _parse_dt(doc.get("authTime"))
                or _parse_dt(doc.get("collectTime"))
                or _parse_dt(doc.get("reportTime"))
                or _parse_dt(doc.get("time"))
            )
            if not t or t < since:
                continue
            name = str(doc.get("itemCnName") or doc.get("itemName") or doc.get("itemCode") or "").strip()
            if not self._match_name_keywords(name, keywords):
                continue
            rv = str(doc.get("result") or doc.get("resultValue") or "").strip()
            if rv:
                return True
        return False

    async def scan_antibiotic_stewardship(self) -> None:
        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        cfg = self.config.yaml_cfg.get("alert_engine", {}).get("antibiotic_stewardship", {})
        timeout_hours = float(cfg.get("empiric_timeout_hours", 48))
        stop_eval_days = float(cfg.get("pct_stop_eval_days", 5))
        vanco_tdm_days = float(cfg.get("vanco_tdm_days", 3))
        duration_limit_days = float(cfg.get("duration_limit_days", 7))

        vanco_keywords = self._get_rule_cfg_list("vancomycin_keywords", ["万古霉素", "vancomycin"])
        amino_keywords = self._get_rule_cfg_list(
            "aminoglycoside_keywords",
            ["阿米卡星", "庆大霉素", "妥布霉素", "依替米星", "奈替米星", "链霉素", "gentamicin", "amikacin", "tobramycin"],
        )
        vanco_tdm_keywords = self._get_rule_cfg_list(
            "vanco_tdm_keywords",
            ["万古霉素谷", "vancomycin trough", "万古霉素血药浓度", "万古霉素浓度"],
        )
        amino_tdm_keywords = self._get_rule_cfg_list(
            "aminoglycoside_tdm_keywords",
            ["阿米卡星谷", "庆大霉素谷", "妥布霉素谷", "氨基糖苷", "amikacin trough", "gentamicin trough"],
        )

        abx_names, broad_names = await self._load_antibiotic_dictionary()

        patient_cursor = self.db.col("patient").find(
            self._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "deptCode": 1},
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        now = datetime.now()
        since_14d = now - timedelta(days=14)
        triggered = 0

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            his_pid = str(patient_doc.get("hisPid") or "").strip()

            drug_events = await self._get_drug_events(pid_str, since_14d)
            if not drug_events:
                continue

            abx_events = [
                e for e in drug_events
                if self._match_name_keywords(e["name"], abx_names)
            ]
            if not abx_events:
                continue

            broad_events = [e for e in abx_events if self._match_name_keywords(e["name"], broad_names)]
            all_course = self._continuous_course(abx_events, now=now)
            broad_course = self._continuous_course(broad_events, now=now) if broad_events else None
            culture_records = await self._get_culture_records(his_pid, since_14d) if his_pid else []

            # (1) 48-72h 经验性用药 time-out + 培养已出但未调整
            if broad_course and broad_course["duration_hours"] >= timeout_hours:
                culture_after_start = [c for c in culture_records if c.get("is_final") and c["time"] >= broad_course["start"]]
                # 仍在使用广谱，且培养已出：提示降阶梯评估
                if culture_after_start:
                    rule_id = "ABX_TIMEOUT_DEESCALATION"
                    if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        latest_culture = culture_after_start[-1]
                        alert = await self._create_alert(
                            rule_id=rule_id,
                            name="广谱抗生素time-out与降阶梯评估提醒",
                            category="antibiotic_stewardship",
                            alert_type="abx_timeout",
                            severity="warning",
                            parameter="broad_spectrum_duration",
                            condition={"operator": ">=", "threshold_hours": timeout_hours},
                            value=round(float(broad_course["duration_hours"]), 2),
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=None,
                            source_time=latest_culture.get("time"),
                            extra={
                                "broad_course_start": broad_course["start"],
                                "broad_course_last": broad_course["last"],
                                "broad_duration_hours": broad_course["duration_hours"],
                                "culture_latest": latest_culture,
                                "suggestion": "请结合培养/药敏结果评估降阶梯或调整方案。",
                            },
                        )
                        if alert:
                            triggered += 1

            # (2) PCT 指导停药
            if all_course and all_course["duration_hours"] >= stop_eval_days * 24 and his_pid:
                pct_series = await self._get_lab_series(his_pid, "pct", since_14d, limit=300)
                pct_series = [
                    x for x in pct_series
                    if x.get("value") is not None and x.get("time") and x["time"] >= all_course["start"]
                ]
                if len(pct_series) >= 2:
                    peak = max(float(x["value"]) for x in pct_series)
                    peak_idx = next(idx for idx, item in enumerate(pct_series) if float(item["value"]) == peak)
                    latest = float(pct_series[-1]["value"])
                    decline_ratio = ((peak - latest) / peak) if peak > 0 else 0.0
                    meets_stop = (decline_ratio > 0.8) or (latest < 0.25)
                    if meets_stop:
                        rule_id = "ABX_PCT_STOP_EVAL"
                        if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                            alert = await self._create_alert(
                                rule_id=rule_id,
                                name="PCT下降达标，评估停用抗生素",
                                category="antibiotic_stewardship",
                                alert_type="abx_stop_recommendation",
                                severity="warning",
                                parameter="pct",
                                condition={
                                    "pct_decline_ratio_gt": 0.8,
                                    "pct_low_threshold_ng_ml": 0.25,
                                    "antibiotic_days_gte": stop_eval_days,
                                },
                                value=round(latest, 3),
                                patient_id=pid_str,
                                patient_doc=patient_doc,
                                device_id=None,
                                source_time=pct_series[-1].get("time"),
                                extra={
                                    "pct_series_start": pct_series[0].get("time"),
                                    "pct_peak_time": pct_series[peak_idx].get("time"),
                                    "pct_peak": peak,
                                    "pct_latest": latest,
                                    "pct_decline_ratio": round(decline_ratio, 3),
                                    "antibiotic_duration_hours": all_course["duration_hours"],
                                },
                            )
                            if alert:
                                triggered += 1

            # (3) 特殊药物 TDM 提醒
            vanco_events = [e for e in abx_events if self._match_name_keywords(e["name"], vanco_keywords)]
            vanco_course = self._continuous_course(vanco_events, now=now) if vanco_events else None
            if vanco_course and vanco_course["duration_hours"] >= vanco_tdm_days * 24 and his_pid:
                has_vanco_tdm = await self._has_tdm_result(his_pid, vanco_course["start"], vanco_tdm_keywords)
                if not has_vanco_tdm:
                    rule_id = "ABX_TDM_VANCO_MISSING"
                    if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self._create_alert(
                            rule_id=rule_id,
                            name="万古霉素用药TDM监测提醒",
                            category="antibiotic_stewardship",
                            alert_type="abx_tdm_reminder",
                            severity="warning",
                            parameter="vancomycin_tdm",
                            condition={"operator": ">=", "threshold_days": vanco_tdm_days},
                            value=round(vanco_course["duration_hours"] / 24.0, 2),
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=None,
                            source_time=vanco_course["last"],
                            extra={
                                "drug_group": "vancomycin",
                                "course_start": vanco_course["start"],
                                "course_duration_hours": vanco_course["duration_hours"],
                                "tdm_detected": False,
                            },
                        )
                        if alert:
                            triggered += 1

            amino_events = [e for e in abx_events if self._match_name_keywords(e["name"], amino_keywords)]
            amino_course = self._continuous_course(amino_events, now=now) if amino_events else None
            if amino_course and his_pid:
                has_amino_tdm = await self._has_tdm_result(his_pid, amino_course["start"], amino_tdm_keywords)
                if not has_amino_tdm:
                    rule_id = "ABX_TDM_AMINO_MISSING"
                    if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self._create_alert(
                            rule_id=rule_id,
                            name="氨基糖苷类用药TDM监测提醒",
                            category="antibiotic_stewardship",
                            alert_type="abx_tdm_reminder",
                            severity="warning",
                            parameter="aminoglycoside_tdm",
                            condition={"operator": "missing"},
                            value=round(amino_course["duration_hours"] / 24.0, 2),
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=None,
                            source_time=amino_course["last"],
                            extra={
                                "drug_group": "aminoglycoside",
                                "course_start": amino_course["start"],
                                "course_duration_hours": amino_course["duration_hours"],
                                "tdm_detected": False,
                            },
                        )
                        if alert:
                            triggered += 1

            # (4) 疗程超限提醒：经验性抗生素 >7d 且无培养依据
            if all_course and all_course["duration_hours"] > duration_limit_days * 24:
                has_positive_culture = any(c.get("is_positive") for c in culture_records if c.get("is_final"))
                if not has_positive_culture:
                    rule_id = "ABX_DURATION_EXCEEDED_NO_CULTURE"
                    if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self._create_alert(
                            rule_id=rule_id,
                            name="经验性抗生素疗程超限提醒",
                            category="antibiotic_stewardship",
                            alert_type="abx_duration_exceeded",
                            severity="warning",
                            parameter="antibiotic_duration",
                            condition={"operator": ">", "threshold_days": duration_limit_days, "culture_positive": False},
                            value=round(all_course["duration_hours"] / 24.0, 2),
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=None,
                            source_time=all_course["last"],
                            extra={
                                "course_start": all_course["start"],
                                "course_duration_days": round(all_course["duration_hours"] / 24.0, 2),
                                "culture_positive": False,
                                "culture_records_count": len(culture_records),
                            },
                        )
                        if alert:
                            triggered += 1

        if triggered > 0:
            self._log_info("抗菌药管理", triggered)
