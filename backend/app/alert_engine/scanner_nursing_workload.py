from __future__ import annotations

from .scanners import BaseScanner, ScannerSpec


class NursingWorkloadScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="nursing_workload",
                interval_key="nursing_workload",
                default_interval=14400,
                initial_delay=41,
            ),
        )

    async def scan(self) -> None:
        rows = await self.engine.scan_nursing_workload()
        if rows:
            high_count = sum(
                1 for row in rows if str(row.get("intensity_level") or "").lower() in {"high", "extreme"}
            )
            self.engine._log_info("护理工作量预测", high_count or len(rows))
