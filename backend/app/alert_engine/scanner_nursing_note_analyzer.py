from __future__ import annotations

from .scanners import BaseScanner, ScannerSpec


class NursingNoteAnalyzerScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="nursing_note_analyzer",
                interval_key="nursing_note_analyzer",
                default_interval=14400,
                initial_delay=45,
            ),
        )

    async def scan(self) -> None:
        await self.engine.scan_nursing_note_signals()
