"""脓毒症筛查与 1h Bundle 抗生素追踪。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.utils.clinical import _extract_param


class SepsisMixin:
    def _sepsis_bundle_cfg(self) -> dict:
        cfg = self.config.yaml_cfg.get("alert_engine", {}).get("sepsis_bundle", {})
        return cfg if isinstance(cfg, dict) else {}

    async def _get_active_sepsis_bundle_tracker(self, pid_str: str) -> dict | None:
        return await self.db.col("score_records").find_one(
            {
                "patient_id": pid_str,
                "score_type": "sepsis_antibiotic_bundle",
                "bundle_type": "sepsis_1h_antibiotic",
                "is_active": True,
            },
            sort=[("bundle_started_at", -1)],
        )

    async def _get_recent_sepsis_bundle_tracker(self, pid_str: str, now: datetime, hours: int) -> dict | None:
        since = now - timedelta(hours=max(1, hours))
        return await self.db.col("score_records").find_one(
            {
                "patient_id": pid_str,
                "score_type": "sepsis_antibiotic_bundle",
                "bundle_type": "sepsis_1h_antibiotic",
                "bundle_started_at": {"$gte": since},
            },
            sort=[("bundle_started_at", -1)],
        )

    async def _start_or_refresh_sepsis_bundle_tracker(
        self,
        *,
        patient_doc: dict,
        pid_str: str,
        now: datetime,
        qsofa_triggered: bool,
        qsofa: int,
        sbp: float | None,
        rr: float | None,
        gcs: float | None,
        sofa_triggered: bool,
        sofa: dict | None,
    ) -> dict | None:
        cfg = self._sepsis_bundle_cfg()
        tracker_window_h = int(cfg.get("tracker_reopen_hours", 24))
        active = await self._get_active_sepsis_bundle_tracker(pid_str)
        recent = active or await self._get_recent_sepsis_bundle_tracker(pid_str, now, tracker_window_h)

        source_rules: list[str] = []
        if qsofa_triggered:
            source_rules.append("SEPSIS_QSOFA")
        if sofa_triggered:
            source_rules.append("SEPSIS_SOFA")
        if not source_rules:
            return active

        if recent:
            await self.db.col("score_records").update_one(
                {"_id": recent["_id"]},
                {
                    "$set": {
                        "calc_time": now,
                        "updated_at": now,
                        "source_rules": sorted(set((recent.get("source_rules") or []) + source_rules)),
                        "qsofa": qsofa,
                        "sbp": sbp,
                        "rr": rr,
                        "gcs": gcs,
                        "sofa_score": (sofa or {}).get("score") if isinstance(sofa, dict) else None,
                        "sofa_delta": (sofa or {}).get("delta") if isinstance(sofa, dict) else None,
                    }
                },
            )
            if active:
                recent.update(
                    {
                        "calc_time": now,
                        "updated_at": now,
                        "source_rules": sorted(set((recent.get("source_rules") or []) + source_rules)),
                        "qsofa": qsofa,
                        "sbp": sbp,
                        "rr": rr,
                        "gcs": gcs,
                        "sofa_score": (sofa or {}).get("score") if isinstance(sofa, dict) else None,
                        "sofa_delta": (sofa or {}).get("delta") if isinstance(sofa, dict) else None,
                    }
                )
                return recent
            return None

        deadline_1h = now + timedelta(minutes=int(cfg.get("deadline_minutes", 60)))
        deadline_3h = now + timedelta(minutes=int(cfg.get("escalation_3h_minutes", 180)))
        tracker = {
            "patient_id": pid_str,
            "patient_name": patient_doc.get("name"),
            "bed": patient_doc.get("hisBed"),
            "dept": patient_doc.get("dept") or patient_doc.get("hisDept"),
            "score_type": "sepsis_antibiotic_bundle",
            "bundle_type": "sepsis_1h_antibiotic",
            "bundle_started_at": now,
            "deadline_1h": deadline_1h,
            "deadline_3h": deadline_3h,
            "status": "pending",
            "is_active": True,
            "compliant_1h": None,
            "source_rules": source_rules,
            "qsofa": qsofa,
            "sbp": sbp,
            "rr": rr,
            "gcs": gcs,
            "sofa_score": (sofa or {}).get("score") if isinstance(sofa, dict) else None,
            "sofa_delta": (sofa or {}).get("delta") if isinstance(sofa, dict) else None,
            "calc_time": now,
            "created_at": now,
            "updated_at": now,
            "month": now.strftime("%Y-%m"),
            "day": now.strftime("%Y-%m-%d"),
        }
        res = await self.db.col("score_records").insert_one(tracker)
        tracker["_id"] = res.inserted_id
        return tracker

    async def _find_first_antibiotic_after(self, pid_str: str, start_time: datetime) -> dict | None:
        abx_names, _ = await self._load_antibiotic_dictionary()
        fallback = self._get_cfg_list(
            ("alert_engine", "antibiotic_stewardship", "antibiotic_keywords"),
            ["头孢", "青霉素", "美罗培南", "左氧氟沙星", "万古霉素", "阿奇霉素", "哌拉西林"],
        )
        keywords = sorted(set([*(abx_names or []), *(fallback or [])]))
        if not keywords:
            return None
        events = await self._get_drug_events(pid_str, start_time)
        for item in events:
            name = str(item.get("name") or "").strip()
            if self._match_name_keywords(name, keywords):
                return item
        return None

    async def _build_sepsis_bundle_explanation(
        self,
        *,
        status: str,
        tracker: dict,
        abx_event: dict | None = None,
    ) -> dict:
        started = tracker.get("bundle_started_at")
        started_text = started.strftime("%H:%M") if isinstance(started, datetime) else "—"
        evidence = [f"脓毒症计时起点 {started_text}"]
        if tracker.get("source_rules"):
            evidence.append("触发来源：" + " / ".join(str(x) for x in tracker.get("source_rules") if x))
        if tracker.get("qsofa") is not None:
            evidence.append(f"qSOFA {tracker.get('qsofa')}")
        if tracker.get("sofa_delta") is not None:
            evidence.append(f"SOFA Δ {tracker.get('sofa_delta')}")
        if abx_event and isinstance(abx_event.get("time"), datetime):
            evidence.append(f"首剂抗生素 {abx_event.get('name')} @ {abx_event['time'].strftime('%H:%M')}")

        if status == "met":
            summary = "脓毒症 1h Bundle 首剂抗生素已在时限内完成。"
            suggestion = "请继续完成血培养、乳酸复测和感染灶控制，并纳入科室合规统计。"
        elif status == "met_late":
            summary = "已执行首剂抗生素，但超过脓毒症 1 小时时限。"
            suggestion = "请尽快补记延迟原因，并纳入 Sepsis Bundle 质控复盘。"
        elif status == "overdue_3h":
            summary = "脓毒症首剂抗生素已超 3 小时仍未执行。"
            suggestion = "请立即完成首剂抗生素给药并升级上报，复盘采样/开立/执行环节阻滞点。"
        else:
            summary = "脓毒症首剂抗生素已超 1 小时未执行。"
            suggestion = "请立即复核医嘱与执行链路，优先完成首剂抗生素给药并记录延迟原因。"

        return await self._polish_structured_alert_explanation(
            {
                "summary": summary,
                "evidence": evidence[:5],
                "suggestion": suggestion,
                "text": "",
            }
        )

    async def _evaluate_sepsis_bundle_tracker(
        self,
        *,
        tracker: dict | None,
        patient_doc: dict,
        pid_str: str,
        device_id: str | None,
        now: datetime,
        same_rule_sec: int,
        max_per_hour: int,
    ) -> int:
        if not tracker:
            return 0
        started = tracker.get("bundle_started_at")
        if not isinstance(started, datetime):
            return 0

        abx_event = await self._find_first_antibiotic_after(pid_str, started)
        if abx_event:
            met_time = abx_event.get("time")
            within_1h = isinstance(met_time, datetime) and met_time <= (tracker.get("deadline_1h") or started + timedelta(hours=1))
            await self.db.col("score_records").update_one(
                {"_id": tracker["_id"]},
                {
                    "$set": {
                        "status": "met" if within_1h else "met_late",
                        "is_active": False,
                        "compliant_1h": bool(within_1h),
                        "first_antibiotic_time": met_time,
                        "first_antibiotic_name": abx_event.get("name"),
                        "resolved_at": now,
                        "calc_time": now,
                        "updated_at": now,
                    }
                },
            )
            return 0

        deadline_1h = tracker.get("deadline_1h") or (started + timedelta(hours=1))
        deadline_3h = tracker.get("deadline_3h") or (started + timedelta(hours=3))
        fired = 0

        if now >= deadline_3h and not tracker.get("overdue_3h_alerted"):
            rule_id = "SEPSIS_ANTIBIOTIC_OVER_3H"
            if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                explanation = await self._build_sepsis_bundle_explanation(status="overdue_3h", tracker=tracker)
                alert = await self._create_alert(
                    rule_id=rule_id,
                    name="脓毒症首剂抗生素超3h未执行",
                    category="bundle",
                    alert_type="sepsis_abx_overdue_3h",
                    severity="critical",
                    parameter="sepsis_first_antibiotic",
                    condition={"deadline_minutes": 180, "bundle_started_at": started},
                    value=round((now - started).total_seconds() / 60.0, 1),
                    patient_id=pid_str,
                    patient_doc=patient_doc,
                    device_id=device_id,
                    source_time=now,
                    explanation=explanation,
                    extra={
                        "bundle_started_at": started,
                        "deadline_1h": deadline_1h,
                        "deadline_3h": deadline_3h,
                        "elapsed_minutes": round((now - started).total_seconds() / 60.0, 1),
                        "source_rules": tracker.get("source_rules") or [],
                        "bundle_status": "overdue_3h",
                    },
                )
                if alert:
                    fired += 1
            await self.db.col("score_records").update_one(
                {"_id": tracker["_id"]},
                {
                    "$set": {
                        "status": "overdue_3h",
                        "overdue_3h_alerted": True,
                        "compliant_1h": False,
                        "is_active": False,
                        "resolved_at": now,
                        "calc_time": now,
                        "updated_at": now,
                    }
                },
            )
            return fired

        if now >= deadline_1h and not tracker.get("overdue_1h_alerted"):
            rule_id = "SEPSIS_ANTIBIOTIC_OVER_1H"
            if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                explanation = await self._build_sepsis_bundle_explanation(status="overdue_1h", tracker=tracker)
                alert = await self._create_alert(
                    rule_id=rule_id,
                    name="脓毒症首剂抗生素超1h未执行",
                    category="bundle",
                    alert_type="sepsis_abx_overdue_1h",
                    severity="critical",
                    parameter="sepsis_first_antibiotic",
                    condition={"deadline_minutes": 60, "bundle_started_at": started},
                    value=round((now - started).total_seconds() / 60.0, 1),
                    patient_id=pid_str,
                    patient_doc=patient_doc,
                    device_id=device_id,
                    source_time=now,
                    explanation=explanation,
                    extra={
                        "bundle_started_at": started,
                        "deadline_1h": deadline_1h,
                        "deadline_3h": deadline_3h,
                        "elapsed_minutes": round((now - started).total_seconds() / 60.0, 1),
                        "source_rules": tracker.get("source_rules") or [],
                        "bundle_status": "overdue_1h",
                    },
                )
                if alert:
                    fired += 1
            await self.db.col("score_records").update_one(
                {"_id": tracker["_id"]},
                {
                    "$set": {
                        "status": "overdue_1h",
                        "overdue_1h_alerted": True,
                        "compliant_1h": False,
                        "calc_time": now,
                        "updated_at": now,
                    }
                },
            )
        return fired

    async def scan_sepsis(self) -> None:
        from .sepsis_scanner import SepsisScanner

        await SepsisScanner(self).scan()
