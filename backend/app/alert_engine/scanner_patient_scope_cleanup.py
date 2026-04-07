from __future__ import annotations

from datetime import datetime

from app.utils.patient_helpers import research_patient_scope_query

from .scanners import BaseScanner, ScannerSpec


class PatientScopeCleanupScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="patient_scope_cleanup",
                interval_key="patient_scope_cleanup",
                default_interval=180,
                initial_delay=23,
            ),
        )

    async def scan(self) -> None:
        patient_cursor = self.engine.db.col("patient").find(
            research_patient_scope_query("in_dept"),
            {"_id": 1, "deptCode": 1},
        )
        active_patient_depts: dict[str, str] = {}
        async for row in patient_cursor:
            pid = str(row.get("_id") or "").strip()
            if not pid:
                continue
            active_patient_depts[pid] = str(row.get("deptCode") or "").strip()

        alert_cursor = self.engine.db.col("alert_records").find(
            {"is_active": True, "patient_id": {"$exists": True, "$nin": [None, ""]}},
            {"_id": 1, "patient_id": 1, "deptCode": 1},
        )

        stale_alert_ids: list = []
        transferred_alert_ids: list = []
        async for alert in alert_cursor:
            patient_id = str(alert.get("patient_id") or "").strip()
            if not patient_id:
                continue
            current_dept_code = active_patient_depts.get(patient_id)
            if current_dept_code is None:
                stale_alert_ids.append(alert.get("_id"))
                continue

            alert_dept_code = str(alert.get("deptCode") or "").strip()
            if alert_dept_code and current_dept_code and alert_dept_code != current_dept_code:
                transferred_alert_ids.append(alert.get("_id"))

        now = datetime.now()
        updated = 0
        if stale_alert_ids:
            result = await self.engine.db.col("alert_records").update_many(
                {"_id": {"$in": stale_alert_ids}},
                {
                    "$set": {
                        "is_active": False,
                        "resolved_at": now,
                        "resolve_reason": "patient_left_in_dept_scope",
                        "lifecycle_updated_at": now,
                    }
                },
            )
            updated += int(result.modified_count or 0)

        if transferred_alert_ids:
            result = await self.engine.db.col("alert_records").update_many(
                {"_id": {"$in": transferred_alert_ids}},
                {
                    "$set": {
                        "is_active": False,
                        "resolved_at": now,
                        "resolve_reason": "patient_dept_changed",
                        "lifecycle_updated_at": now,
                    }
                },
            )
            updated += int(result.modified_count or 0)

        if updated > 0:
            self.engine._log_info("患者范围清理", updated)
