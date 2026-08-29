"""SOFA-2 评分计算器。

Sequential Organ Failure Assessment 2 (SOFA-2)。
基于 2025 年官方 JAMA 主论文 Table 2 及脚注 implementing 6 个器官系统。

从 critical-care-alert-platform 迁移，导入路径已调整。
"""

from __future__ import annotations

from datetime import datetime

from ...enums import ObservationCategory
from ...observation import Observation
from ..missing_policy import MissingDataPolicy, MissingDataPolicyConfig, apply_policy
from ..organ_support import (
    CeilingOfTreatmentContext,
    CirculatorySupportType,
    DeliriumTreatmentAdministration,
    GCSAssessment,
    MechanicalCirculatorySupport,
    MedicationAdministration,
    MotorResponseAssessment,
    MotorResponseCategory,
    NorepinephrineSaltForm,
    RenalReplacementTherapy,
    RespiratorySupport,
    RespiratorySupportType,
    SedationEpisode,
    SupportIndication,
)
from ..rulepacks.loaded_rulepack import LoadedRulepack
from ..score_result import ScoreComponent, ScoreResult
from ..window_spec import ScoreWindowSpec, WindowSpec
from .common import (
    filter_by_code,
    filter_in_window,
    get_worst,
    make_component,
    make_missing_component,
)

VERSION = "sofa-2-2025.1"

ORGAN_NAMES = [
    "brain",
    "respiratory",
    "hemostasis",
    "liver",
    "kidney",
    "cardiovascular",
]

# 盐型转换系数 -> NE Base
_NE_SALT_CONVERSION = {
    NorepinephrineSaltForm.BASE: 1.0,
    NorepinephrineSaltForm.BITARTRATE_MONOHYDRATE: 0.50,
    NorepinephrineSaltForm.ANHYDROUS_BITARTRATE: 1.0 / 1.89,
    NorepinephrineSaltForm.HYDROCHLORIDE: 1.0 / 1.22,
}


class SOFA2Calculator:
    """SOFA-2 评分计算器。官方 Table 2 完整实现。"""

    def __init__(self, rulepack: LoadedRulepack | None = None) -> None:
        self._rulepack = rulepack

    @property
    def score_name(self) -> str:
        return "SOFA"

    @property
    def rulepack_version(self) -> str:
        return VERSION

    def calculate(
        self,
        observations: list[Observation],
        *,
        evaluation_time: datetime,
        window_spec: ScoreWindowSpec,
        respiratory_supports: list[RespiratorySupport] | None = None,
        circulatory_supports: list[MechanicalCirculatorySupport] | None = None,
        rrt_records: list[RenalReplacementTherapy] | None = None,
        medications: list[MedicationAdministration] | None = None,
        ceiling_contexts: list[CeilingOfTreatmentContext] | None = None,
        gcs_assessments: list[GCSAssessment] | None = None,
        motor_assessments: list[MotorResponseAssessment] | None = None,
        sedation_episodes: list[SedationEpisode] | None = None,
        delirium_administrations: list[DeliriumTreatmentAdministration] | None = None,
        patient_weight_kg: float | None = None,
        missing_policy: MissingDataPolicy | str = MissingDataPolicy.STRICT_PARTIAL,
        is_day1: bool = True,
        locf_components: dict[str, ScoreComponent] | None = None,
        locf_source_times: dict[str, datetime] | None = None,
    ) -> ScoreResult:
        if evaluation_time.tzinfo is None:
            raise ValueError("evaluation_time 必须为 timezone-aware")

        policy_enum = MissingDataPolicy(missing_policy)
        policy_config = MissingDataPolicyConfig(policy=policy_enum, day_number=1 if is_day1 else 2)

        valid_obs = [o for o in observations if o.observed_at and o.observed_at <= evaluation_time]
        specs_by_name = {s.component_name: s for s in window_spec.components}

        components: list[ScoreComponent] = []
        missing_items: list[str] = []
        data_quality_issues: list[str] = []

        # 1. Brain
        brain_score, brain_obs, brain_path, brain_imputed = self._calc_brain(
            valid_obs, gcs_assessments, motor_assessments, sedation_episodes, delirium_administrations,
            specs_by_name.get("brain") or specs_by_name.get("central_nervous_system"), evaluation_time,
        )
        if brain_score is not None:
            comp = make_component(
                "brain",
                brain_obs or Observation(
                    category=ObservationCategory.CLINICAL_SCORE, code="GCS",
                    display_name="Brain (GCS)", value_number=15, unit="score", observed_at=evaluation_time,
                ),
                float(brain_score),
            )
            if brain_imputed:
                comp = comp.model_copy(update={"data_quality_flags": [f"imputed_zero:{brain_path}"]})
            components.append(comp)
        else:
            components.append(make_missing_component("brain"))
            missing_items.append("brain")

        # 2. Respiratory
        resp_score, resp_obs, resp_dq = self._calc_respiratory(
            valid_obs, respiratory_supports, ceiling_contexts,
            specs_by_name.get("respiratory"), evaluation_time,
        )
        data_quality_issues.extend(resp_dq)
        if resp_score is not None:
            components.append(make_component(
                "respiratory",
                resp_obs or Observation(
                    category=ObservationCategory.LABORATORY, code="PaO2_FiO2",
                    display_name="PaO2/FiO2", value_number=400, unit="mmHg", observed_at=evaluation_time,
                ),
                float(resp_score),
            ))
        else:
            components.append(make_missing_component("respiratory"))
            missing_items.append("respiratory")

        # 3. Hemostasis
        hemo_score, hemo_obs, hemo_dq = self._calc_hemostasis(
            valid_obs, specs_by_name.get("hemostasis") or specs_by_name.get("coagulation"), evaluation_time
        )
        data_quality_issues.extend(hemo_dq)
        if hemo_score is not None:
            assert hemo_obs is not None
            components.append(make_component("hemostasis", hemo_obs, float(hemo_score)))
        else:
            components.append(make_missing_component("hemostasis"))
            missing_items.append("hemostasis")

        # 4. Liver
        liv_score, liv_obs, liv_dq = self._calc_liver(valid_obs, specs_by_name.get("liver"), evaluation_time)
        data_quality_issues.extend(liv_dq)
        if liv_score is not None:
            assert liv_obs is not None
            components.append(make_component("liver", liv_obs, float(liv_score)))
        else:
            components.append(make_missing_component("liver"))
            missing_items.append("liver")

        # 5. Kidney
        kid_score, kid_obs, kid_dq = self._calc_kidney(
            valid_obs, rrt_records, ceiling_contexts,
            specs_by_name.get("kidney") or specs_by_name.get("renal"), evaluation_time, patient_weight_kg,
        )
        data_quality_issues.extend(kid_dq)
        if kid_score is not None:
            components.append(make_component(
                "kidney",
                kid_obs or Observation(
                    category=ObservationCategory.LABORATORY, code="Creatinine",
                    display_name="Creatinine", value_number=0.9, unit="mg/dL", observed_at=evaluation_time,
                ),
                float(kid_score),
            ))
        else:
            components.append(make_missing_component("kidney"))
            missing_items.append("kidney")

        # 6. Cardiovascular
        cv_score, cv_obs, cv_dq = self._calc_cardiovascular(
            valid_obs, medications, circulatory_supports, ceiling_contexts,
            specs_by_name.get("cardiovascular"), evaluation_time,
        )
        data_quality_issues.extend(cv_dq)
        if cv_score is not None:
            components.append(make_component(
                "cardiovascular",
                cv_obs or Observation(
                    category=ObservationCategory.VITAL_SIGN, code="MAP",
                    display_name="MAP", value_number=80, unit="mmHg", observed_at=evaluation_time,
                ),
                float(cv_score),
            ))
        else:
            components.append(make_missing_component("cardiovascular"))
            missing_items.append("cardiovascular")

        # Missing Data Policy Processing
        final_components, total_score, result_status = apply_policy(
            policy_config.policy, components, missing_items,
            day_number=policy_config.day_number,
            locf_components=locf_components, locf_source_times=locf_source_times,
        )

        present_components = [c for c in final_components if not c.is_missing]
        completeness = len(present_components) / 6.0

        return ScoreResult(
            score_name=self.score_name,
            score_variant="sofa_2_2025",
            rulepack_id=self._rulepack.config.rulepack_id if self._rulepack else "sofa-2-2025",
            rulepack_version=self._rulepack.rulepack_version if self._rulepack else VERSION,
            rulepack_content_hash=self._rulepack.content_hash if self._rulepack else "",
            reference_year=2025,
            clinical_approval_status=self._rulepack.config.clinical_approval_status if self._rulepack else "not_approved",
            lifecycle_status=self._rulepack.config.lifecycle_status if self._rulepack else "experimental",
            window_spec_id=window_spec.spec_id,
            evaluation_time=evaluation_time,
            total_score=total_score,
            result_status=result_status,
            completeness=completeness,
            components=final_components,
            missing_items=missing_items,
            data_quality_issues=data_quality_issues,
            missing_data_policy_id=policy_config.policy_id,
            missing_data_policy_hash=policy_config.policy_hash,
        )

    # ------------------------------------------------------------------
    # 1. Brain
    # ------------------------------------------------------------------
    def _calc_brain(self, observations, gcs_assessments, motor_assessments, sedation_episodes,
                    delirium_administrations, spec, evaluation_time):
        has_delirium_tx = False
        if delirium_administrations:
            for d in delirium_administrations:
                if d.explicit_delirium_indication and not d.is_prescription_only and d.administered_at <= evaluation_time:
                    has_delirium_tx = True
                    break

        active_sedation = None
        if sedation_episodes:
            for s in sedation_episodes:
                if s.start_time <= evaluation_time and (s.end_time is None or s.end_time >= evaluation_time):
                    active_sedation = s
                    break

        if active_sedation:
            if active_sedation.pre_sedation_gcs is not None:
                gcs_val = active_sedation.pre_sedation_gcs
                pts = self._score_gcs(gcs_val)
                if has_delirium_tx:
                    pts = max(pts, 1)
                return pts, None, "gcs_pre_sedation", False
            elif active_sedation.pre_sedation_gcs_unknown:
                return 0, None, "pre_sedation_gcs_unknown_official_zero", True

        if gcs_assessments:
            valid_gcs = [g for g in gcs_assessments if g.assessed_at <= evaluation_time]
            if valid_gcs:
                worst_gcs = min(valid_gcs, key=lambda g: g.gcs_total)
                pts = self._score_gcs(worst_gcs.gcs_total)
                if has_delirium_tx:
                    pts = max(pts, 1)
                obs = Observation(
                    category=ObservationCategory.CLINICAL_SCORE, code="GCS",
                    display_name="GCS Total", value_number=float(worst_gcs.gcs_total),
                    unit="score", observed_at=worst_gcs.assessed_at,
                )
                return pts, obs, "gcs_assessment", False

        if spec:
            gcs_obs = get_worst(
                filter_in_window(filter_by_code(observations, ["param_score_gcs_obs", "gcsScore", "GCS"]), spec, evaluation_time),
                reverse=True,
            )
            if gcs_obs and gcs_obs.value_number is not None:
                pts = self._score_gcs(int(gcs_obs.value_number))
                if has_delirium_tx:
                    pts = max(pts, 1)
                return pts, gcs_obs, "gcs_obs", False

        if motor_assessments:
            valid_m = [m for m in motor_assessments if m.assessed_at <= evaluation_time]
            if valid_m:
                worst_m = max(valid_m, key=lambda m: self._score_motor(m.motor_response))
                pts = self._score_motor(worst_m.motor_response)
                if has_delirium_tx:
                    pts = max(pts, 1)
                obs = Observation(
                    category=ObservationCategory.CLINICAL_SCORE, code="GCS_Motor",
                    display_name="Motor Fallback", value_number=float(pts),
                    unit="score", observed_at=worst_m.assessed_at,
                )
                return pts, obs, "motor_fallback", False

        if has_delirium_tx:
            return 1, None, "delirium_only", False

        return None, None, "missing", False

    @staticmethod
    def _score_gcs(gcs: int) -> int:
        if gcs >= 15: return 0
        elif gcs >= 13: return 1
        elif gcs >= 9: return 2
        elif gcs >= 6: return 3
        else: return 4

    @staticmethod
    def _score_motor(cat: MotorResponseCategory) -> int:
        mapping = {
            MotorResponseCategory.THUMBS_UP_FIST_PEACE: 0,
            MotorResponseCategory.LOCALIZING_PAIN: 1,
            MotorResponseCategory.WITHDRAWAL_PAIN: 2,
            MotorResponseCategory.FLEXION_PAIN: 3,
            MotorResponseCategory.EXTENSION_NO_RESPONSE_MYOCLONUS: 4,
        }
        return mapping.get(cat, 0)

    # ------------------------------------------------------------------
    # 2. Respiratory
    # ------------------------------------------------------------------
    def _calc_respiratory(self, observations, supports, ceilings, spec, evaluation_time):
        dq: list[str] = []
        if not spec:
            return None, None, dq

        has_resp_ecmo = False
        if supports:
            for s in supports:
                if (s.started_at <= evaluation_time and (s.ended_at is None or s.ended_at >= evaluation_time)
                        and s.support_type == RespiratorySupportType.ECMO):
                    has_resp_ecmo = True

        if has_resp_ecmo:
            ecmo_obs = Observation(
                category=ObservationCategory.DEVICE_PARAMETER, code="ECMO_Respiratory",
                display_name="ECMO (Respiratory)", value_number=4.0, unit="score", observed_at=evaluation_time,
            )
            return 4, ecmo_obs, dq

        has_advanced_support = False
        support_precluded = False
        if supports:
            for s in supports:
                if s.started_at <= evaluation_time and (s.ended_at is None or s.ended_at >= evaluation_time):
                    if s.support_type in [
                        RespiratorySupportType.HFNC, RespiratorySupportType.CPAP,
                        RespiratorySupportType.BIPAP, RespiratorySupportType.NIV,
                        RespiratorySupportType.IMV, RespiratorySupportType.HOME_VENT,
                        RespiratorySupportType.ECMO,
                    ]:
                        has_advanced_support = True
                    if s.ceiling_of_treatment or s.unavailable_due_to_resource:
                        support_precluded = True

        if ceilings:
            for c in ceilings:
                if (c.organ_system == "respiratory" and c.effective_time <= evaluation_time
                        and (c.support_precluded or c.support_unavailable)):
                    support_precluded = True

        pao2_obs = get_worst(
            filter_in_window(filter_by_code(observations, ["param_PaO2", "PaO2"]), spec, evaluation_time), reverse=True
        )
        fio2_obs = get_worst(
            filter_in_window(filter_by_code(observations, ["param_FiO2", "FiO2"]), spec, evaluation_time), reverse=False
        )

        if pao2_obs and fio2_obs and pao2_obs.value_number and fio2_obs.value_number:
            fio2_val = fio2_obs.value_number
            if fio2_val > 1.0:
                fio2_val = fio2_val / 100.0
            if 0 < fio2_val <= 1.0:
                pf_ratio = pao2_obs.value_number / fio2_val
                pts = self._score_pf(pf_ratio, has_advanced_support or support_precluded)
                ratio_obs = Observation(
                    category=ObservationCategory.LABORATORY, code="PaO2_FiO2_Ratio",
                    display_name="PaO2/FiO2 Ratio", value_number=pf_ratio,
                    unit="mmHg", observed_at=pao2_obs.observed_at or evaluation_time,
                )
                return pts, ratio_obs, dq

        spo2_obs = get_worst(
            filter_in_window(filter_by_code(observations, ["SpO2", "param_SpO2"]), spec, evaluation_time), reverse=True
        )
        if spo2_obs and fio2_obs and spo2_obs.value_number and fio2_obs.value_number:
            if spo2_obs.value_number < 98.0:
                fio2_val = fio2_obs.value_number
                if fio2_val > 1.0:
                    fio2_val = fio2_val / 100.0
                if 0 < fio2_val <= 1.0:
                    sf_ratio = spo2_obs.value_number / fio2_val
                    pts = self._score_sf(sf_ratio, has_advanced_support or support_precluded)
                    sf_obs = Observation(
                        category=ObservationCategory.VITAL_SIGN, code="SpO2_FiO2_Ratio",
                        display_name="SpO2/FiO2 Ratio", value_number=sf_ratio,
                        unit="%", observed_at=spo2_obs.observed_at or evaluation_time,
                    )
                    return pts, sf_obs, dq
            else:
                dq.append("SpO2 >= 98%, SpO2/FiO2 alternative path disallowed")

        return None, None, dq

    @staticmethod
    def _score_pf(ratio: float, with_support: bool) -> int:
        if ratio > 300: return 0
        elif ratio > 225: return 1
        elif ratio > 150: return 2
        elif ratio > 75: return 3 if with_support else 2
        else: return 4 if with_support else 2

    @staticmethod
    def _score_sf(ratio: float, with_support: bool) -> int:
        if ratio > 300: return 0
        elif ratio > 250: return 1
        elif ratio > 200: return 2
        elif ratio > 120: return 3 if with_support else 2
        else: return 4 if with_support else 2

    # ------------------------------------------------------------------
    # 3. Hemostasis
    # ------------------------------------------------------------------
    def _calc_hemostasis(self, observations, spec, evaluation_time):
        dq: list[str] = []
        if not spec:
            return None, None, dq
        obs = get_worst(
            filter_in_window(filter_by_code(observations, ["PLT", "platelets"]), spec, evaluation_time), reverse=True
        )
        if obs and obs.value_number is not None:
            val = obs.value_number
            if val < 0 or val > 2000:
                dq.append(f"Platelet value out of range: {val}")
                return None, None, dq
            if val > 150: return 0, obs, dq
            elif val > 100: return 1, obs, dq
            elif val > 80: return 2, obs, dq
            elif val > 50: return 3, obs, dq
            else: return 4, obs, dq
        return None, None, dq

    # ------------------------------------------------------------------
    # 4. Liver
    # ------------------------------------------------------------------
    def _calc_liver(self, observations, spec, evaluation_time):
        dq: list[str] = []
        if not spec:
            return None, None, dq
        obs = get_worst(
            filter_in_window(filter_by_code(observations, ["TBIL", "bilirubin"]), spec, evaluation_time), reverse=False
        )
        if obs and obs.value_number is not None:
            val = obs.value_number
            unit = (obs.unit or "mg/dL").lower()
            if "umol" in unit or "μmol" in unit:
                val = val / 17.104
            if val <= 1.20: return 0, obs, dq
            elif val <= 3.0: return 1, obs, dq
            elif val <= 6.0: return 2, obs, dq
            elif val <= 12.0: return 3, obs, dq
            else: return 4, obs, dq
        return None, None, dq

    # ------------------------------------------------------------------
    # 5. Kidney
    # ------------------------------------------------------------------
    def _calc_kidney(self, observations, rrt_records, ceilings, spec, evaluation_time, weight_kg):
        dq: list[str] = []
        if not spec:
            return None, None, dq

        has_rrt_4 = False
        if rrt_records:
            for r in rrt_records:
                if r.started_at <= evaluation_time:
                    if r.indication == SupportIndication.NON_RENAL:
                        continue
                    if r.chronic_use:
                        has_rrt_4 = True
                        break
                    if not r.terminated and (r.ended_at is None or r.ended_at >= evaluation_time or r.intermittent):
                        has_rrt_4 = True
                        break

        if not has_rrt_4:
            cr_obs = get_worst(
                filter_in_window(filter_by_code(observations, ["CREA", "creatinine"]), spec, evaluation_time), reverse=False,
            )
            k_obs = get_worst(
                filter_in_window(filter_by_code(observations, ["K", "potassium"]), spec, evaluation_time), reverse=False
            )
            ph_obs = get_worst(
                filter_in_window(filter_by_code(observations, ["pH", "pH_art"]), spec, evaluation_time), reverse=True
            )
            hco3_obs = get_worst(
                filter_in_window(filter_by_code(observations, ["HCO3", "bicarbonate"]), spec, evaluation_time), reverse=True,
            )

            cr_val_mg_dl = None
            if cr_obs and cr_obs.value_number:
                unit = (cr_obs.unit or "mg/dL").lower()
                cr_val_mg_dl = cr_obs.value_number / 88.4 if ("umol" in unit or "μmol" in unit) else cr_obs.value_number

            cr_or_uo_met = cr_val_mg_dl is not None and cr_val_mg_dl > 1.20
            k_met = k_obs.value_number is not None and k_obs.value_number >= 6.0 if k_obs else False
            acidosis_met = (
                ph_obs.value_number is not None and ph_obs.value_number <= 7.20
                and hco3_obs.value_number is not None and hco3_obs.value_number <= 12.0
                if (ph_obs and hco3_obs) else False
            )

            if cr_or_uo_met and (k_met or acidosis_met):
                has_rrt_4 = True

        if has_rrt_4:
            rrt_obs = Observation(
                category=ObservationCategory.CLINICAL_SCORE, code="RRT",
                display_name="RRT Active / Criteria Met", value_number=4.0,
                unit="score", observed_at=evaluation_time,
            )
            return 4, rrt_obs, dq

        cr_score: int | None = None
        cr_obs = get_worst(
            filter_in_window(filter_by_code(observations, ["CREA", "creatinine"]), spec, evaluation_time), reverse=False
        )
        if cr_obs and cr_obs.value_number is not None:
            val = cr_obs.value_number
            unit = (cr_obs.unit or "mg/dL").lower()
            if "umol" in unit or "μmol" in unit:
                val = val / 88.4
            if val <= 1.20: cr_score = 0
            elif val <= 2.0: cr_score = 1
            elif val <= 3.50: cr_score = 2
            else: cr_score = 3

        uo_score: int | None = None
        if weight_kg is None or weight_kg <= 0:
            dq.append("Patient weight missing; urine output mL/kg/h path skipped")
        else:
            uo_obs = filter_in_window(
                filter_by_code(observations, ["urine_output", "urineVolume"]), spec, evaluation_time
            )
            if uo_obs:
                valid_uo = [o for o in uo_obs if o.value_number is not None]
                if valid_uo:
                    total_ml = sum(o.value_number for o in valid_uo if o.value_number)
                    hours = spec.lookback_window.total_seconds() / 3600.0
                    rate = (total_ml / hours) / weight_kg if hours > 0 else 0.0
                    if total_ml == 0 and hours >= 12: uo_score = 3
                    elif rate < 0.3 and hours >= 24: uo_score = 3
                    elif rate < 0.5 and hours >= 12: uo_score = 2
                    elif rate < 0.5 and hours >= 6: uo_score = 1
                    else: uo_score = 0

        scores = [s for s in [cr_score, uo_score] if s is not None]
        if scores:
            max_s = max(scores)
            selected_obs = cr_obs if cr_score == max_s and cr_obs else None
            return max_s, selected_obs, dq

        return None, None, dq

    # ------------------------------------------------------------------
    # 6. Cardiovascular
    # ------------------------------------------------------------------
    def _calc_cardiovascular(self, observations, medications, supports, ceilings, spec, evaluation_time):
        dq: list[str] = []
        if not spec:
            return None, None, dq

        if supports:
            for s in supports:
                if (s.started_at <= evaluation_time and (s.ended_at is None or s.ended_at >= evaluation_time)
                        and s.support_type in [
                            CirculatorySupportType.VA_ECMO, CirculatorySupportType.IABP,
                            CirculatorySupportType.LVAD, CirculatorySupportType.MICROAXIAL_FLOW_PUMP,
                        ]):
                    mcs_obs = Observation(
                        category=ObservationCategory.DEVICE_PARAMETER, code="Mechanical_Circulatory_Support",
                        display_name="Mechanical Circulatory Support", value_number=4.0,
                        unit="score", observed_at=evaluation_time,
                    )
                    return 4, mcs_obs, dq

        ne_base_dose = 0.0
        epi_base_dose = 0.0
        dopamine_dose = 0.0
        has_other_pressor = False
        has_active_pressor = False

        if medications:
            for m in medications:
                if m.start_time <= evaluation_time and (m.end_time is None or m.end_time >= evaluation_time):
                    if m.infusion_type != "continuous" or m.duration_minutes < 60.0:
                        dq.append(f"Excluded non-continuous or <1h infusion for {m.medication}")
                        continue

                    med_name = m.medication.lower()
                    dose = m.dose

                    if "norepinephrine" in med_name or "noradrenaline" in med_name:
                        multiplier = _NE_SALT_CONVERSION.get(m.salt_form, 1.0)
                        if m.salt_form == NorepinephrineSaltForm.UNKNOWN:
                            dq.append("Norepinephrine salt form unknown; assuming base")
                        ne_base_dose += dose * multiplier
                        has_active_pressor = True
                    elif "epinephrine" in med_name or "adrenaline" in med_name:
                        epi_base_dose += dose
                        has_active_pressor = True
                    elif "dopamine" in med_name:
                        dopamine_dose += dose
                        has_active_pressor = True
                    elif any(k in med_name for k in ["dobutamine", "vasopressin", "phenylephrine", "milrinone", "isoproterenol"]):
                        has_other_pressor = True
                        has_active_pressor = True

        if has_active_pressor:
            ne_epi_sum = ne_base_dose + epi_base_dose

            if dopamine_dose > 0 and ne_epi_sum == 0 and not has_other_pressor:
                if dopamine_dose > 40.0: pts = 4
                elif dopamine_dose > 20.0: pts = 3
                else: pts = 2
                dop_obs = Observation(
                    category=ObservationCategory.CLINICAL_SCORE, code="dopamine_dose",
                    display_name="Dopamine Infusion", value_number=dopamine_dose,
                    unit="μg/kg/min", observed_at=evaluation_time,
                )
                return pts, dop_obs, dq

            if ne_epi_sum > 0.40: pts = 4
            elif ne_epi_sum > 0.20: pts = 4 if has_other_pressor else 3
            elif ne_epi_sum > 0: pts = 3 if has_other_pressor else 2
            elif has_other_pressor: pts = 2
            else: pts = 0

            vp_obs = Observation(
                category=ObservationCategory.CLINICAL_SCORE, code="vasopressor_sum",
                display_name="NE+Epi Base Dose Sum", value_number=ne_epi_sum,
                unit="μg/kg/min", observed_at=evaluation_time,
            )
            return pts, vp_obs, dq

        map_obs = get_worst(
            filter_in_window(filter_by_code(observations, ["MAP", "mean_arterial_pressure"]), spec, evaluation_time),
            reverse=True,
        )
        pressors_precluded = False

        if ceilings:
            for c in ceilings:
                if (c.organ_system == "cardiovascular" and c.effective_time <= evaluation_time
                        and (c.support_precluded or c.support_unavailable)):
                    pressors_precluded = True

        if map_obs and map_obs.value_number is not None:
            m_val = map_obs.value_number
            if pressors_precluded:
                if m_val >= 70: return 0, map_obs, dq
                elif m_val >= 60: return 1, map_obs, dq
                elif m_val >= 50: return 2, map_obs, dq
                elif m_val >= 40: return 3, map_obs, dq
                else: return 4, map_obs, dq
            else:
                if m_val >= 70: return 0, map_obs, dq
                else: return 1, map_obs, dq

        return None, None, dq
