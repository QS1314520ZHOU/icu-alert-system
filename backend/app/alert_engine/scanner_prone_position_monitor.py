from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

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


class PronePositionMonitorScanner(BaseScanner):
    """ARDS 俯卧位适应证与执行质量监测。"""

    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="prone_position_monitor",
                interval_key="prone_position_monitor",
                default_interval=3600,
                initial_delay=96,
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
        cfg = self.engine._cfg("alert_engine", "prone_position_monitor", default={}) or {}
        return cfg if isinstance(cfg, dict) else {}

    def _position_code(self) -> str:
        return str(self._cfg().get("position_code") or "param_TiWei").strip() or "param_TiWei"

    def _position_value_text(self, row: dict[str, Any]) -> str:
        return " ".join(
            str(row.get(key) or "")
            for key in ("strVal", "value", "intVal", "fVal", "name", "paramName", "itemName", "remark")
        ).strip().lower()

    def _match_position_state(self, text: str) -> str | None:
        cfg = self._cfg()
        prone_values = [str(item).strip().lower() for item in cfg.get("prone_values", ["俯卧位", "俯卧", "prone", "pronation", "proning"]) if str(item).strip()]
        supine_values = [str(item).strip().lower() for item in cfg.get("supine_values", ["仰卧位", "仰卧", "平卧", "supine", "return supine", "恢复仰卧"]) if str(item).strip()]
        if any(token in text for token in prone_values):
            return "prone"
        if any(token in text for token in supine_values):
            return "supine"
        return None

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
            self.engine._log_info("俯卧位监测", len(alerts))
        return alerts

    async def _target_patients(self, patient_id: str | None) -> list[dict[str, Any]]:
        projection = {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "clinicalDiagnosis": 1, "admissionDiagnosis": 1}
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
        if assessment.get("candidate") and not assessment.get("currently_proned"):
            rule_id = "PRONE_POSITION_CANDIDATE"
            if not await self.engine._is_suppressed(patient_id_str, rule_id, same_rule_sec, max_per_hour):
                alert = await self.engine._create_alert(
                    rule_id=rule_id,
                    name="ARDS 患者符合俯卧位指征",
                    category="ventilator",
                    alert_type="prone_position_candidate",
                    severity="high",
                    parameter="prone_position",
                    condition={"pf_ratio_lt": assessment.get("pf_ratio"), "fio2_gte": assessment.get("fio2"), "peep_gte": assessment.get("peep")},
                    value=assessment.get("pf_ratio"),
                    patient_id=patient_id_str,
                    patient_doc=patient_doc,
                    device_id=None,
                    source_time=now,
                    explanation={
                        "summary": "当前 ARDS 患者满足俯卧位治疗适应证，但未见俯卧位执行记录。",
                        "evidence": assessment.get("evidence") or [],
                        "suggestion": "建议尽快评估并启动俯卧位治疗，目标每日累计俯卧位时长至少 16 小时。",
                        "text": "",
                    },
                    extra={"detail": assessment},
                )
                if alert:
                    alerts.append(alert)

        prone_hours = float(assessment.get("prone_hours_24h") or 0.0)
        if assessment.get("candidate") and prone_hours > 0 and prone_hours < float(self._cfg().get("target_hours_per_day", 16) or 16):
            rule_id = "PRONE_POSITION_DURATION"
            if not await self.engine._is_suppressed(patient_id_str, rule_id, same_rule_sec, max_per_hour):
                alert = await self.engine._create_alert(
                    rule_id=rule_id,
                    name="俯卧位时长未达标",
                    category="ventilator",
                    alert_type="prone_position_duration",
                    severity="warning" if prone_hours >= 8 else "high",
                    parameter="prone_hours_24h",
                    condition={"target_hours": self._cfg().get("target_hours_per_day", 16)},
                    value=round(prone_hours, 1),
                    patient_id=patient_id_str,
                    patient_doc=patient_doc,
                    device_id=None,
                    source_time=now,
                    explanation={
                        "summary": "最近 24 小时俯卧位累计时长不足，可能影响肺保护获益。",
                        "evidence": assessment.get("evidence") or [],
                        "suggestion": f"建议在无禁忌情况下将俯卧位累计时长提升至 {int(float(self._cfg().get('target_hours_per_day', 16) or 16))}h/天，并持续复评氧合改善。",
                        "text": "",
                    },
                    extra={"detail": assessment},
                )
                if alert:
                    alerts.append(alert)

        if assessment.get("complications"):
            rule_id = "PRONE_POSITION_COMPLICATION"
            if not await self.engine._is_suppressed(patient_id_str, rule_id, same_rule_sec, max_per_hour):
                alert = await self.engine._create_alert(
                    rule_id=rule_id,
                    name="俯卧位相关并发症风险",
                    category="ventilator",
                    alert_type="prone_position_complication",
                    severity="high",
                    parameter="prone_complication",
                    condition={"complication_count": len(assessment.get("complications") or [])},
                    value=len(assessment.get("complications") or []),
                    patient_id=patient_id_str,
                    patient_doc=patient_doc,
                    device_id=None,
                    source_time=now,
                    explanation={
                        "summary": "俯卧位期间出现并发症线索，需要及时复核体位治疗耐受性与管路安全。",
                        "evidence": list(assessment.get("complications") or [])[:5],
                        "suggestion": "建议立即复查面部/皮肤受压、管路固定、分泌物引流和血流动力学耐受性，必要时提前结束本轮俯卧位。",
                        "text": "",
                    },
                    extra={"detail": assessment},
                )
                if alert:
                    alerts.append(alert)
        return alerts

    async def _build_assessment(self, *, patient_doc: dict[str, Any], patient_id: Any, his_pid: str, now: datetime) -> dict[str, Any] | None:
        device_id = await self.engine._get_device_id_for_patient(patient_doc, ["vent"])
        if not device_id:
            return None
        cap = await self.engine._get_latest_device_cap(device_id)
        if not cap:
            return None
        fio2 = self.engine._vent_param(cap, "fio2", "param_FiO2")
        peep = self.engine._vent_param_priority(cap, ["peep_measured", "peep_set"], ["param_vent_measure_peep", "param_vent_peep"])
        if fio2 is None or peep is None:
            return None
        fio2_frac = fio2 / 100.0 if fio2 > 1 else fio2
        labs = await self.engine._get_latest_labs_map(his_pid, lookback_hours=24)
        pao2 = _to_float(((labs.get("pao2") or {}).get("value")) if isinstance(labs.get("pao2"), dict) else None)
        pf_ratio = round(float(pao2) / float(fio2_frac), 1) if pao2 is not None and fio2_frac > 0 else None
        ards_alert = await self.engine._get_latest_active_alert(str(patient_id), ["ards"], hours=24)
        candidate = bool((pf_ratio is not None and pf_ratio < float(self._cfg().get("pf_threshold", 150) or 150) and fio2_frac >= float(self._cfg().get("fio2_threshold", 0.6) or 0.6) and peep >= float(self._cfg().get("peep_threshold", 5) or 5)) or ards_alert)
        sessions = await self._prone_sessions(str(patient_id), now)
        prone_hours_24h = round(sum(self._session_hours_in_window(row, now - timedelta(hours=24), now) for row in sessions), 2)
        current_session = sessions[-1] if sessions and sessions[-1].get("open") else None
        complications = await self._prone_complications(patient_id, now) if current_session or prone_hours_24h > 0 else []
        evidence = []
        if pf_ratio is not None:
            evidence.append(f"P/F {pf_ratio}")
        evidence.append(f"FiO2 {round(fio2_frac, 2)}")
        evidence.append(f"PEEP {peep}")
        if prone_hours_24h > 0:
            evidence.append(f"24h俯卧位 {prone_hours_24h}h")
        if sessions:
            evidence.append(f"体位来源 {sessions[-1].get('source')}")
        return {
            "candidate": candidate,
            "currently_proned": bool(current_session),
            "pf_ratio": pf_ratio,
            "fio2": round(fio2_frac, 3),
            "peep": round(float(peep), 1),
            "prone_hours_24h": prone_hours_24h,
            "sessions": sessions,
            "complications": complications,
            "evidence": evidence,
        }

    async def _prone_sessions(self, patient_id: str, now: datetime) -> list[dict[str, Any]]:
        sessions = await self._prone_sessions_from_position_code(patient_id, now)
        if sessions:
            return sessions
        return await self._prone_sessions_from_text(patient_id, now)

    async def _prone_sessions_from_position_code(self, patient_id: str, now: datetime) -> list[dict[str, Any]]:
        since = now - timedelta(hours=48)
        cursor = self.engine.db.col("bedside").find(
            {"pid": str(patient_id), "code": self._position_code(), "time": {"$gte": since}},
            {"time": 1, "code": 1, "strVal": 1, "value": 1, "intVal": 1, "fVal": 1, "name": 1, "paramName": 1, "itemName": 1, "remark": 1},
        ).sort("time", 1).limit(2000)
        states: list[dict[str, Any]] = []
        async for row in cursor:
            event_time = row.get("time")
            if not isinstance(event_time, datetime):
                continue
            state = self._match_position_state(self._position_value_text(row))
            if not state:
                continue
            states.append({"time": event_time, "state": state, "source": "param_TiWei"})
        if not states:
            return []
        sessions: list[dict[str, Any]] = []
        open_start = None
        last_state = None
        for row in states:
            state = row["state"]
            if state == last_state:
                continue
            last_state = state
            if state == "prone":
                open_start = row["time"]
            elif state == "supine" and isinstance(open_start, datetime) and row["time"] > open_start:
                sessions.append(
                    {
                        "start": open_start,
                        "end": row["time"],
                        "hours": round((row["time"] - open_start).total_seconds() / 3600.0, 2),
                        "open": False,
                        "source": "position_code",
                    }
                )
                open_start = None
        if isinstance(open_start, datetime):
            sessions.append(
                {
                    "start": open_start,
                    "end": now,
                    "hours": round((now - open_start).total_seconds() / 3600.0, 2),
                    "open": True,
                    "source": "position_code",
                }
            )
        return sessions

    async def _prone_sessions_from_text(self, patient_id: str, now: datetime) -> list[dict[str, Any]]:
        cfg = self._cfg()
        start_keywords = [str(item).lower() for item in cfg.get("start_keywords", ["俯卧位", "prone", "proning"]) if str(item).strip()]
        end_keywords = [str(item).lower() for item in cfg.get("end_keywords", ["恢复仰卧", "结束俯卧位", "supine", "return supine", "停止俯卧位"]) if str(item).strip()]
        events = await self.engine._get_recent_text_events(patient_id, list(set(start_keywords + end_keywords)), hours=48, limit=1200)
        rows = []
        for event in sorted(events, key=lambda row: row.get("time") or datetime.min):
            text = " ".join(str(event.get(key) or "") for key in ("code", "strVal", "value")).lower()
            is_start = any(keyword in text for keyword in start_keywords)
            is_end = any(keyword in text for keyword in end_keywords)
            rows.append({"time": event.get("time"), "is_start": is_start, "is_end": is_end, "text": text})
        sessions: list[dict[str, Any]] = []
        open_start = None
        for row in rows:
            if row["is_start"]:
                open_start = row["time"]
            elif row["is_end"] and isinstance(open_start, datetime) and isinstance(row["time"], datetime) and row["time"] > open_start:
                hours = round((row["time"] - open_start).total_seconds() / 3600.0, 2)
                sessions.append({"start": open_start, "end": row["time"], "hours": hours, "open": False, "source": "text"})
                open_start = None
        if isinstance(open_start, datetime):
            sessions.append({"start": open_start, "end": now, "hours": round((now - open_start).total_seconds() / 3600.0, 2), "open": True, "source": "text"})
        return sessions

    async def _prone_complications(self, patient_id: Any, now: datetime) -> list[str]:
        cfg = self._cfg()
        keywords = [str(item) for item in cfg.get("complication_keywords", ["面部水肿", "压疮", "皮肤破损", "管路脱出", "tube dislodgement", "device_position_abnormal"]) if str(item).strip()]
        events = await self.engine._get_recent_text_events(patient_id, keywords, hours=24, limit=200)
        evidence = [" ".join(str(event.get(key) or "") for key in ("code", "strVal", "value")).strip() for event in events[:4]]
        device_alert = await self.engine._get_latest_active_alert(str(patient_id), ["device_position_abnormal"], hours=24)
        if device_alert:
            evidence.append("近期存在导管/管路位置异常告警")
        return [item for item in evidence if item][:5]

    def _session_hours_in_window(self, session: dict[str, Any], start: datetime, end: datetime) -> float:
        session_start = session.get("start")
        session_end = session.get("end")
        if not isinstance(session_start, datetime) or not isinstance(session_end, datetime):
            return 0.0
        overlap_start = max(session_start, start)
        overlap_end = min(session_end, end)
        if overlap_end <= overlap_start:
            return 0.0
        return round((overlap_end - overlap_start).total_seconds() / 3600.0, 2)

    async def _persist_assessment(self, *, patient_doc: dict[str, Any], assessment: dict[str, Any], now: datetime) -> dict[str, Any]:
        doc = {
            "patient_id": str(patient_doc.get("_id") or ""),
            "patient_name": patient_doc.get("name") or "",
            "bed": patient_doc.get("hisBed") or "",
            "dept": patient_doc.get("dept") or patient_doc.get("hisDept") or "",
            "score_type": "prone_position_monitor",
            "assessment": assessment,
            "calc_time": now,
            "updated_at": now,
            "month": now.strftime("%Y-%m"),
            "day": now.strftime("%Y-%m-%d"),
        }
        result = await self.engine.db.col("score").insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc
