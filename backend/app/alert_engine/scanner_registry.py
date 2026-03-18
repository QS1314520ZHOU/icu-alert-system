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
from .scanner_composite_deterioration import CompositeDeteriorationScanner
from .scanner_cardiac_arrest_risk import CardiacArrestRiskScanner
from .scanner_liberation_bundle import LiberationBundleScanner
from .scanner_ecash_bundle import EcashBundleScanner
from .scanner_icu_aw_mobility import IcuAwMobilityScanner
from .scanner_microbiology import MicrobiologyScanner
from .scanner_hemodynamic_advisor import HemodynamicAdvisorScanner
from .scanner_right_heart_monitor import RightHeartMonitorScanner
from .scanner_dose_adjustment import DoseAdjustmentScanner
from .scanner_discharge_readiness import DischargeReadinessScanner
from .scanner_adaptive_thresholds import AdaptiveThresholdsScanner
from .scanner_ai_risk import AiRiskScanner
from .scanner_alert_reasoning import AlertReasoningScanner
from .scanner_nurse_reminders import NurseRemindersScanner

if TYPE_CHECKING:
    from . import AlertEngine


def build_scanners(engine: AlertEngine) -> list[BaseScanner]:
    return [
        VitalSignsScanner(engine),
        LabResultsScanner(engine),
        SepsisScanner(engine),
        AkiScanner(engine),
        TrendScanner(engine),
        CrrtScanner(engine),
        ArdsScanner(engine),
        DicScanner(engine),
        TbiScanner(engine),
        BleedingScanner(engine),
        TemporalRiskScanner(engine),
        VentilatorWeaningScanner(engine),
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
        HemodynamicAdvisorScanner(engine),
        RightHeartMonitorScanner(engine),
        DoseAdjustmentScanner(engine),
        DischargeReadinessScanner(engine),
        AdaptiveThresholdsScanner(engine),
        AiRiskScanner(engine),
        AlertReasoningScanner(engine),
        NurseRemindersScanner(engine),
    ]
