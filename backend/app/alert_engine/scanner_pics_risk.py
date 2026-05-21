from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.services.followup_service import FollowupService

from .scanners import BaseScanner, ScannerSpec


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except Exception:
        return None


class PicsRiskScanner(BaseScanner):
    """ICU 后综合征 PICS 风险预警。"""

    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="pics_risk",
                interval_key="pics_risk",
                default_interval=7200,
                initial_delay=115,
            ),
        )

    def is_enabled(self) -> bool:
        return super().is_enabled() and bool(self._cfg().get("enabled", True))

    def interval_seconds(self) -> int:
        value = self._cfg().get("scan_interval")
        try:
            return max(600, int(value))
        except (TypeError, ValueError):
            return super().interval_seconds()

    def _cfg(self) -> dict[str, Any]:
        cfg = self.engine._cfg("alert_engine", "pics_risk", default={}) or {}
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
            self.engine._log_info("PICS 风险", len(alerts))
        return alerts

    async def _target_patients(self, patient_id: str | None) -> list[dict[str, Any]]:
        projection = {
            "_id": 1,
            "name": 1,
            "hisPid": 1,
            "hisBed": 1,
            "dept": 1,
            "hisDept": 1,
            "icuAdmissionTime": 1,
            "admissionTime": 1,
            "inTime": 1,
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
        if not patient_id:
            return []
        patient_id_str = str(patient_id)
        assessment = await self._build_assessment(patient_doc=patient_doc, patient_id=patient_id, now=now)
        if not assessment:
            return []
        await self._persist_assessment(patient_doc=patient_doc, assessment=assessment, now=now)
        severity = assessment.get("severity")
        if severity not in {"warning", "high"}:
            return []
        rule_id = "PICS_RISK_HIGH" if severity == "high" else "PICS_RISK_WARNING"
        if await self.engine._is_suppressed(patient_id_str, rule_id, same_rule_sec, max_per_hour):
            return []
        alert = await self.engine._create_alert(
            rule_id=rule_id,
            name="PICS 风险预警",
            category="rehabilitation",
            alert_type="pics_risk",
            severity=severity,
            parameter="pics_score",
            condition={"overall_score": assessment.get("overall_score"), "transfer_candidate": assessment.get("transfer_candidate")},
            value=assessment.get("overall_score"),
            patient_id=patient_id_str,
            patient_doc=patient_doc,
            device_id=None,
            source_time=now,
            explanation={
                "summary": assessment.get("summary"),
                "evidence": assessment.get("evidence") or [],
                "suggestion": assessment.get("suggestion"),
                "text": "",
            },
            extra={"detail": assessment},
        )
        return [alert] if alert else []

    async def _build_assessment(self, *, patient_doc: dict[str, Any], patient_id: Any, now: datetime) -> dict[str, Any] | None:
        cfg = self._cfg()
        pid_str = str(patient_id)
        admission_t = None
        for key in ("icuAdmissionTime", "admissionTime", "inTime"):
            if isinstance(patient_doc.get(key), datetime):
                admission_t = patient_doc.get(key)
                break
        icu_days = round(max(0.0, (now - admission_t).total_seconds() / 86400.0), 2) if isinstance(admission_t, datetime) else None

        discharge_signal = await self.engine._detect_transfer_candidate_signal(patient_doc, pid_str, now) if hasattr(self.engine, "_detect_transfer_candidate_signal") else {"candidate": False}
        transfer_candidate = bool(discharge_signal.get("candidate")) or (icu_days is not None and icu_days >= float(cfg.get("icu_days_threshold", 5) or 5))

        physical = await self._physical_dimension(patient_doc=patient_doc, patient_id=patient_id, now=now)
        cognitive = await self._cognitive_dimension(patient_doc=patient_doc, patient_id=patient_id, now=now)
        psychological = await self._psychological_dimension(patient_doc=patient_doc, patient_id=patient_id, now=now)
        dimensions = {"physical": physical, "cognitive": cognitive, "psychological": psychological}
        overall = round(sum(float(dimensions[key].get("score") or 0.0) for key in dimensions) / max(len(dimensions), 1), 2)
        severity = None
        if overall >= float(cfg.get("high_threshold", 70) or 70):
            severity = "high"
        elif overall >= float(cfg.get("warning_threshold", 45) or 45):
            severity = "warning"
        if not transfer_candidate and severity == "warning" and overall < float(cfg.get("early_warning_threshold", 55) or 55):
            severity = None
        summary = f"PICS 综合风险评分 {overall} 分，身体/认知/心理维度分别为 {physical.get('score')} / {cognitive.get('score')} / {psychological.get('score')}。"
        evidence = []
        for label, item in [("身体", physical), ("认知", cognitive), ("心理", psychological)]:
            if item.get("evidence"):
                evidence.append(f"{label}: {item['evidence'][0]}")
        suggestion = "建议在 ICU 转出或出院前启动 PICS 风险交班，联合康复、护理和随访门诊制定身体、认知与心理恢复计划。"
        return {
            "transfer_candidate": transfer_candidate,
            "icu_days": icu_days,
            "overall_score": overall,
            "severity": severity,
            "dimensions": dimensions,
            "summary": summary,
            "evidence": evidence[:6],
            "suggestion": suggestion,
            "transfer_signal": discharge_signal,
        }

    async def _physical_dimension(self, *, patient_doc: dict[str, Any], patient_id: Any, now: datetime) -> dict[str, Any]:
        pid_str = str(patient_id)
        latest_icu_aw = await self.engine.db.col("alert_records").find_one(
            {"patient_id": pid_str, "alert_type": {"$in": ["icu_aw_risk", "early_mobility_recommendation"]}, "created_at": {"$gte": now - timedelta(days=7)}},
            sort=[("created_at", -1)],
        )
        admission_t = self.engine._icu_aw_admission_time(patient_doc) if hasattr(self.engine, "_icu_aw_admission_time") else None
        vent_info = await self.engine._get_ventilation_days(patient_id, now, admission_t) if hasattr(self.engine, "_get_ventilation_days") else {"days": 0}
        immobility = await self.engine._immobility_hours(patient_doc, patient_id, now) if hasattr(self.engine, "_immobility_hours") else 0.0
        score = 0.0
        evidence = []
        if latest_icu_aw:
            sev = str(latest_icu_aw.get("severity") or "").lower()
            score += 40 if sev in {"high", "critical"} else 25
            evidence.append("近 7 天存在 ICU-AW / 早期活动高风险信号")
        if float(vent_info.get("days") or 0.0) >= 7:
            score += 30
            evidence.append(f"机械通气 {vent_info.get('days')} 天")
        elif float(vent_info.get("days") or 0.0) >= 3:
            score += 20
        if float(immobility or 0.0) >= 72:
            score += 20
            evidence.append(f"卧床/活动缺失 {round(float(immobility), 1)} h")
        return {"score": round(min(score, 100.0), 2), "evidence": evidence}

    async def _cognitive_dimension(self, *, patient_doc: dict[str, Any], patient_id: Any, now: datetime) -> dict[str, Any]:
        pid_str = str(patient_id)
        cam_positive = await self.engine.db.col("alert_records").find_one(
            {
                "patient_id": pid_str,
                "alert_type": {"$in": ["cam_icu_positive", "delirium_risk", "sedation_delirium_conversion"]},
                "is_active": True,
                "created_at": {"$gte": now - timedelta(days=7)},
            },
            sort=[("created_at", -1)],
        )
        gcs = await self.engine._get_latest_assessment(patient_id, "gcs")
        rass = await self.engine._get_latest_assessment(patient_id, "rass")
        score = 0.0
        evidence = []
        if cam_positive:
            sev = str(cam_positive.get("severity") or "").lower()
            score += 45 if sev in {"high", "critical"} else 30
            evidence.append("近 7 天存在谵妄/认知波动告警")
        if gcs is not None and gcs < float(self._cfg().get("gcs_low_threshold", 13) or 13):
            score += 20
            evidence.append(f"GCS {gcs}")
        if rass is not None and rass <= float(self._cfg().get("deep_sedation_threshold", -3) or -3):
            score += 15
            evidence.append(f"深镇静 RASS {rass}")
        return {"score": round(min(score, 100.0), 2), "evidence": evidence}

    async def _psychological_dimension(self, *, patient_doc: dict[str, Any], patient_id: Any, now: datetime) -> dict[str, Any]:
        pid_str = str(patient_id)
        note = await self.engine.latest_nursing_note_analysis(pid_str, hours=48) if hasattr(self.engine, "latest_nursing_note_analysis") else None
        keywords = self._cfg().get("psychological_keywords", ["焦虑", "恐惧", "失眠", "噩梦", "创伤", "panic", "ptsd", "睡眠差"])
        events = await self.engine._get_recent_text_events(patient_id, keywords, hours=72, limit=200)
        severe_alerts = await self.engine.db.col("alert_records").count_documents(
            {"patient_id": pid_str, "severity": {"$in": ["high", "critical"]}, "created_at": {"$gte": now - timedelta(hours=72)}}
        )
        score = 0.0
        evidence = []
        if events:
            score += 35
            evidence.append("护理/文本记录存在焦虑或睡眠障碍线索")
        if note and any(str(item).strip() for item in (note.get("signal_labels") or []) if "意识" in str(item) or "沟通" in str(item)):
            score += 15
        if severe_alerts >= int(self._cfg().get("high_alert_threshold", 5) or 5):
            score += 20
            evidence.append(f"近72h高等级事件 {severe_alerts} 条")
        return {"score": round(min(score, 100.0), 2), "evidence": evidence}

    async def _persist_assessment(self, *, patient_doc: dict[str, Any], assessment: dict[str, Any], now: datetime) -> dict[str, Any]:
        doc = {
            "patient_id": str(patient_doc.get("_id") or ""),
            "patient_name": patient_doc.get("name") or "",
            "bed": patient_doc.get("hisBed") or "",
            "dept": patient_doc.get("dept") or patient_doc.get("hisDept") or "",
            "score_type": "pics_risk_assessment",
            "assessment": assessment,
            "calc_time": now,
            "updated_at": now,
            "month": now.strftime("%Y-%m"),
            "day": now.strftime("%Y-%m-%d"),
        }
        result = await self.engine.db.col("score").insert_one(doc)
        doc["_id"] = result.inserted_id
        await self.engine.db.col("patient").update_one(
            {"_id": patient_doc.get("_id")},
            {"$set": {"current_profile.pics_risk": {"assessment": assessment, "updated_at": now, "record_id": result.inserted_id}}},
        )
        try:
            await FollowupService(db=self.engine.db, config=getattr(self.engine, "config", None)).sync_case_from_pics(
                patient_doc=patient_doc,
                assessment=assessment,
                risk_record_id=result.inserted_id,
                now=now,
            )
        except Exception:
            pass
        return doc
