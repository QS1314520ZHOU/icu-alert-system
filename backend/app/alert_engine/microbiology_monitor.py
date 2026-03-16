"""微生物与药敏监测。"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from .antibiotic_stewardship import _parse_dt
from .base import _lab_time, _parse_number


class MicrobiologyMonitorMixin:
    def _micro_cfg_list(self, key: str, default: list[str] | dict[str, list[str]]):
        cfg = self.config.yaml_cfg.get("alert_engine", {}).get("microbiology", {})
        if not isinstance(cfg, dict):
            return default
        value = cfg.get(key, default)
        return value

    def _normalize_sus_result(self, text: str) -> str | None:
        t = str(text or "").strip().lower()
        if not t:
            return None
        if any(k in t for k in ["耐药", " resistant", "resistant", " r ", "(r)", "＝r", "=r", "结果:r"]):
            return "R"
        if any(k in t for k in ["中介", " intermediate", "intermediate", " i ", "(i)", "＝i", "=i", "结果:i"]):
            return "I"
        if any(k in t for k in ["敏感", " sensitive", "sensitive", " s ", "(s)", "＝s", "=s", "结果:s"]):
            return "S"
        stripped = re.sub(r"[^A-Za-z]", " ", t)
        tokens = {x for x in stripped.split() if x}
        if "r" in tokens:
            return "R"
        if "i" in tokens:
            return "I"
        if "s" in tokens:
            return "S"
        return None

    def _extract_sample_type(self, doc: dict) -> str:
        for key in ("sampleType", "sampleName", "specimen", "specimenName", "specimenType", "examName", "requestName"):
            value = str(doc.get(key) or "").strip()
            if value:
                return value
        return ""

    def _extract_organism_text(self, doc: dict, name: str, result_text: str) -> str:
        candidates = [
            doc.get("organism"),
            doc.get("organismName"),
            doc.get("bacteriaName"),
            doc.get("germName"),
            doc.get("cultureName"),
            doc.get("cultureResult"),
            doc.get("examName"),
            doc.get("requestName"),
        ]
        for value in candidates:
            text = str(value or "").strip()
            if text:
                return text
        blob = " | ".join(x for x in [name, result_text] if x)
        match = re.search(r"(?:检出|分离出|培养出|detected|isolated)\s*([^,;；，]+)", blob, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return name or "未知菌种"

    def _extract_mic_value(self, doc: dict, text: str) -> float | None:
        for key in ("mic", "micValue", "MIC", "resultValue"):
            num = _parse_number(doc.get(key))
            if num is not None:
                return num
        match = re.search(r"mic[^0-9<>]*([<>]?\s*\d+(?:\.\d+)?)", str(text or ""), flags=re.IGNORECASE)
        if match:
            return _parse_number(match.group(1))
        return None

    def _pick_antibiotic_from_text(self, text: str, antibiotic_names: list[str]) -> str:
        for drug in antibiotic_names:
            if self._match_name_keywords(text, [drug]):
                return drug
        return ""

    async def _parse_susceptibility_report(self, his_pid: str, since: datetime) -> list[dict]:
        if not his_pid:
            return []
        susceptibility_keywords = self._micro_cfg_list(
            "susceptibility_keywords",
            ["药敏", "susceptibility", "MIC", "敏感", "耐药", "中介", "resistant", "sensitive", "intermediate"],
        )
        antibiotic_names, _ = await self._load_antibiotic_dictionary()
        cursor = self.db.dc_col("VI_ICU_EXAM_ITEM").find({"hisPid": his_pid}).sort("authTime", -1).limit(4000)
        rows: list[dict] = []
        async for doc in cursor:
            t = _lab_time(doc)
            if not t or t < since:
                continue
            name = str(doc.get("itemCnName") or doc.get("itemName") or doc.get("itemCode") or "").strip()
            result_text = str(doc.get("result") or doc.get("resultValue") or "").strip()
            flag = str(doc.get("resultFlag") or doc.get("flag") or doc.get("seriousFlag") or "").strip()
            combined = " | ".join(x for x in [name, result_text, flag] if x)
            if not self._match_name_keywords(combined, susceptibility_keywords):
                continue

            result = self._normalize_sus_result(combined)
            if result is None:
                continue

            antibiotic = (
                str(doc.get("antibiotic") or doc.get("drugName") or doc.get("drug") or "").strip()
                or self._pick_antibiotic_from_text(combined, antibiotic_names)
            )
            organism = self._extract_organism_text(doc, name, result_text)
            mic = self._extract_mic_value(doc, combined)
            rows.append(
                {
                    "organism": organism or "未知菌种",
                    "antibiotic": antibiotic or "未知抗生素",
                    "result": result,
                    "mic": mic,
                    "time": t,
                    "sample_type": self._extract_sample_type(doc),
                    "raw_name": name,
                    "raw_result": result_text,
                }
            )
        rows.sort(key=lambda x: x["time"])
        return rows

    async def _get_current_antibiotic_courses(self, pid_str: str, now: datetime, antibiotic_names: list[str]) -> list[dict]:
        since = now - timedelta(days=14)
        drug_events = await self._get_drug_events(pid_str, since)
        abx_events = [e for e in drug_events if self._match_name_keywords(e["name"], antibiotic_names)]
        if not abx_events:
            return []

        grouped: dict[str, list[dict]] = {}
        for event in abx_events:
            grouped.setdefault(event["name"], []).append(event)

        current: list[dict] = []
        for name, events in grouped.items():
            course = self._continuous_course(events, now=now)
            if not course:
                continue
            latest_event = events[-1]
            current.append(
                {
                    "name": name,
                    "course": course,
                    "latest_doc": latest_event.get("doc") or {},
                    "latest_time": latest_event.get("time"),
                }
            )
        return current

    async def _check_coverage_mismatch(self, pid_str, his_pid, susceptibility_reports, current_drugs) -> list[dict]:
        del pid_str, his_pid
        if not susceptibility_reports or not current_drugs:
            return []

        mismatches: list[dict] = []
        grouped: dict[str, list[dict]] = {}
        for row in susceptibility_reports:
            organism = str(row.get("organism") or "").strip()
            if not organism:
                continue
            grouped.setdefault(organism, []).append(row)

        for organism, reports in grouped.items():
            resistant_to: list[str] = []
            matched_any = False
            has_sensitive = False
            for drug in current_drugs:
                drug_name = str(drug.get("name") or "").strip()
                if not drug_name:
                    continue
                statuses = [
                    str(r.get("result") or "")
                    for r in reports
                    if self._match_name_keywords(str(r.get("antibiotic") or ""), [drug_name])
                    or self._match_name_keywords(drug_name, [str(r.get("antibiotic") or "")])
                ]
                if not statuses:
                    continue
                matched_any = True
                if "S" in statuses:
                    has_sensitive = True
                elif any(x in ("R", "I") for x in statuses):
                    resistant_to.append(drug_name)

            if matched_any and not has_sensitive and resistant_to:
                mismatches.append(
                    {
                        "organism": organism,
                        "resistant_to": resistant_to,
                        "current_drugs": [str(x.get("name") or "") for x in current_drugs if str(x.get("name") or "").strip()],
                        "suggestion": f"{organism} 当前在用方案缺乏敏感药覆盖，建议依据药敏结果调整抗菌方案。",
                    }
                )
        return mismatches

    async def _latest_tdm_numeric_result(self, his_pid: str, since: datetime, keywords: list[str]) -> dict | None:
        if not his_pid or not keywords:
            return None
        cursor = self.db.dc_col("VI_ICU_EXAM_ITEM").find({"hisPid": his_pid}).sort("authTime", -1).limit(1000)
        async for doc in cursor:
            t = _lab_time(doc)
            if not t or t < since:
                continue
            name = str(doc.get("itemCnName") or doc.get("itemName") or doc.get("itemCode") or "").strip()
            if not self._match_name_keywords(name, keywords):
                continue
            value = _parse_number(doc.get("result") or doc.get("resultValue") or doc.get("value"))
            if value is None:
                continue
            return {
                "time": t,
                "value": value,
                "unit": str(doc.get("unit") or doc.get("resultUnit") or "").strip(),
                "name": name,
            }
        return None

    def _match_mdro_type(self, organism: str, raw_text: str) -> str | None:
        defaults = {
            "MRSA": ["mrsa", "耐甲氧西林金黄色葡萄球菌"],
            "CRE": ["cre", "碳青霉烯耐药肠杆菌", "耐碳青霉烯"],
            "VRE": ["vre", "耐万古霉素肠球菌"],
            "CRAB": ["crab", "鲍曼不动杆菌", "耐碳青霉烯鲍曼"],
            "CRPA": ["crpa", "耐碳青霉烯铜绿假单胞菌"],
        }
        mdro_cfg = self._micro_cfg_list("mdro_keywords", defaults)
        mapping = mdro_cfg if isinstance(mdro_cfg, dict) else defaults
        blob = f"{organism} {raw_text}".lower()
        for mdro_type, keywords in mapping.items():
            words = keywords if isinstance(keywords, list) else [str(keywords)]
            if any(str(k).strip().lower() in blob for k in words if str(k).strip()):
                return str(mdro_type)
        return None

    async def scan_microbiology(self) -> None:
        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        vanco_keywords = self._get_cfg_list(("alert_engine", "antibiotic_stewardship", "vancomycin_keywords"), ["万古霉素", "vancomycin"])
        vanco_tdm_keywords = self._get_cfg_list(
            ("alert_engine", "antibiotic_stewardship", "vanco_tdm_keywords"),
            ["万古霉素谷", "vancomycin trough", "万古霉素血药浓度", "万古霉素浓度"],
        )
        meropenem_keywords = self._get_cfg_list(
            ("alert_engine", "microbiology", "meropenem_keywords"),
            ["美罗培南", "meropenem"],
        )
        iv_route_keywords = self._get_cfg_list(
            ("alert_engine", "microbiology", "iv_route_keywords"),
            ["静脉", "iv", "ivgtt", "静滴", "静注", "静脉滴注"],
        )

        antibiotic_names, _ = await self._load_antibiotic_dictionary()
        patient_cursor = self.db.col("patient").find(
            self._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "deptCode": 1},
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        triggered = 0
        now = datetime.now()
        since_14d = now - timedelta(days=14)

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            his_pid = str(patient_doc.get("hisPid") or "").strip()
            if not his_pid:
                continue

            susceptibility_reports = await self._parse_susceptibility_report(his_pid, since_14d)
            current_drugs = await self._get_current_antibiotic_courses(pid_str, now, antibiotic_names)

            # A. 覆盖不足检查
            mismatches = await self._check_coverage_mismatch(pid_str, his_pid, susceptibility_reports, current_drugs)
            for mismatch in mismatches:
                rule_id = "MICRO_COVERAGE_MISMATCH"
                if await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    continue
                alert = await self._create_alert(
                    rule_id=rule_id,
                    name="抗生素覆盖不足(药敏不匹配)",
                    category="antibiotic_stewardship",
                    alert_type="coverage_mismatch",
                    severity="high",
                    parameter="coverage",
                    condition={"operator": "mismatch"},
                    value=len(mismatch.get("resistant_to") or []),
                    patient_id=pid_str,
                    patient_doc=patient_doc,
                    device_id=None,
                    source_time=now,
                    extra=mismatch,
                )
                if alert:
                    triggered += 1

            # B. MDRO 检出
            mdro_seen: set[str] = set()
            for row in susceptibility_reports:
                mdro_type = self._match_mdro_type(str(row.get("organism") or ""), f"{row.get('raw_name') or ''} {row.get('raw_result') or ''}")
                if not mdro_type:
                    continue
                dedupe_key = f"{mdro_type}:{row.get('organism')}"
                if dedupe_key in mdro_seen:
                    continue
                mdro_seen.add(dedupe_key)
                rule_id = "MICRO_MDRO_DETECTED"
                if await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    continue
                alert = await self._create_alert(
                    rule_id=rule_id,
                    name=f"多重耐药菌检出({mdro_type})",
                    category="antibiotic_stewardship",
                    alert_type="mdro_detected",
                    severity="critical",
                    parameter="mdro",
                    condition={"mdro_type": mdro_type},
                    value=1,
                    patient_id=pid_str,
                    patient_doc=patient_doc,
                    device_id=None,
                    source_time=row.get("time") or now,
                    extra={
                        "mdro_type": mdro_type,
                        "organism": row.get("organism"),
                        "sample_type": row.get("sample_type") or "",
                        "isolation_precaution_advice": f"检出 {mdro_type}，建议立即评估接触隔离与院感上报流程。",
                    },
                )
                if alert:
                    triggered += 1

            # C1. 万古霉素 TDM 异常
            vanco_courses = [x for x in current_drugs if self._match_name_keywords(x.get("name"), vanco_keywords)]
            for vanco in vanco_courses:
                course = vanco.get("course") or {}
                if float(course.get("duration_hours") or 0) < 48:
                    continue
                tdm = await self._latest_tdm_numeric_result(his_pid, course.get("start") or since_14d, vanco_tdm_keywords)
                if not tdm:
                    continue
                trough = float(tdm.get("value") or 0)
                if not (trough < 10 or trough > 20):
                    continue
                rule_id = "MICRO_VANCO_TROUGH_ABNORMAL"
                if await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    continue
                alert = await self._create_alert(
                    rule_id=rule_id,
                    name="万古霉素谷浓度异常",
                    category="antibiotic_stewardship",
                    alert_type="vanco_trough_abnormal",
                    severity="high",
                    parameter="vancomycin_trough",
                    condition={"target_low": 10, "target_high": 20},
                    value=round(trough, 2),
                    patient_id=pid_str,
                    patient_doc=patient_doc,
                    device_id=None,
                    source_time=tdm.get("time") or now,
                    extra={
                        "drug_name": vanco.get("name"),
                        "course_duration_hours": course.get("duration_hours"),
                        "tdm_name": tdm.get("name"),
                        "trough_value": trough,
                        "unit": tdm.get("unit") or "μg/mL",
                        "suggestion": "建议结合AUC/MIC目标重新评估给药方案与复测频率。",
                    },
                )
                if alert:
                    triggered += 1

            # C2. 美罗培南延长输注提醒
            for item in current_drugs:
                if not self._match_name_keywords(item.get("name"), meropenem_keywords):
                    continue
                latest_doc = item.get("latest_doc") or {}
                freq_text = " ".join(
                    str(latest_doc.get(k) or "")
                    for k in ("frequency", "freq", "executeFreq", "orderFreq", "dosageFreq", "usage")
                ).lower()
                route_text = " ".join(
                    str(latest_doc.get(k) or "")
                    for k in ("route", "routeName", "administrationRoute")
                ).lower()
                if not any(k in freq_text for k in ["q8h", "tid", "每日3", "一日三次", "q 8"]):
                    continue
                if not any(str(k).lower() in route_text for k in iv_route_keywords):
                    continue
                rule_id = "MICRO_MEROPENEM_EXTENDED_INFUSION"
                if await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    continue
                alert = await self._create_alert(
                    rule_id=rule_id,
                    name="美罗培南延长输注提醒",
                    category="antibiotic_stewardship",
                    alert_type="meropenem_extended_infusion",
                    severity="warning",
                    parameter="meropenem_infusion",
                    condition={"frequency": freq_text or "q8h/tid", "route": route_text or "iv"},
                    value=1,
                    patient_id=pid_str,
                    patient_doc=patient_doc,
                    device_id=None,
                    source_time=item.get("latest_time") or now,
                    extra={
                        "drug_name": item.get("name"),
                        "frequency": freq_text,
                        "route": route_text,
                        "suggestion": "若病原负荷高或MIC偏高，可考虑3h以上延长输注以优化T>MIC。",
                    },
                )
                if alert:
                    triggered += 1

        if triggered > 0:
            self._log_info("微生物监测", triggered)
