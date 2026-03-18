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
from .scanners import BaseScanner, ScannerSpec


class AntibioticStewardshipScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="antibiotic_stewardship",
                interval_key="antibiotic_stewardship",
                default_interval=1800,
                initial_delay=42,
            ),
        )

    async def scan(self) -> None:
        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        cfg = self.engine.config.yaml_cfg.get("alert_engine", {}).get("antibiotic_stewardship", {})
        timeout_hours = float(cfg.get("empiric_timeout_hours", 48))
        stop_eval_days = float(cfg.get("pct_stop_eval_days", 5))
        vanco_tdm_days = float(cfg.get("vanco_tdm_days", 3))
        duration_limit_days = float(cfg.get("duration_limit_days", 7))

        vanco_keywords = self.engine._get_rule_cfg_list("vancomycin_keywords", ["万古霉素", "vancomycin"])
        amino_keywords = self.engine._get_rule_cfg_list(
            "aminoglycoside_keywords",
            ["阿米卡星", "庆大霉素", "妥布霉素", "依替米星", "奈替米星", "链霉素", "gentamicin", "amikacin", "tobramycin"],
        )
        vanco_tdm_keywords = self.engine._get_rule_cfg_list(
            "vanco_tdm_keywords",
            ["万古霉素谷", "vancomycin trough", "万古霉素血药浓度", "万古霉素浓度"],
        )
        amino_tdm_keywords = self.engine._get_rule_cfg_list(
            "aminoglycoside_tdm_keywords",
            ["阿米卡星谷", "庆大霉素谷", "妥布霉素谷", "氨基糖苷", "amikacin trough", "gentamicin trough"],
        )

        abx_names, broad_names = await self.engine._load_antibiotic_dictionary()

        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
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

            drug_events = await self.engine._get_drug_events(pid_str, since_14d)
            if not drug_events:
                continue

            abx_events = [
                e for e in drug_events
                if self.engine._match_name_keywords(e["name"], abx_names)
            ]
            if not abx_events:
                continue

            broad_events = [e for e in abx_events if self.engine._match_name_keywords(e["name"], broad_names)]
            all_course = self.engine._continuous_course(abx_events, now=now)
            broad_course = self.engine._continuous_course(broad_events, now=now) if broad_events else None
            culture_records = await self.engine._get_culture_records(his_pid, since_14d) if his_pid else []

            # (1) 48-72h 经验性用药 time-out + 培养已出但未调整
            if broad_course and broad_course["duration_hours"] >= timeout_hours:
                culture_after_start = [c for c in culture_records if c.get("is_final") and c["time"] >= broad_course["start"]]
                # 仍在使用广谱，且培养已出：提示降阶梯评估
                if culture_after_start:
                    rule_id = "ABX_TIMEOUT_DEESCALATION"
                    if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        latest_culture = culture_after_start[-1]
                        alert = await self.engine._create_alert(
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
                pct_series = await self.engine._get_lab_series(his_pid, "pct", since_14d, limit=300)
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
                        if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                            alert = await self.engine._create_alert(
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
            vanco_events = [e for e in abx_events if self.engine._match_name_keywords(e["name"], vanco_keywords)]
            vanco_course = self.engine._continuous_course(vanco_events, now=now) if vanco_events else None
            if vanco_course and vanco_course["duration_hours"] >= vanco_tdm_days * 24 and his_pid:
                has_vanco_tdm = await self.engine._has_tdm_result(his_pid, vanco_course["start"], vanco_tdm_keywords)
                if not has_vanco_tdm:
                    rule_id = "ABX_TDM_VANCO_MISSING"
                    if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self.engine._create_alert(
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

            amino_events = [e for e in abx_events if self.engine._match_name_keywords(e["name"], amino_keywords)]
            amino_course = self.engine._continuous_course(amino_events, now=now) if amino_events else None
            if amino_course and his_pid:
                has_amino_tdm = await self.engine._has_tdm_result(his_pid, amino_course["start"], amino_tdm_keywords)
                if not has_amino_tdm:
                    rule_id = "ABX_TDM_AMINO_MISSING"
                    if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self.engine._create_alert(
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
                    if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self.engine._create_alert(
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
            self.engine._log_info("抗菌药管理", triggered)
