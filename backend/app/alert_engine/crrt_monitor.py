"""CRRT 监测。"""
from __future__ import annotations

from datetime import datetime, timedelta

from .base import _detect_trend


class CrrtMonitorMixin:
    async def _get_crrt_runtime_hours(self, pid) -> float | None:
        pid_str = self._pid_str(pid)
        if not pid_str:
            return None
        doc = await self.db.col("deviceBind").find_one(
            {"pid": pid_str, "unBindTime": None, "type": {"$in": ["crrt", "CRRT"]}},
            sort=[("bindTime", -1)],
        )
        if not doc:
            return None
        bind_time = doc.get("bindTime")
        if not isinstance(bind_time, datetime):
            return None
        return round((datetime.now() - bind_time).total_seconds() / 3600.0, 1)

    async def _get_crrt_param_series(self, pid, codes: list[str], hours: int = 8) -> list[dict]:
        since = datetime.now() - timedelta(hours=hours)
        points = []
        for code in codes:
            series = await self._get_param_series_by_pid(pid, code, since, prefer_device_types=["crrt"], limit=400)
            for row in series:
                points.append({**row, "code": code})
        points.sort(key=lambda x: x["time"])
        return points

    async def scan_crrt_monitor(self) -> None:
        patient_cursor = self.db.col("patient").find(
            self._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "weight": 1, "weightKg": 1},
        )
        patients = [p async for p in patient_cursor]
        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        triggered = 0

        tmp_codes = ["param_crrt_tmp", "TMP", "crrt_tmp", "param_TMP"]
        pre_codes = ["param_crrt_pre_pressure", "filter_pre_pressure"]
        post_codes = ["param_crrt_post_pressure", "filter_post_pressure"]
        return_codes = ["param_crrt_return_pressure", "return_pressure"]
        effluent_codes = ["param_crrt_effluent_rate", "effluent_rate", "param_effluent"]

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            his_pid = patient_doc.get("hisPid")
            if not pid:
                continue
            device_id = await self._get_device_id_for_patient(patient_doc, ["crrt"])
            if not device_id:
                continue
            pid_str = str(pid)

            tmp_series = await self._get_crrt_param_series(pid, tmp_codes, hours=8)
            if tmp_series:
                vals = [x["value"] for x in tmp_series]
                trend = _detect_trend(vals, window=min(6, len(vals)))
                latest = vals[-1]
                if latest > 250 or trend.get("slope", 0) > 10:
                    rule_id = "CRRT_FILTER_CLOTTING"
                    if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self._create_alert(
                            rule_id=rule_id,
                            name="CRRT管路凝堵风险",
                            category="crrt",
                            alert_type="crrt_filter_clotting",
                            severity="high" if latest <= 280 else "critical",
                            parameter="TMP",
                            condition={"slope_gt_mmHg_h": 10, "tmp_gt": 250},
                            value=latest,
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=device_id,
                            source_time=tmp_series[-1]["time"],
                            extra={"trend": trend, "tmp_latest": latest},
                        )
                        if alert:
                            triggered += 1

            labs = await self._get_latest_labs_map(his_pid, lookback_hours=12) if his_pid else {}
            ica = labs.get("ica", {}).get("value") if labs else None
            total_ca = labs.get("ca", {}).get("value") if labs else None
            act = labs.get("act", {}).get("value") if labs else None
            drugs = await self._get_recent_drugs(pid, hours=24)
            citrate = any("枸橼酸" in d for d in drugs)
            heparin = any("肝素" in d for d in drugs)
            runtime_hours = await self._get_crrt_runtime_hours(pid)

            if runtime_hours is not None and runtime_hours >= 24:
                rule_id = "CRRT_FILTER_RUNTIME_LONG"
                if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self._create_alert(
                        rule_id=rule_id,
                        name="CRRT滤器/管路使用时长偏长",
                        category="crrt",
                        alert_type="crrt_filter_runtime",
                        severity="warning" if runtime_hours < 48 else "high",
                        parameter="filter_runtime",
                        condition={"runtime_warn_h": 24, "runtime_high_h": 48},
                        value=runtime_hours,
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        device_id=device_id,
                        source_time=datetime.now(),
                        extra={"runtime_hours": runtime_hours},
                    )
                    if alert:
                        triggered += 1

            if citrate and ica is not None and (ica < 0.9 or ica > 1.3):
                rule_id = "CRRT_CITRATE_ICA"
                if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self._create_alert(
                        rule_id=rule_id,
                        name="CRRT枸橼酸抗凝 iCa 偏离目标",
                        category="crrt",
                        alert_type="crrt_citrate_ica",
                        severity="high",
                        parameter="iCa",
                        condition={"target_low": 0.9, "target_high": 1.3},
                        value=ica,
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        device_id=device_id,
                        source_time=labs.get("ica", {}).get("time"),
                        extra={"anticoagulation": "citrate", "iCa": ica},
                    )
                    if alert:
                        triggered += 1

            if citrate and total_ca is not None and ica not in (None, 0):
                ca_ratio = round(float(total_ca) / float(ica), 2)
                if ca_ratio > 2.5:
                    rule_id = "CRRT_CITRATE_ACCUMULATION"
                    if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self._create_alert(
                            rule_id=rule_id,
                            name="CRRT枸橼酸蓄积风险",
                            category="crrt",
                            alert_type="crrt_citrate_accumulation",
                            severity="high",
                            parameter="ca_total_ion_ratio",
                            condition={"operator": ">", "threshold": 2.5},
                            value=ca_ratio,
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=device_id,
                            source_time=labs.get("ca", {}).get("time") or labs.get("ica", {}).get("time"),
                            extra={"ca_total": total_ca, "iCa": ica, "ratio": ca_ratio},
                        )
                        if alert:
                            triggered += 1

            if heparin and act is not None and (act < 180 or act > 220):
                rule_id = "CRRT_HEPARIN_ACT"
                if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                    alert = await self._create_alert(
                        rule_id=rule_id,
                        name="CRRT肝素抗凝 ACT 偏离目标",
                        category="crrt",
                        alert_type="crrt_heparin_act",
                        severity="warning",
                        parameter="ACT",
                        condition={"target_low": 180, "target_high": 220},
                        value=act,
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        device_id=device_id,
                        source_time=labs.get("act", {}).get("time"),
                        extra={"anticoagulation": "heparin", "ACT": act},
                    )
                    if alert:
                        triggered += 1

            effluent_series = await self._get_crrt_param_series(pid, effluent_codes, hours=8)
            weight = self._get_patient_weight(patient_doc)
            if effluent_series and weight:
                recent_6h = [x for x in effluent_series if (datetime.now() - x["time"]).total_seconds() <= 6 * 3600]
                latest_eff = effluent_series[-1]["value"]
                dose = latest_eff / weight if weight > 0 else None
                low_dose_sustained = bool(recent_6h) and all((x["value"] / weight) < 20 for x in recent_6h)
                if dose is not None and dose < 20 and low_dose_sustained:
                    rule_id = "CRRT_DOSE_INADEQUATE"
                    if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self._create_alert(
                            rule_id=rule_id,
                            name="CRRT剂量不足",
                            category="crrt",
                            alert_type="crrt_dose_low",
                            severity="warning",
                            parameter="effluent_dose",
                            condition={"operator": "<", "threshold": 20},
                            value=round(dose, 1),
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=device_id,
                            source_time=effluent_series[-1]["time"],
                            extra={
                                "effluent_rate": latest_eff,
                                "dose_ml_kg_h": round(dose, 1),
                                "low_dose_sustained_6h": low_dose_sustained,
                                "recent_points_6h": len(recent_6h),
                            },
                        )
                        if alert:
                            triggered += 1

            if labs:
                stale_fields = []
                for key in ("ica", "k", "mg", "po4"):
                    t = labs.get(key, {}).get("time")
                    if isinstance(t, datetime) and (datetime.now() - t).total_seconds() > 6 * 3600:
                        stale_fields.append(key)
                    elif t is None:
                        stale_fields.append(key)
                if stale_fields:
                    rule_id = "CRRT_ELECTROLYTE_RECHECK"
                    if not await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self._create_alert(
                            rule_id=rule_id,
                            name="CRRT运行中电解质复查提醒",
                            category="crrt",
                            alert_type="crrt_electrolyte_recheck",
                            severity="warning",
                            parameter="electrolyte_recheck",
                            condition={"max_interval_h": 6, "fields": stale_fields},
                            value=len(stale_fields),
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=device_id,
                            source_time=datetime.now(),
                            extra={"stale_fields": stale_fields},
                        )
                        if alert:
                            triggered += 1

        if triggered > 0:
            self._log_info("CRRT监测", triggered)
