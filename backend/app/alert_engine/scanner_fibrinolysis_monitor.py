from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

from .scanners import BaseScanner, ScannerSpec


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"[-+]?\d+(?:\.\d+)?", str(value).strip())
    if not match:
        return None
    try:
        return float(match.group(0))
    except (TypeError, ValueError):
        return None


class FibrinolysisMonitorScanner(BaseScanner):
    """纤溶功能动态监测。"""

    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="fibrinolysis_monitor",
                interval_key="fibrinolysis_monitor",
                default_interval=3600,
                initial_delay=91,
            ),
        )

    def is_enabled(self) -> bool:
        return super().is_enabled() and bool(self._cfg().get("enabled", True))

    def interval_seconds(self) -> int:
        value = self._cfg().get("scan_interval")
        try:
            return max(300, int(value))
        except (TypeError, ValueError):
            return super().interval_seconds()

    def _cfg(self) -> dict[str, Any]:
        cfg = self.engine._cfg("alert_engine", "fibrinolysis_monitor", default={}) or {}
        return cfg if isinstance(cfg, dict) else {}

    async def scan(self, patient_id: str | None = None) -> list[dict[str, Any]]:
        patients = await self._target_patients(patient_id)
        if not patients:
            return []
        suppression = self.engine._cfg("alert_engine", "suppression", default={}) or {}
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        now = datetime.now()
        alerts: list[dict[str, Any]] = []
        for patient_doc in patients:
            alerts.extend(await self._scan_patient(patient_doc=patient_doc, now=now, same_rule_sec=same_rule_sec, max_per_hour=max_per_hour))
        if alerts:
            self.engine._log_info("纤溶监测", len(alerts))
        return alerts

    async def _target_patients(self, patient_id: str | None) -> list[dict[str, Any]]:
        projection = {
            "_id": 1,
            "name": 1,
            "hisPid": 1,
            "hisBed": 1,
            "dept": 1,
            "hisDept": 1,
            "clinicalDiagnosis": 1,
            "admissionDiagnosis": 1,
            "current_profile": 1,
        }
        if patient_id:
            patient_doc, _ = await self.engine._load_patient(patient_id)
            return [patient_doc] if isinstance(patient_doc, dict) else []
        cursor = self.engine.db.col("patient").find(self.engine._active_patient_query(), projection)
        return [row async for row in cursor]

    async def _scan_patient(self, *, patient_doc: dict[str, Any], now: datetime, same_rule_sec: int, max_per_hour: int) -> list[dict[str, Any]]:
        patient_id = patient_doc.get("_id")
        his_pid = str(patient_doc.get("hisPid") or "").strip()
        if not patient_id or not his_pid:
            return []
        patient_id_str = str(patient_id)
        assessment = await self._build_assessment(patient_doc=patient_doc, patient_id=patient_id, his_pid=his_pid, now=now)
        if not assessment:
            return []
        await self._persist_assessment(patient_doc=patient_doc, assessment=assessment, now=now)
        alerts: list[dict[str, Any]] = []
        phenotype = str(assessment.get("phenotype") or "")
        if phenotype == "hyperfibrinolysis":
            rule_id = "FIBRINOLYSIS_HYPER"
            if not await self.engine._is_suppressed(patient_id_str, rule_id, same_rule_sec, max_per_hour):
                alert = await self.engine._create_alert(
                    rule_id=rule_id,
                    name="高纤溶/纤溶亢进风险",
                    category="hematology",
                    alert_type="hyperfibrinolysis",
                    severity=str(assessment.get("severity") or "high"),
                    parameter="fibrinolysis_state",
                    condition={"phenotype": phenotype},
                    value=assessment.get("score"),
                    patient_id=patient_id_str,
                    patient_doc=patient_doc,
                    device_id=None,
                    source_time=now,
                    explanation={
                        "summary": "当前凝血谱提示高纤溶或纤溶亢进风险，需警惕进行性出血和凝血因子消耗。",
                        "evidence": assessment.get("evidence") or [],
                        "suggestion": "建议立即复核 D-dimer、纤维蛋白原、血小板及 TEG/ROTEM（如有），必要时评估止血/血制品支持与抗纤溶策略。",
                        "text": "",
                    },
                    extra={"detail": assessment},
                )
                if alert:
                    alerts.append(alert)
        elif phenotype == "fibrinolysis_shutdown":
            rule_id = "FIBRINOLYSIS_SHUTDOWN"
            if not await self.engine._is_suppressed(patient_id_str, rule_id, same_rule_sec, max_per_hour):
                alert = await self.engine._create_alert(
                    rule_id=rule_id,
                    name="纤溶关闭风险",
                    category="hematology",
                    alert_type="fibrinolysis_shutdown",
                    severity=str(assessment.get("severity") or "warning"),
                    parameter="fibrinolysis_state",
                    condition={"phenotype": phenotype},
                    value=assessment.get("score"),
                    patient_id=patient_id_str,
                    patient_doc=patient_doc,
                    device_id=None,
                    source_time=now,
                    explanation={
                        "summary": "当前纤溶活性偏低，需警惕微血栓负荷和器官灌注进一步恶化。",
                        "evidence": assessment.get("evidence") or [],
                        "suggestion": "建议结合 DIC、感染和器官灌注状态复核纤溶关闭风险，优先补充 TEG/ROTEM 或连续凝血监测证据。",
                        "text": "",
                    },
                    extra={"detail": assessment},
                )
                if alert:
                    alerts.append(alert)
        return alerts

    async def _build_assessment(self, *, patient_doc: dict[str, Any], patient_id: Any, his_pid: str, now: datetime) -> dict[str, Any] | None:
        cfg = self._cfg()
        labs = await self.engine._get_latest_labs_map(his_pid, lookback_hours=72)
        ddimer = _to_float(((labs.get("ddimer") or {}).get("value")) if isinstance(labs.get("ddimer"), dict) else None)
        fib = _to_float(((labs.get("fib") or {}).get("value")) if isinstance(labs.get("fib"), dict) else None)
        plt = _to_float(((labs.get("plt") or {}).get("value")) if isinstance(labs.get("plt"), dict) else None)
        inr = _to_float(((labs.get("inr") or {}).get("value")) if isinstance(labs.get("inr"), dict) else None)
        pt = _to_float(((labs.get("pt") or {}).get("value")) if isinstance(labs.get("pt"), dict) else None)
        lysis = await self._latest_lysis_marker(his_pid=his_pid, since=now - timedelta(hours=72))
        active_bleeding = await self.engine._get_latest_active_alert(str(patient_id), ["gi_bleeding", "active_bleeding_risk", "dic"], hours=24)
        sepsis_context = await self.engine.db.col("alert_records").find_one(
            {
                "patient_id": str(patient_id),
                "created_at": {"$gte": now - timedelta(hours=24)},
                "alert_type": {"$in": ["qsofa", "sofa", "septic_shock", "dic"]},
            },
            sort=[("created_at", -1)],
        )
        hyper_score = 0.0
        shutdown_score = 0.0
        evidence: list[str] = []

        if lysis.get("ly30") is not None and float(lysis["ly30"]) >= float(cfg.get("ly30_hyper_threshold", 7.5) or 7.5):
            hyper_score += 4
            evidence.append(f"LY30 {lysis['ly30']}")
        if ddimer is not None and ddimer >= float(cfg.get("ddimer_hyper_threshold", 5.0) or 5.0):
            hyper_score += 2
            evidence.append(f"D-dimer {ddimer}")
        if fib is not None and fib <= float(cfg.get("fibrinogen_low_threshold", 1.5) or 1.5):
            hyper_score += 2
            evidence.append(f"Fib {fib}")
        if plt is not None and plt <= float(cfg.get("platelet_low_threshold", 80) or 80):
            hyper_score += 1
            evidence.append(f"PLT {plt}")
        if (inr is not None and inr >= float(cfg.get("inr_high_threshold", 1.5) or 1.5)) or (pt is not None and pt >= float(cfg.get("pt_high_threshold", 16) or 16)):
            hyper_score += 1
        if active_bleeding:
            hyper_score += 2
            evidence.append("伴活动性出血/DIC 告警")

        if lysis.get("ly30") is not None and float(lysis["ly30"]) <= float(cfg.get("ly30_shutdown_threshold", 0.8) or 0.8):
            shutdown_score += 4
            evidence.append(f"LY30 {lysis['ly30']}")
        if ddimer is not None and ddimer <= float(cfg.get("ddimer_shutdown_threshold", 1.0) or 1.0):
            shutdown_score += 1
        if fib is not None and fib >= float(cfg.get("fibrinogen_high_threshold", 4.0) or 4.0):
            shutdown_score += 2
            evidence.append(f"Fib {fib}")
        if sepsis_context:
            shutdown_score += 1
        if plt is not None and plt <= float(cfg.get("platelet_low_threshold", 80) or 80):
            shutdown_score += 1

        phenotype = ""
        severity = None
        score = 0.0
        if hyper_score >= float(cfg.get("hyper_score_threshold", 5) or 5):
            phenotype = "hyperfibrinolysis"
            score = round(hyper_score, 2)
            severity = "critical" if hyper_score >= float(cfg.get("hyper_critical_threshold", 7) or 7) else "high"
        elif shutdown_score >= float(cfg.get("shutdown_score_threshold", 5) or 5):
            phenotype = "fibrinolysis_shutdown"
            score = round(shutdown_score, 2)
            severity = "high" if shutdown_score >= float(cfg.get("shutdown_high_threshold", 6) or 6) else "warning"
        if not phenotype:
            return None
        return {
            "phenotype": phenotype,
            "score": score,
            "severity": severity,
            "labs": {"ddimer": ddimer, "fib": fib, "plt": plt, "inr": inr, "pt": pt},
            "lysis_marker": lysis,
            "bleeding_context": bool(active_bleeding),
            "sepsis_context": bool(sepsis_context),
            "evidence": evidence[:6],
        }

    async def _latest_lysis_marker(self, *, his_pid: str, since: datetime) -> dict[str, Any]:
        keywords = {
            "ly30": self._cfg().get("ly30_keywords", ["ly30", "lysis30", "lysis at 30 min", "li30"]),
            "ml": self._cfg().get("max_lysis_keywords", ["ml", "maximum lysis", "max lysis"]),
        }
        cursor = self.engine.db.dc_col("VI_ICU_EXAM_ITEM").find({"hisPid": his_pid}).sort("authTime", -1).limit(1200)
        result: dict[str, Any] = {"ly30": None, "ml": None}
        async for doc in cursor:
            time_value = doc.get("authTime") or doc.get("collectTime") or doc.get("reportTime") or doc.get("time")
            if isinstance(time_value, datetime) and time_value < since:
                continue
            name = str(doc.get("itemCnName") or doc.get("itemName") or doc.get("itemCode") or "").lower()
            if not name:
                continue
            value = _to_float(doc.get("result") or doc.get("resultValue") or doc.get("value"))
            if value is None:
                continue
            if result["ly30"] is None and any(str(keyword).lower() in name for keyword in keywords["ly30"]):
                result["ly30"] = float(value)
            if result["ml"] is None and any(str(keyword).lower() in name for keyword in keywords["ml"]):
                result["ml"] = float(value)
            if result["ly30"] is not None and result["ml"] is not None:
                break
        return result

    async def _persist_assessment(self, *, patient_doc: dict[str, Any], assessment: dict[str, Any], now: datetime) -> dict[str, Any]:
        doc = {
            "patient_id": str(patient_doc.get("_id") or ""),
            "patient_name": patient_doc.get("name") or "",
            "bed": patient_doc.get("hisBed") or "",
            "dept": patient_doc.get("dept") or patient_doc.get("hisDept") or "",
            "score_type": "fibrinolysis_monitor",
            "assessment": assessment,
            "calc_time": now,
            "updated_at": now,
            "month": now.strftime("%Y-%m"),
            "day": now.strftime("%Y-%m-%d"),
        }
        result = await self.engine.db.col("score").insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc
