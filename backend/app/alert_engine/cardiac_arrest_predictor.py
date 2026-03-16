"""心脏骤停风险预测。"""
from __future__ import annotations

from datetime import datetime, timedelta

from .base import _cap_time, _cap_value


class CardiacArrestPredictorMixin:
    async def _get_qrs_records(self, pid, hours: int = 48) -> list[dict]:
        pid_str = self._pid_str(pid)
        if not pid_str:
            return []
        since = datetime.now() - timedelta(hours=hours)
        cursor = self.db.col("bedside").find(
            {"pid": pid_str, "time": {"$gte": since}},
            {"time": 1, "code": 1, "strVal": 1, "intVal": 1, "fVal": 1, "value": 1},
        ).sort("time", 1).limit(400)

        rows: list[dict] = []
        async for doc in cursor:
            code = str(doc.get("code") or "").lower()
            if not any(key.lower() in code for key in ["param_QRS", "QRS", "qrs_duration"]):
                continue
            value = _cap_value(doc)
            t = _cap_time(doc)
            if value is None or not isinstance(t, datetime):
                continue
            rows.append({"time": t, "value": value, "code": doc.get("code")})
        return rows

    def _detect_brady_tachy_alternating(self, hr_series: list[dict]) -> tuple[bool, dict]:
        if not hr_series:
            return False, {"alternations": 0, "pattern": []}

        buckets: dict[datetime, list[float]] = {}
        for row in hr_series:
            t = row.get("time")
            v = row.get("value")
            if not isinstance(t, datetime) or v is None:
                continue
            bucket = t.replace(minute=(t.minute // 5) * 5, second=0, microsecond=0)
            buckets.setdefault(bucket, []).append(float(v))

        ordered = []
        for bucket, values in sorted(buckets.items(), key=lambda x: x[0]):
            states: list[str] = []
            if any(v < 50 for v in values):
                states.append("brady")
            if any(v > 120 for v in values):
                states.append("tachy")
            ordered.extend(states)

        compressed: list[str] = []
        for state in ordered:
            if not compressed or compressed[-1] != state:
                compressed.append(state)

        alternations = 0
        for idx in range(1, len(compressed)):
            if {compressed[idx - 1], compressed[idx]} == {"brady", "tachy"}:
                alternations += 1
        return alternations >= 2, {"alternations": alternations, "pattern": compressed[-8:]}

    async def scan_cardiac_arrest_risk(self) -> None:
        patient_cursor = self.db.col("patient").find(
            self._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "deptCode": 1},
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        cfg = self.config.yaml_cfg.get("alert_engine", {}).get("cardiac_arrest", {})
        weights = cfg.get("factor_weights", {}) if isinstance(cfg, dict) else {}
        warning_score = float(cfg.get("warning_score", 4))
        high_score = float(cfg.get("high_score", 6))
        critical_score = float(cfg.get("critical_score", 8))

        triggered = 0
        now = datetime.now()

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            his_pid = patient_doc.get("hisPid")
            device_id = await self._get_device_id_for_patient(patient_doc, ["monitor"])

            latest_cap = await self._get_latest_param_snapshot_by_pid(
                pid,
                codes=["param_HR", "param_nibp_s", "param_ibp_s", "param_nibp_m", "param_ibp_m"],
            )
            if not latest_cap and device_id:
                latest_cap = await self._get_latest_device_cap(
                    device_id,
                    codes=["param_HR", "param_nibp_s", "param_ibp_s", "param_nibp_m", "param_ibp_m"],
                )
            if latest_cap:
                latest_cap, _ = await self._filter_snapshot_quality(
                    pid=pid,
                    pid_str=pid_str,
                    patient_doc=patient_doc,
                    cap=latest_cap,
                    device_id=device_id,
                    same_rule_sec=same_rule_sec,
                    max_per_hour=max_per_hour,
                )

            hr_latest = self._get_priority_param(latest_cap or {}, ["param_HR"]) if latest_cap else None
            sbp_latest = self._get_sbp(latest_cap) if latest_cap else None
            map_latest = self._get_map(latest_cap) if latest_cap else None

            hr_series = await self._get_param_series_by_pid(
                pid,
                "param_HR",
                now - timedelta(hours=2),
                prefer_device_types=["monitor"],
                limit=500,
            )
            hr_series = self._filter_series_quality("param_HR", hr_series)
            qrs_records = await self._get_qrs_records(pid, hours=48)
            labs = await self._get_latest_labs_map(his_pid, lookback_hours=72) if his_pid else {}
            k_value = labs.get("k", {}).get("value") if labs else None
            ica_value = labs.get("ica", {}).get("value") if labs else None
            lac_series = await self._get_lab_series(his_pid, "lac", now - timedelta(hours=6), limit=40) if his_pid else []
            lac_latest = lac_series[-1]["value"] if lac_series else None

            score = 0.0
            factors: list[dict] = []

            def add_factor(key: str, matched: bool, evidence: str, default_weight: float) -> None:
                nonlocal score
                if not matched:
                    return
                w = float(weights.get(key, default_weight))
                score += w
                factors.append({"factor": key, "weight": w, "evidence": evidence})

            alternating, alternating_meta = self._detect_brady_tachy_alternating(hr_series)
            add_factor(
                "brady_tachy_alternating",
                alternating,
                f"2h内心率快慢交替 {alternating_meta.get('alternations', 0)} 次, pattern={alternating_meta.get('pattern')}",
                3,
            )

            add_factor(
                "extreme_bradycardia",
                hr_latest is not None and hr_latest < 40,
                f"最新HR={hr_latest}",
                3,
            )

            latest_qrs = qrs_records[-1] if qrs_records else None
            baseline_qrs = next((row for row in qrs_records if row["time"] <= now - timedelta(hours=24) and row["value"] <= 120), None)
            add_factor(
                "new_wide_qrs",
                bool(latest_qrs and latest_qrs["value"] > 120 and baseline_qrs),
                f"QRS {latest_qrs['value'] if latest_qrs else '—'} ms, 24h前={baseline_qrs['value'] if baseline_qrs else '—'} ms",
                2,
            )

            add_factor(
                "hyperkalemia",
                k_value is not None and k_value > 6.5,
                f"K⁺={k_value} mmol/L",
                4,
            )
            add_factor(
                "severe_hypokalemia",
                k_value is not None and k_value < 2.5,
                f"K⁺={k_value} mmol/L",
                3,
            )
            add_factor(
                "severe_hypocalcemia",
                ica_value is not None and ica_value < 0.8,
                f"iCa={ica_value} mmol/L",
                3,
            )

            lac_earliest = lac_series[0]["value"] if lac_series else None
            lac_doubled = bool(
                lac_latest is not None and lac_earliest not in (None, 0) and float(lac_latest) >= float(lac_earliest) * 2
            )
            add_factor(
                "lactate_surge_with_map_drop",
                lac_doubled and map_latest is not None and map_latest < 60,
                f"Lac {lac_earliest}->{lac_latest} mmol/L, MAP={map_latest}",
                3,
            )

            hr_recent = await self._get_param_series_by_pid(
                pid,
                "param_HR",
                now - timedelta(minutes=30),
                prefer_device_types=["monitor"],
                limit=120,
            )
            hr_recent = self._filter_series_quality("param_HR", hr_recent)
            sbp_recent = await self._get_param_series_by_pid(
                pid,
                "param_nibp_s",
                now - timedelta(minutes=30),
                prefer_device_types=["monitor"],
                limit=120,
            )
            sbp_recent = self._filter_series_quality("param_nibp_s", sbp_recent)
            if not sbp_recent:
                sbp_recent = await self._get_param_series_by_pid(
                    pid,
                    "param_ibp_s",
                    now - timedelta(minutes=30),
                    prefer_device_types=["monitor"],
                    limit=120,
                )
                sbp_recent = self._filter_series_quality("param_ibp_s", sbp_recent)
            sbp_recent_numeric = [float(x["value"]) for x in sbp_recent if x.get("value") is not None]
            persistent_low_sbp = len(sbp_recent_numeric) >= 2 and all(v < 60 for v in sbp_recent_numeric)
            add_factor(
                "pea_risk_pattern",
                bool(hr_recent and persistent_low_sbp),
                f"30min内HR存在({len(hr_recent)}点)且SBP持续<60, latest_sbp={sbp_latest}",
                2,
            )

            if score < warning_score:
                continue

            severity = "warning"
            if score >= critical_score:
                severity = "critical"
            elif score >= high_score:
                severity = "high"

            rule_id = f"CARDIAC_ARREST_RISK_{severity.upper()}"
            if await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                continue

            time_candidates = [
                latest_cap.get("time") if latest_cap else None,
                latest_qrs.get("time") if latest_qrs else None,
                labs.get("k", {}).get("time") if labs else None,
                labs.get("ica", {}).get("time") if labs else None,
                lac_series[-1]["time"] if lac_series else None,
            ]
            source_time = max([t for t in time_candidates if isinstance(t, datetime)] or [now])

            alert = await self._create_alert(
                rule_id=rule_id,
                name="心脏骤停风险预警",
                category="syndrome",
                alert_type="cardiac_arrest_risk",
                severity=severity,
                parameter="cardiac_arrest_score",
                condition={
                    "warning_score": warning_score,
                    "high_score": high_score,
                    "critical_score": critical_score,
                },
                value=round(score, 1),
                patient_id=pid_str,
                patient_doc=patient_doc,
                device_id=device_id,
                source_time=source_time,
                extra={
                    "factors": factors,
                    "hr": hr_latest,
                    "k": k_value,
                    "ica": ica_value,
                    "lac": lac_latest,
                    "map": map_latest,
                    "qrs_duration": latest_qrs["value"] if latest_qrs else None,
                    "snapshots": {
                        "hr": hr_latest,
                        "sbp": sbp_latest,
                        "map": map_latest,
                        "k": k_value,
                        "ica": ica_value,
                        "lac_latest": lac_latest,
                        "lac_baseline_6h": lac_earliest,
                        "qrs_duration": latest_qrs["value"] if latest_qrs else None,
                    },
                },
            )
            if alert:
                triggered += 1

        if triggered > 0:
            self._log_info("心脏骤停风险", triggered)
