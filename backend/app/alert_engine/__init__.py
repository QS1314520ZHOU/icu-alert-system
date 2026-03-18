"""
ICU智能预警系统 - 预警规则引擎 v2
包含: 阈值预警 + 检验扫描 + 综合征识别 + 趋势恶化 + AI 综合分析 + 护理提醒
"""
from __future__ import annotations

import asyncio
import logging

from .ai_risk import AiRiskMixin
from .adaptive_threshold_advisor import AdaptiveThresholdAdvisorMixin
from .alert_reasoning_agent import AlertReasoningAgentMixin
from .alert_intelligence import AlertIntelligenceMixin
from .antibiotic_stewardship import AntibioticStewardshipMixin
from .antimicrobial_pk import AntimicrobialPKMixin
from .base import BaseEngine
from .composite_deterioration import CompositeDeteriorationMixin
from .crrt_monitor import CrrtMonitorMixin
from .circadian_protector import CircadianProtectorMixin
from .data_quality_filter import DataQualityFilterMixin
from .diaphragm_protection import DiaphragmProtectionMixin
from .delirium_risk import DeliriumRiskMixin
from .device_management import DeviceManagementMixin
from .discharge_readiness import DischargeReadinessMixin
from .dose_adjustment import DoseAdjustmentMixin
from .drug_safety import DrugSafetyMixin
from .fluid_balance import FluidBalanceMixin
from .glycemic_control import GlycemicControlMixin
from .hai_bundle_monitor import HaiBundleMonitorMixin
from .hemodynamic_advisor import HemodynamicAdvisorMixin
from .immunocompromised_monitor import ImmunocompromisedMonitorMixin
from .lab_scanner import LabScannerMixin
from .liberation_bundle import LiberationBundleMixin
from .nurse_reminder import NurseReminderMixin
from .nutrition_monitor import NutritionMonitorMixin
from .syndrome_aki import AkiMixin
from .syndrome_ards import ArdsMixin
from .syndrome_bleeding import BleedingMixin
from .syndrome_dic import DicMixin
from .syndrome_sepsis import SepsisMixin
from .syndrome_tbi import TbiMixin
from .temporal_risk_scanner import TemporalRiskScannerMixin
from .trend_analyzer import TrendMixin
from .vte_prophylaxis import VteProphylaxisMixin
from .vital_signs import VitalSignsMixin
from .ventilator import VentilatorMixin
from .cardiac_arrest_predictor import CardiacArrestPredictorMixin
from .microbiology_monitor import MicrobiologyMonitorMixin
from .pe_detector import PeDetectorMixin
from .palliative_trigger import PalliativeTriggerMixin
from .postop_monitor import PostopMonitorMixin
from .right_heart_monitor import RightHeartMonitorMixin
from .ecash_bundle import EcashBundleMixin
from .icu_aw_mobility import IcuAwMobilityMixin
from .similar_case_review import SimilarCaseReviewMixin

logger = logging.getLogger("icu-alert")


class AlertEngine(
    BaseEngine,
    AlertIntelligenceMixin,
    AlertReasoningAgentMixin,
    DataQualityFilterMixin,
    DiaphragmProtectionMixin,
    VitalSignsMixin,
    LabScannerMixin,
    SepsisMixin,
    ImmunocompromisedMonitorMixin,
    ArdsMixin,
    AkiMixin,
    DicMixin,
    TbiMixin,
    BleedingMixin,
    TemporalRiskScannerMixin,
    VentilatorMixin,
    DrugSafetyMixin,
    AntibioticStewardshipMixin,
    AntimicrobialPKMixin,
    DeliriumRiskMixin,
    DeviceManagementMixin,
    HaiBundleMonitorMixin,
    FluidBalanceMixin,
    GlycemicControlMixin,
    VteProphylaxisMixin,
    NutritionMonitorMixin,
    CompositeDeteriorationMixin,
    CrrtMonitorMixin,
    CircadianProtectorMixin,
    LiberationBundleMixin,
    HemodynamicAdvisorMixin,
    DoseAdjustmentMixin,
    DischargeReadinessMixin,
    CardiacArrestPredictorMixin,
    MicrobiologyMonitorMixin,
    PeDetectorMixin,
    PalliativeTriggerMixin,
    PostopMonitorMixin,
    RightHeartMonitorMixin,
    EcashBundleMixin,
    IcuAwMobilityMixin,
    SimilarCaseReviewMixin,
    TrendMixin,
    AdaptiveThresholdAdvisorMixin,
    AiRiskMixin,
    NurseReminderMixin,
):
    def __init__(self, db, config, ws_manager=None) -> None:
        super().__init__(db, config, ws_manager)
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []
        max_concurrent = int(self.config.yaml_cfg.get("alert_engine", {}).get("max_concurrent_scans", 4) or 4)
        self._scan_semaphore = asyncio.Semaphore(max(1, max_concurrent))

    async def start(self) -> None:
        self._stop_event.clear()
        intervals = self.config.yaml_cfg.get("alert_engine", {}).get("scan_intervals", {})

        self._tasks = [
            asyncio.create_task(self._loop("vital_signs", self.scan_vital_signs, int(intervals.get("vital_signs", 60)))),
            asyncio.create_task(self._loop("lab_results", self.scan_lab_results, int(intervals.get("lab_results", 300)))),
            asyncio.create_task(self._loop("sepsis", self.scan_sepsis, int(intervals.get("sepsis", 300)))),
            asyncio.create_task(self._loop("ards", self.scan_ards, int(intervals.get("ards", 300)))),
            asyncio.create_task(self._loop("aki", self.scan_aki, int(intervals.get("aki", 600)))),
            asyncio.create_task(self._loop("dic", self.scan_dic, int(intervals.get("dic", 900)))),
            asyncio.create_task(self._loop("tbi", self.scan_tbi, int(intervals.get("tbi", 300)))),
            asyncio.create_task(self._loop("bleeding", self.scan_bleeding, int(intervals.get("bleeding", 600)))),
            asyncio.create_task(self._loop("temporal_risk_scanner", self.scan_temporal_risk, int(intervals.get("temporal_risk_scanner", 900)))),
            asyncio.create_task(self._loop("ventilator", self.scan_ventilator_weaning, int(intervals.get("ventilator", 3600)))),
            asyncio.create_task(self._loop("diaphragm_protection", self.scan_diaphragm_protection, int(intervals.get("diaphragm_protection", 900)))),
            asyncio.create_task(self._loop("drug_safety", self.scan_drug_safety, int(intervals.get("drug_safety", 1800)))),
            asyncio.create_task(self._loop("antibiotic_stewardship", self.scan_antibiotic_stewardship, int(intervals.get("antibiotic_stewardship", 1800)))),
            asyncio.create_task(self._loop("arc_risk", self.scan_arc_risk, int(intervals.get("arc_risk", 300)))),
            asyncio.create_task(self._loop("antimicrobial_pk", self.scan_antimicrobial_pk, int(intervals.get("antimicrobial_pk", 600)))),
            asyncio.create_task(self._loop("vanco_tdm_closed_loop", self.scan_vanco_tdm_closed_loop, int(intervals.get("vanco_tdm_closed_loop", 600)))),
            asyncio.create_task(self._loop("immunocompromised_monitor", self.scan_immunocompromised_monitor, int(intervals.get("immunocompromised_monitor", 600)))),
            asyncio.create_task(self._loop("delirium_risk", self.scan_delirium_risk, int(intervals.get("delirium_risk", 900)))),
            asyncio.create_task(self._loop("circadian_protector", self.scan_circadian_protector, int(intervals.get("circadian_protector", 900)))),
            asyncio.create_task(self._loop("device_management", self.scan_device_management, int(intervals.get("device_management", 3600)))),
            asyncio.create_task(self._loop("hai_bundle", self.scan_hai_bundle, int(intervals.get("hai_bundle", 1800)))),
            asyncio.create_task(self._loop("fluid_balance", self.scan_fluid_balance, int(intervals.get("fluid_balance", 600)))),
            asyncio.create_task(self._loop("glycemic_control", self.scan_glycemic_control, int(intervals.get("glycemic_control", 300)))),
            asyncio.create_task(self._loop("vte_prophylaxis", self.scan_vte_prophylaxis, int(intervals.get("vte_prophylaxis", 900)))),
            asyncio.create_task(self._loop("pe_detection", self.scan_pe_risk, int(intervals.get("pe_detection", 600)))),
            asyncio.create_task(self._loop("palliative_trigger", self.scan_palliative_trigger, int(intervals.get("palliative_trigger", 1800)))),
            asyncio.create_task(self._loop("postop_monitor", self.scan_postop_complications, int(intervals.get("postop_monitor", 1800)))),
            asyncio.create_task(self._loop("nutrition_monitor", self.scan_nutrition_monitor, int(intervals.get("nutrition_monitor", 900)))),
            asyncio.create_task(self._loop("composite_deterioration", self.scan_composite_deterioration, int(intervals.get("composite_deterioration", 300)))),
            asyncio.create_task(self._loop("cardiac_arrest", self.scan_cardiac_arrest_risk, int(intervals.get("cardiac_arrest", 120)))),
            asyncio.create_task(self._loop("crrt_monitor", self.scan_crrt_monitor, int(intervals.get("crrt_monitor", 600)))),
            asyncio.create_task(self._loop("liberation_bundle", self.scan_liberation_bundle, int(intervals.get("liberation_bundle", 900)))),
            asyncio.create_task(self._loop("ecash_bundle", self.scan_ecash_bundle, int(intervals.get("ecash_bundle", 600)))),
            asyncio.create_task(self._loop("icu_aw_mobility", self.scan_icu_aw_mobility, int(intervals.get("icu_aw_mobility", 900)))),
            asyncio.create_task(self._loop("microbiology", self.scan_microbiology, int(intervals.get("microbiology", 1800)))),
            asyncio.create_task(self._loop("hemodynamic_advisor", self.scan_hemodynamic_advisor, int(intervals.get("hemodynamic_advisor", 300)))),
            asyncio.create_task(self._loop("right_heart_monitor", self.scan_right_heart_monitor, int(intervals.get("right_heart_monitor", 600)))),
            asyncio.create_task(self._loop("dose_adjustment", self.scan_dose_adjustment, int(intervals.get("dose_adjustment", 1800)))),
            asyncio.create_task(self._loop("discharge_readiness", self.scan_discharge_readiness, int(intervals.get("discharge_readiness", 1800)))),
            asyncio.create_task(self._loop("trend_analysis", self.scan_trends, int(intervals.get("trend_analysis", 900)))),
            asyncio.create_task(self._loop("adaptive_threshold_advisor", self.scan_adaptive_thresholds, int(intervals.get("adaptive_threshold_advisor", 7200)))),
            asyncio.create_task(self._loop("ai_analysis", self.scan_ai_risk, 1800)),
            asyncio.create_task(self._loop("alert_reasoning", self.scan_alert_reasoning, int(intervals.get("alert_reasoning", 300)))),
            asyncio.create_task(self._loop("nurse_reminders", self.scan_nurse_reminders, int(intervals.get("assessments", 600)))),
        ]
        logger.info(f"✅ 预警引擎启动完成 ({len(self._tasks)} 个扫描任务)")

    async def stop(self) -> None:
        self._stop_event.set()
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("⏹️ 预警引擎已停止")

    async def _loop(self, name: str, func, interval: int) -> None:
        delays = {
            "vital_signs": 5,
            "lab_results": 10,
            "sepsis": 15,
            "ards": 20,
            "aki": 25,
            "dic": 30,
            "tbi": 22,
            "bleeding": 27,
            "temporal_risk_scanner": 28,
            "ventilator": 40,
            "diaphragm_protection": 34,
            "drug_safety": 45,
            "antibiotic_stewardship": 42,
            "arc_risk": 46,
            "antimicrobial_pk": 48,
            "vanco_tdm_closed_loop": 50,
            "immunocompromised_monitor": 52,
            "delirium_risk": 35,
            "circadian_protector": 36,
            "cardiac_arrest": 32,
            "device_management": 37,
            "hai_bundle": 54,
            "fluid_balance": 39,
            "glycemic_control": 41,
            "vte_prophylaxis": 43,
            "pe_detection": 44,
            "palliative_trigger": 58,
            "postop_monitor": 64,
            "nutrition_monitor": 47,
            "composite_deterioration": 49,
            "crrt_monitor": 51,
            "liberation_bundle": 53,
            "ecash_bundle": 66,
            "icu_aw_mobility": 68,
            "microbiology": 62,
            "hemodynamic_advisor": 55,
            "right_heart_monitor": 56,
            "dose_adjustment": 57,
            "discharge_readiness": 59,
            "trend_analysis": 30,
            "adaptive_threshold_advisor": 70,
            "ai_analysis": 60,
            "alert_reasoning": 75,
            "nurse_reminders": 17,
        }
        await self._sleep(delays.get(name, 5))
        while not self._stop_event.is_set():
            try:
                async with self._scan_semaphore:
                    await func()
            except Exception as e:
                logger.exception(f"[{name}] 扫描失败: {e}")
            await self._sleep(interval)

    async def _sleep(self, seconds: int) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=max(seconds, 1))
        except asyncio.TimeoutError:
            return
