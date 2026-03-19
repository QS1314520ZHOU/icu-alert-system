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
from .proactive_management_engine import ProactiveManagementEngineMixin
from .extended_scenario_engine import ExtendedScenarioMixin
from .similar_case_review import SimilarCaseReviewMixin
from .scanner_registry import build_scanners
from .scanners import BaseScanner

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
    ProactiveManagementEngineMixin,
    ExtendedScenarioMixin,
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
        self.scanners: list[BaseScanner] = build_scanners(self)
        max_concurrent = int(self.config.yaml_cfg.get("alert_engine", {}).get("max_concurrent_scans", 4) or 4)
        self._scan_semaphore = asyncio.Semaphore(max(1, max_concurrent))

    def _active_scanners(self) -> list[BaseScanner]:
        active: list[BaseScanner] = []
        for scanner in self.scanners:
            try:
                if scanner.is_enabled():
                    active.append(scanner)
            except Exception as exc:
                logger.exception(f"[scanner_registry] 扫描器初始化失败: {exc}")
        return active

    async def start(self) -> None:
        self._stop_event.clear()
        active_scanners = self._active_scanners()
        self._tasks = [
            asyncio.create_task(
                self._loop(
                    scanner.name,
                    scanner.scan,
                    scanner.interval_seconds(),
                    scanner.initial_delay,
                )
            )
            for scanner in active_scanners
        ]
        logger.info(f"✅ 预警引擎启动完成 ({len(self._tasks)} 个扫描任务)")

    async def run_all(self) -> None:
        for scanner in self._active_scanners():
            try:
                async with self._scan_semaphore:
                    await scanner.scan()
            except Exception as exc:
                logger.exception(f"[{scanner.name}] 单次执行失败: {exc}")

    async def stop(self) -> None:
        self._stop_event.set()
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("⏹️ 预警引擎已停止")

    async def _loop(self, name: str, func, interval: int, initial_delay: int = 5) -> None:
        await self._sleep(initial_delay)
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
