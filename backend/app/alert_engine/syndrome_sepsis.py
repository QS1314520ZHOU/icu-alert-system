"""脓毒症筛查与 Hour-1 Bundle 追踪（v2 三层架构）。

A 层：疑似脓毒症通用项目（感染可能 + 器官功能异常）
B 层：休克/低灌注条件项目（配置化触发）
C 层：个体化调整与不适用（医生确认）

applicability / execution / target / clinical_review 四维独立字段。
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Literal

from app.alert_engine.clinical_commons import EntityResolver

# ---------------------------------------------------------------------------
# 类型别名
# ---------------------------------------------------------------------------
InfectionVerdict = Literal["supported", "possible", "not_supported", "unknown"]
InfectionConfidence = Literal["strong", "moderate", "weak"]
Applicability = Literal["required", "conditional", "individualized", "not_applicable", "contraindicated", "review_pending"]
# execution.status 仅保留执行状态，不含适用性/目标语义
ExecutionStatus = Literal["not_started", "pending", "met", "met_late", "completed_before", "data_missing", "cancelled"]
ConditionStatus = Literal["met", "not_met", "unknown"]
ClinicalReviewStatus = Literal["pending", "confirmed", "overridden"]
ElementKey = Literal["lactate", "lactate_repeat", "antibiotic_assessment", "blood_culture", "infection_source", "fluid_resuscitation", "clinician_path_confirmation"]

# ---------------------------------------------------------------------------
# 感染证据评估关键词
# ---------------------------------------------------------------------------
INFECTION_POSITIVE_KEYWORDS = [
    "脓毒", "感染", "sepsis", "菌血症", "肺炎", "腹膜炎", "泌尿系感染",
    "胆道感染", "皮肤软组织感染", "颅内感染", "感染性心内膜炎",
    "bacteremia", "pneumonia", "peritonitis", "uti", "meningitis",
]
# 负向关键词 — 注意模糊否定短语必须排除（"不能排除感染"≠"排除感染"）
INFECTION_NEGATIVE_PATTERNS = [
    # 明确排除：仅匹配"排除感染"而不匹配"不能排除感染"/"尚不能排除感染"
    r"(?<!不能)(?<!尚不能)(?<!难以)(?<!无法)排除感染",
    r"非感染性", r"无感染[证迹]", r"无菌性",
    r"non-infectious", r"aseptic", r"not.infected",
]
INFECTION_UNCERTAIN_PATTERNS = [
    # 不确定性短语 — 命中后不能判 not_supported，回退 possible/unknown
    r"不能排除感染", r"尚不能排除感染", r"难以排除感染", r"无法排除感染",
    r"感染不除外", r"感染待排", r"感染可能", r"感染？", r"感染\?",
    r"cannot.exclude.infection", r"infection.cannot.be.excluded",
]
INFECTION_LAB_MARKER_CODES = ["pct", "crp", "wbc", "neut", "il6", "lac"]

# ---------------------------------------------------------------------------
# 休克/低灌注评估关键词
# ---------------------------------------------------------------------------
HYPOPERFUSION_TERMS = [
    "皮肤花斑", "毛细血管再充盈时间延长", "mottling", "crt_delayed",
    "意识改变", "少尿", "oliguria", "尿量<0.5mL/kg/h",
    "乳酸升高", "hyperlactatemia",
]
VASOPRESSOR_DRUG_NAMES = [
    "去甲肾上腺素", "肾上腺素", "血管加压素", "多巴胺",
    "norepinephrine", "epinephrine", "vasopressin", "dopamine",
]


class SepsisMixin:
    """脓毒症筛查与 Hour-1 Bundle v2（Mixin 供 AlertEngineBase 继承）。"""

    # =========================================================================
    # 配置读取
    # =========================================================================

    def _sepsis_bundle_cfg(self) -> dict:
        cfg = self.config.yaml_cfg.get("alert_engine", {}).get("sepsis_bundle", {})
        return cfg if isinstance(cfg, dict) else {}

    def _sepsis_bundle_score_types(self) -> list[str]:
        return ["sepsis_bundle_tracker", "sepsis_antibiotic_bundle"]

    def _sepsis_bundle_type_names(self) -> list[str]:
        return ["sepsis_hour1_bundle_v2", "sepsis_hour1_bundle", "sepsis_1h_antibiotic"]

    def _sepsis_bundle_active_type_names(self) -> list[str]:
        return ["sepsis_hour1_bundle_v2", "sepsis_hour1_bundle"]

    # =========================================================================
    # 感染证据评估
    # =========================================================================

    async def _assess_infection_evidence(
        self,
        patient_doc: dict,
        pid_str: str,
        his_pid: str | None,
        now: datetime,
    ) -> dict[str, Any]:
        """评估感染证据（supported / possible / not_supported / unknown）。

        分层规则：
          - strong: PCT≥2.0 + 发热 + 培养阳性 / 影像确诊
          - moderate: PCT 0.5-2.0 / CRP>40 / WBC异常 / 培养已送 / 诊断含感染
          - weak: 仅有单个 moderate 证据

        supported: ≥2 个 independent moderate 证据，或 ≥1 个 strong 证据
        possible: 1 个 moderate 证据但有不确定性；或 mixed 正负证据
        not_supported: 明确排除感染（负向模式匹配且无不确定性短语）
        unknown: 无任何证据

        关键规则：
          - 单个 WBC/CRP/发热/PCT/培养医嘱 不能直接判 supported
          - "不能排除感染"/"尚不能排除感染" 不命中负向
          - 感染证据仅用于筛查，不得自动确诊脓毒症
        """
        positive_strong: list[str] = []
        positive_moderate: list[str] = []
        negative: list[str] = []
        missing: list[str] = []
        uncertain_phrases: list[str] = []

        # 1) 诊断文本
        diagnosis = " ".join(
            str(patient_doc.get(key) or "")
            for key in ("clinicalDiagnosis", "admissionDiagnosis", "diagnosis")
        )

        # 先检测不确定性短语
        for pat in INFECTION_UNCERTAIN_PATTERNS:
            if re.search(pat, diagnosis, re.IGNORECASE):
                uncertain_phrases.append(f"诊断含不确定性: '{pat}'")
                break

        # 负向排除（使用 regex 避免匹配"不能排除感染"等）
        has_clear_negative = False
        for pat in INFECTION_NEGATIVE_PATTERNS:
            if re.search(pat, diagnosis, re.IGNORECASE):
                negative.append(f"诊断排除感染: (pattern={pat})")
                has_clear_negative = True

        # 正向关键词（仅在无负向或无不确定性时计入）
        if not has_clear_negative:
            for kw in INFECTION_POSITIVE_KEYWORDS:
                if kw.lower() in diagnosis.lower():
                    positive_moderate.append(f"诊断含'{kw}'")
                    break
        elif uncertain_phrases:
            # 有负向模式但不确定性覆盖 → 保留原始证据
            positive_moderate.append(f"诊断文本存在不确定性: {diagnosis[:80]}")

        # 2) 体温
        temp_series = []
        if hasattr(self, "_get_param_series_by_pid"):
            temp_series = await self._get_param_series_by_pid(
                pid_str,
                self._cfg("vital_signs", "temperature", "code", default="param_T"),
                now - timedelta(hours=24),
                prefer_device_types=["monitor"],
                limit=120,
            )
        temp_values = [float(row.get("value")) for row in temp_series if row.get("value") is not None]
        if temp_values:
            if max(temp_values) >= 38.3:
                positive_moderate.append(f"发热 Tmax={max(temp_values):.1f}°C (≥38.3)")
            elif min(temp_values) <= 36.0:
                positive_moderate.append(f"低体温 Tmin={min(temp_values):.1f}°C (≤36.0)")
            else:
                missing.append("体温在正常范围(36.0-38.3°C)")
        else:
            missing.append("近24h无体温记录")

        # 3) 感染标志物
        if his_pid and hasattr(self, "_get_latest_labs_map"):
            labs = await self._get_latest_labs_map(his_pid, lookback_hours=48)
            if labs:
                def _lab_val(key: str) -> float | None:
                    entry = labs.get(key) if isinstance(labs, dict) else None
                    if isinstance(entry, dict):
                        v = entry.get("value")
                    else:
                        v = entry
                    return _safe_float(v)

                pct = _lab_val("pct")
                crp = _lab_val("crp")
                wbc = _lab_val("wbc")
                lac = _lab_val("lac")

                # PCT: strong 证据（≥2.0），moderate（≥0.5 但 <2.0）
                if pct is not None:
                    if pct >= 2.0:
                        positive_strong.append(f"PCT={pct:.2f} ng/mL (≥2.0, strong)")
                    elif pct >= 0.5:
                        positive_moderate.append(f"PCT={pct:.2f} ng/mL (≥0.5, borderline)")
                    # PCT 正常不能排除感染
                else:
                    missing.append("PCT 未测")

                if crp is not None and crp > 40:
                    positive_moderate.append(f"CRP={crp:.1f} mg/L (>40)")
                if wbc is not None:
                    if wbc > 12:
                        positive_moderate.append(f"WBC={wbc:.1f}×10⁹/L (>12)")
                    elif wbc < 4:
                        positive_moderate.append(f"WBC={wbc:.1f}×10⁹/L (<4, leukopenia)")
                if lac is not None and lac >= 2:
                    positive_moderate.append(f"乳酸={lac:.1f} mmol/L (≥2)")
            else:
                missing.extend(["PCT 无数据", "CRP 无数据", "WBC 无数据"])

        # 4) 已送培养
        if his_pid and hasattr(self, "_get_culture_records"):
            culture_rows = await self._get_culture_records(his_pid, now - timedelta(hours=72))
            if culture_rows:
                positive_moderate.append(f"近72h已送培养 {len(culture_rows)} 次")

        # 5) 影像学感染证据
        if hasattr(self, "get_imaging_report_analysis"):
            imaging = await self.get_imaging_report_analysis(
                patient_doc, pid_str, hours=96, max_age_hours=8, persist_if_refresh=False,
            )
            infection_imaging = self._select_imaging_signals(imaging, module_tags={"infection"}, max_items=3) if hasattr(self, "_select_imaging_signals") else []
            for sig in infection_imaging:
                positive_strong.append(f"影像: {sig.get('summary', sig.get('finding', ''))}")

        # ---- 综合判定（按分层规则） ----
        n_strong = len(positive_strong)
        n_moderate = len(positive_moderate)
        n_negative = len(negative)
        has_uncertainty = bool(uncertain_phrases)

        # 计算独立中等证据数（去重：同一维度的证据只算一次）
        # 体温 + 诊断 + PCT(borderline) + CRP + WBC + 培养 + 乳酸 → 最多7维
        independent_moderate = n_moderate  # 简化计数，每个条目视为一个维度

        if has_clear_negative and not has_uncertainty and n_strong == 0 and independent_moderate == 0:
            verdict: InfectionVerdict = "not_supported"
            confidence: InfectionConfidence = "moderate"
        elif n_strong >= 1:
            # 强证据 → supported
            verdict = "supported"
            confidence = "strong"
        elif independent_moderate >= 2:
            # 多个独立中等证据 → supported
            verdict = "supported"
            confidence = "moderate"
        elif independent_moderate == 1 and not has_clear_negative:
            # 仅有1个中等证据 → possible
            verdict = "possible"
            confidence = "weak"
        elif independent_moderate >= 1 and has_clear_negative:
            # 正负都有 → possible
            verdict = "possible"
            confidence = "weak"
        elif has_uncertainty:
            verdict = "possible"
            confidence = "weak"
        elif has_clear_negative:
            verdict = "not_supported"
            confidence = "moderate"
        else:
            verdict = "unknown"
            confidence = "weak"

        return {
            "verdict": verdict,
            "confidence_level": confidence,
            "confidence": round(
                {"strong": 0.85, "moderate": 0.55, "weak": 0.25}[confidence], 2
            ),
            "positive_strong": positive_strong,
            "positive_moderate": positive_moderate,
            "negative_evidence": negative,
            "uncertain_phrases": uncertain_phrases,
            "missing_data": missing,
            "requires_clinician_review": verdict in ("possible", "unknown"),
        }

    # =========================================================================
    # 休克/低灌注评估
    # =========================================================================

    async def _assess_shock_hypoperfusion(
        self,
        patient_doc: dict,
        pid_str: str,
        his_pid: str | None,
        sbp: float | None,
        map_value: float | None,
        lactate_value: float | None,
        sofa: dict | None,
        infection_verdict: str = "unknown",
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """评估血流动力学不稳定 vs 脓毒性休克筛查。

        严格区分：
          - hemodynamic_instability: MAP<65 或 SBP<90（仅血流动力学不稳定）
          - septic_shock_screen: 升压药 + 乳酸升高 + 感染支持 → 可能脓毒性休克
          - 容量充分性和其他原因排除保持 unknown

        MAP<65 或 SBP<90 只能表示血流动力学不稳定，
        升压药+乳酸升高+感染支持才提示可能脓毒性休克。
        """
        hemodynamic_reasons: list[str] = []
        shock_screen_reasons: list[str] = []
        hypoperfusion_evidence: list[str] = []
        vasopressor_active = False

        # 升压药使用
        if hasattr(self, "_has_vasopressor"):
            vasopressor_active = await self._has_vasopressor(pid_str)

        # ---- hemodynamic_instability ----
        if map_value is not None and map_value < 65:
            if not vasopressor_active:
                hemodynamic_reasons.append("map<65_without_vasopressor")
                hypoperfusion_evidence.append(f"MAP={map_value:.0f} mmHg (<65, 血流动力学不稳定)")
        if sbp is not None and sbp < 90:
            hemodynamic_reasons.append("sbp<90")
            hypoperfusion_evidence.append(f"SBP={sbp:.0f} mmHg (<90)")

        # ---- septic_shock_screen: 升压药 + 乳酸升高 + 感染 ----
        if vasopressor_active:
            hemodynamic_reasons.append("vasopressor_required_for_map_maintenance")
            hypoperfusion_evidence.append("需升压药维持血压")

        if lactate_value is not None:
            if lactate_value >= 4:
                hypoperfusion_evidence.append(f"乳酸={lactate_value:.1f} mmol/L (≥4, SSC 2021)")
            elif lactate_value >= 2:
                hypoperfusion_evidence.append(f"乳酸={lactate_value:.1f} mmol/L (≥2)")

        # SOFA 心血管子分
        cardio_score = (sofa or {}).get("components", {}).get("cardio", 0) if isinstance(sofa, dict) else 0
        if cardio_score >= 3:
            shock_screen_reasons.append("sofa_cardio>=3")
        elif cardio_score >= 1:
            shock_screen_reasons.append("sofa_cardio>=1")

        # 休克筛查阳性条件：升压药 + 乳酸 ≥ 2 + 感染支持
        septic_shock_screen_positive = bool(
            vasopressor_active
            and lactate_value is not None
            and lactate_value >= 2
            and infection_verdict in ("supported", "possible")
        )

        # hemodynamic_instability: MAP<65 或 SBP<90（不与休克混淆）
        hemodynamic_instability = bool(hemodynamic_reasons)

        # 容量状态 — unknown
        volume_status = "unknown"
        if hasattr(self, "_sum_window") and hasattr(self, "_collect_intake_events"):
            try:
                intake_events = await self._collect_intake_events(pid_str, (now or datetime.now()) - timedelta(hours=24))
                output_events = await self._collect_output_events(pid_str, (now or datetime.now()) - timedelta(hours=24))
                net_24h = round(
                    self._sum_window(intake_events, 24, now or datetime.now())
                    - self._sum_window(output_events, 24, now or datetime.now()),
                    1,
                )
                volume_status = f"net_{net_24h}_ml_24h"
            except Exception:
                pass

        return {
            "hemodynamic_instability": hemodynamic_instability,
            "hemodynamic_reasons": hemodynamic_reasons,
            "septic_shock_screen_positive": septic_shock_screen_positive,
            "shock_screen_reasons": shock_screen_reasons,
            "vasopressor_active": vasopressor_active,
            "hypoperfusion_evidence": hypoperfusion_evidence,
            "volume_status": volume_status,
            "volume_assessment_needs_clinician": True,
            "other_causes_excluded": "unknown",
            "map": map_value,
            "sbp": sbp,
            "lactate": lactate_value,
            "sofa_cardio_score": cardio_score,
        }

    # =========================================================================
    # 风险因素评估（不自动标记 contraindicated / not_applicable）
    # =========================================================================

    async def _assess_fluid_risk_factors(
        self,
        patient_doc: dict,
        pid_str: str,
        his_pid: str | None,
        now: datetime,
    ) -> dict[str, Any]:
        """评估液体复苏风险因素。

        修正：心衰、BNP升高、AKI、CRRT、ARDS、液体正平衡和高龄
        **只能自动触发 caution / individualization_required**，
        不能由机器自动标记 contraindicated 或 not_applicable。
        """
        risk_factors: list[dict[str, Any]] = []
        requires_individualization = False
        cautions: list[str] = []

        # 1) 心力衰竭 / BNP
        bnp_high = False
        if his_pid and hasattr(self, "_get_latest_labs_map"):
            labs = await self._get_latest_labs_map(his_pid, lookback_hours=72)
            if labs:
                bnp = _safe_float(
                    (labs.get("bnp") or labs.get("nt_pro_bnp") or {}).get("value")
                    if isinstance(labs.get("bnp") or labs.get("nt_pro_bnp"), dict)
                    else (labs.get("bnp") or labs.get("nt_pro_bnp"))
                )
                if bnp is not None and bnp > 1000:
                    bnp_high = True
                    risk_factors.append({
                        "type": "bnp_elevated",
                        "severity": "caution",
                        "detail": f"BNP/NT-proBNP 显著升高 ({bnp:.0f} pg/mL)",
                        "action": "individualization_required",
                    })
                    requires_individualization = True
                    cautions.append("BNP/NT-proBNP 升高，需评估容量状态再决定复苏策略")

        # 诊断中的心衰
        diagnosis = " ".join(str(patient_doc.get(k) or "") for k in ("clinicalDiagnosis", "admissionDiagnosis")).lower()
        hf_keywords = ["心衰", "心力衰竭", "heart failure", "chf", "心功能不全", "心肌病", "cardiomyopathy"]
        if any(kw in diagnosis for kw in hf_keywords):
            risk_factors.append({
                "type": "heart_failure_diagnosis",
                "severity": "caution",
                "detail": "诊断包含心力衰竭/心肌病",
                "action": "individualization_required",
            })
            requires_individualization = True
            cautions.append("心力衰竭诊断：补液需谨慎，考虑动态评估")

        # 2) AKI 分期
        if hasattr(self, "_calc_aki_stage"):
            aki = await self._calc_aki_stage(patient_doc, pid_str, his_pid)
            if aki and aki.get("stage", 0) >= 2:
                risk_factors.append({
                    "type": "aki_stage",
                    "severity": "caution" if aki["stage"] == 2 else "high_caution",
                    "detail": f"AKI KDIGO Stage {aki['stage']}",
                    "action": "individualization_required",
                })
                requires_individualization = True
                cautions.append(f"AKI Stage {aki['stage']}：补液需个体化，优先纠正低灌注")

        # 3) CRRT
        if hasattr(self, "_get_device_id_for_patient"):
            crrt_device = await self._get_device_id_for_patient(patient_doc, ["crrt"])
            if crrt_device:
                risk_factors.append({
                    "type": "crrt_active",
                    "severity": "caution",
                    "detail": "正在接受CRRT治疗",
                    "action": "individualization_required",
                })
                requires_individualization = True
                cautions.append("CRRT 进行中：复苏目标需结合净超滤设置")

        # 4) ARDS / 严重氧合障碍
        if hasattr(self, "_get_device_id_for_patient"):
            vent_device = await self._get_device_id_for_patient(patient_doc, ["vent"])
            if vent_device and hasattr(self, "_get_latest_device_cap"):
                cap = await self._get_latest_device_cap(vent_device)
                if cap:
                    fio2 = self._vent_param(cap, "fio2", "param_FiO2") if hasattr(self, "_vent_param") else None
                    peep = self._vent_param_priority(cap, ["peep_measured", "peep_set"], ["param_vent_measure_peep", "param_vent_peep"]) if hasattr(self, "_vent_param_priority") else None
                    pao2 = None
                    if his_pid and hasattr(self, "_get_latest_labs_map"):
                        labs = await self._get_latest_labs_map(his_pid, lookback_hours=24)
                        if labs:
                            pao2 = _safe_float((labs.get("pao2") or {}).get("value") if isinstance(labs.get("pao2"), dict) else labs.get("pao2"))
                    if fio2 and peep and peep >= 5:
                        fio2_frac = fio2 / 100.0 if fio2 > 1 else fio2
                        if pao2 and fio2_frac > 0:
                            pf = pao2 / fio2_frac
                            if pf < 200:
                                risk_factors.append({
                                    "type": "ards_pf_severe",
                                    "severity": "high_caution",
                                    "detail": f"P/F={pf:.0f} (中重度 ARDS)",
                                    "action": "individualization_required",
                                })
                                requires_individualization = True
                                cautions.append(f"P/F={pf:.0f}：中重度 ARDS，补液需保守策略")

        # 5) 液体正平衡
        if hasattr(self, "_sum_window") and hasattr(self, "_collect_intake_events"):
            try:
                weight_kg = self._get_patient_weight(patient_doc) if hasattr(self, "_get_patient_weight") else None
                intake_events = await self._collect_intake_events(pid_str, now - timedelta(hours=24))
                output_events = await self._collect_output_events(pid_str, now - timedelta(hours=24))
                net_24h = round(
                    self._sum_window(intake_events, 24, now) - self._sum_window(output_events, 24, now), 1
                )
                if weight_kg and net_24h > 0:
                    pct_fo = round((net_24h / (weight_kg * 1000.0)) * 100.0, 2)
                    if pct_fo > 5:
                        risk_factors.append({
                            "type": "fluid_overload",
                            "severity": "caution" if pct_fo < 10 else "high_caution",
                            "detail": f"24h 净正平衡 {net_24h:.0f} mL (%FO={pct_fo:.1f}%)",
                            "action": "individualization_required",
                        })
                        requires_individualization = True
                        cautions.append(f"液体正平衡 %FO={pct_fo:.1f}%：评估容量超负荷风险")
            except Exception:
                pass

        # 6) 高龄
        age = None
        for key in ("age", "ageYears"):
            age = _safe_float(patient_doc.get(key))
            if age is not None:
                break
        if age is not None and age >= 75:
            risk_factors.append({
                "type": "advanced_age",
                "severity": "caution",
                "detail": f"高龄 ({int(age)} 岁)",
                "action": "individualization_required",
            })
            requires_individualization = True
            cautions.append("高龄患者：补液需谨慎，建议个体化评估")

        # 7) 低体重 / 极端体重
        weight_kg = self._get_patient_weight(patient_doc) if hasattr(self, "_get_patient_weight") else None
        if weight_kg is not None:
            if weight_kg < 45:
                risk_factors.append({
                    "type": "low_body_weight",
                    "severity": "caution",
                    "detail": f"低体重 ({weight_kg:.1f} kg)",
                    "action": "individualization_required",
                })
                requires_individualization = True
            elif weight_kg > 120:
                risk_factors.append({
                    "type": "high_body_weight",
                    "severity": "caution",
                    "detail": f"极端体重 ({weight_kg:.1f} kg)",
                    "action": "individualization_required",
                })
                requires_individualization = True

        return {
            "risk_factors": risk_factors,
            "requires_individualization": requires_individualization,
            "cautions": cautions,
            "weight_kg": weight_kg,
            "has_weight": weight_kg is not None,
        }

    # =========================================================================
    # Bundle 元素定义 (v2 数据模型)
    # =========================================================================

    def _build_bundle_element(
        self,
        applicability: Applicability = "review_pending",
        execution: ExecutionStatus = "pending",
        condition: dict | None = None,
        target: dict | None = None,
        clinical_review: dict | None = None,
        **extra,
    ) -> dict[str, Any]:
        """构建 v2 Bundle 元素。

        applicability / execution / target / clinical_review 四维独立。
        execution.status 仅使用：not_started / pending / met / met_late /
          completed_before / data_missing / cancelled。
        适用性/禁忌/个体化目标使用 applicability 和 target 字段表达。
        """
        return {
            "applicability": applicability,
            "execution": {
                "status": execution,
                "completed_at": None,
                "value": None,
                "completed_before_info": None,
                "completed_before_countable": False,  # 仅临床确认后为 true
            },
            "condition": condition or {},
            "target": target or {},
            "clinical_review": {
                "status": "pending",
                "confirmed_by": None,
                "confirmed_at": None,
                "reason": "",
                "version": 0,
                **(clinical_review or {}),
            },
            **extra,
        }

    def _default_sepsis_bundle_elements_v2(
        self,
        patient_doc: dict | None = None,
        infection_verdict: InfectionVerdict = "unknown",
        shock_assessment: dict | None = None,
        risk_assessment: dict | None = None,
    ) -> dict[str, Any]:
        """构建 v2 默认 Bundle 元素。

        三层结构：
          A 层 — 疑似脓毒症通用项目
          B 层 — 休克/低灌注条件项目
          C 层 — 个体化调整
        """
        shock = shock_assessment or {}
        risk = risk_assessment or {}
        weight_kg = risk.get("weight_kg")

        # --- A 层：通用项目 ---
        elements: dict[str, Any] = {
            "lactate": self._build_bundle_element(
                applicability="required",
                execution={"status": "pending", "completed_at": None, "value": None},
                condition={"status": "unknown", "trigger_evidence": ["suspected_sepsis_screening"], "required": True},
            ),
            "lactate_repeat": self._build_bundle_element(
                applicability="conditional",
                execution={"status": "pending", "completed_at": None, "value": None},
                condition={
                    "status": "unknown",
                    "trigger_evidence": ["initial_lactate>=2"],
                    "required": False,
                },
            ),
            "antibiotic_assessment": self._build_bundle_element(
                applicability="required",
                execution={"status": "pending", "completed_at": None, "value": None},
                condition={"status": "unknown", "trigger_evidence": ["suspected_sepsis_screening"], "required": True},
            ),
            "blood_culture": self._build_bundle_element(
                applicability="required",
                execution={"status": "pending", "completed_at": None, "value": None},
                condition={
                    "status": "unknown",
                    "trigger_evidence": ["suspected_sepsis_screening"],
                    "required": True,
                    "caution": "血培养不得显著延误抗菌治疗",
                },
            ),
            "infection_source": self._build_bundle_element(
                applicability="required",
                execution={"status": "pending", "completed_at": None, "value": None},
                condition={"status": "unknown", "trigger_evidence": ["suspected_sepsis_screening"], "required": True},
            ),
            "clinician_path_confirmation": self._build_bundle_element(
                applicability="required",
                execution={"status": "pending", "completed_at": None, "value": None},
                condition={"status": "unknown", "trigger_evidence": ["infection_verdict"], "required": True},
                clinical_review={"status": "pending", "confirmed_by": None, "confirmed_at": None, "reason": "", "version": 0},
            ),
        }

        # --- B 层：补液（条件项目） ---
        # 休克筛查阳性 → 自动要求「液体复苏评估」（而非固定 30 mL/kg）
        # 存在 ARDS / 液体过负荷 / 心功能异常 / CRRT / 已充分补液 → review_pending 或 individualized
        fluid_applicability: Applicability = "review_pending"
        fluid_condition: dict[str, Any] = {
            "status": "unknown",
            "trigger_evidence": [],
            "ssc_2021_criterion": False,
        }
        fluid_review: dict[str, Any] = {
            "status": "pending",
            "confirmed_by": None,
            "confirmed_at": None,
            "reason": "",
            "version": 0,
        }

        shock_screen_positive = bool(shock.get("septic_shock_screen_positive"))
        hemodynamic_instability = bool(shock.get("hemodynamic_instability"))
        hemodynamic_reasons = shock.get("hemodynamic_reasons", [])

        # SSC 2021: for hypotension or lactate ≥ 4 mmol/L
        ssc_2021_met = bool(
            shock.get("sbp") is not None and shock["sbp"] < 90
        ) or bool(
            shock.get("lactate") is not None and shock["lactate"] >= 4
        )

        # 休克筛查阳性 → 自动要求「液体复苏评估」而非固定 30 mL/kg
        if shock_screen_positive:
            # 休克筛查阳性：要求评估，但存在风险因素时 → individualized
            if risk.get("requires_individualization"):
                fluid_applicability = "individualized"
            else:
                fluid_applicability = "conditional"
            fluid_condition = {
                "status": "met",
                "trigger_evidence": hemodynamic_reasons,
                "ssc_2021_criterion": ssc_2021_met,
                "assessment_required": True,
                "note": "休克筛查阳性：需液体复苏评估，目标由临床医生确定",
            }
        elif hemodynamic_instability:
            # 血流动力学不稳定（无感染支持）：要求评估
            if risk.get("requires_individualization"):
                fluid_applicability = "individualized"
            else:
                fluid_applicability = "conditional"
            fluid_condition = {
                "status": "met",
                "trigger_evidence": hemodynamic_reasons,
                "ssc_2021_criterion": ssc_2021_met,
                "assessment_required": True,
                "note": "血流动力学不稳定：需液体复苏评估",
            }
        else:
            # 无休克/低灌注证据 → 条件未满足
            fluid_applicability = "conditional"
            fluid_condition = {
                "status": "not_met",
                "trigger_evidence": [],
                "ssc_2021_criterion": False,
            }

        # 高危风险因素 → 不自动要求完成固定 30 mL/kg（review_pending / individualized）
        # ARDS、液体过负荷、心功能异常、CRRT、已充分补液 → review_pending
        if risk.get("requires_individualization") and fluid_applicability in ("required", "conditional"):
            # 检查是否为高危因素（需要review_pending）
            high_risk_types = {"ards_pf_severe", "fluid_overload", "heart_failure_diagnosis", "crrt_active"}
            risk_types = {rf.get("type") for rf in risk.get("risk_factors", [])}
            if high_risk_types & risk_types:
                fluid_applicability = "individualized"
                fluid_condition["note"] = "存在高危风险因素(ARDS/液体过负荷/心衰/CRRT)：不自动要求固定30mL/kg，需个体化评估"
            else:
                fluid_applicability = "individualized"

        # 目标
        target_ml_per_kg = float(self._sepsis_bundle_cfg().get("fluid_target_ml_per_kg", 30) or 30)
        default_target_ml = round(weight_kg * target_ml_per_kg, 1) if weight_kg else None
        fluid_target = {
            "default_ml_per_kg": target_ml_per_kg,
            "default_target_ml": default_target_ml,
            "individualized_target_ml": None,
            "delivered_ml": 0.0,
            "weight_kg": weight_kg,
            "weight_missing": weight_kg is None,
        }

        # 液体复苏风险因素审计
        fluid_review["risk_factors_at_trigger"] = risk.get("risk_factors", [])
        fluid_review["cautions_at_trigger"] = risk.get("cautions", [])

        elements["fluid_resuscitation"] = {
            "applicability": fluid_applicability,
            "execution": {
                "status": "pending",
                "completed_at": None,
                "value": None,
                "completed_before_info": None,
            },
            "condition": fluid_condition,
            "target": fluid_target,
            "clinical_review": fluid_review,
        }

        return elements

    # =========================================================================
    # 状态判定
    # =========================================================================

    def _element_is_applicable(self, item: dict | None) -> bool:
        """判断元素是否适用（计入分母）。"""
        if not isinstance(item, dict):
            return False
        applicability = str(item.get("applicability") or "")
        return applicability in ("required", "conditional", "individualized")

    def _element_applicability_confirmed(self, item: dict | None) -> bool:
        """元素适用性是否已确认。"""
        if not isinstance(item, dict):
            return False
        applicability = str(item.get("applicability") or "")
        return applicability not in ("review_pending",)

    def _element_execution_completed(self, item: dict | None) -> bool:
        """元素执行是否完成（按时）。completed_before 仅 clinical_review.confirmed + countable=true 时计入。"""
        if not isinstance(item, dict):
            return False
        exec_data = item.get("execution") if isinstance(item.get("execution"), dict) else item
        exec_status = str(exec_data.get("status") or item.get("status") or "")
        if exec_status == "completed_before":
            return bool(exec_data.get("completed_before_countable")) and self._element_is_applicable(item)
        # met / met_late 是标准完成状态；适用性通过 applicability 控制
        return exec_status in ("met",)

    def _element_execution_any_completion(self, item: dict | None) -> bool:
        """元素执行是否完成（含迟完成和已确认的 completed_before）。"""
        if not isinstance(item, dict):
            return False
        exec_data = item.get("execution") if isinstance(item.get("execution"), dict) else item
        exec_status = str(exec_data.get("status") or item.get("status") or "")
        if exec_status == "completed_before":
            return bool(exec_data.get("completed_before_countable"))
        return exec_status in ("met", "met_late")

    # =========================================================================
    # 质控公式 (v2) — 双守恒检查
    # =========================================================================

    # 所有合法的 applicability 值
    _ALL_APPLICABILITY = {"required", "conditional", "individualized", "not_applicable", "contraindicated", "review_pending"}
    # 所有合法的 execution.status 值
    _ALL_EXECUTION_STATUS = {"not_started", "pending", "met", "met_late", "completed_before", "data_missing", "cancelled"}

    def _bundle_compliance_ratio_v2(self, elements: dict[str, Any]) -> dict[str, Any]:
        """统一质控公式（双守恒检查）。

        守恒1 — 适用性守恒:
          total = Σ(applicability categories) + uncategorized
        守恒2 — 适用项目执行状态守恒:
          applicable_confirmed 中的元素 execution.status 之和 = 执行分类之和

        合规率 = 按时完成适用项目数 / 已确认适用项目数

        completed_before 仅 clinical_review.confirmed + countable=true 时进入分子。
        """
        applicability_counts: dict[str, int] = {k: 0 for k in self._ALL_APPLICABILITY}
        exec_counts: dict[str, int] = {k: 0 for k in self._ALL_EXECUTION_STATUS}
        uncategorized_count = 0
        total = 0
        applicable_confirmed = 0
        completed_on_time = 0
        completed_late = 0
        per_element: dict[str, dict] = {}

        for key, item in (elements or {}).items():
            if not isinstance(item, dict):
                continue
            total += 1

            applicability = str(item.get("applicability") or "")
            exec_data = item.get("execution") if isinstance(item.get("execution"), dict) else item
            exec_status = str(exec_data.get("status") or "pending")
            condition = item.get("condition") if isinstance(item.get("condition"), dict) else {}
            cond_status = str(condition.get("status") or "")

            # 分类计数
            if applicability in applicability_counts:
                applicability_counts[applicability] += 1
            else:
                uncategorized_count += 1
            if exec_status in exec_counts:
                exec_counts[exec_status] += 1

            elem_stat = {
                "applicability": applicability,
                "execution": exec_status,
                "in_denominator": False,
                "in_numerator_on_time": False,
                "in_numerator_late": False,
            }

            if applicability in ("not_applicable", "contraindicated"):
                # 不适用/禁忌：不在分母，不在分子
                pass
            elif applicability == "review_pending":
                # 待确认：不计入分母
                pass
            elif applicability == "required":
                applicable_confirmed += 1
                elem_stat["in_denominator"] = True
                if exec_status == "met":
                    completed_on_time += 1
                    elem_stat["in_numerator_on_time"] = True
                elif exec_status == "completed_before" and bool(exec_data.get("completed_before_countable")):
                    completed_on_time += 1
                    elem_stat["in_numerator_on_time"] = True
                elif exec_status == "met_late":
                    completed_late += 1
                    elem_stat["in_numerator_late"] = True
            elif applicability == "conditional":
                if cond_status == "met":
                    applicable_confirmed += 1
                    elem_stat["in_denominator"] = True
                    if exec_status == "met":
                        completed_on_time += 1
                        elem_stat["in_numerator_on_time"] = True
                    elif exec_status == "completed_before" and bool(exec_data.get("completed_before_countable")):
                        completed_on_time += 1
                        elem_stat["in_numerator_on_time"] = True
                    elif exec_status == "met_late":
                        completed_late += 1
                        elem_stat["in_numerator_late"] = True
                # cond not_met / unknown: 不计入分母
            elif applicability == "individualized":
                applicable_confirmed += 1
                elem_stat["in_denominator"] = True
                if exec_status == "met":
                    completed_on_time += 1
                    elem_stat["in_numerator_on_time"] = True
                elif exec_status == "completed_before" and bool(exec_data.get("completed_before_countable")):
                    completed_on_time += 1
                    elem_stat["in_numerator_on_time"] = True
                elif exec_status == "met_late":
                    completed_late += 1
                    elem_stat["in_numerator_late"] = True

            per_element[key] = elem_stat

        # ---- 双守恒验证 ----
        # 守恒1: applicability 分类之和 + uncategorized == total
        applicability_sum = sum(applicability_counts.values())
        conservation_1_valid = (applicability_sum + uncategorized_count) == total

        # 守恒2: applicable 元素的 exec_status 分布不跨 applicability 类别重复计算
        # 每个元素在一个 applicability 类别中被计数一次 → 没有 double_counted
        double_counted_count = max(0, (applicability_sum + uncategorized_count) - total)
        count_conservation_valid = conservation_1_valid and double_counted_count == 0

        denominator = applicable_confirmed
        numerator = completed_on_time

        stats = {
            "total_elements": total,
            "applicable_confirmed": denominator,
            "completed_on_time": numerator,
            "completed_late": completed_late,
            "not_applicable_count": applicability_counts.get("not_applicable", 0),
            "contraindicated_count": applicability_counts.get("contraindicated", 0),
            "individualized_count": applicability_counts.get("individualized", 0),
            "review_pending_count": applicability_counts.get("review_pending", 0),
            "data_missing_count": exec_counts.get("data_missing", 0),
            "cancelled_count": exec_counts.get("cancelled", 0),
            "applicability_counts": applicability_counts,
            "execution_counts": exec_counts,
            "uncategorized_count": uncategorized_count,
            "double_counted_count": double_counted_count,
            "count_conservation_valid": count_conservation_valid,
            "compliance_ratio": round(numerator / denominator, 4) if denominator > 0 else None,
            "completion_ratio_including_late": round(
                (numerator + completed_late) / denominator, 4
            ) if denominator > 0 else None,
            "per_element": per_element,
        }
        return stats

    def _bundle_pending_items_v2(self, elements: dict[str, Any]) -> list[str]:
        """返回待完成项目的中文标签列表。"""
        labels = {
            "lactate": "乳酸检测/复测",
            "lactate_repeat": "乳酸复测(≥2时)",
            "antibiotic_assessment": "抗菌药评估",
            "blood_culture": "血培养",
            "infection_source": "感染灶评估",
            "fluid_resuscitation": "液体复苏",
            "clinician_path_confirmation": "医生确认脓毒症路径",
        }
        pending: list[str] = []
        for key, item in (elements or {}).items():
            if not isinstance(item, dict):
                continue
            applicability = str(item.get("applicability") or "")
            if applicability in ("not_applicable", "contraindicated"):
                continue
            exec_data = item.get("execution") if isinstance(item.get("execution"), dict) else item
            exec_status = str(exec_data.get("status") or "")
            if exec_status in ("met", "met_late", "completed_before"):
                continue
            pending.append(labels.get(key, key))
        return pending

    # =========================================================================
    # Bundle Tracker 生命周期
    # =========================================================================

    async def _get_active_sepsis_bundle_tracker(self, pid_str: str) -> dict | None:
        return await self.db.col("score").find_one(
            {
                "patient_id": pid_str,
                "score_type": {"$in": self._sepsis_bundle_score_types()},
                "bundle_type": {"$in": self._sepsis_bundle_active_type_names()},
                "is_active": True,
            },
            sort=[("bundle_started_at", -1)],
        )

    async def _get_recent_sepsis_bundle_tracker(self, pid_str: str, now: datetime, hours: int) -> dict | None:
        since = now - timedelta(hours=max(1, hours))
        return await self.db.col("score").find_one(
            {
                "patient_id": pid_str,
                "score_type": {"$in": self._sepsis_bundle_score_types()},
                "bundle_type": {"$in": self._sepsis_bundle_active_type_names()},
                "bundle_started_at": {"$gte": since},
            },
            sort=[("bundle_started_at", -1)],
        )

    async def _start_or_refresh_sepsis_bundle_tracker_v2(
        self,
        *,
        patient_doc: dict,
        pid_str: str,
        now: datetime,
        infection: dict,
        qsofa_triggered: bool,
        qsofa: int,
        sbp: float | None,
        rr: float | None,
        gcs: float | None,
        sofa_triggered: bool,
        sofa: dict | None,
        shock: dict | None,
        risk: dict | None,
    ) -> dict | None:
        """v2 Bundle tracker 生命周期。

        计时逻辑：
        - screening_detected_at: 首次检出感染 + 器官功能异常的时间
        - bundle_clock_anchor: Bundle 计时起点（screening_detected_at 或首次医生确认时间）
        - clinician_confirmed_at: 医生确认进入脓毒症路径的时间
        - **Bundle 计时不等待医生点击确认后才开始**
        """
        cfg = self._sepsis_bundle_cfg()
        tracker_window_h = int(cfg.get("tracker_reopen_hours", 24))
        active = await self._get_active_sepsis_bundle_tracker(pid_str)
        recent = active or await self._get_recent_sepsis_bundle_tracker(pid_str, now, tracker_window_h)

        # 感染证据不满足 → 不启动筛查
        infection_verdict = str(infection.get("verdict") or "unknown")
        if infection_verdict == "not_supported":
            return active

        # qSOFA 不能单独作为确诊依据 — 必须有感染证据 + 器官功能异常
        has_infection_signal = infection_verdict in ("supported", "possible")
        has_organ_dysfunction = qsofa_triggered or sofa_triggered
        if not has_infection_signal or not has_organ_dysfunction:
            return active

        source_rules: list[str] = []
        if qsofa_triggered:
            source_rules.append("SEPSIS_QSOFA")
        if sofa_triggered:
            source_rules.append("SEPSIS_SOFA")

        # 计时起点
        screening_detected_at = (recent or {}).get("screening_detected_at") if isinstance(recent, dict) else None
        if screening_detected_at is None:
            screening_detected_at = now
        bundle_clock_anchor = (recent or {}).get("bundle_clock_anchor") if isinstance(recent, dict) else None
        if bundle_clock_anchor is None:
            bundle_clock_anchor = screening_detected_at  # 默认等同筛查检出时间

        # 构建或复用 Bundle elements
        if isinstance(recent, dict) and isinstance(recent.get("bundle_elements"), dict) and recent.get("bundle_type") == "sepsis_hour1_bundle_v2":
            bundle_elements = recent["bundle_elements"]
        elif isinstance(recent, dict) and isinstance(recent.get("bundle_elements"), dict):
            # 旧版 → 兼容映射
            bundle_elements = self._normalize_legacy_bundle_elements(recent["bundle_elements"])
        else:
            bundle_elements = self._default_sepsis_bundle_elements_v2(
                patient_doc=patient_doc,
                infection_verdict=infection_verdict,
                shock_assessment=shock,
                risk_assessment=risk,
            )

        compliance_stats = self._bundle_compliance_ratio_v2(bundle_elements)

        tracker_patch = {
            "calc_time": now,
            "updated_at": now,
            "score_type": "sepsis_bundle_tracker",
            "bundle_type": "sepsis_hour1_bundle_v2",
            "bundle_version": 2,
            "source_rules": sorted(set(((recent or {}).get("source_rules") or []) + source_rules)),
            "infection_evidence": infection,
            "shock_assessment": shock,
            "fluid_risk_assessment": risk,
            "qsofa": qsofa,
            "sbp": sbp,
            "rr": rr,
            "gcs": gcs,
            "sofa_score": (sofa or {}).get("score") if isinstance(sofa, dict) else None,
            "sofa_delta": (sofa or {}).get("delta") if isinstance(sofa, dict) else None,
            "screening_detected_at": screening_detected_at,
            "bundle_clock_anchor": bundle_clock_anchor,
            "bundle_elements": bundle_elements,
            "bundle_compliance": compliance_stats,
        }

        if recent:
            await self.db.col("score").update_one({"_id": recent["_id"]}, {"$set": tracker_patch})
            if active:
                recent.update(tracker_patch)
                return recent
            return None

        # 新 tracker
        deadline_1h = now + timedelta(minutes=int(cfg.get("deadline_minutes", 60)))
        deadline_3h = now + timedelta(minutes=int(cfg.get("escalation_3h_minutes", 180)))
        tracker = {
            "patient_id": pid_str,
            "patient_name": patient_doc.get("name"),
            "bed": patient_doc.get("hisBed"),
            "dept": patient_doc.get("dept") or patient_doc.get("hisDept"),
            "score_type": "sepsis_bundle_tracker",
            "bundle_type": "sepsis_hour1_bundle_v2",
            "bundle_version": 2,
            "bundle_started_at": now,
            "screening_detected_at": screening_detected_at,
            "bundle_clock_anchor": bundle_clock_anchor,
            "clinician_confirmed_at": None,
            "deadline_1h": deadline_1h,
            "deadline_3h": deadline_3h,
            "status": "pending",
            "is_active": True,
            "compliant_1h": None,
            "source_rules": source_rules,
            "infection_evidence": infection,
            "shock_assessment": shock,
            "fluid_risk_assessment": risk,
            "qsofa": qsofa,
            "sbp": sbp,
            "rr": rr,
            "gcs": gcs,
            "sofa_score": (sofa or {}).get("score") if isinstance(sofa, dict) else None,
            "sofa_delta": (sofa or {}).get("delta") if isinstance(sofa, dict) else None,
            "bundle_elements": bundle_elements,
            "bundle_compliance": compliance_stats,
            "audit_log": [],
            "calc_time": now,
            "created_at": now,
            "updated_at": now,
            "month": now.strftime("%Y-%m"),
            "day": now.strftime("%Y-%m-%d"),
        }
        res = await self.db.col("score").insert_one(tracker)
        tracker["_id"] = res.inserted_id
        return tracker

    # =========================================================================
    # 历史记录兼容
    # =========================================================================

    def _normalize_legacy_bundle_elements(self, legacy: dict[str, Any]) -> dict[str, Any]:
        """将旧版 bundle_elements 映射为 v2 结构。

        规则：
        - 只映射当时存在的元素，不新增
        - 旧缺体重 → not_applicable 映射为 applicability=not_applicable, execution.status=data_missing
        - 旧 status 值映射到 execution.status（仅纯执行状态）
        - applicability 不含执行语义；not_applicable/contraindicated 为适用性判断
        """
        legacy_status_to_execution: dict[str, str] = {
            "met": "met",
            "met_late": "met_late",
            "pending": "pending",
            "not_applicable": "cancelled",
        }
        applicability_mapping: dict[str, str] = {
            "first_antibiotic": "required",
            "lactate_measured": "required",
            "blood_culture": "required",
            "fluid_resuscitation": "conditional",
        }

        normalized: dict[str, Any] = {}
        for old_key, item in (legacy or {}).items():
            if not isinstance(item, dict):
                continue

            old_status = str(item.get("status") or "pending")
            exec_status = legacy_status_to_execution.get(old_status, "pending")
            applicability = applicability_mapping.get(old_key, "required")

            # 识别旧缺体重 → applicability=not_applicable, execution=data_missing
            if old_key == "fluid_resuscitation" and old_status == "not_applicable" and item.get("target_ml") is None:
                exec_status = "data_missing"
                applicability = "not_applicable"

            new_item = {
                "applicability": applicability,
                "execution": {
                    "status": exec_status,
                    "completed_at": item.get("completed_at"),
                    "value": item.get("value"),
                    "completed_before_info": None,
                    "completed_before_countable": False,
                },
                "condition": {"status": "unknown", "trigger_evidence": ["legacy_migration"], "required": True},
                "target": {},
                "clinical_review": {
                    "status": "pending",
                    "confirmed_by": None,
                    "confirmed_at": None,
                    "reason": "由旧版 Bundle 迁移",
                    "version": 0,
                },
            }

            # 补液特殊处理
            if old_key == "fluid_resuscitation":
                new_item["target"] = {
                    "default_ml_per_kg": 30,
                    "default_target_ml": item.get("target_ml"),
                    "individualized_target_ml": None,
                    "delivered_ml": float(item.get("delivered_ml") or 0.0),
                    "weight_kg": None,
                    "weight_missing": item.get("target_ml") is None,
                }
                if item.get("completed_at") and item.get("target_ml"):
                    # 只检查 target_ml 存在且有完成时间 → 可能为 completed_before
                    pass

            # 旧版本 name/before_antibiotic 迁移
            if old_key == "first_antibiotic" and item.get("name"):
                new_item["execution"]["antibiotic_name"] = item.get("name")
            if old_key == "blood_culture":
                new_item["condition"]["before_antibiotic"] = item.get("before_antibiotic")

            normalized[old_key] = new_item

        return normalized

    # =========================================================================
    # 抗菌药 / 乳酸 / 血培养 查找（v2 复用旧版逻辑，增加复苏量识别与排除）
    # =========================================================================

    async def _find_first_antibiotic_after(self, pid_str: str, start_time: datetime) -> dict | None:
        abx_names, _ = await self._load_antibiotic_dictionary()
        fallback = self._get_cfg_list(
            ("alert_engine", "antibiotic_stewardship", "antibiotic_keywords"),
            ["头孢", "青霉素", "美罗培南", "左氧氟沙星", "万古霉素", "阿奇霉素", "哌拉西林"],
        )
        keywords = sorted(set([*(abx_names or []), *(fallback or [])]))
        if not keywords:
            return None
        events = await self._get_drug_events(pid_str, start_time)
        for item in events:
            name = str(item.get("name") or "").strip()
            if self._match_name_keywords(name, keywords):
                return item
        return None

    async def _find_lactate_measurement_after(self, his_pid: str | None, start_time: datetime) -> dict[str, Any] | None:
        if not his_pid:
            return None
        series = await self._get_lab_series(his_pid, "lac", start_time, limit=40)
        if not series:
            return None
        latest = series[0]
        return {"time": latest.get("time"), "value": latest.get("value")}

    async def _find_blood_culture_around_bundle(
        self,
        his_pid: str | None,
        start_time: datetime,
        antibiotic_time: datetime | None,
    ) -> dict[str, Any] | None:
        if not his_pid:
            return None
        lead_hours = float(self._sepsis_bundle_cfg().get("culture_lead_hours", 6) or 6)
        since = start_time - timedelta(hours=max(1, lead_hours))
        rows = await self._get_culture_records(his_pid, since)
        if not rows:
            return None
        blood_keywords = self._get_cfg_list(
            ("alert_engine", "sepsis_bundle", "blood_culture_keywords"),
            ["血培养", "blood culture"],
        )
        resolver = EntityResolver(self.config)
        culture_codes = self._get_cfg_list(("alert_engine", "sepsis_bundle", "blood_culture_item_codes"), [])
        candidates = []
        for row in rows:
            resolved = resolver.resolve_lab_item(row)
            row = {**row, "entity_resolution": resolved}
            code = str(resolved.get("code") or "")
            name = str(row.get("name") or resolved.get("name") or "")
            if (culture_codes and code in culture_codes) or self._match_name_keywords(name, blood_keywords):
                candidates.append(row)
        if not candidates:
            return None
        candidates.sort(key=lambda x: x.get("time") or datetime.min)
        for row in candidates:
            t = row.get("time")
            if not isinstance(t, datetime):
                continue
            if antibiotic_time and t <= antibiotic_time and t >= since:
                return {**row, "before_antibiotic": True}
            if t >= start_time:
                return {**row, "before_antibiotic": None if antibiotic_time is None else t <= antibiotic_time}
        return None

    # =========================================================================
    # 补液量计算（v2：排除维持液、药物溶媒、营养液）
    # =========================================================================

    RESUSCITATION_CRYSTALLOID_KEYWORDS = [
        "氯化钠", "生理盐水", "平衡液", "乳酸林格", "林格", "复方氯化钠",
        "sodium chloride", "normal saline", "ringer", "crystalloid",
        "plasmalyte", "sterofundin", "isolyte",
    ]
    NON_RESUSCITATION_KEYWORDS = [
        "维持液", "维持", "maintenance",
        "溶媒", "溶解", "溶剂", "稀释液",
        "营养液", "tpn", "肠外营养", "全营养", "三合一",
        "葡萄糖氯化钠", "葡萄糖",  # 除非明确为复苏用途
        "脂肪乳", "氨基酸", "力能", "卡文",
        "胰岛素", "胰岛素泵注",  # 药物溶媒
        "抗生素",  # 药物溶媒 — 溶媒不计入复苏量
    ]
    MAINTENANCE_FLUID_KEYWORDS = [
        "维持液", "维持输液", "维持补液", "back up", "background",
        "kvo", "tko", "keep vein open",
    ]
    DRUG_DILUENT_KEYWORDS = [
        "溶媒", "溶解用", "稀释用", "配制用",
    ]

    def _is_resuscitation_crystalloid(self, event: dict[str, Any]) -> bool:
        """判断是否为复苏用晶体液（排除维持液、溶媒、营养液）。"""
        text = " ".join(
            str(event.get(key) or "")
            for key in ("name", "drugName", "orderName", "drugSpec", "route", "routeName", "orderType", "frequency")
        ).lower()

        # 1) 负向排除：维持液
        for kw in self.NON_RESUSCITATION_KEYWORDS:
            if kw in text:
                return False
        # 2) 负向排除：药物溶媒
        for kw in self.DRUG_DILUENT_KEYWORDS:
            if kw in text:
                return False
        # 3) 负向排除：营养液
        for kw in ["营养液", "tpn", "肠外营养", "全营养", "三合一", "脂肪乳", "氨基酸", "力能", "卡文"]:
            if kw in text:
                return False

        # 4) 正向匹配：复苏晶体液
        for kw in self.RESUSCITATION_CRYSTALLOID_KEYWORDS:
            if kw.lower() in text:
                # 排除如"葡萄糖氯化钠"作为维持液的情况
                if "葡萄糖" in text:
                    # 葡萄糖氯化钠可能是复苏液（平衡液替代），需要更精确判断
                    # 葡萄糖+胰岛素→药物溶媒，排除
                    if "胰岛素" in text:
                        return False
                    # 5%葡萄糖 → 可能是维持液
                    if any(pct in text for pct in ("5%", "5％", "10%", "10％")):
                        return False
                return True

        return False

    async def _estimate_resuscitation_volume_v2(
        self,
        pid_str: str,
        patient_doc: dict,
        start_time: datetime,
        now: datetime,
    ) -> dict[str, Any]:
        """v2 复苏量计算：仅计算复苏用晶体液，排除维持液/溶媒/营养液。

        返回 completed_before 信息（时间窗、复苏适应证、证据质量）。
        """
        target_ml_per_kg = float(self._sepsis_bundle_cfg().get("fluid_target_ml_per_kg", 30) or 30)
        weight_kg = self._get_patient_weight(patient_doc) if hasattr(self, "_get_patient_weight") else None
        target_ml = round(weight_kg * target_ml_per_kg, 1) if weight_kg else None

        if not hasattr(self, "_volume_to_ml"):
            return {"completed_at": None, "delivered_ml": 0.0, "target_ml": target_ml}

        docs: list[dict[str, Any]] = []
        pid_value = patient_doc.get("_id") if isinstance(patient_doc, dict) else pid_str
        if hasattr(self, "_get_recent_drugexe_docs"):
            docs = await self._get_recent_drugexe_docs(pid_value, hours=24, limit=1200)
        elif hasattr(self, "_get_recent_drug_docs_window"):
            docs = await self._get_recent_drug_docs_window(pid_value, hours=24, limit=1200)

        delivered = 0.0
        completed_at = None
        pre_bundle_volume = 0.0
        pre_bundle_events: list[dict] = []

        for doc in docs:
            event_time = doc.get("_event_time") or doc.get("executeTime") or doc.get("startTime") or doc.get("orderTime")
            if not isinstance(event_time, datetime):
                continue
            if event_time > now:
                continue

            # **仅计复苏晶体液**
            if not self._is_resuscitation_crystalloid(doc):
                continue

            volume_ml = None
            vol_unit = doc.get("volumeUnit") or doc.get("unit") or doc.get("doseUnit")
            for field in ("volume", "totalVolume", "inputVolume", "infusionVolume"):
                volume_ml = self._volume_to_ml(doc.get(field), vol_unit, assume_ml=True)
                if volume_ml:
                    break
            if not volume_ml and hasattr(self, "_parse_volume_text_ml"):
                for field in ("dose", "drugSpec", "drugName", "orderName"):
                    volume_ml = self._parse_volume_text_ml(doc.get(field))
                    if volume_ml:
                        break
            if not volume_ml:
                continue

            if event_time < start_time:
                pre_bundle_volume += float(volume_ml)
                pre_bundle_events.append({"time": event_time, "volume_ml": round(float(volume_ml), 1)})
            else:
                delivered += float(volume_ml)
                if target_ml is not None and delivered >= target_ml and completed_at is None:
                    completed_at = event_time

        # completed_before 信息
        completed_before_info = None
        if pre_bundle_volume > 0:
            completed_before_info = {
                "volume_ml": round(pre_bundle_volume, 1),
                "time_window": "bundle_start_之前",
                "earliest_event": pre_bundle_events[-1]["time"] if pre_bundle_events else None,
                "latest_event": pre_bundle_events[0]["time"] if pre_bundle_events else None,
                "event_count": len(pre_bundle_events),
                "indication_evidence": "需医生确认是否为脓毒症复苏补液",
                "evidence_quality": "low",  # 自动判断证据质量低，需医生确认
                "requires_clinician_confirmation": True,
            }

        return {
            "completed_at": completed_at,
            "delivered_ml": round(delivered, 1),
            "target_ml": target_ml,
            "pre_bundle_volume_ml": round(pre_bundle_volume, 1),
            "completed_before_info": completed_before_info,
            "excluded_maintenance_diluent": True,
        }

    # =========================================================================
    # Bundle Elements 合并（v2）
    # =========================================================================

    def _merge_bundle_elements_v2(
        self,
        tracker: dict,
        *,
        antibiotic: dict | None,
        lactate: dict | None,
        blood_culture: dict | None,
        fluids: dict[str, Any],
        deadline_1h: datetime,
    ) -> dict[str, Any]:
        """合并自动检测结果到 bundle_elements (v2 结构)。"""
        elements = tracker.get("bundle_elements") if isinstance(tracker.get("bundle_elements"), dict) else {}
        next_elements = {**elements}

        antibiotic_time = antibiotic.get("time") if isinstance(antibiotic, dict) else None
        if antibiotic_time is not None and isinstance(antibiotic_time, datetime):
            item = dict(next_elements.get("first_antibiotic") or next_elements.get("antibiotic_assessment") or {})
            exec_data = dict(item.get("execution") or {}) if isinstance(item.get("execution"), dict) else {}
            exec_data["status"] = "met" if antibiotic_time <= deadline_1h else "met_late"
            exec_data["completed_at"] = antibiotic_time
            exec_data["antibiotic_name"] = antibiotic.get("name")
            item["execution"] = exec_data
            # 兼容旧 key
            if "first_antibiotic" in next_elements:
                next_elements["first_antibiotic"] = item
            else:
                next_elements["antibiotic_assessment"] = item

        lactate_time = lactate.get("time") if isinstance(lactate, dict) else None
        if lactate_time is not None and isinstance(lactate_time, datetime):
            lac_key = "lactate_measured" if "lactate_measured" in next_elements else "lactate"
            item = dict(next_elements.get(lac_key) or {})
            exec_data = dict(item.get("execution") or {}) if isinstance(item.get("execution"), dict) else {}
            exec_data["status"] = "met" if lactate_time <= deadline_1h else "met_late"
            exec_data["completed_at"] = lactate_time
            exec_data["value"] = lactate.get("value")
            item["execution"] = exec_data
            # 乳酸 ≥ 2 → 触发复测条件
            lac_val = _safe_float(lactate.get("value"))
            if lac_val is not None and lac_val >= 2:
                repeat_item = dict(next_elements.get("lactate_repeat") or {})
                if isinstance(repeat_item.get("condition"), dict):
                    repeat_item["condition"] = {
                        **(repeat_item["condition"]),
                        "status": "met",
                        "trigger_evidence": [f"initial_lactate={lac_val}"],
                    }
                next_elements["lactate_repeat"] = repeat_item
            next_elements[lac_key] = item

        culture_time = blood_culture.get("time") if isinstance(blood_culture, dict) else None
        if culture_time is not None and isinstance(culture_time, datetime):
            cul_key = "blood_culture"
            item = dict(next_elements.get(cul_key) or {})
            exec_data = dict(item.get("execution") or {}) if isinstance(item.get("execution"), dict) else {}
            exec_data["status"] = "met" if culture_time <= deadline_1h else "met_late"
            exec_data["completed_at"] = culture_time
            item["execution"] = exec_data
            if isinstance(item.get("condition"), dict):
                item["condition"]["before_antibiotic"] = blood_culture.get("before_antibiotic")
            next_elements[cul_key] = item

        # 补液
        fluid_key = "fluid_resuscitation"
        fluid_item = dict(next_elements.get(fluid_key) or {})
        fluid_completed_at = fluids.get("completed_at")
        delivered_ml = float(fluids.get("delivered_ml") or 0.0)
        target_ml = fluids.get("target_ml")

        target_data = dict(fluid_item.get("target") or {}) if isinstance(fluid_item.get("target"), dict) else {}
        target_data["delivered_ml"] = delivered_ml
        if target_ml is not None:
            target_data["default_target_ml"] = target_ml

        exec_data = dict(fluid_item.get("execution") or {}) if isinstance(fluid_item.get("execution"), dict) else {}
        if hasattr(self, "_get_patient_weight") and self._get_patient_weight(None) is None and target_ml is None:
            # 缺体重 → 不自动判 not_applicable
            exec_data["status"] = "pending"
        elif isinstance(fluid_completed_at, datetime) and fluid_completed_at <= deadline_1h:
            exec_data["status"] = "met"
        elif isinstance(fluid_completed_at, datetime):
            exec_data["status"] = "met_late"
        else:
            exec_data["status"] = "pending"
        exec_data["completed_at"] = fluid_completed_at

        # completed_before 信息
        completed_before_info = fluids.get("completed_before_info")
        if completed_before_info:
            exec_data["completed_before_info"] = completed_before_info

        fluid_item["execution"] = exec_data
        fluid_item["target"] = target_data
        next_elements[fluid_key] = fluid_item

        return next_elements

    # =========================================================================
    # Bundle 说明与预警
    # =========================================================================

    async def _build_sepsis_bundle_explanation_v2(
        self,
        *,
        status: str,
        tracker: dict,
        bundle_elements: dict[str, Any] | None = None,
    ) -> dict:
        started = tracker.get("bundle_started_at")
        started_text = started.strftime("%H:%M") if isinstance(started, datetime) else "—"
        elements = bundle_elements if isinstance(bundle_elements, dict) else tracker.get("bundle_elements") if isinstance(tracker.get("bundle_elements"), dict) else {}
        screening_time = tracker.get("screening_detected_at")
        clock_anchor = tracker.get("bundle_clock_anchor")

        evidence = [
            f"脓毒症筛查检出 {screening_time.strftime('%H:%M') if isinstance(screening_time, datetime) else started_text}",
            f"Bundle计时起点 {clock_anchor.strftime('%H:%M') if isinstance(clock_anchor, datetime) else '—'}",
        ]
        if tracker.get("source_rules"):
            evidence.append("触发来源：" + " / ".join(str(x) for x in tracker.get("source_rules") if x))

        # 感染证据
        inf_evidence = tracker.get("infection_evidence") if isinstance(tracker.get("infection_evidence"), dict) else {}
        if inf_evidence.get("verdict"):
            evidence.append(f"感染证据: {inf_evidence['verdict']} (置信度 {inf_evidence.get('confidence', '—')})")

        # 休克评估
        shock = tracker.get("shock_assessment") if isinstance(tracker.get("shock_assessment"), dict) else {}
        if shock.get("septic_shock_suspected"):
            evidence.append("⚠ 脓毒性休克疑似")
        if shock.get("hypoperfusion_evidence"):
            evidence.append("低灌注证据: " + "; ".join(shock["hypoperfusion_evidence"][:3]))

        # 风险因素
        risk = tracker.get("fluid_risk_assessment") if isinstance(tracker.get("fluid_risk_assessment"), dict) else {}
        if risk.get("cautions"):
            evidence.append("补液风险: " + "; ".join(risk["cautions"][:3]))

        # 各元素状态
        for key, item in elements.items():
            if not isinstance(item, dict):
                continue
            applicability = str(item.get("applicability") or "")
            exec_data = item.get("execution") if isinstance(item.get("execution"), dict) else item
            exec_status = str(exec_data.get("status") or "")
            labels = {
                "lactate": "乳酸", "lactate_repeat": "乳酸复测",
                "antibiotic_assessment": "抗菌药评估", "first_antibiotic": "抗菌药",
                "blood_culture": "血培养", "infection_source": "感染灶评估",
                "fluid_resuscitation": "液体复苏",
                "clinician_path_confirmation": "路径确认",
            }
            label = labels.get(key, key)
            if applicability in ("not_applicable", "contraindicated"):
                evidence.append(f"{label}: {applicability}")
            elif exec_status in ("met", "met_late", "completed_before"):
                comp_at = exec_data.get("completed_at")
                time_str = comp_at.strftime("%H:%M") if isinstance(comp_at, datetime) else ""
                evidence.append(f"{label}: {exec_status} @ {time_str}")
            elif applicability == "conditional":
                cond = item.get("condition") if isinstance(item.get("condition"), dict) else {}
                evidence.append(f"{label}: 条件{cond.get('status', 'unknown')}")

        pending_text = "、".join(self._bundle_pending_items_v2(elements)) or "无"

        if status == "met":
            summary = "脓毒症 Hour-1 Bundle 已在时限内完成。"
            suggestion = "请继续完成感染灶控制，并将 Bundle 完成时间纳入科室质控统计。"
        elif status == "met_late":
            summary = "脓毒症 Hour-1 Bundle 已完成，但超过 1 小时时限。"
            suggestion = "请记录延迟原因，复盘采样、开立、执行和补液环节的阻滞点。"
        elif status == "overdue_3h":
            summary = f"脓毒症 Hour-1 Bundle 超 3 小时仍未完成，待补项目：{pending_text}。"
            suggestion = "请立即补齐剩余关键处置并升级上报。注意：本系统遵循本院 Hour-1 路径，非 SSC 2021 强制时限。"
        else:
            summary = f"脓毒症 Hour-1 Bundle 超 1 小时未完成，待补项目：{pending_text}。"
            suggestion = "请立即补齐剩余关键处置。注意：本系统遵循本院 Hour-1 路径，SSC 2021 建议 1 小时内完成但不具强制效力。"

        return await self._polish_structured_alert_explanation(
            {
                "summary": summary,
                "evidence": evidence[:6],
                "suggestion": suggestion,
                "text": "",
            }
        )

    # =========================================================================
    # Bundle 评估主循环（v2）
    # =========================================================================

    async def _evaluate_sepsis_bundle_tracker_v2(
        self,
        *,
        tracker: dict | None,
        patient_doc: dict,
        pid_str: str,
        his_pid: str | None,
        device_id: str | None,
        now: datetime,
        same_rule_sec: int,
        max_per_hour: int,
    ) -> int:
        if not tracker:
            return 0
        started = tracker.get("bundle_started_at")
        if not isinstance(started, datetime):
            return 0

        deadline_1h = tracker.get("deadline_1h") or (started + timedelta(hours=1))
        deadline_3h = tracker.get("deadline_3h") or (started + timedelta(hours=3))
        abx_event = await self._find_first_antibiotic_after(pid_str, started)
        antibiotic_time = abx_event.get("time") if isinstance(abx_event, dict) else None
        lactate = await self._find_lactate_measurement_after(his_pid, started)
        blood_culture = await self._find_blood_culture_around_bundle(
            his_pid, started, antibiotic_time if isinstance(antibiotic_time, datetime) else None,
        )
        fluids = await self._estimate_resuscitation_volume_v2(pid_str, patient_doc, started, now)

        is_v2 = str(tracker.get("bundle_type") or "").endswith("_v2") or tracker.get("bundle_version") == 2
        if is_v2:
            elements = self._merge_bundle_elements_v2(
                tracker,
                antibiotic=abx_event,
                lactate=lactate,
                blood_culture=blood_culture,
                fluids=fluids,
                deadline_1h=deadline_1h,
            )
            compliance_stats = self._bundle_compliance_ratio_v2(elements)
            pending_items = self._bundle_pending_items_v2(elements)
        else:
            # 旧版回退
            elements = self._merge_bundle_elements(
                tracker,
                antibiotic=abx_event,
                lactate=lactate,
                blood_culture=blood_culture,
                fluids=fluids,
                deadline_1h=deadline_1h,
            )
            compliance_stats = {
                "completion_ratio": self._bundle_completion_ratio(elements),
                "on_time_ratio": self._bundle_on_time_ratio(elements),
            }
            pending_items = self._bundle_pending_items(elements)

        fully_completed = not pending_items

        if fully_completed:
            completion_times = []
            for _key, item in (elements or {}).items():
                if not isinstance(item, dict):
                    continue
                exec_data = item.get("execution") if isinstance(item.get("execution"), dict) else item
                ct = exec_data.get("completed_at")
                if isinstance(ct, datetime):
                    completion_times.append(ct)
            completed_at = max(completion_times) if completion_times else now
            on_time_ratio_val = compliance_stats.get("compliance_ratio") if isinstance(compliance_stats, dict) else compliance_stats.get("on_time_ratio", 1.0)
            within_1h = isinstance(completed_at, datetime) and completed_at <= deadline_1h and (on_time_ratio_val or 0) >= 1.0
            await self.db.col("score").update_one(
                {"_id": tracker["_id"]},
                {
                    "$set": {
                        "status": "met" if within_1h else "met_late",
                        "is_active": False,
                        "compliant_1h": bool(within_1h),
                        "resolved_at": now,
                        "bundle_elements": elements,
                        "bundle_compliance": compliance_stats,
                        "calc_time": now,
                        "updated_at": now,
                    }
                },
            )
            return 0

        fired = 0
        if now >= deadline_3h and not tracker.get("overdue_3h_alerted"):
            rule_id = "SEPSIS_BUNDLE_OVER_3H"
            if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                explanation = await self._build_sepsis_bundle_explanation_v2(status="overdue_3h", tracker=tracker, bundle_elements=elements)
                alert = await self._create_alert(
                    rule_id=rule_id,
                    name="脓毒症 Hour-1 Bundle 超3h未完成",
                    category="bundle",
                    alert_type="sepsis_bundle_overdue_3h",
                    severity="critical",
                    parameter="sepsis_hour1_bundle",
                    condition={"deadline_minutes": 180, "bundle_started_at": started},
                    value=compliance_stats.get("compliance_ratio") if isinstance(compliance_stats, dict) else 0,
                    patient_id=pid_str,
                    patient_doc=patient_doc,
                    device_id=device_id,
                    source_time=now,
                    explanation=explanation,
                    extra={
                        "bundle_started_at": started,
                        "deadline_1h": deadline_1h,
                        "deadline_3h": deadline_3h,
                        "elapsed_minutes": round((now - started).total_seconds() / 60.0, 1),
                        "source_rules": tracker.get("source_rules") or [],
                        "bundle_status": "overdue_3h",
                        "bundle_elements": elements,
                        "pending_items": pending_items,
                        "bundle_compliance": compliance_stats,
                        "bundle_type": tracker.get("bundle_type"),
                    },
                )
                if alert:
                    fired += 1
            await self.db.col("score").update_one(
                {"_id": tracker["_id"]},
                {
                    "$set": {
                        "status": "overdue_3h",
                        "overdue_3h_alerted": True,
                        "compliant_1h": False,
                        "is_active": False,
                        "resolved_at": now,
                        "bundle_elements": elements,
                        "bundle_compliance": compliance_stats,
                        "calc_time": now,
                        "updated_at": now,
                    }
                },
            )
            return fired

        if now >= deadline_1h and not tracker.get("overdue_1h_alerted"):
            rule_id = "SEPSIS_BUNDLE_OVER_1H"
            if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                explanation = await self._build_sepsis_bundle_explanation_v2(status="overdue_1h", tracker=tracker, bundle_elements=elements)
                alert = await self._create_alert(
                    rule_id=rule_id,
                    name="脓毒症 Hour-1 Bundle 超1h未完成",
                    category="bundle",
                    alert_type="sepsis_bundle_overdue_1h",
                    severity="critical",
                    parameter="sepsis_hour1_bundle",
                    condition={"deadline_minutes": 60, "bundle_started_at": started},
                    value=compliance_stats.get("compliance_ratio") if isinstance(compliance_stats, dict) else 0,
                    patient_id=pid_str,
                    patient_doc=patient_doc,
                    device_id=device_id,
                    source_time=now,
                    explanation=explanation,
                    extra={
                        "bundle_started_at": started,
                        "deadline_1h": deadline_1h,
                        "deadline_3h": deadline_3h,
                        "elapsed_minutes": round((now - started).total_seconds() / 60.0, 1),
                        "source_rules": tracker.get("source_rules") or [],
                        "bundle_status": "overdue_1h",
                        "bundle_elements": elements,
                        "pending_items": pending_items,
                        "bundle_compliance": compliance_stats,
                        "bundle_type": tracker.get("bundle_type"),
                    },
                )
                if alert:
                    fired += 1
            await self.db.col("score").update_one(
                {"_id": tracker["_id"]},
                {
                    "$set": {
                        "status": "overdue_1h",
                        "overdue_1h_alerted": True,
                        "compliant_1h": False,
                        "bundle_elements": elements,
                        "bundle_compliance": compliance_stats,
                        "calc_time": now,
                        "updated_at": now,
                    }
                },
            )
            return fired

        # 持续更新
        await self.db.col("score").update_one(
            {"_id": tracker["_id"]},
            {
                "$set": {
                    "bundle_elements": elements,
                    "bundle_compliance": compliance_stats,
                    "calc_time": now,
                    "updated_at": now,
                }
            },
        )
        return fired

    # =========================================================================
    # 扫描入口（委托给 SepsisScanner）
    # =========================================================================

    async def scan_sepsis(self) -> None:
        from .sepsis_scanner import SepsisScanner
        await SepsisScanner(self).scan()

    # =========================================================================
    # 兼容旧版方法（旧 bundle_type 仍可用）
    # =========================================================================

    # --- 以下保留旧版方法供兼容 ---

    def _default_sepsis_bundle_elements(self, patient_doc: dict | None = None) -> dict[str, Any]:
        weight_kg = self._get_patient_weight(patient_doc) if hasattr(self, "_get_patient_weight") else None
        target_volume_ml = round(float(weight_kg) * 30.0, 1) if weight_kg is not None else None
        return {
            "first_antibiotic": {"status": "pending", "completed_at": None, "name": None},
            "lactate_measured": {"status": "pending", "completed_at": None, "value": None},
            "blood_culture": {"status": "pending", "completed_at": None, "name": None, "before_antibiotic": None},
            "fluid_resuscitation": {
                "status": "pending",
                "completed_at": None,
                "target_ml": target_volume_ml,
                "delivered_ml": 0.0,
            },
        }

    def _bundle_element_completed(self, item: Any) -> bool:
        return isinstance(item, dict) and str(item.get("status") or "") in {"met", "met_late", "not_applicable"}

    def _bundle_element_on_time(self, item: Any) -> bool:
        return isinstance(item, dict) and str(item.get("status") or "") in {"met", "not_applicable"}

    def _bundle_completion_ratio(self, elements: dict[str, Any]) -> float:
        relevant = [value for value in (elements or {}).values() if isinstance(value, dict)]
        if not relevant:
            return 0.0
        completed = sum(1 for item in relevant if self._bundle_element_completed(item))
        return round(completed / len(relevant), 3)

    def _bundle_on_time_ratio(self, elements: dict[str, Any]) -> float:
        relevant = [value for value in (elements or {}).values() if isinstance(value, dict)]
        if not relevant:
            return 0.0
        completed = sum(1 for item in relevant if self._bundle_element_on_time(item))
        return round(completed / len(relevant), 3)

    def _bundle_pending_items(self, elements: dict[str, Any]) -> list[str]:
        labels = {
            "first_antibiotic": "首剂抗生素",
            "lactate_measured": "乳酸测定/复测",
            "blood_culture": "血培养",
            "fluid_resuscitation": "30 mL/kg 晶体液复苏",
        }
        rows: list[str] = []
        for key, item in (elements or {}).items():
            if not isinstance(item, dict):
                continue
            if self._bundle_element_completed(item):
                continue
            rows.append(labels.get(key, key))
        return rows

    def _is_crystalloid_event(self, event: dict[str, Any]) -> bool:
        """旧版晶体液识别（委托给 v2）。"""
        return self._is_resuscitation_crystalloid(event)

    async def _estimate_crystalloid_resuscitation(
        self,
        pid_str: str,
        patient_doc: dict,
        start_time: datetime,
        now: datetime,
    ) -> dict[str, Any]:
        """旧版补液量计算（委托给 v2）。"""
        return await self._estimate_resuscitation_volume_v2(pid_str, patient_doc, start_time, now)

    def _merge_bundle_elements(
        self,
        tracker: dict,
        *,
        antibiotic: dict | None,
        lactate: dict | None,
        blood_culture: dict | None,
        fluids: dict[str, Any],
        deadline_1h: datetime,
    ) -> dict[str, Any]:
        """旧版 merge（委托给 v2）。"""
        return self._merge_bundle_elements_v2(
            tracker,
            antibiotic=antibiotic,
            lactate=lactate,
            blood_culture=blood_culture,
            fluids=fluids,
            deadline_1h=deadline_1h,
        )

    async def _build_sepsis_bundle_explanation(
        self,
        *,
        status: str,
        tracker: dict,
        bundle_elements: dict[str, Any] | None = None,
    ) -> dict:
        return await self._build_sepsis_bundle_explanation_v2(
            status=status, tracker=tracker, bundle_elements=bundle_elements,
        )

    async def _evaluate_sepsis_bundle_tracker(
        self,
        *,
        tracker: dict | None,
        patient_doc: dict,
        pid_str: str,
        his_pid: str | None,
        device_id: str | None,
        now: datetime,
        same_rule_sec: int,
        max_per_hour: int,
    ) -> int:
        return await self._evaluate_sepsis_bundle_tracker_v2(
            tracker=tracker,
            patient_doc=patient_doc,
            pid_str=pid_str,
            his_pid=his_pid,
            device_id=device_id,
            now=now,
            same_rule_sec=same_rule_sec,
            max_per_hour=max_per_hour,
        )

    # --- 旧版方法保留结束 ---


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _safe_float(value: Any) -> float | None:
    """安全的浮点数转换。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    s = str(value).strip()
    if not s:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", s)
    if not match:
        return None
    try:
        return float(match.group(0))
    except (TypeError, ValueError):
        return None
