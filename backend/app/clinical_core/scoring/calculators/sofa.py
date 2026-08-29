"""SOFA 评分计算器。

Sequential Organ Failure Assessment。
6 个器官系统: respiratory, coagulation, liver, cardiovascular, central_nervous_system, renal
采用 24 小时窗口内最差值。

来源: Vincent JL, et al. Intensive Care Med. 1996;22:707-710.

从 critical-care-alert-platform 迁移，导入路径已调整。
"""

from __future__ import annotations

from datetime import UTC, datetime

from ...enums import ObservationCategory
from ...observation import Observation
from ..rulepacks.loaded_rulepack import LoadedRulepack
from ..score_result import ScoreComponent, ScoreResult
from ..window_spec import ScoreWindowSpec, WindowSpec
from .common import (
    filter_by_code,
    filter_in_window,
    get_latest,
    get_worst,
    is_stale,
    make_component,
    make_missing_component,
)

VERSION = "sofa-1.0"

# 6 个器官系统名称
ORGAN_NAMES = [
    "respiratory",
    "coagulation",
    "liver",
    "cardiovascular",
    "central_nervous_system",
    "renal",
]

# 最大配对时间间隔（秒）
_MAX_PAIR_SECONDS = 1800  # 30 minutes


def _pao2_fio2_score(pao2: float, fio2: float) -> int:
    ratio = pao2 / fio2 if fio2 > 0 else 0
    if ratio >= 400:
        return 0
    elif ratio >= 300:
        return 1
    elif ratio >= 200:
        return 2
    elif ratio >= 100:
        return 3
    else:
        return 4


def _platelets_score(plat: float) -> int:
    if plat >= 150:
        return 0
    elif plat >= 100:
        return 1
    elif plat >= 50:
        return 2
    elif plat >= 20:
        return 3
    else:
        return 4


def _bilirubin_score(bili: float) -> int:
    if bili < 20:
        return 0
    elif bili < 33:
        return 1
    elif bili < 102:
        return 2
    elif bili < 204:
        return 3
    else:
        return 4


def _vasopressor_score(dose: float) -> int:
    if dose <= 0:
        return 0
    elif dose < 0.1:
        return 1
    elif dose < 0.2:
        return 2
    elif dose < 0.5:
        return 3
    else:
        return 4


def _gcs_score(gcs: float) -> int:
    if gcs >= 15:
        return 0
    elif gcs >= 13:
        return 1
    elif gcs >= 10:
        return 2
    elif gcs >= 6:
        return 3
    else:
        return 4


def _creatinine_score(crea_umol: float) -> int:
    """SOFA 肌酐评分。阈值来自 rulepack，此处保留为兜底默认。"""
    if crea_umol < 110:
        return 0
    elif crea_umol < 170:
        return 1
    elif crea_umol < 300:
        return 2
    elif crea_umol < 440:
        return 3
    else:
        return 4


def _urine_score_daily(ml_per_24h: float) -> int:
    """SOFA 肾脏尿量评分（每日总尿量）。"""
    if ml_per_24h < 200:
        return 4
    elif ml_per_24h < 500:
        return 3
    else:
        return 0


class SOFACalculator:
    """SOFA 评分计算器。6 个器官系统。阈值来自 rulepack。"""

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
        patient_weight_kg: float | None = None,
    ) -> ScoreResult:
        components: list[ScoreComponent] = []
        missing_items: list[str] = []
        data_quality_issues: list[str] = []
        specs_by_name = {s.component_name: s for s in window_spec.components}

        # 1. Respiratory: PaO2/FiO2
        resp_score, _, resp_dq = self._calc_respiratory(observations, specs_by_name.get("respiratory"), evaluation_time)
        if resp_score is not None:
            pao2_obs = self._get_worst(
                observations, ["param_PaO2", "PaO2"], specs_by_name.get("respiratory"), evaluation_time, reverse=True
            )
            components.append(
                make_component(
                    "respiratory",
                    pao2_obs or observations[0]
                    if observations
                    else Observation(
                        category=ObservationCategory.LABORATORY,
                        code="PaO2",
                        display_name="PaO2",
                        value_number=0,
                        unit="mmHg",
                        observed_at=evaluation_time,
                    ),
                    float(resp_score),
                )
            )
        else:
            components.append(make_missing_component("respiratory"))
            missing_items.append("respiratory")
        data_quality_issues.extend(resp_dq)

        # 2. Coagulation: Platelets
        plt_score, _ = self._calc_platelets(observations, specs_by_name.get("coagulation"), evaluation_time)
        if plt_score is not None:
            plt_obs = self._get_worst(
                observations, ["PLT", "platelets"], specs_by_name.get("coagulation"), evaluation_time, reverse=True
            )
            if plt_obs:
                components.append(make_component("coagulation", plt_obs, float(plt_score)))
            else:
                components.append(make_missing_component("coagulation"))
                missing_items.append("coagulation")
        else:
            components.append(make_missing_component("coagulation"))
            missing_items.append("coagulation")

        # 3. Liver: Bilirubin
        liv_score = self._calc_bilirubin(observations, specs_by_name.get("liver"), evaluation_time)
        if liv_score is not None:
            bili_obs = self._get_worst(
                observations, ["TBIL", "bilirubin"], specs_by_name.get("liver"), evaluation_time, reverse=False
            )
            if bili_obs:
                components.append(make_component("liver", bili_obs, float(liv_score)))
            else:
                components.append(make_missing_component("liver"))
                missing_items.append("liver")
        else:
            components.append(make_missing_component("liver"))
            missing_items.append("liver")

        # 4. Cardiovascular: Vasopressors
        cv_score = self._calc_cardiovascular(observations, specs_by_name.get("cardiovascular"), evaluation_time)
        if cv_score is not None:
            vp_obs = self._get_latest(
                observations,
                ["vasopressor_dose", "norepinephrine_dose", "dopamine_dose"],
                specs_by_name.get("cardiovascular"),
                evaluation_time,
            )
            if vp_obs:
                components.append(make_component("cardiovascular", vp_obs, float(cv_score)))
            else:
                default_obs = Observation(
                    category=ObservationCategory.DEVICE_PARAMETER,
                    code="vasopressor_dose",
                    display_name="vasopressor",
                    value_number=0.0,
                    unit="ug/kg/min",
                    observed_at=evaluation_time,
                )
                components.append(make_component("cardiovascular", default_obs, float(cv_score)))
        else:
            components.append(make_missing_component("cardiovascular"))
            missing_items.append("cardiovascular")

        # 5. Central Nervous System: GCS
        cns_score = self._calc_gcs(observations, specs_by_name.get("central_nervous_system"), evaluation_time)
        if cns_score is not None:
            gcs_obs = self._get_worst(
                observations,
                ["param_score_gcs_obs", "gcsScore", "GCS"],
                specs_by_name.get("central_nervous_system"),
                evaluation_time,
                reverse=True,
            )
            if gcs_obs:
                components.append(make_component("central_nervous_system", gcs_obs, float(cns_score)))
            else:
                components.append(make_missing_component("central_nervous_system"))
                missing_items.append("central_nervous_system")
        else:
            components.append(make_missing_component("central_nervous_system"))
            missing_items.append("central_nervous_system")

        # 6. Renal: Creatinine AND Urine Output
        renal_score, _, renal_dq = self._calc_renal(
            observations, specs_by_name.get("renal"), evaluation_time, patient_weight_kg
        )
        if renal_score is not None:
            renal_obs = self._get_worst(
                observations, ["CREA", "creatinine"], specs_by_name.get("renal"), evaluation_time, reverse=False
            )
            if not renal_obs:
                renal_obs = self._get_latest(
                    observations, ["urine_output", "urineVolume"], specs_by_name.get("renal"), evaluation_time
                )
            if renal_obs:
                components.append(make_component("renal", renal_obs, float(renal_score)))
            else:
                components.append(make_missing_component("renal"))
                missing_items.append("renal")
        else:
            components.append(make_missing_component("renal"))
            missing_items.append("renal")
        data_quality_issues.extend(renal_dq)

        # Validate: exactly 6 organs
        assert len(components) == 6, f"SOFA must have exactly 6 organ components, got {len(components)}"
        assert len(set(c.name for c in components)) == 6, "SOFA organ names must be unique"

        total = sum(c.score_points for c in components if not c.is_missing)
        present = [c for c in components if not c.is_missing]
        completeness = len(present) / 6

        if completeness < 0.5:
            result_status = "insufficient"
        elif missing_items:
            result_status = "partial"
        else:
            result_status = "complete"

        return ScoreResult(
            score_name=self.score_name,
            score_variant=self._rulepack.config.score_variant if self._rulepack else "classic_sofa_1996",
            rulepack_id=self._rulepack.config.rulepack_id if self._rulepack else "classic-sofa-1996",
            rulepack_version=self._rulepack.rulepack_version if self._rulepack else VERSION,
            rulepack_content_hash=self._rulepack.content_hash if self._rulepack else "",
            reference_year=self._rulepack.config.reference_year if self._rulepack else 1996,
            clinical_approval_status=self._rulepack.config.clinical_approval_status
            if self._rulepack
            else "not_approved",
            lifecycle_status=self._rulepack.config.lifecycle_status if self._rulepack else "experimental",
            window_spec_id=window_spec.spec_id,
            evaluation_time=evaluation_time,
            total_score=total if completeness >= 0.5 else None,
            result_status=result_status,
            completeness=completeness,
            components=components,
            missing_items=missing_items,
            data_quality_issues=data_quality_issues,
        )

    def _calc_respiratory(
        self,
        observations: list[Observation],
        spec: WindowSpec | None,
        evaluation_time: datetime,
    ) -> tuple[int | None, bool, list[str]]:
        if not spec:
            return None, True, []
        pao2 = self._get_worst(observations, ["param_PaO2", "PaO2"], spec, evaluation_time, reverse=True)
        fio2 = self._get_worst(observations, ["param_FiO2", "FiO2"], spec, evaluation_time, reverse=False)
        dq: list[str] = []
        if pao2 and fio2 and pao2.value_number and fio2.value_number:
            if pao2.observed_at and fio2.observed_at:
                diff = abs((pao2.observed_at - fio2.observed_at).total_seconds())
                if diff > _MAX_PAIR_SECONDS:
                    return None, True, ["PaO2 and FiO2 time gap >30min"]
            return _pao2_fio2_score(pao2.value_number, fio2.value_number), False, dq
        return None, True, dq

    def _calc_platelets(
        self,
        observations: list[Observation],
        spec: WindowSpec | None,
        evaluation_time: datetime,
    ) -> tuple[int | None, bool]:
        if not spec:
            return None, True
        obs = self._get_worst(observations, ["PLT", "platelets"], spec, evaluation_time, reverse=True)
        if obs and obs.value_number is not None:
            return _platelets_score(obs.value_number), False
        return None, True

    def _calc_bilirubin(
        self,
        observations: list[Observation],
        spec: WindowSpec | None,
        evaluation_time: datetime,
    ) -> int | None:
        if not spec:
            return None
        obs = self._get_worst(observations, ["TBIL", "bilirubin"], spec, evaluation_time, reverse=False)
        if obs and obs.value_number is not None:
            return _bilirubin_score(obs.value_number)
        return None

    def _calc_cardiovascular(
        self,
        observations: list[Observation],
        spec: WindowSpec | None,
        evaluation_time: datetime,
    ) -> int | None:
        if not spec:
            return None
        obs = self._get_latest(
            observations,
            ["vasopressor_dose", "norepinephrine_dose", "dopamine_dose", "dobutamine_dose", "epinephrine_dose"],
            spec,
            evaluation_time,
        )
        if obs and obs.value_number is not None:
            return _vasopressor_score(obs.value_number)
        return 0

    def _calc_gcs(
        self,
        observations: list[Observation],
        spec: WindowSpec | None,
        evaluation_time: datetime,
    ) -> int | None:
        if not spec:
            return None
        obs = self._get_worst(
            observations, ["param_score_gcs_obs", "gcsScore", "GCS"], spec, evaluation_time, reverse=True
        )
        if obs and obs.value_number is not None:
            return _gcs_score(obs.value_number)
        return None

    def _calc_renal(
        self,
        observations: list[Observation],
        spec: WindowSpec | None,
        evaluation_time: datetime,
        weight_kg: float | None,
    ) -> tuple[int | None, bool, list[str]]:
        if not spec:
            return None, True, []
        dq: list[str] = []

        # Creatinine path - use rulepack threshold if available
        crea_score: int | None = None
        crea_obs = self._get_worst(observations, ["CREA", "creatinine"], spec, evaluation_time, reverse=False)
        if crea_obs and crea_obs.value_number is not None:
            if self._rulepack is not None:
                tl = self._rulepack.get_threshold_lookup("renal_creatinine")
                if tl:
                    crea_score = tl.lookup(crea_obs.value_number)
            if crea_score is None:
                crea_score = _creatinine_score(crea_obs.value_number)

        # SOFA urine path: uses total mL/24h (not mL/kg/h)
        urine_score: int | None = None
        urine_obs = self._get_sum(observations, ["urine_output", "urineVolume"], spec, evaluation_time)
        if urine_obs and urine_obs.value_number is not None:
            hours = spec.lookback_window.total_seconds() / 3600
            if hours < 23.5:
                dq.append(f"Urine window coverage: {hours:.1f}h (expected 24h)")
            if self._rulepack is not None:
                tl = self._rulepack.get_threshold_lookup("renal_urine")
                if tl:
                    urine_score = tl.lookup(urine_obs.value_number)
            if urine_score is None:
                urine_score = _urine_score_daily(urine_obs.value_number)

        if crea_score is not None and urine_score is not None:
            return max(crea_score, urine_score), False, dq
        elif crea_score is not None:
            dq.append("Urine output path missing")
            return crea_score, False, dq
        elif urine_score is not None:
            dq.append("Creatinine path missing")
            return urine_score, False, dq
        return None, True, dq

    def _get_latest(
        self,
        observations: list[Observation],
        codes: list[str],
        spec: WindowSpec | None,
        evaluation_time: datetime,
    ) -> Observation | None:
        if not spec:
            return None
        filtered = filter_by_code(observations, codes)
        in_window = filter_in_window(filtered, spec, evaluation_time)
        latest = get_latest(in_window)
        if latest and is_stale(latest, spec.max_staleness, evaluation_time):
            return None
        return latest

    def _get_worst(
        self,
        observations: list[Observation],
        codes: list[str],
        spec: WindowSpec | None,
        evaluation_time: datetime,
        *,
        reverse: bool = False,
    ) -> Observation | None:
        if not spec:
            return None
        filtered = filter_by_code(observations, codes)
        in_window = filter_in_window(filtered, spec, evaluation_time)
        return get_worst(in_window, reverse=reverse)

    def _get_sum(
        self,
        observations: list[Observation],
        codes: list[str],
        spec: WindowSpec | None,
        evaluation_time: datetime,
    ) -> Observation | None:
        if not spec:
            return None
        filtered = filter_by_code(observations, codes)
        in_window = filter_in_window(filtered, spec, evaluation_time)
        valid = [o for o in in_window if o.value_number is not None]
        if not valid:
            return None
        values = [o.value_number for o in valid if o.value_number is not None]
        total = sum(values)
        latest = max(valid, key=lambda o: o.observed_at or datetime.min.replace(tzinfo=UTC))
        return latest.model_copy(update={"value_number": total})
