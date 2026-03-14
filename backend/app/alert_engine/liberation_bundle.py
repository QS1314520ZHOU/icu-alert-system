"""ABCDEF bundle 合规评估。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


class LiberationBundleMixin:
    def _bundle_state(self, *, hours_since: float | None, green_h: float, yellow_h: float) -> str:
        if hours_since is None:
            return "red"
        if hours_since <= green_h:
            return "green"
        if hours_since <= yellow_h:
            return "yellow"
        return "red"

    async def _latest_event_hours(self, pid, keywords: list[str], lookback_hours: int = 72) -> float | None:
        events = await self._get_recent_text_events(pid, keywords, hours=lookback_hours, limit=800)
        if not events:
            return None
        t = events[0].get("time")
        if not isinstance(t, datetime):
            return None
        return round((datetime.now() - t).total_seconds() / 3600.0, 1)

    async def get_liberation_bundle_status(self, patient_doc: dict) -> dict[str, Any]:
        pid = patient_doc.get("_id")
        if not pid:
            return {"lights": {}}
        now = datetime.now()

        cpot_hours = await self._latest_event_hours(pid, ["cpot", "bps", "疼痛"], lookback_hours=24)
        cam_hours = await self._latest_event_hours(pid, ["cam-icu", "cam icu", "谵妄"], lookback_hours=24)
        mobility_hours = await self._latest_event_hours(pid, ["早期活动", "下床", "站立", "行走", "康复", "活动"], lookback_hours=72)
        family_hours = await self._latest_event_hours(pid, ["家属沟通", "家属告知", "沟通记录", "家属参与"], lookback_hours=72)

        sedatives = await self._find_recent_drug_docs(pid, ["丙泊酚", "右美托咪定", "咪达唑仑", "地西泮", "劳拉西泮"], hours=24)
        benzo = [d for d in sedatives if any(k in self._drug_text(d).lower() for k in ["咪达唑仑", "地西泮", "劳拉西泮"])]
        preferred = [d for d in sedatives if any(k in self._drug_text(d).lower() for k in ["丙泊酚", "右美托咪定"])]
        sedation_state = "green" if preferred else "yellow" if sedatives and not benzo else "red" if benzo else "yellow"

        sbt_alert = await self._get_latest_active_alert(str(pid), ["weaning"], hours=36)
        sat_hours = await self._latest_event_hours(pid, ["sat", "唤醒试验", "停镇静"], lookback_hours=36)
        sbt_state = "green" if (sbt_alert or (sat_hours is not None and sat_hours <= 24)) else "red"

        lights = {
            "A": self._bundle_state(hours_since=cpot_hours, green_h=4, yellow_h=6),
            "B": sbt_state,
            "C": sedation_state,
            "D": self._bundle_state(hours_since=cam_hours, green_h=8, yellow_h=12),
            "E": self._bundle_state(hours_since=mobility_hours, green_h=24, yellow_h=36),
            "F": self._bundle_state(hours_since=family_hours, green_h=24, yellow_h=48),
        }
        compliance = round(sum(1 for v in lights.values() if v == "green") / 6.0, 3)
        return {
            "lights": lights,
            "compliance": compliance,
            "detail": {
                "pain_hours": cpot_hours,
                "delirium_hours": cam_hours,
                "mobility_hours": mobility_hours,
                "family_hours": family_hours,
                "sat_hours": sat_hours,
                "sbt_ready": bool(sbt_alert),
            },
            "updated_at": now,
        }

    async def scan_liberation_bundle(self) -> None:
        patient_cursor = self.db.col("patient").find(
            self._active_patient_query(),
            {"_id": 1, "name": 1, "hisBed": 1, "dept": 1, "hisDept": 1},
        )
        patients = [p async for p in patient_cursor]
        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        triggered = 0

        for patient_doc in patients:
            status = await self.get_liberation_bundle_status(patient_doc)
            lights = status.get("lights", {})
            red_items = [k for k, v in lights.items() if v == "red"]
            if not red_items:
                continue
            pid_str = str(patient_doc.get("_id"))
            rule_id = "LIBERATION_BUNDLE_OVERDUE"
            if await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                continue
            alert = await self._create_alert(
                rule_id=rule_id,
                name="ABCDEF Bundle 合规待补全",
                category="bundle",
                alert_type="liberation_bundle",
                severity="warning" if len(red_items) <= 2 else "high",
                parameter="bundle_lights",
                condition={"red_items": red_items},
                value=len(red_items),
                patient_id=pid_str,
                patient_doc=patient_doc,
                source_time=status.get("updated_at"),
                extra=status,
            )
            if alert:
                triggered += 1

        if triggered > 0:
            self._log_info("Bundle合规", triggered)

