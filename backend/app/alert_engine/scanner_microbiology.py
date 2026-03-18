from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any
from .antibiotic_stewardship import _parse_dt
from app.utils.labs import _lab_time
from app.utils.parse import _parse_number
from .scanners import BaseScanner, ScannerSpec


class MicrobiologyScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="microbiology",
                interval_key="microbiology",
                default_interval=1800,
                initial_delay=62,
            ),
        )

    async def scan(self) -> None:
        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        vanco_keywords = self.engine._get_cfg_list(("alert_engine", "antibiotic_stewardship", "vancomycin_keywords"), ["万古霉素", "vancomycin"])
        vanco_tdm_keywords = self.engine._get_cfg_list(
            ("alert_engine", "antibiotic_stewardship", "vanco_tdm_keywords"),
            ["万古霉素谷", "vancomycin trough", "万古霉素血药浓度", "万古霉素浓度"],
        )
        meropenem_keywords = self.engine._get_cfg_list(
            ("alert_engine", "microbiology", "meropenem_keywords"),
            ["美罗培南", "meropenem"],
        )
        iv_route_keywords = self.engine._get_cfg_list(
            ("alert_engine", "microbiology", "iv_route_keywords"),
            ["静脉", "iv", "ivgtt", "静滴", "静注", "静脉滴注"],
        )

        antibiotic_names, _ = await self.engine._load_antibiotic_dictionary()
        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
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

            susceptibility_reports = await self.engine._parse_susceptibility_report(his_pid, since_14d)
            current_drugs = await self.engine._get_current_antibiotic_courses(pid_str, now, antibiotic_names)

            # A. 覆盖不足检查
            mismatches = await self.engine._check_coverage_mismatch(pid_str, his_pid, susceptibility_reports, current_drugs)
            for mismatch in mismatches:
                rule_id = "MICRO_COVERAGE_MISMATCH"
                if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    continue
                alert = await self.engine._create_alert(
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
                mdro_type = self.engine._match_mdro_type(str(row.get("organism") or ""), f"{row.get('raw_name') or ''} {row.get('raw_result') or ''}")
                if not mdro_type:
                    continue
                dedupe_key = f"{mdro_type}:{row.get('organism')}"
                if dedupe_key in mdro_seen:
                    continue
                mdro_seen.add(dedupe_key)
                rule_id = "MICRO_MDRO_DETECTED"
                if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    continue
                alert = await self.engine._create_alert(
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
            vanco_courses = [x for x in current_drugs if self.engine._match_name_keywords(x.get("name"), vanco_keywords)]
            for vanco in vanco_courses:
                course = vanco.get("course") or {}
                if float(course.get("duration_hours") or 0) < 48:
                    continue
                tdm = await self.engine._latest_tdm_numeric_result(his_pid, course.get("start") or since_14d, vanco_tdm_keywords)
                if not tdm:
                    continue
                trough = float(tdm.get("value") or 0)
                if not (trough < 10 or trough > 20):
                    continue
                rule_id = "MICRO_VANCO_TROUGH_ABNORMAL"
                if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    continue
                alert = await self.engine._create_alert(
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
                if not self.engine._match_name_keywords(item.get("name"), meropenem_keywords):
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
                if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    continue
                alert = await self.engine._create_alert(
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
            self.engine._log_info("微生物监测", triggered)
