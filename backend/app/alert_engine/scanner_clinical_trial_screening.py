from __future__ import annotations

from .scanners import BaseScanner, ScannerSpec


class ClinicalTrialScreeningScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="clinical_trial_screening",
                interval_key="clinical_trial_screening",
                default_interval=1800,
                initial_delay=75,
            ),
        )

    async def scan(self) -> None:
        from app.services.clinical_trial_service import screen_patients

        result = await screen_patients()
        count = len(result.get("candidates") or [])
        if count:
            self.engine._log_info("临床试验智能筛选", count)
