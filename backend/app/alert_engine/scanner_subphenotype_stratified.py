from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .scanner_sepsis_subphenotype import SepsisSubphenotypeScanner
from .scanners import BaseScanner, ScannerSpec
from .subphenotype_stratified_outcome import SubphenotypeStratifiedOutcomeMixin

logger = logging.getLogger("icu-alert")


class SubphenotypeStratifiedScanner(BaseScanner):
    """Scanner that computes subphenotype × treatment_class × outcome signals.

    Runs periodically, aggregates historical alert outcomes by subphenotype
    and treatment class, identifies significant deviations, and persists
    signals to the score collection for human review.
    """

    def __init__(self, engine: SubphenotypeStratifiedOutcomeMixin) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="subphenotype_stratified",
                interval_key="subphenotype_stratified",
                default_interval=3600,
                initial_delay=120,
                maturity="experimental",
            ),
        )

    def is_enabled(self) -> bool:
        return super().is_enabled() and bool(self._cfg().get("enabled", True))

    def interval_seconds(self) -> int:
        value = self._cfg().get("scan_interval")
        try:
            return max(300, int(value))
        except (TypeError, ValueError):
            return super().interval_seconds()

    def _cfg(self) -> dict[str, Any]:
        cfg = self.engine._cfg("alert_engine", "subphenotype_stratified", default={}) or {}
        return cfg if isinstance(cfg, dict) else {}

    async def scan(self, patient_id: str | None = None) -> list[dict[str, Any]]:
        """Compute and persist stratified outcome signals.

        This scanner does not produce alerts; it produces score documents
        with score_type='subphenotype_treatment_signal' for human review.
        """
        now = datetime.now()
        try:
            signals = await self.engine.compute_stratified_signals(now=now)
            if signals:
                count = await self.engine._persist_signals(signals)
                logger.info(
                    "[subphenotype_stratified] Persisted %d signals (%d computed)",
                    count,
                    len(signals),
                )
            else:
                logger.debug("[subphenotype_stratified] No signals produced this cycle")
        except Exception as exc:
            logger.error("[subphenotype_stratified] Signal computation failed: %s", exc)
        return []  # This scanner does not produce alerts
