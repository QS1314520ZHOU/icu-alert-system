"""
ICU智能预警系统 - 预警规则引擎 v2
包含: 阈值预警 + 检验扫描 + 综合征识别 + 趋势恶化 + AI 综合分析 + 护理提醒
"""
from __future__ import annotations

import asyncio
import logging

from .ai_risk import AiRiskMixin
from .antibiotic_stewardship import AntibioticStewardshipMixin
from .base import BaseEngine
from .composite_deterioration import CompositeDeteriorationMixin
from .crrt_monitor import CrrtMonitorMixin
from .delirium_risk import DeliriumRiskMixin
from .device_management import DeviceManagementMixin
from .discharge_readiness import DischargeReadinessMixin
from .dose_adjustment import DoseAdjustmentMixin
from .drug_safety import DrugSafetyMixin
from .fluid_balance import FluidBalanceMixin
from .glycemic_control import GlycemicControlMixin
from .hemodynamic_advisor import HemodynamicAdvisorMixin
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
from .trend_analyzer import TrendMixin
from .vte_prophylaxis import VteProphylaxisMixin
from .vital_signs import VitalSignsMixin
from .ventilator import VentilatorMixin

logger = logging.getLogger("icu-alert")


class AlertEngine(
    BaseEngine,
    VitalSignsMixin,
    LabScannerMixin,
    SepsisMixin,
    ArdsMixin,
    AkiMixin,
    DicMixin,
    TbiMixin,
    BleedingMixin,
    VentilatorMixin,
    DrugSafetyMixin,
    AntibioticStewardshipMixin,
    DeliriumRiskMixin,
    DeviceManagementMixin,
    FluidBalanceMixin,
    GlycemicControlMixin,
    VteProphylaxisMixin,
    NutritionMonitorMixin,
    CompositeDeteriorationMixin,
    CrrtMonitorMixin,
    LiberationBundleMixin,
    HemodynamicAdvisorMixin,
    DoseAdjustmentMixin,
    DischargeReadinessMixin,
    TrendMixin,
    AiRiskMixin,
    NurseReminderMixin,
):
    def __init__(self, db, config, ws_manager=None) -> None:
        super().__init__(db, config, ws_manager)
        self._stop_event = asyncio.Event()
        self._tasks: list[asyncio.Task] = []

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
            asyncio.create_task(self._loop("ventilator", self.scan_ventilator_weaning, int(intervals.get("ventilator", 3600)))),
            asyncio.create_task(self._loop("drug_safety", self.scan_drug_safety, int(intervals.get("drug_safety", 1800)))),
            asyncio.create_task(self._loop("antibiotic_stewardship", self.scan_antibiotic_stewardship, int(intervals.get("antibiotic_stewardship", 1800)))),
            asyncio.create_task(self._loop("delirium_risk", self.scan_delirium_risk, int(intervals.get("delirium_risk", 900)))),
            asyncio.create_task(self._loop("device_management", self.scan_device_management, int(intervals.get("device_management", 3600)))),
            asyncio.create_task(self._loop("fluid_balance", self.scan_fluid_balance, int(intervals.get("fluid_balance", 600)))),
            asyncio.create_task(self._loop("glycemic_control", self.scan_glycemic_control, int(intervals.get("glycemic_control", 300)))),
            asyncio.create_task(self._loop("vte_prophylaxis", self.scan_vte_prophylaxis, int(intervals.get("vte_prophylaxis", 900)))),
            asyncio.create_task(self._loop("nutrition_monitor", self.scan_nutrition_monitor, int(intervals.get("nutrition_monitor", 900)))),
            asyncio.create_task(self._loop("composite_deterioration", self.scan_composite_deterioration, int(intervals.get("composite_deterioration", 300)))),
            asyncio.create_task(self._loop("crrt_monitor", self.scan_crrt_monitor, int(intervals.get("crrt_monitor", 600)))),
            asyncio.create_task(self._loop("liberation_bundle", self.scan_liberation_bundle, int(intervals.get("liberation_bundle", 900)))),
            asyncio.create_task(self._loop("hemodynamic_advisor", self.scan_hemodynamic_advisor, int(intervals.get("hemodynamic_advisor", 300)))),
            asyncio.create_task(self._loop("dose_adjustment", self.scan_dose_adjustment, int(intervals.get("dose_adjustment", 1800)))),
            asyncio.create_task(self._loop("trend_analysis", self.scan_trends, int(intervals.get("trend_analysis", 900)))),
            asyncio.create_task(self._loop("ai_analysis", self.scan_ai_risk, 1800)),
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
            "tbi": 20,
            "bleeding": 25,
            "ventilator": 40,
            "drug_safety": 45,
            "antibiotic_stewardship": 40,
            "delirium_risk": 35,
            "device_management": 35,
            "fluid_balance": 35,
            "glycemic_control": 35,
            "vte_prophylaxis": 35,
            "nutrition_monitor": 35,
            "composite_deterioration": 35,
            "crrt_monitor": 35,
            "liberation_bundle": 35,
            "hemodynamic_advisor": 35,
            "dose_adjustment": 35,
            "trend_analysis": 30,
            "ai_analysis": 60,
            "nurse_reminders": 15,
        }
        await self._sleep(delays.get(name, 5))
        while not self._stop_event.is_set():
            try:
                await func()
            except Exception as e:
                logger.exception(f"[{name}] 扫描失败: {e}")
            await self._sleep(interval)

    async def _sleep(self, seconds: int) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=max(seconds, 1))
        except asyncio.TimeoutError:
            return
