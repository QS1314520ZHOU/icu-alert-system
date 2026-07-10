from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any

from app.services.llm_runtime import call_llm_chat

from .scanners import BaseScanner, ScannerSpec


def _to_float(value: Any) -> float | None:
    """安全解析浮点数。"""
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


def _parse_json_block(text: str) -> dict[str, Any] | None:
    """从 LLM 文本中提取 JSON。"""
    content = str(text or "").strip()
    if not content:
        return None
    content = re.sub(r"^\s*```(?:json)?\s*", "", content, flags=re.IGNORECASE)
    content = re.sub(r"\s*```\s*$", "", content, flags=re.IGNORECASE)
    try:
        parsed = json.loads(content)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", content)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None


class VentilatorAsynchronyScanner(BaseScanner):
    """基于呼吸机参数与患者状态识别人机不同步。"""

    def __init__(self, engine) -> None:
        """初始化扫描器。"""
        super().__init__(
            engine,
            ScannerSpec(
                name="ventilator_asynchrony",
                interval_key="ventilator_asynchrony",
                default_interval=1800,
                initial_delay=52,
            ),
        )

    def is_enabled(self) -> bool:
        """判断扫描器是否启用。"""
        return super().is_enabled() and bool(self._cfg().get("enabled", True))

    def interval_seconds(self) -> int:
        """读取配置中的自定义扫描间隔。"""
        interval = self._cfg().get("scan_interval")
        try:
            return max(300, int(interval))
        except (TypeError, ValueError):
            return super().interval_seconds()

    def _cfg(self) -> dict[str, Any]:
        """读取 scanner 配置。"""
        cfg = self.engine._cfg("alert_engine", "ventilator_asynchrony", default={}) or {}
        return cfg if isinstance(cfg, dict) else {}

    def _signal_codes(self, key: str, defaults: list[str]) -> list[str]:
        """读取信号编码配置。"""
        signal_codes = self._cfg().get("signal_codes", {})
        if isinstance(signal_codes, dict):
            value = signal_codes.get(key)
            if isinstance(value, str) and value.strip():
                return [value.strip()]
            if isinstance(value, list):
                rows = [str(item).strip() for item in value if str(item).strip()]
                if rows:
                    return rows
        return defaults

    def _snapshot_value(self, snapshot: dict[str, Any] | None, codes: list[str], *, numeric: bool = True) -> Any:
        """从快照中按优先级提取值。"""
        if not isinstance(snapshot, dict):
            return None
        params = snapshot.get("params") if isinstance(snapshot.get("params"), dict) else snapshot
        for code in codes:
            value = params.get(code)
            if value in (None, ""):
                continue
            if not numeric:
                return value
            number = _to_float(value)
            if number is not None:
                return number
        return None

    async def scan(self, patient_id: str | None = None) -> list[dict[str, Any]]:
        """扫描全部或指定患者，并返回本次生成的告警。"""
        patients = await self._target_patients(patient_id)
        if not patients:
            return []

        suppression = self.engine._cfg("alert_engine", "suppression", default={}) or {}
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        triggered = 0
        now = datetime.now()
        alerts: list[dict[str, Any]] = []
        for patient_doc in patients:
            patient_alerts = await self._scan_patient(
                patient_doc=patient_doc,
                now=now,
                same_rule_sec=same_rule_sec,
                max_per_hour=max_per_hour,
            )
            alerts.extend(patient_alerts)
            triggered += len(patient_alerts)

        if triggered > 0:
            self.engine._log_info("呼吸机不同步", triggered)
        return alerts

    async def _target_patients(self, patient_id: str | None) -> list[dict[str, Any]]:
        """读取本轮扫描目标患者。"""
        projection = {
            "_id": 1,
            "name": 1,
            "hisPid": 1,
            "hisBed": 1,
            "dept": 1,
            "hisDept": 1,
            "height": 1,
            "heightCm": 1,
            "gender": 1,
            "hisSex": 1,
        }
        if patient_id:
            patient_doc, _ = await self.engine._load_patient(patient_id)
            return [patient_doc] if isinstance(patient_doc, dict) else []
        patient_cursor = self.engine.db.col("patient").find(self.engine._active_patient_query(), projection)
        return [patient async for patient in patient_cursor]

    async def _scan_patient(
        self,
        *,
        patient_doc: dict[str, Any],
        now: datetime,
        same_rule_sec: int,
        max_per_hour: int,
    ) -> list[dict[str, Any]]:
        """扫描单个患者。"""
        patient_id = patient_doc.get("_id")
        if not patient_id:
            return []
        patient_id_str = str(patient_id)

        active_bind = await self.engine._get_active_vent_bind(patient_id_str)
        if not active_bind:
            return []
        device_id = active_bind.get("deviceID")
        if not device_id:
            return []

        cap = await self.engine._get_latest_device_cap(device_id, codes=self._required_codes())
        if not cap:
            return []

        if await self._on_neuromuscular_blockade(patient_id):
            return []

        state = await self._build_state(
            patient_doc=patient_doc,
            patient_id=patient_id,
            patient_id_str=patient_id_str,
            device_id=device_id,
            cap=cap,
            now=now,
        )
        detections = self._detect_asynchronies(state)
        dominant = self._pick_dominant_detection(detections)
        ai_index = self._compute_ai_index(state, detections) if detections else 0.0
        severity = self._severity_from_ai_and_type(ai_index=ai_index, base_level=str((dominant or {}).get("level") or "warning")) if dominant else "warning"
        module_links = await self._build_module_links(
            patient_id=patient_id_str,
            dominant=dominant or {},
            state=state,
            now=now,
        )
        llm_analysis = await self._llm_analysis(dominant=dominant or {}, state=state, ai_index=ai_index, module_links=module_links) if dominant else None
        recommendation = self._heuristic_suggestion(dominant=dominant or {"type": "none"}, state=state, ai_index=ai_index, module_links=module_links) if dominant else "当前未识别出明确的人机不同步模式。"
        if isinstance(llm_analysis, dict) and str(llm_analysis.get("recommendation") or "").strip():
            recommendation = str(llm_analysis.get("recommendation") or "").strip()
        await self.engine._persist_ventilator_asynchrony_assessment(
            pid_str=patient_id_str,
            patient_doc=patient_doc,
            now=now,
            assessment={
                "ai_index": round(ai_index * 100, 1),
                "severity": severity if dominant else "normal",
                "dominant_type": (dominant or {}).get("type"),
                "dominant_label": self._type_label(str((dominant or {}).get("type") or "")) if dominant else "无明确不同步",
                "detected_types": detections,
                "recommendation": recommendation,
                "module_links": module_links,
                "llm_analysis": llm_analysis,
                "ventilator_state": state,
            },
        )
        if not detections or not dominant:
            return []

        rule_id = f"VENT_ASYNCHRONY_{str(dominant.get('type') or 'UNKNOWN').upper()}"
        if await self.engine._is_suppressed(patient_id_str, rule_id, same_rule_sec, max_per_hour):
            return []

        suggestion = recommendation

        title = f"呼吸机不同步 - {self._type_label(str(dominant.get('type') or ''))}"
        evidence_source = str(self._cfg().get("evidence_source") or "SYNAPsE Delphi Consensus 2026, Intensive Care Medicine").strip()
        explanation = {
            "summary": f"{title}，当前不同步指数约 {ai_index * 100:.1f}%。",
            "evidence": self._explanation_evidence(dominant=dominant, state=state, detections=detections, ai_index=ai_index),
            "suggestion": suggestion,
            "text": "",
        }
        alert = await self.engine._create_alert(
            rule_id=rule_id,
            name=title,
            category="ventilator",
            alert_type="ventilator_asynchrony",
            severity=severity,
            parameter="asynchrony_index",
            condition={"asynchrony_type": dominant.get("type"), "analysis_window_minutes": state.get("window_minutes")},
            value=round(ai_index * 100, 1),
            patient_id=patient_id_str,
            patient_doc=patient_doc,
            device_id=device_id,
            source_time=state.get("source_time") or now,
            explanation=explanation,
            extra={
                "detail": {
                    "asynchrony_type": dominant.get("type"),
                    "asynchrony_type_label": self._type_label(str(dominant.get("type") or "")),
                    "detected_types": detections,
                    "asynchrony_index": round(ai_index * 100, 1),
                    "observed_stacked_vt": state.get("vt_actual"),
                    "ibw_vt_limit": state.get("ibw_vt_limit_ml"),
                    "current_mode": state.get("mode"),
                    "current_rass": state.get("rass"),
                    "ventilator_state": state,
                    "module_links": module_links,
                    "llm_analysis": llm_analysis,
                    "suggestion": suggestion,
                    "evidence": evidence_source,
                }
            },
        )
        return [alert] if alert else []

    def _required_codes(self) -> list[str]:
        """汇总扫描所需的监护/呼吸机参数编码。"""
        codes: list[str] = []
        default_map = {
            "mode": ["param_HuXiMoShi", "param_vent_mode"],
            "vt_set": ["param_vent_set_vt"],
            "rr_set": ["param_HuXiPinLv", "param_vent_rr_set"],
            "peep": ["param_vent_measure_peep", "param_vent_peep"],
            "ps": ["param_vent_ps"],
            "ti_set": ["param_vent_ti", "param_vent_insp_time"],
            "trigger_sensitivity": ["param_vent_trigger", "param_trigger_sensitivity"],
            "vt_actual": ["param_vent_vt"],
            "rr_total": ["param_vent_resp", "param_vent_rr_total"],
            "rr_spontaneous": ["param_vent_rr_spont", "param_vent_rr_spontaneous"],
            "pip": ["param_vent_pip"],
            "pplat": ["param_vent_plat_pressure"],
            "minute_vent": ["param_vent_VE"],
            "double_trigger_count": ["param_vent_async_double_count"],
            "ineffective_trigger_count": ["param_vent_async_ineffective_count"],
            "reverse_trigger_count": ["param_vent_async_reverse_count"],
            "flow_starvation_count": ["param_vent_async_flow_starvation_count"],
            "premature_cycling_count": ["param_vent_async_premature_count"],
            "delayed_cycling_count": ["param_vent_async_delayed_count"],
            "double_trigger_interval_ratio": ["param_vent_double_trigger_interval_ratio"],
            "pressure_scooping_flag": ["param_vent_pressure_scooping_flag"],
            "reverse_trigger_flag": ["param_vent_reverse_trigger_flag"],
            "premature_cycling_flag": ["param_vent_premature_cycling_flag"],
            "delayed_cycling_flag": ["param_vent_delayed_cycling_flag"],
            "expiratory_muscle_flag": ["param_vent_expiratory_muscle_flag"],
            "cycling_flow_ratio": ["param_vent_cycling_flow_ratio"],
        }
        for key, defaults in default_map.items():
            for code in self._signal_codes(key, defaults):
                if code not in codes:
                    codes.append(code)
        return codes

    async def _collect_window_metrics(self, *, patient_id: Any, window_minutes: int) -> dict[str, dict[str, float | int | None]]:
        """采集时间窗级参数统计，用于近似波形识别。"""
        since = datetime.now() - timedelta(minutes=max(window_minutes, 5))
        metric_keys = [
            "vt_actual",
            "vt_set",
            "rr_total",
            "rr_set",
            "rr_spontaneous",
            "ti_set",
            "double_trigger_count",
            "ineffective_trigger_count",
            "reverse_trigger_count",
            "flow_starvation_count",
            "premature_cycling_count",
            "delayed_cycling_count",
            "double_trigger_interval_ratio",
            "pressure_scooping_flag",
            "reverse_trigger_flag",
            "premature_cycling_flag",
            "delayed_cycling_flag",
            "expiratory_muscle_flag",
            "cycling_flow_ratio",
        ]
        summary: dict[str, dict[str, float | int | None]] = {}
        for key in metric_keys:
            values: list[float] = []
            for code in self._signal_codes(key, []):
                series = await self.engine._get_param_series_by_pid(
                    patient_id,
                    code,
                    since,
                    prefer_device_types=["vent"],
                    limit=600,
                )
                local_values = [_to_float(item.get("value")) for item in series]
                local_values = [float(item) for item in local_values if item is not None]
                if local_values:
                    values = local_values
                    break
            if not values:
                summary[key] = {"latest": None, "max": None, "min": None, "mean": None, "delta": None, "positive_samples": 0}
                continue
            latest = values[-1]
            maximum = max(values)
            minimum = min(values)
            mean_value = round(sum(values) / len(values), 4)
            delta = None
            if len(values) >= 2:
                delta = round(values[-1] - values[0], 4)
            positive_samples = len([value for value in values if value > 0])
            summary[key] = {
                "latest": round(latest, 4),
                "max": round(maximum, 4),
                "min": round(minimum, 4),
                "mean": mean_value,
                "delta": delta,
                "positive_samples": positive_samples,
            }
        return summary

    async def _build_state(
        self,
        *,
        patient_doc: dict[str, Any],
        patient_id: Any,
        patient_id_str: str,
        device_id: str,
        cap: dict[str, Any],
        now: datetime,
    ) -> dict[str, Any]:
        """构建不同步检测状态。"""
        window_minutes = int(self._cfg().get("analysis_window_minutes", 30) or 30)
        pbw = self.engine._predicted_body_weight(patient_doc)
        drive = await self.engine._latest_diaphragm_drive(patient_id, device_id)
        window_metrics = await self._collect_window_metrics(patient_id=patient_id, window_minutes=window_minutes)
        vt_actual = self._snapshot_value(cap, self._signal_codes("vt_actual", ["param_vent_vt"]))
        vt_set = self._snapshot_value(cap, self._signal_codes("vt_set", ["param_vent_set_vt"]))
        rr_total = self._snapshot_value(cap, self._signal_codes("rr_total", ["param_vent_resp", "param_vent_rr_total"]))
        rr_set = self._snapshot_value(cap, self._signal_codes("rr_set", ["param_HuXiPinLv", "param_vent_rr_set"]))
        return {
            "patient_id": patient_id_str,
            "source_time": cap.get("time") if isinstance(cap, dict) else now,
            "window_minutes": window_minutes,
            "mode": str(self._snapshot_value(cap, self._signal_codes("mode", ["param_HuXiMoShi", "param_vent_mode"]), numeric=False) or "").strip(),
            "vt_set": vt_set,
            "vt_actual": vt_actual,
            "rr_set": rr_set,
            "rr_total": rr_total,
            "rr_spontaneous": self._snapshot_value(cap, self._signal_codes("rr_spontaneous", ["param_vent_rr_spont", "param_vent_rr_spontaneous"])),
            "peep": self._snapshot_value(cap, self._signal_codes("peep", ["param_vent_measure_peep", "param_vent_peep"])),
            "ps": self._snapshot_value(cap, self._signal_codes("ps", ["param_vent_ps"])),
            "trigger_sensitivity": self._snapshot_value(cap, self._signal_codes("trigger_sensitivity", ["param_vent_trigger", "param_trigger_sensitivity"])),
            "ti_set": self._snapshot_value(cap, self._signal_codes("ti_set", ["param_vent_ti", "param_vent_insp_time"])),
            "pip": self._snapshot_value(cap, self._signal_codes("pip", ["param_vent_pip"])),
            "pplat": self._snapshot_value(cap, self._signal_codes("pplat", ["param_vent_plat_pressure"])),
            "minute_vent": self._snapshot_value(cap, self._signal_codes("minute_vent", ["param_vent_VE"])),
            "double_trigger_count": self._snapshot_value(cap, self._signal_codes("double_trigger_count", ["param_vent_async_double_count"])),
            "ineffective_trigger_count": self._snapshot_value(cap, self._signal_codes("ineffective_trigger_count", ["param_vent_async_ineffective_count"])),
            "reverse_trigger_count": self._snapshot_value(cap, self._signal_codes("reverse_trigger_count", ["param_vent_async_reverse_count"])),
            "flow_starvation_count": self._snapshot_value(cap, self._signal_codes("flow_starvation_count", ["param_vent_async_flow_starvation_count"])),
            "premature_cycling_count": self._snapshot_value(cap, self._signal_codes("premature_cycling_count", ["param_vent_async_premature_count"])),
            "delayed_cycling_count": self._snapshot_value(cap, self._signal_codes("delayed_cycling_count", ["param_vent_async_delayed_count"])),
            "double_trigger_interval_ratio": self._snapshot_value(cap, self._signal_codes("double_trigger_interval_ratio", ["param_vent_double_trigger_interval_ratio"])),
            "pressure_scooping_flag": self._snapshot_value(cap, self._signal_codes("pressure_scooping_flag", ["param_vent_pressure_scooping_flag"])),
            "reverse_trigger_flag": self._snapshot_value(cap, self._signal_codes("reverse_trigger_flag", ["param_vent_reverse_trigger_flag"])),
            "premature_cycling_flag": self._snapshot_value(cap, self._signal_codes("premature_cycling_flag", ["param_vent_premature_cycling_flag"])),
            "delayed_cycling_flag": self._snapshot_value(cap, self._signal_codes("delayed_cycling_flag", ["param_vent_delayed_cycling_flag"])),
            "expiratory_muscle_flag": self._snapshot_value(cap, self._signal_codes("expiratory_muscle_flag", ["param_vent_expiratory_muscle_flag"])),
            "cycling_flow_ratio": self._snapshot_value(cap, self._signal_codes("cycling_flow_ratio", ["param_vent_cycling_flow_ratio"])),
            "rass": await self.engine._get_latest_assessment(patient_id, "rass"),
            "p0_1": _to_float((drive or {}).get("p0_1")),
            "edi": _to_float((drive or {}).get("edi")),
            "pbw": pbw,
            "vt_ml_kg": round(float(vt_actual) / float(pbw), 2) if vt_actual is not None and pbw else None,
            "ibw_vt_limit_ml": round(float(pbw) * 8.0, 1) if pbw else None,
            "recent_drives": drive,
            "window_metrics": window_metrics,
        }

    async def _on_neuromuscular_blockade(self, patient_id: Any) -> bool:
        """判断近期是否存在肌松药暴露。"""
        keywords = self._cfg().get("muscle_relaxant_keywords", [])
        if not isinstance(keywords, list) or not keywords:
            keywords = ["罗库溴铵", "维库溴铵", "顺式阿曲库铵", "阿曲库铵", "mivacurium", "rocuronium", "vecuronium", "cisatracurium"]
        docs = await self.engine._get_recent_drug_docs_window(patient_id, hours=8, limit=200)
        blob = " ".join(
            " ".join(str(doc.get(key) or "") for key in ("drugName", "orderName", "drugSpec"))
            for doc in docs
        ).lower()
        return any(str(keyword).strip().lower() in blob for keyword in keywords if str(keyword).strip())

    def _detect_asynchronies(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        """根据状态识别人机不同步类型。"""
        cfg = self._cfg()
        detections: list[dict[str, Any]] = []
        window_metrics = state.get("window_metrics") if isinstance(state.get("window_metrics"), dict) else {}
        total_breaths = max(int((_to_float(state.get("rr_total")) or _to_float(state.get("rr_set")) or 0) * int(state.get("window_minutes") or 30)), 1)
        vt_ml_kg = _to_float(state.get("vt_ml_kg"))
        ti_set = _to_float(state.get("ti_set"))
        rr_set = _to_float(state.get("rr_set"))
        rr_total = _to_float(state.get("rr_total"))
        rr_spont = _to_float(state.get("rr_spontaneous"))
        p01 = _to_float(state.get("p0_1"))
        edi = _to_float(state.get("edi"))
        mode = str(state.get("mode") or "").upper()
        rass = _to_float(state.get("rass"))

        heuristic_map = cfg.get("heuristic_event_fraction", {}) if isinstance(cfg.get("heuristic_event_fraction"), dict) else {}
        level_map = cfg.get("type_severity", {}) if isinstance(cfg.get("type_severity"), dict) else {}

        def window_latest(metric_key: str) -> float | None:
            row = window_metrics.get(metric_key)
            return _to_float(row.get("latest")) if isinstance(row, dict) else None

        def window_max(metric_key: str) -> float | None:
            row = window_metrics.get(metric_key)
            return _to_float(row.get("max")) if isinstance(row, dict) else None

        def window_delta(metric_key: str) -> float | None:
            row = window_metrics.get(metric_key)
            return _to_float(row.get("delta")) if isinstance(row, dict) else None

        def window_positive(metric_key: str) -> int:
            row = window_metrics.get(metric_key)
            if not isinstance(row, dict):
                return 0
            try:
                return int(row.get("positive_samples") or 0)
            except (TypeError, ValueError):
                return 0

        def event_count(counter_key: str, heuristic_key: str, fallback_fraction: float, flag_key: str | None = None) -> int:
            counter = _to_float(state.get(counter_key))
            if counter is not None and counter > 0:
                return int(counter)
            counter_delta = window_delta(counter_key)
            if counter_delta is not None and counter_delta > 0:
                return max(1, int(counter_delta))
            if flag_key:
                positive_samples = window_positive(flag_key)
                if positive_samples > 0:
                    return positive_samples
            return max(1, int(total_breaths * float(heuristic_map.get(heuristic_key, fallback_fraction))))

        drive_high = bool((p01 is not None and p01 >= float(cfg.get("drive_p0_1_threshold", 3.5) or 3.5)) or (edi is not None and edi >= float(cfg.get("drive_edi_threshold", 15) or 15)))
        controlled_mode = any(token in mode for token in ["AC", "VC", "PC", "SIMV", "APRV"])
        psv_mode = "PSV" in mode
        interval_ratio = _to_float(state.get("double_trigger_interval_ratio"))
        if interval_ratio is None:
            interval_ratio = window_latest("double_trigger_interval_ratio")
        cycling_flow_ratio = _to_float(state.get("cycling_flow_ratio"))
        if cycling_flow_ratio is None:
            cycling_flow_ratio = window_latest("cycling_flow_ratio")
        pressure_scooping = (_to_float(state.get("pressure_scooping_flag")) or 0) > 0 or window_positive("pressure_scooping_flag") > 0
        reverse_trigger_flag = (_to_float(state.get("reverse_trigger_flag")) or 0) > 0 or window_positive("reverse_trigger_flag") > 0
        premature_flag = (_to_float(state.get("premature_cycling_flag")) or 0) > 0 or window_positive("premature_cycling_flag") > 0
        delayed_flag = (_to_float(state.get("delayed_cycling_flag")) or 0) > 0 or window_positive("delayed_cycling_flag") > 0
        expiratory_flag = (_to_float(state.get("expiratory_muscle_flag")) or 0) > 0 or window_positive("expiratory_muscle_flag") > 0
        rr_total_peak = window_max("rr_total") or rr_total
        rr_spont_peak = window_max("rr_spontaneous") or rr_spont

        if ((rr_total is not None and rr_set is not None and rr_total <= rr_set + float(cfg.get("ineffective_rr_gap_tolerance", 1) or 1)) and drive_high):
            if (_to_float(state.get("ineffective_trigger_count")) or 0) > 0 or expiratory_flag or (rr_spont_peak is not None and rr_spont_peak <= float(cfg.get("ineffective_spontaneous_rr_max", 2) or 2)):
                detections.append({"type": "ineffective_triggering", "level": str(level_map.get("ineffective_triggering") or "warning"), "event_count": event_count("ineffective_trigger_count", "ineffective_triggering", 0.08, "expiratory_muscle_flag")})

        if vt_ml_kg is not None and vt_ml_kg > float(cfg.get("stacked_vt_ml_kg_threshold", 8.0) or 8.0):
            vt_ratio = (_to_float(state.get("vt_actual")) or 0.0) / max((_to_float(state.get("vt_set")) or 1.0), 1.0)
            if (_to_float(state.get("double_trigger_count")) or 0) > 0 or (interval_ratio is not None and interval_ratio < float(cfg.get("double_trigger_interval_ratio_threshold", 0.5) or 0.5)) or ((rr_total_peak or 0) >= (rr_set or 0) + float(cfg.get("double_trigger_rr_excess", 5) or 5) and vt_ratio >= float(cfg.get("double_trigger_vt_ratio", 1.5) or 1.5)):
                detections.append({"type": "double_triggering", "level": str(level_map.get("double_triggering") or "high"), "event_count": event_count("double_trigger_count", "double_triggering", 0.12)})

        if controlled_mode and rass is not None and rass <= float(cfg.get("reverse_rass_threshold", -3) or -3):
            if (_to_float(state.get("reverse_trigger_count")) or 0) > 0 or reverse_trigger_flag or ((rr_spont_peak or 0) > 0 and drive_high):
                detections.append({"type": "reverse_triggering", "level": str(level_map.get("reverse_triggering") or "high"), "event_count": event_count("reverse_trigger_count", "reverse_triggering", 0.1, "reverse_trigger_flag")})

        if "AC-VC" in mode or ("AC" in mode and "VC" in mode):
            if pressure_scooping or ((rr_total_peak or 0) > (rr_set or 0) + float(cfg.get("flow_starvation_rr_excess", 3) or 3) and drive_high):
                detections.append({"type": "flow_starvation", "level": str(level_map.get("flow_starvation") or "warning"), "event_count": event_count("flow_starvation_count", "flow_starvation", 0.08, "pressure_scooping_flag")})

        if psv_mode and ti_set is not None and ti_set < float(cfg.get("premature_ti_threshold", 0.5) or 0.5):
            if (_to_float(state.get("premature_cycling_count")) or 0) > 0 or premature_flag or (cycling_flow_ratio or 0) > float(cfg.get("cycling_flow_ratio_threshold", 0.25) or 0.25):
                detections.append({"type": "premature_cycling", "level": str(level_map.get("premature_cycling") or "warning"), "event_count": event_count("premature_cycling_count", "premature_cycling", 0.06, "premature_cycling_flag")})

        if psv_mode and ti_set is not None and ti_set > float(cfg.get("delayed_ti_threshold", 1.5) or 1.5):
            if (_to_float(state.get("delayed_cycling_count")) or 0) > 0 or delayed_flag or expiratory_flag:
                detections.append({"type": "delayed_cycling", "level": str(level_map.get("delayed_cycling") or "warning"), "event_count": event_count("delayed_cycling_count", "delayed_cycling", 0.06, "delayed_cycling_flag")})

        return detections

    def _pick_dominant_detection(self, detections: list[dict[str, Any]]) -> dict[str, Any] | None:
        """选择主导不同步类型。"""
        if not detections:
            return None
        rank = {"warning": 1, "high": 2, "critical": 3}
        return max(detections, key=lambda item: (rank.get(str(item.get("level") or "warning"), 0), int(item.get("event_count") or 0)))

    def _compute_ai_index(self, state: dict[str, Any], detections: list[dict[str, Any]]) -> float:
        """计算不同步指数。"""
        rr_total = _to_float(state.get("rr_total")) or _to_float(state.get("rr_set")) or 0.0
        total_breaths = max(rr_total * float(state.get("window_minutes") or 30), 1.0)
        event_count = sum(max(int(item.get("event_count") or 0), 0) for item in detections)
        return min(round(event_count / total_breaths, 4), 1.0)

    def _severity_from_ai_and_type(self, *, ai_index: float, base_level: str) -> str:
        """结合类型严重度和不同步指数输出最终级别。"""
        cfg = self._cfg()
        critical_thr = float(cfg.get("ai_threshold_critical", 0.30) or 0.30)
        high_thr = float(cfg.get("ai_threshold_high", 0.10) or 0.10)
        warning_thr = float(cfg.get("ai_threshold_warning", 0.10) or 0.10)
        if ai_index >= critical_thr:
            return "critical"
        if ai_index >= high_thr:
            return "high"
        if ai_index >= warning_thr:
            return "warning" if base_level == "warning" else base_level
        return base_level

    def _type_label(self, asynchrony_type: str) -> str:
        """不同步类型中文名。"""
        labels = {
            "ineffective_triggering": "无效触发",
            "double_triggering": "双触发",
            "reverse_triggering": "反向触发",
            "flow_starvation": "流量饥饿",
            "premature_cycling": "呼气末提前终止",
            "delayed_cycling": "延迟终止",
        }
        return labels.get(asynchrony_type, asynchrony_type)

    def _explanation_evidence(self, *, dominant: dict[str, Any], state: dict[str, Any], detections: list[dict[str, Any]], ai_index: float) -> list[str]:
        """生成简要证据列表。"""
        evidence = [
            f"模式 {state.get('mode') or '未知'}",
            f"AI {ai_index * 100:.1f}%",
            f"RR设定/总频率 {state.get('rr_set')} / {state.get('rr_total')}",
        ]
        if state.get("vt_actual") is not None and state.get("ibw_vt_limit_ml") is not None:
            evidence.append(f"VTe {state.get('vt_actual')} mL，IBW上限 {state.get('ibw_vt_limit_ml')} mL")
        if state.get("rass") is not None:
            evidence.append(f"RASS {state.get('rass')}")
        if state.get("p0_1") is not None:
            evidence.append(f"P0.1 {state.get('p0_1')}")
        if len(detections) > 1:
            evidence.append("并存类型：" + " / ".join(self._type_label(str(item.get("type") or "")) for item in detections[:3]))
        return evidence[:5]

    async def _build_module_links(self, *, patient_id: str, dominant: dict[str, Any], state: dict[str, Any], now: datetime) -> dict[str, Any]:
        """构建与现有模块的联动信息。"""
        dominant_type = str(dominant.get("type") or "")
        links: dict[str, Any] = {
            "weaning_delay": False,
            "diaphragm_vidd_risk": False,
            "ards_lung_protection": False,
        }
        recent_weaning = await self.engine.db.col("score").find_one(
            {"patient_id": patient_id, "score_type": "weaning_assessment", "calc_time": {"$gte": now - timedelta(hours=24)}},
            sort=[("calc_time", -1)],
        )
        if recent_weaning and str(dominant.get("level") or "") in {"high", "critical"}:
            links["weaning_delay"] = True
            links["recent_weaning_assessment"] = {
                "risk_level": recent_weaning.get("risk_level"),
                "recommendation": recent_weaning.get("recommendation"),
                "calc_time": recent_weaning.get("calc_time"),
            }

        drive_high = bool((_to_float(state.get("p0_1")) or 0) >= float(self._cfg().get("drive_p0_1_threshold", 3.5) or 3.5) or (_to_float(state.get("edi")) or 0) >= float(self._cfg().get("drive_edi_threshold", 15) or 15))
        if drive_high or dominant_type in {"ineffective_triggering", "double_triggering", "flow_starvation"}:
            links["diaphragm_vidd_risk"] = True

        recent_ards = await self.engine.db.col("alert_records").find_one(
            {"patient_id": patient_id, "alert_type": "ards", "created_at": {"$gte": now - timedelta(hours=24)}},
            sort=[("created_at", -1)],
        )
        if recent_ards and dominant_type == "double_triggering" and (_to_float(state.get("vt_ml_kg")) or 0) > 8:
            links["ards_lung_protection"] = True
            links["recent_ards_alert"] = {"severity": recent_ards.get("severity"), "created_at": recent_ards.get("created_at")}
        return links

    def _heuristic_suggestion(self, *, dominant: dict[str, Any], state: dict[str, Any], ai_index: float, module_links: dict[str, Any]) -> str:
        """生成规则化建议。"""
        asynchrony_type = str(dominant.get("type") or "")
        if asynchrony_type == "double_triggering":
            suggestion = (
                f"检测到双触发(AI={ai_index * 100:.1f}%)，叠加潮气量 {state.get('vt_actual')}mL 显著超过保护性通气目标。"
                "建议：①延长吸气时间至约1.0s ②评估是否需加深镇静 ③排除疼痛、焦虑、代谢性酸中毒等人机对抗原因。"
            )
        elif asynchrony_type == "ineffective_triggering":
            suggestion = (
                "检测到无效触发，提示患者努力未被有效识别。"
                "建议：①下调触发阈值或提升触发灵敏度 ②排查 Auto-PEEP/分泌物负荷 ③复核镇静深度与呼吸驱动。"
            )
        elif asynchrony_type == "reverse_triggering":
            suggestion = "检测到反向触发，建议复核深镇静策略、呼吸机模式与驱动频率，避免机控呼吸诱发规律性膈肌收缩。"
        elif asynchrony_type == "flow_starvation":
            suggestion = "检测到流量饥饿，建议增加吸气流速或调整通气模式/支持水平，并同步评估疼痛焦虑导致的高驱动。"
        elif asynchrony_type == "premature_cycling":
            suggestion = "检测到呼气末提前终止，建议适度延长吸气时间或优化 PSV 切换阈值，减轻吸气努力被过早截断。"
        else:
            suggestion = "检测到延迟终止，建议缩短吸气时间或调整 PSV 切换阈值，减轻呼气肌对抗和呼气末负担。"

        if module_links.get("weaning_delay"):
            suggestion += " 当前不同步可能干扰撤机评估，建议先控制不同步后再决定是否推进 SBT。"
        if module_links.get("diaphragm_vidd_risk"):
            suggestion += " 同时存在膈肌负荷异常/VIDD 风险，建议结合 P0.1/Edi 共同评估。"
        if module_links.get("ards_lung_protection"):
            suggestion += " ARDS 背景下双触发叠加 VT 需强化肺保护通气。"
        return suggestion

    async def _llm_analysis(self, *, dominant: dict[str, Any], state: dict[str, Any], ai_index: float, module_links: dict[str, Any]) -> dict[str, Any] | None:
        """调用 LLM 输出原因分析与参数调整建议。"""
        cfg = self._cfg()
        if not bool(cfg.get("use_llm_analysis", True)):
            return None
        system_prompt = (
            "你是 ICU 机械通气与人机不同步专家。"
            "请基于输入的呼吸机参数、患者状态和已识别不同步类型，输出严格 JSON。"
            "字段仅允许 analysis、recommendation、parameter_adjustments。"
        )
        user_prompt = json.dumps(
            {
                "asynchrony_type": dominant.get("type"),
                "asynchrony_label": self._type_label(str(dominant.get("type") or "")),
                "ai_index_percent": round(ai_index * 100, 1),
                "ventilator_state": state,
                "module_links": module_links,
            },
            ensure_ascii=False,
            default=str,
        )
        result = await self._safe_llm_call(
            call_llm_chat(
                cfg=self.engine.config,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=self.engine.config.llm_fast_model,
                temperature=float(cfg.get("llm_temperature", 0.1) or 0.1),
                max_tokens=int(cfg.get("llm_max_tokens", 600) or 600),
                timeout_seconds=float(cfg.get("llm_timeout", 20) or 20),
            ),
            fallback=None,
            timeout=float(cfg.get("llm_timeout", 20) or 20),
        )
        if not isinstance(result, dict):
            return None
        return _parse_json_block(str(result.get("text") or ""))
