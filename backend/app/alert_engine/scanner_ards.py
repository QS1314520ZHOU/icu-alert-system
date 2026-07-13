"""
基于 Berlin 2012 氧合条件的 ARDS 筛查扫描器。

核心设计原则:
- P/F 以 PaO2 采样时间为锚点，优先使用该时刻之前的 FiO2/PEEP
- 找不到锚点附近的 FiO2/PEEP 时，不得使用当前最新值进行 Berlin 分级
- PaO2/FiO2 时间差超过阈值 → machine_status=insufficient_data，仅保留预览比值
- S/F 不写入 oxygenation_grade，使用 sf_screen_positive / sf_screen_band
- BNP 仅作为替代病因线索；低 BNP 或无 HF 记录不自动标记 cardiogenic_exclusion=supported
- 影像 NLP 命中最多为 indeterminate，保留原始证据句
- 起病/影像/心源排除不可靠时，不得自动进入 possible_ards
- 区分 current (≤2h) / recent (2-6h) / stale (>6h)；recent 仅作为历史参考
- 按氧合等级区分 rule_id，避免轻度→重度升级时被抑制
- 机器评估状态与医生复核状态分开保存
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

from .scanners import BaseScanner, ScannerSpec


# ── 数据时效配置 ──────────────────────────────────────────────────────────

DEFAULT_FRESHNESS = {
    # current: 支持实时筛查及 P0/P1 告警
    "current_max_age_minutes": 120,
    # recent: 仅作为历史事件记录，不触发 P0/P1
    "recent_max_age_minutes": 360,
    # 超过此值视为过期
    "stale_max_age_minutes": 360,
    # PaO2 与 FiO2 测量时间最大允许差 (超过→ insufficient_data)
    "pao2_fio2_max_gap_minutes": 60,
    # SpO2 与 FiO2 测量时间最大允许差
    "spo2_fio2_max_gap_minutes": 30,
    # 影像报告最大有效时间
    "imaging_max_age_hours": 24,
    # 时间锚定查询：仅允许采样后这么久的参数（保守默认0，只用采样前）
    "forward_window_minutes": 0,
    # SF 筛查阈值
    "sf_screen_mild_band": 315,
    "sf_screen_moderate_band": 235,
    "sf_screen_severe_band": 148,
}


def _freshness_cfg(engine) -> dict[str, Any]:
    cfg = engine._cfg("alert_engine", "ards_oxygenation", default={}) or {}
    user = cfg.get("data_freshness", {}) if isinstance(cfg, dict) else {}
    merged = dict(DEFAULT_FRESHNESS)
    if isinstance(user, dict):
        merged.update(user)
    return merged


def _parse_dt_safe(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _format_number(value: object, digits: int = 1) -> str:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(num):
        return "-"
    rounded = round(num, digits)
    if digits <= 0 or abs(rounded - round(rounded)) < 1e-9:
        return str(int(round(rounded)))
    return f"{rounded:.{digits}f}".rstrip("0").rstrip(".")


def _round_number(value: object, digits: int = 1) -> float | int | None:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(num):
        return None
    rounded = round(num, digits)
    if digits <= 0 or abs(rounded - round(rounded)) < 1e-9:
        return int(round(rounded))
    return rounded


def _minutes_ago(t: datetime | None, now: datetime) -> float | None:
    if not isinstance(t, datetime):
        return None
    return (now - t).total_seconds() / 60.0


def _data_tier(age_minutes: float | None, freshness: dict) -> str:
    """Classify data as current / recent / stale."""
    if age_minutes is None:
        return "unknown"
    if age_minutes <= freshness["current_max_age_minutes"]:
        return "current"
    if age_minutes <= freshness["recent_max_age_minutes"]:
        return "recent"
    return "stale"


# ── Berlin 2012 P/F 阈值 ──────────────────────────────────────────────────

BERLIN_PF_THRESHOLDS = {"severe": 100, "moderate": 200, "mild": 300}

# ── S/F 筛查带 ────────────────────────────────────────────────────────────

SF_BANDS = {
    "severe": (1, 148),
    "moderate": (149, 235),
    "mild": (236, 315),
}


def _sf_band(sf_value: float) -> str:
    for band, (lo, hi) in SF_BANDS.items():
        if lo <= sf_value <= hi:
            return band
    return "none"


# ═══════════════════════════════════════════════════════════════════════════
# ArdsScanner
# ═══════════════════════════════════════════════════════════════════════════

class ArdsScanner(BaseScanner):
    """基于 Berlin 2012 氧合条件的 ARDS 筛查扫描器。"""

    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="ards",
                interval_key="ards",
                default_interval=300,
                initial_delay=20,
            ),
        )

    def _ards_cfg(self) -> dict[str, Any]:
        return self.engine._cfg("alert_engine", "ards_oxygenation", default={}) or {}

    def _freshness(self) -> dict[str, Any]:
        return _freshness_cfg(self.engine)

    # ── 主扫描入口 ────────────────────────────────────────────────

    async def scan(self) -> None:
        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {
                "_id": 1, "name": 1, "hisPid": 1, "hisBed": 1,
                "dept": 1, "hisDept": 1,
                "icuAdmissionTime": 1, "admissionTime": 1, "admitTime": 1,
                "gender": 1, "hisSex": 1, "height": 1, "heightCm": 1,
            },
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        triggered = 0
        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            his_pid = patient_doc.get("hisPid")
            if not his_pid:
                continue

            result = await self._assess_patient(patient_doc, pid_str, his_pid)
            if result is None:
                continue

            alert = await self._create_ards_alert(patient_doc, pid_str, result)
            if alert:
                triggered += 1

        if triggered > 0:
            self.engine._log_info("ARDS氧合筛查", triggered)

    # ── 核心评估逻辑 ──────────────────────────────────────────────

    async def _assess_patient(
        self, patient_doc: dict, pid_str: str, his_pid: str,
    ) -> dict[str, Any] | None:
        """执行完整 ARDS 氧合筛查评估。"""
        now = datetime.now()
        freshness = self._freshness()
        cfg = self._ards_cfg()
        peep_threshold = float(cfg.get("peep_threshold", 5) or 5)

        # 1. 呼吸机设备
        device_id = await self.engine._get_device_id_for_patient(patient_doc, ["vent"])
        if not device_id:
            return None

        # 2. 血气数据
        labs = await self.engine._get_latest_labs_map(his_pid, lookback_hours=24)
        pao2_entry = labs.get("pao2") if labs else None
        pao2 = pao2_entry.get("value") if isinstance(pao2_entry, dict) else None
        pao2_time = _parse_dt_safe(pao2_entry.get("time")) if isinstance(pao2_entry, dict) else None

        spo2_entry = labs.get("spo2") if labs else None
        spo2_lab = spo2_entry.get("value") if isinstance(spo2_entry, dict) else None
        spo2_lab_time = _parse_dt_safe(spo2_entry.get("time")) if isinstance(spo2_entry, dict) else None

        cap = await self.engine._get_latest_device_cap(device_id)
        vent_spo2 = self.engine._vent_param(cap, "spo2", "param_spo2") if cap else None

        # 3. 数据时效分层
        pao2_age = _minutes_ago(pao2_time, now)
        pao2_tier = _data_tier(pao2_age, freshness)

        can_use_abg = pao2 is not None and pao2_time is not None and pao2_tier != "stale"
        can_use_spo2_lab = (
            spo2_lab is not None and spo2_lab_time is not None
            and _data_tier(_minutes_ago(spo2_lab_time, now), freshness) != "stale"
        )
        spo2_value = spo2_lab if can_use_spo2_lab else vent_spo2

        if not can_use_abg and spo2_value is None:
            return None

        is_current = pao2_tier == "current"

        # 4. 时间锚定 FiO2 / PEEP
        anchor_time = pao2_time if can_use_abg else (spo2_lab_time if can_use_spo2_lab else now)
        fio2_result = await self._get_fio2_near_time(device_id, anchor_time, freshness)
        peep_result = await self._get_peep_near_time(device_id, anchor_time, freshness)

        fio2_raw = fio2_result.get("value") if isinstance(fio2_result, dict) else None
        fio2_time = fio2_result.get("time") if isinstance(fio2_result, dict) else None
        fio2_valid_for_berlin = fio2_result.get("valid_for_berlin", False) if isinstance(fio2_result, dict) else False
        fio2_temporal_rel = fio2_result.get("temporal_relation") if isinstance(fio2_result, dict) else None

        peep_raw = peep_result.get("value") if isinstance(peep_result, dict) else None
        peep_time = peep_result.get("time") if isinstance(peep_result, dict) else None
        peep_valid_for_berlin = peep_result.get("valid_for_berlin", False) if isinstance(peep_result, dict) else False

        peep_ok = peep_raw is not None and peep_raw >= peep_threshold

        # 5. 数据完备性
        missing_criteria: list[str] = []
        if fio2_raw is None:
            missing_criteria.append("fio2_missing")
        if peep_raw is None:
            missing_criteria.append("peep_missing")

        if not fio2_valid_for_berlin and fio2_raw is not None:
            missing_criteria.append("fio2_time_window_mismatch")
        if not peep_valid_for_berlin and peep_raw is not None:
            missing_criteria.append("peep_time_window_mismatch")

        data_freshness = {
            "pao2_age_minutes": pao2_age,
            "pao2_tier": pao2_tier,
            "fio2_age_minutes": _minutes_ago(fio2_time, now),
            "fio2_tier": _data_tier(_minutes_ago(fio2_time, now), freshness),
            "fio2_valid_for_berlin": fio2_valid_for_berlin,
            "fio2_temporal_relation": fio2_temporal_rel,
            "peep_age_minutes": _minutes_ago(peep_time, now),
            "peep_tier": _data_tier(_minutes_ago(peep_time, now), freshness),
            "peep_valid_for_berlin": peep_valid_for_berlin,
        }

        # 6. 计算比值与分级
        fio2_frac = None
        if fio2_raw is not None:
            fio2_frac = fio2_raw / 100.0 if fio2_raw > 1 else fio2_raw

        # 评估结果默认值
        oxygenation_grade = None
        ratio_type = None
        ratio_value = None
        measurement_time_gap = None
        calculated_ratio_preview = None
        calculated_ratio_valid = False
        sf_screen_positive = None
        sf_screen_band = None
        requires_abg_confirmation = False

        # --- P/F 路径 ---
        if can_use_abg and fio2_frac is not None and fio2_frac > 0 and fio2_time is not None:
            computed = pao2 / fio2_frac
            gap = abs((pao2_time - fio2_time).total_seconds() / 60.0)
            measurement_time_gap = gap

            if gap > freshness["pao2_fio2_max_gap_minutes"]:
                # 时间不匹配 → insufficient_data, 仅保留预览
                missing_criteria.append("pao2_fio2_time_mismatch")
                ratio_type = "pf"
                calculated_ratio_preview = _round_number(computed, 1)
                calculated_ratio_valid = False
            elif not fio2_valid_for_berlin or not peep_valid_for_berlin:
                # FiO2/PEEP 不在有效时间窗内 → insufficient_data
                ratio_type = "pf"
                calculated_ratio_preview = _round_number(computed, 1)
                calculated_ratio_valid = False
            else:
                # 完整有效
                ratio_value = computed
                ratio_type = "pf"
                calculated_ratio_preview = _round_number(computed, 1)
                calculated_ratio_valid = True
                if ratio_value <= BERLIN_PF_THRESHOLDS["severe"]:
                    oxygenation_grade = "severe"
                elif ratio_value <= BERLIN_PF_THRESHOLDS["moderate"]:
                    oxygenation_grade = "moderate"
                elif ratio_value <= BERLIN_PF_THRESHOLDS["mild"]:
                    oxygenation_grade = "mild"

        # --- S/F 路径 ---
        elif spo2_value is not None and fio2_frac is not None and fio2_frac > 0:
            spo2_num = float(spo2_value)
            if spo2_num <= 97:
                spo2_anchor = spo2_lab_time if can_use_spo2_lab else fio2_time
                computed = spo2_num / fio2_frac
                gap = abs((spo2_anchor - fio2_time).total_seconds() / 60.0) if spo2_anchor and fio2_time else None
                measurement_time_gap = gap

                if gap and gap > freshness["spo2_fio2_max_gap_minutes"]:
                    missing_criteria.append("spo2_fio2_time_mismatch")
                    calculated_ratio_preview = _round_number(computed, 1)
                    calculated_ratio_valid = False
                else:
                    calculated_ratio_preview = _round_number(computed, 1)
                    calculated_ratio_valid = fio2_valid_for_berlin

                ratio_type = "sf"
                sf_screen_positive = True
                sf_screen_band = _sf_band(computed)
                requires_abg_confirmation = True
                # S/F 不写入 oxygenation_grade — 使用 sf_screen_* 字段
            else:
                return None  # SpO2 > 97%

        if ratio_type is None:
            return None

        # 7. 确定 machine_status
        has_valid_ratio = calculated_ratio_valid and ratio_value is not None
        has_time_mismatch = "pao2_fio2_time_mismatch" in missing_criteria
        has_fio2_peep_window_mismatch = (
            "fio2_time_window_mismatch" in missing_criteria
            or "peep_time_window_mismatch" in missing_criteria
        )

        if has_time_mismatch or has_fio2_peep_window_mismatch or not has_valid_ratio:
            machine_status = "insufficient_data"
            oxygenation_grade = None
            ratio_value = None
        elif not is_current and pao2_tier == "recent":
            # recent data: oxygen_grade available but only as historical reference
            machine_status = "oxygenation_criteria_met"
        else:
            machine_status = "oxygenation_criteria_met"

        # 8. 急性起病
        icu_admission = self.engine._patient_icu_start_time(patient_doc)
        acute_onset_status = self._check_acute_onset(patient_doc, icu_admission, now)

        # 9. 影像 (保守)
        imaging = await self.engine.get_imaging_report_analysis(
            patient_doc, pid_str, hours=96,
            max_age_hours=int(freshness["imaging_max_age_hours"]),
            persist_if_refresh=False,
        )
        bilateral_status, imaging_evidence = self._check_bilateral_opacity(imaging)

        # 10. 心源排除 (极端保守)
        cardiogenic_status = await self._check_cardiogenic_exclusion(his_pid, imaging)

        # 11. 呼吸支持
        respiratory_support = self._determine_respiratory_support(peep_ok, fio2_frac)

        # 12. 汇总 missing_criteria
        if acute_onset_status == "unknown":
            missing_criteria.append("acute_onset")
        if bilateral_status == "indeterminate":
            missing_criteria.append("bilateral_opacity")
        if cardiogenic_status in ("not_excluded", "unknown"):
            missing_criteria.append("cardiogenic_exclusion")

        # 13. 整合后的综合状态
        status = self._determine_status(
            machine_status=machine_status,
            oxygenation_grade=oxygenation_grade,
            ratio_type=ratio_type,
            acute_onset_status=acute_onset_status,
            bilateral_status=bilateral_status,
            cardiogenic_status=cardiogenic_status,
            missing_criteria=missing_criteria,
            is_current=is_current,
        )

        assessment = {
            "assessment_type": "ards_oxygenation_screen",
            "definition_profile": "berlin_2012_oxygenation",
            "oxygenation_grade": oxygenation_grade,
            "ratio_type": ratio_type,
            "ratio_value": _round_number(ratio_value, 1) if ratio_value is not None else None,
            "calculated_ratio_preview": calculated_ratio_preview,
            "calculated_ratio_valid": calculated_ratio_valid,
            "fio2": _round_number(fio2_raw, 0 if (fio2_raw and fio2_raw > 1) else 2),
            "peep": _round_number(peep_raw, 1),
            "oxygenation_time": pao2_time.isoformat() if pao2_time else None,
            "fio2_time": fio2_time.isoformat() if fio2_time else None,
            "peep_time": peep_time.isoformat() if peep_time else None,
            "measurement_time_gap_minutes": _round_number(measurement_time_gap, 1),
            "acute_onset_status": acute_onset_status,
            "bilateral_opacity_status": bilateral_status,
            "bilateral_opacity_evidence": imaging_evidence,
            "cardiogenic_exclusion_status": cardiogenic_status,
            "respiratory_support_status": respiratory_support,
            "missing_criteria": missing_criteria,
            "status": status,
            "data_tier": pao2_tier if can_use_abg else _data_tier(_minutes_ago(spo2_lab_time, now), freshness),
            "requires_clinician_confirmation": status in {
                "possible_ards", "oxygenation_criteria_met",
                "alternative_explanation_possible", "insufficient_data",
            },
            # S/F 专用字段
            "sf_screen_positive": sf_screen_positive,
            "sf_screen_band": sf_screen_band,
            "requires_abg_confirmation": requires_abg_confirmation,
            # 数据新鲜度
            "data_freshness": data_freshness,
            # 机器评估（不可被医生复核覆盖）
            "machine_assessment": {
                "status": status,
                "oxygenation_grade": oxygenation_grade,
                "ratio_type": ratio_type,
                "ratio_value": _round_number(ratio_value, 1) if ratio_value is not None else None,
                "calculated_ratio_preview": calculated_ratio_preview,
                "calculated_ratio_valid": calculated_ratio_valid,
                "assessed_at": now.isoformat(),
                "definition_profile": "berlin_2012_oxygenation",
                "data_tier": pao2_tier if can_use_abg else (
                    _data_tier(_minutes_ago(spo2_lab_time, now), freshness)
                ),
            },
            "clinician_review": None,
        }

        return assessment

    # ── 时间锚定查询 ──────────────────────────────────────────────

    async def _get_fio2_near_time(
        self, device_id: str, anchor_time: datetime, freshness: dict,
    ) -> dict[str, Any]:
        """查询锚点附近的 FiO2，优先采样前参数。"""
        max_gap = freshness.get("fio2_max_age_minutes", freshness.get("current_max_age_minutes", 120))
        forward = freshness.get("forward_window_minutes", 0)
        return await self._get_vent_param_anchored(
            device_id, ["fio2"], ["param_FiO2"], anchor_time, max_gap, forward,
        )

    async def _get_peep_near_time(
        self, device_id: str, anchor_time: datetime, freshness: dict,
    ) -> dict[str, Any]:
        """查询锚点附近的 PEEP，优先采样前参数。"""
        max_gap = freshness.get("peep_max_age_minutes", freshness.get("current_max_age_minutes", 120))
        forward = freshness.get("forward_window_minutes", 0)
        return await self._get_vent_param_anchored(
            device_id, ["peep_measured", "peep_set"],
            ["param_vent_measure_peep", "param_vent_peep"],
            anchor_time, max_gap, forward,
        )

    async def _get_vent_param_anchored(
        self,
        device_id: str,
        concept_names: list[str],
        default_codes: list[str],
        anchor_time: datetime,
        max_gap_minutes: float,
        forward_minutes: float,
    ) -> dict[str, Any]:
        """
        时间锚定查询呼吸机参数。

        优先级:
        1. anchor_time 之前最近的值（在 max_gap_minutes 窗口内）→ valid_for_berlin=true, temporal_relation=before
        2. anchor_time 之后非常接近的值（在 forward_minutes 内，需配置允许）→ valid_for_berlin=true, temporal_relation=after
        3. 回退到最新值 → valid_for_berlin=false, 仅作参考展示

        返回: {"value": float|None, "time": datetime|None,
                "valid_for_berlin": bool, "temporal_relation": "before"|"after"|"fallback_latest"}
        """
        codes: list[str] = []
        for i, name in enumerate(concept_names):
            defs = [default_codes[i]] if i < len(default_codes) else []
            codes.extend(self.engine._vent_mapping_codes_sync(name, defs))
        codes = list(dict.fromkeys(codes))

        if not codes:
            return {"value": None, "time": None, "valid_for_berlin": False, "temporal_relation": None}

        # 主查询窗口: [anchor - max_gap, anchor + forward]
        window_start = anchor_time - timedelta(minutes=max_gap_minutes)
        window_end = anchor_time + timedelta(minutes=max(forward_minutes, 1))

        query = {
            "deviceID": device_id,
            "code": {"$in": codes},
            "time": {"$gte": window_start, "$lte": window_end},
        }

        best_before_val = None
        best_before_time = None
        best_before_gap = float("inf")
        best_after_val = None
        best_after_time = None
        best_after_gap = float("inf")

        cursor = self.engine.db.col("deviceCap").find(query).sort("time", -1).limit(200)
        async for doc in cursor:
            from app.utils.clinical import _cap_value, _cap_time
            v = _cap_value(doc)
            if v is None:
                continue
            t = _cap_time(doc)
            if t is None:
                continue
            if t <= anchor_time:
                gap = (anchor_time - t).total_seconds()
                if gap < best_before_gap:
                    best_before_gap = gap
                    best_before_val = v
                    best_before_time = t
            else:
                gap = (t - anchor_time).total_seconds()
                if gap < best_after_gap:
                    best_after_gap = gap
                    best_after_val = v
                    best_after_time = t

        # 优先 before
        if best_before_val is not None and (best_before_gap / 60.0) <= max_gap_minutes:
            return {
                "value": best_before_val, "time": best_before_time,
                "valid_for_berlin": True, "temporal_relation": "before",
            }

        # 其次 after (仅 forward_minutes > 0 时使用)
        if forward_minutes > 0 and best_after_val is not None and (best_after_gap / 60.0) <= forward_minutes:
            return {
                "value": best_after_val, "time": best_after_time,
                "valid_for_berlin": True, "temporal_relation": "after",
            }

        # 回退最新值 — 仅参考，不用于 Berlin 分级
        cap = await self.engine._get_latest_device_cap(device_id, codes=codes)
        if cap:
            from app.utils.clinical import _extract_param, _cap_time
            for code in codes:
                v = _extract_param(cap, code)
                if v is not None:
                    return {
                        "value": v, "time": _cap_time(cap),
                        "valid_for_berlin": False, "temporal_relation": "fallback_latest",
                    }

        return {"value": None, "time": None, "valid_for_berlin": False, "temporal_relation": None}

    # ── Berlin 标准判断（保守） ──────────────────────────────────

    def _check_acute_onset(
        self, patient_doc: dict, icu_admission: datetime | None, now: datetime,
    ) -> str:
        """急性起病判断 (Berlin: ≤1 week)。保守: unknown when >7d。"""
        if icu_admission is None:
            return "unknown"
        days = (now - icu_admission).total_seconds() / 86400.0
        return "met" if days <= 7 else "unknown"

    def _check_bilateral_opacity(self, imaging: dict | None) -> tuple[str, list[str]]:
        """
        影像双侧浸润检查。极度保守策略:

        - NLP 命中最多为 indeterminate（不可自动满足 Berlin 影像标准）
        - 明确否定 → not_met
        - 无报告 → unknown
        - 保留原始证据句供人工复核

        返回: (status, evidence_sentences)
        """
        evidence: list[str] = []
        if not isinstance(imaging, dict):
            return "unknown", evidence

        signals = imaging.get("matched_signals")
        if not isinstance(signals, list) or not signals:
            report_count = imaging.get("report_count", 0)
            if report_count > 0:
                return "not_met", evidence
            return "unknown", evidence

        # 收集肺实质相关信号作为证据
        parenchymal_codes = {"pulmonary_infiltrate_present", "pulmonary_infiltrate_progression"}
        for sig in signals:
            code = str(sig.get("code") or "")
            sentence = str(sig.get("sentence") or sig.get("label") or "").strip()
            if code in parenchymal_codes and sentence:
                evidence.append(sentence[:200])

        # NLP 命中最多为 indeterminate — 必须有医生确认才能升级为 met
        if evidence:
            return "indeterminate", evidence
        return "unknown", evidence

    async def _check_cardiogenic_exclusion(
        self, his_pid: str, imaging: dict | None,
    ) -> str:
        """
        心源性排除判断。极度保守:

        - 影像明确提示心源性 → not_excluded
        - BNP 明显升高/上升 → not_excluded
        - BNP 低、无 HF 记录、无医生/超声证据 → unknown（不得自动标记 supported）
        - 任何不确定场景 → unknown

        supported 状态仅可由医生复核后写入。
        """
        imaging_signals = (imaging or {}).get("matched_signals") if isinstance(imaging, dict) else None
        has_cardiogenic_hint = False

        if isinstance(imaging_signals, list):
            for sig in imaging_signals:
                sentence = str(sig.get("sentence") or sig.get("label") or "").lower()
                if any(kw in sentence for kw in [
                    "心源性", "心衰", "心功能不全", "心影增大", "肺淤血",
                    "肺水肿", "间质性肺水肿", "kerley",
                ]):
                    has_cardiogenic_hint = True

        bnp_trend = {}
        if hasattr(self.engine, "_get_bnp_trend"):
            try:
                bnp_trend = await self.engine._get_bnp_trend(his_pid, datetime.now(), hours=72)
            except Exception:
                pass

        bnp_latest = bnp_trend.get("latest") if isinstance(bnp_trend, dict) else None
        bnp_high = (bnp_latest or 0) >= 1000
        bnp_rising = (bnp_trend.get("ratio") or 0) >= 1.5 if isinstance(bnp_trend, dict) else False

        if has_cardiogenic_hint:
            return "not_excluded"
        if bnp_high or bnp_rising:
            return "not_excluded"

        # 即使 BNP 低、无 HF 记录，也不能自动标记 supported
        # supported 仅由医生复核后写入 clinician_review
        return "unknown"

    def _determine_respiratory_support(
        self, peep_ok: bool, fio2_frac: float | None,
    ) -> str:
        if peep_ok:
            return "invasive_ventilation_with_peep"
        if fio2_frac is not None and fio2_frac > 0.21:
            return "supplemental_oxygen"
        return "none"

    def _determine_status(
        self, *,
        machine_status: str,
        oxygenation_grade: str | None,
        ratio_type: str,
        acute_onset_status: str,
        bilateral_status: str,
        cardiogenic_status: str,
        missing_criteria: list[str],
        is_current: bool,
    ) -> str:
        """确定综合机器评估状态。保守原则: 不清不楚不进 possible_ards。"""
        # insufficient_data 优先
        if machine_status == "insufficient_data":
            return "insufficient_data"

        # S/F → 非 Berlin 氧合
        if ratio_type == "sf":
            return "oxygenation_criteria_met"

        # 无有效氧合分级
        if oxygenation_grade is None or oxygenation_grade == "none":
            return "insufficient_data" if missing_criteria else "oxygenation_criteria_met"

        # 心源性未排除
        if cardiogenic_status in ("not_excluded", "unknown"):
            return "alternative_explanation_possible"

        # 影像 indeterminate/unknown → 不满足完整 Berlin
        if bilateral_status != "met":
            return "oxygenation_criteria_met"

        # 起病不确定
        if acute_onset_status != "met":
            return "oxygenation_criteria_met"

        # 有缺失项 → 不进入 possible_ards
        if missing_criteria:
            return "oxygenation_criteria_met"

        # 仅当 recent → 历史参考
        if not is_current:
            return "oxygenation_criteria_met"

        # 全部满足（极其罕见，需医生确认）→ possible_ards
        # 仅当: all Berlin criteria met + cardiogenic explicitly supported by clinician
        # 由于 cardiogenic 自动判断不会返回 supported，possible_ards
        # 实际上只能由医生复核后达到
        return "possible_ards"

    # ── 告警生成 ──────────────────────────────────────────────

    async def _create_ards_alert(
        self, patient_doc: dict, pid_str: str, assessment: dict,
    ) -> dict | None:
        ratio_type = assessment["ratio_type"]
        status = assessment["status"]
        ratio_value = assessment["ratio_value"]
        preview = assessment["calculated_ratio_preview"]
        valid = assessment["calculated_ratio_valid"]
        oxygenation_grade = assessment.get("oxygenation_grade")
        sf_band = assessment.get("sf_screen_band")
        data_tier = assessment.get("data_tier", "unknown")

        # 确定告警名称和严重度
        name, severity = self._alert_name_and_severity(
            ratio_type=ratio_type,
            oxygenation_grade=oxygenation_grade,
            sf_band=sf_band,
            valid=valid,
            status=status,
            data_tier=data_tier,
        )
        if name is None:
            return None

        rule_id = self._build_rule_id(oxygenation_grade, ratio_type, sf_band)

        suppression = self.engine._cfg("alert_engine", "suppression", default={}) or {}
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
            return None

        clinical_episode_id = f"resp_ep_{pid_str}"
        device_id = await self.engine._get_device_id_for_patient(patient_doc, ["vent"])

        peep = assessment["peep"]
        fio2_raw = assessment["fio2"]

        ratio_display = _format_number(ratio_value or preview, 1)
        fio2_display = _format_number(fio2_raw, 0 if (fio2_raw and fio2_raw > 1) else 2)
        peep_display = _format_number(peep, 1)

        # 影像
        imaging_findings = None
        try:
            img = await self.engine.get_imaging_report_analysis(
                patient_doc, pid_str, hours=96, max_age_hours=8, persist_if_refresh=False,
            )
            if img:
                signals = self.engine._select_imaging_signals(img, module_tags={"ards"}, max_items=3)
                imaging_findings = {"summary": self.engine._build_imaging_summary(signals), "matched_signals": signals}
        except Exception:
            pass

        explanation = await self.engine._polish_structured_alert_explanation(
            self._build_explanation_payload(
                name=name, severity=severity, ratio_type=ratio_type,
                ratio_value=ratio_display, peep=peep_display, fio2=fio2_display,
                assessment=assessment, imaging_findings=imaging_findings,
            )
        )

        condition = {
            "ratio_type": ratio_type,
            "ratio_value": _round_number(ratio_value, 1) if ratio_value is not None else None,
            "calculated_ratio_preview": preview,
            "calculated_ratio_valid": valid,
            "peep": _round_number(peep, 1),
            "fio2": _round_number(fio2_raw, 0 if (fio2_raw and fio2_raw > 1) else 2),
        }
        rounded_extra = {
            "pao2": assessment.get("pao2"),
            "spo2": assessment.get("spo2"),
            "fio2": condition["fio2"],
            "peep": condition["peep"],
        }

        alert = await self.engine._create_alert(
            rule_id=rule_id, name=name, category="syndrome",
            alert_type="ards_oxygenation_screen", severity=severity,
            parameter=ratio_type, condition=condition,
            value=condition["ratio_value"] or preview,
            patient_id=pid_str, patient_doc=patient_doc, device_id=device_id,
            source_time=_parse_dt_safe(assessment.get("oxygenation_time")) or datetime.now(),
            explanation=explanation,
            extra={
                **rounded_extra, "assessment": assessment,
                "clinical_episode_id": clinical_episode_id,
                "imaging_findings": imaging_findings,
            },
        )
        return alert

    def _build_rule_id(self, oxygenation_grade: str | None, ratio_type: str, sf_band: str | None = None) -> str:
        if ratio_type == "sf":
            band_upper = (sf_band or "none").upper()
            return f"ARDS_SF_SCREEN_{band_upper}"
        grade_upper = (oxygenation_grade or "insufficient").upper()
        return f"ARDS_OXYGENATION_{grade_upper}"

    def _build_clinical_episode_id(self, pid_str: str) -> str:
        return f"resp_ep_{pid_str}"

    def _alert_name_and_severity(
        self, *, ratio_type, oxygenation_grade, sf_band, valid, status, data_tier,
    ) -> tuple[str | None, str | None]:
        """生成告警名称和严重度。"""

        # insufficient_data
        if status == "insufficient_data":
            if ratio_type == "sf":
                return ("S/F数据不足以完成ARDS氧合筛查，建议复查动脉血气", "info")
            return ("ARDS氧合筛查数据不足，建议重新采集血气并复核呼吸机参数", "info")

        # S/F
        if ratio_type == "sf":
            band_labels = {"severe": "重度", "moderate": "中度", "mild": "轻度"}
            band_text = band_labels.get(sf_band or "", "")
            if band_text:
                return (f"S/F提示{band_text}氧合风险，建议复查动脉血气确认", "warning")
            return ("S/F提示ARDS氧合风险，建议复查动脉血气", "warning")

        # P/F with valid ratio
        if not valid:
            return ("ARDS氧合筛查数据不足，建议重新采集血气并复核呼吸机参数", "info")

        # recent tier → 仅作为历史参考，不触发 P0/P1
        if data_tier == "recent":
            return ("近期ARDS氧合分级筛查（历史参考，需更新数据）", "info")

        if oxygenation_grade == "severe":
            return ("符合ARDS重度氧合分级，需临床确认", "critical")
        elif oxygenation_grade == "moderate":
            return ("符合ARDS中度氧合分级，需结合影像和病程确认", "high")
        elif oxygenation_grade == "mild":
            return ("符合ARDS轻度氧合分级，需结合影像和病程确认", "warning")
        return (None, None)

    def _build_explanation_payload(
        self, *, name, severity, ratio_type, ratio_value, peep, fio2,
        assessment, imaging_findings,
    ) -> dict:
        ratio_label = "P/F" if ratio_type == "pf" else "S/F"
        status = assessment["status"]
        valid = assessment.get("calculated_ratio_valid", False)
        preview = assessment.get("calculated_ratio_preview")
        sf_band = assessment.get("sf_screen_band")

        parts = [f"{name}"]

        if status == "insufficient_data":
            if preview is not None:
                parts.append(f"，参考比值 {ratio_label} {_format_number(preview, 1)}（数据不足以正式分级）")
            parts.append("；建议重新采集动脉血气并在血气采样时间窗口内记录呼吸机参数")
        elif ratio_type == "sf" and sf_band:
            parts.append(f"，S/F ≈ {ratio_value}（{sf_band} 风险带），需复查动脉血气确认")
            parts.append("；S/F 为筛查工具，不可替代 Berlin 分级")
        else:
            parts.append(f"，当前 {ratio_label} {ratio_value}、PEEP {peep} cmH₂O")
            parts.append("；此为基于 Berlin 2012 氧合条件的筛查结果，需临床确认")

        summary = "".join(parts) + "。"

        evidence = [f"FiO₂ {fio2}", f"PEEP {peep}"]
        if assessment.get("pao2") is not None:
            evidence.append(f"PaO₂ {_format_number(assessment.get('pao2'), 0)} mmHg")
        if assessment.get("spo2") is not None:
            evidence.append(f"SpO₂ {_format_number(assessment.get('spo2'), 0)}%")
        if not valid and preview is not None:
            evidence.append(f"参考比值({ratio_label}) {_format_number(preview, 1)} — 数据不满足时效要求")
        evidence.append(f"起病时间: {self._status_label(assessment.get('acute_onset_status', 'unknown'))}")
        img_status = assessment.get("bilateral_opacity_status", "unknown")
        if img_status == "indeterminate":
            img_evidence = assessment.get("bilateral_opacity_evidence", [])
            if img_evidence:
                evidence.append(f"影像(NLP): {img_evidence[0][:120]}")
            evidence.append("双肺影像: 待医生确认（NLP 不足以独立满足 Berlin 影像标准）")
        else:
            evidence.append(f"双肺影像: {self._status_label(img_status)}")

        cardio = assessment.get("cardiogenic_exclusion_status", "unknown")
        if cardio == "not_excluded":
            evidence.append("心源性原因未排除，建议心脏超声+临床综合评估")
        else:
            evidence.append("心源性排除状态不明，建议完善心脏评估（不可仅凭 BNP 排除）")

        suggestion = (
            "本筛查基于 Berlin 2012 氧合条件，不构成完整 ARDS 诊断。"
            "请结合病程、影像和心功能评估完成临床诊断。"
            "S/F 仅作为筛查工具，BNP 不可单独用于排除心源性病因。"
        )
        if assessment.get("requires_abg_confirmation"):
            suggestion = "S/F 提示氧合风险，建议尽快复查动脉血气获取 P/F 比值。" + suggestion

        return {"summary": summary, "evidence": evidence, "suggestion": suggestion, "text": ""}

    @staticmethod
    def _status_label(status: str) -> str:
        labels = {
            "met": "符合", "not_met": "不符合", "unknown": "待确认",
            "indeterminate": "待医生确认", "not_excluded": "未排除",
            "supported": "可排除（已由医生确认）",
        }
        return labels.get(status, status)
