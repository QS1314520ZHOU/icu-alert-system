from __future__ import annotations

from .scanners import BaseScanner, ScannerSpec


class ImagingReportAnalyzerScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="imaging_report_analyzer",
                interval_key="imaging_report_analyzer",
                default_interval=7200,
                initial_delay=52,
            ),
        )

    async def scan(self) -> None:
        await self.engine.scan_imaging_report_signals()
