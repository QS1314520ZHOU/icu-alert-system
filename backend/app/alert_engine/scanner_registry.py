from __future__ import annotations

from typing import TYPE_CHECKING

from .scanners import BaseScanner
from .vital_signs_scanner import VitalSignsScanner
from .lab_results_scanner import LabResultsScanner
from .sepsis_scanner import SepsisScanner
from .aki_scanner import AkiScanner
from .trend_scanner import TrendScanner
from .crrt_scanner import CrrtScanner
from .scanner_ards import ArdsScanner
from .scanner_dic import DicScanner
from .scanner_tbi import TbiScanner
from .scanner_bleeding import BleedingScanner
from .scanner_temporal_risk import TemporalRiskScanner
from .scanner_foundation_model_risk import FoundationModelRiskScanner
from .scanner_trajectory_drift import TrajectoryDriftScanner
from .scanner_ventilator_weaning import VentilatorWeaningScanner
from .scanner_diaphragm_protection import DiaphragmProtectionScanner
from .scanner_drug_safety import DrugSafetyScanner
from .scanner_antibiotic_stewardship import AntibioticStewardshipScanner
from .scanner_arc_risk import ArcRiskScanner
from .scanner_antimicrobial_pk import AntimicrobialPkScanner
from .scanner_vanco_tdm_closed_loop import VancoTdmClosedLoopScanner
from .scanner_immunocompromised_monitor import ImmunocompromisedMonitorScanner
from .scanner_delirium_risk import DeliriumRiskScanner
from .scanner_circadian_protector import CircadianProtectorScanner
from .scanner_device_management import DeviceManagementScanner
from .scanner_hai_bundle import HaiBundleScanner
from .scanner_fluid_balance import FluidBalanceScanner
from .scanner_glycemic_control import GlycemicControlScanner
from .scanner_vte_prophylaxis import VteProphylaxisScanner
from .scanner_pe_risk import PeRiskScanner
from .scanner_palliative_trigger import PalliativeTriggerScanner
from .scanner_postop_complications import PostopComplicationsScanner
from .scanner_nutrition_monitor import NutritionMonitorScanner
from .scanner_noninvasive_respiratory_support import NoninvasiveRespiratorySupportScanner
from .scanner_composite_deterioration import CompositeDeteriorationScanner
from .scanner_cardiac_arrest_risk import CardiacArrestRiskScanner
from .scanner_liberation_bundle import LiberationBundleScanner
from .scanner_ecash_bundle import EcashBundleScanner
from .scanner_fibrinolysis_monitor import FibrinolysisMonitorScanner
from .scanner_icu_aw_mobility import IcuAwMobilityScanner
from .scanner_microbiology import MicrobiologyScanner
from .scanner_hemodynamic_advisor import HemodynamicAdvisorScanner
from .scanner_imaging_report_analyzer import ImagingReportAnalyzerScanner
from .scanner_pics_risk import PicsRiskScanner
from .scanner_prone_position_monitor import PronePositionMonitorScanner
from .scanner_right_heart_monitor import RightHeartMonitorScanner
from .scanner_sepsis_subphenotype import SepsisSubphenotypeScanner
from .scanner_dose_adjustment import DoseAdjustmentScanner
from .scanner_discharge_readiness import DischargeReadinessScanner
from .scanner_adaptive_thresholds import AdaptiveThresholdsScanner
from .scanner_proactive_management import ProactiveManagementScanner
from .scanner_extended_scenarios import ExtendedScenariosScanner
from .scanner_ai_risk import AiRiskScanner
from .scanner_alert_reasoning import AlertReasoningScanner
from .scanner_beta_blocker_advisor import BetaBlockerAdvisorScanner
from .scanner_integrated_risk_reasoning import IntegratedRiskReasoningScanner
from .scanner_metabolic_phase_detector import MetabolicPhaseDetectorScanner
from .scanner_nurse_reminders import NurseRemindersScanner
from .scanner_nursing_note_analyzer import NursingNoteAnalyzerScanner
from .scanner_nursing_workload import NursingWorkloadScanner
from .scanner_patient_scope_cleanup import PatientScopeCleanupScanner
from .scanner_ventilator_asynchrony import VentilatorAsynchronyScanner
from .scanner_clinical_trial_screening import ClinicalTrialScreeningScanner

if TYPE_CHECKING:
    from . import AlertEngine


def build_scanners(engine: AlertEngine) -> list[BaseScanner]:
    return [
        VitalSignsScanner(engine),
        LabResultsScanner(engine),
        SepsisScanner(engine),
        SepsisSubphenotypeScanner(engine),
        AkiScanner(engine),
        TrendScanner(engine),
        CrrtScanner(engine),
        ArdsScanner(engine),
        PronePositionMonitorScanner(engine),
        DicScanner(engine),
        FibrinolysisMonitorScanner(engine),
        TbiScanner(engine),
        BleedingScanner(engine),
        FoundationModelRiskScanner(engine),
        TrajectoryDriftScanner(engine),
        TemporalRiskScanner(engine),
        VentilatorWeaningScanner(engine),
        NoninvasiveRespiratorySupportScanner(engine),
        VentilatorAsynchronyScanner(engine),
        DiaphragmProtectionScanner(engine),
        DrugSafetyScanner(engine),
        AntibioticStewardshipScanner(engine),
        ArcRiskScanner(engine),
        AntimicrobialPkScanner(engine),
        VancoTdmClosedLoopScanner(engine),
        ImmunocompromisedMonitorScanner(engine),
        DeliriumRiskScanner(engine),
        CircadianProtectorScanner(engine),
        DeviceManagementScanner(engine),
        HaiBundleScanner(engine),
        FluidBalanceScanner(engine),
        GlycemicControlScanner(engine),
        VteProphylaxisScanner(engine),
        PeRiskScanner(engine),
        PalliativeTriggerScanner(engine),
        PostopComplicationsScanner(engine),
        NutritionMonitorScanner(engine),
        CompositeDeteriorationScanner(engine),
        CardiacArrestRiskScanner(engine),
        LiberationBundleScanner(engine),
        EcashBundleScanner(engine),
        IcuAwMobilityScanner(engine),
        MicrobiologyScanner(engine),
        ImagingReportAnalyzerScanner(engine),
        HemodynamicAdvisorScanner(engine),
        RightHeartMonitorScanner(engine),
        DoseAdjustmentScanner(engine),
        DischargeReadinessScanner(engine),
        AdaptiveThresholdsScanner(engine),
        ProactiveManagementScanner(engine),
        ExtendedScenariosScanner(engine),
        MetabolicPhaseDetectorScanner(engine),
        BetaBlockerAdvisorScanner(engine),
        PicsRiskScanner(engine),
        IntegratedRiskReasoningScanner(engine),
        AiRiskScanner(engine),
        AlertReasoningScanner(engine),
        PatientScopeCleanupScanner(engine),
        NurseRemindersScanner(engine),
        NursingNoteAnalyzerScanner(engine),
        NursingWorkloadScanner(engine),
        ClinicalTrialScreeningScanner(engine),
    ]
