"""多器官恶化趋势（MODI）"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def _severity_weight(severity: str) -> int:
    return {"warning": 1, "high": 2, "critical": 3}.get(str(severity or "").lower(), 1)


class CompositeDeteriorationMixin:
    def _contains_any(self, text: str, keywords: list[str]) -> bool:
        t = str(text or "").lower()
        return any(str(k).strip().lower() in t for k in keywords if str(k).strip())

    def _organ_mapping_defaults(self) -> dict[str, dict[str, list[str]]]:
        return {
            "respiratory": {
                "alert_types": ["ards", "weaning", "opioid_respiratory_depression"],
                "categories": ["ventilator"],
                "parameters": ["param_resp", "param_spo2", "pao2", "oxygen", "fio2", "peep"],
                "keywords": ["呼吸", "氧", "spo2", "p/f", "呼吸机", "af/a", "resp"],
            },
            "circulatory": {
                "alert_types": ["septic_shock", "qsofa", "sofa", "brady_hypotension", "af_afl_new_onset"],
                "categories": ["vital_signs"],
                "parameters": ["param_ibp_m", "param_nibp_m", "param_ibp_s", "param_nibp_s", "map", "sbp", "hr", "shock"],
                "keywords": ["循环", "休克", "低血压", "心动过缓", "房颤", "房扑", "map", "sbp"],
            },
            "renal": {
                "alert_types": ["aki", "nephrotoxicity", "fluid_balance"],
                "categories": [],
                "parameters": ["cr", "creatinine", "urine", "尿", "renal"],
                "keywords": ["肾", "肌酐", "尿量", "液体平衡", "renal", "aki"],
            },
            "coagulation": {
                "alert_types": ["dic", "hit", "gi_bleeding"],
                "categories": [],
                "parameters": ["plt", "inr", "pt", "fib", "ddimer", "coag"],
                "keywords": ["凝血", "血小板", "d-dimer", "出血", "coag"],
            },
            "hepatic": {
                "alert_types": [],
                "categories": [],
                "parameters": ["bil", "bilirubin", "tbil", "liver", "hepatic"],
                "keywords": ["肝", "胆红素", "liver", "hepatic"],
            },
            "neurologic": {
                "alert_types": ["pupil", "tbi", "icp", "cpp", "gcs_drop", "delirium_risk", "sedation_delirium_conversion"],
                "categories": ["tbi"],
                "parameters": ["gcs", "rass", "icp", "cpp", "pupil", "neuro"],
                "keywords": ["神经", "意识", "谵妄", "瞳孔", "颅脑", "neuro", "gcs", "rass"],
            },
        }

    def _resolve_organ_mapping(self, cfg: dict) -> dict[str, dict[str, list[str]]]:
        defaults = self._organ_mapping_defaults()
        mapping_cfg = cfg.get("organ_mapping", {}) if isinstance(cfg, dict) else {}
        if not isinstance(mapping_cfg, dict):
            return defaults
        merged: dict[str, dict[str, list[str]]] = {}
        for organ, d in defaults.items():
            user = mapping_cfg.get(organ, {})
            if not isinstance(user, dict):
                user = {}
            merged[organ] = {
                "alert_types": user.get("alert_types", d.get("alert_types", [])),
                "categories": user.get("categories", d.get("categories", [])),
                "parameters": user.get("parameters", d.get("parameters", [])),
                "keywords": user.get("keywords", d.get("keywords", [])),
            }
        return merged

    def _map_alert_to_organs(self, alert_doc: dict, mapping: dict[str, dict[str, list[str]]]) -> list[str]:
        category = str(alert_doc.get("category") or "").lower()
        alert_type = str(alert_doc.get("alert_type") or "").lower()
        parameter = str(alert_doc.get("parameter") or "").lower()
        name = str(alert_doc.get("name") or "").lower()
        rule_id = str(alert_doc.get("rule_id") or "").lower()
        text = " ".join([category, alert_type, parameter, name, rule_id])

        organs: list[str] = []
        for organ, conf in mapping.items():
            types = [str(x).lower() for x in conf.get("alert_types", [])]
            cats = [str(x).lower() for x in conf.get("categories", [])]
            params = [str(x).lower() for x in conf.get("parameters", [])]
            kws = [str(x).lower() for x in conf.get("keywords", [])]

            matched = False
            if alert_type and alert_type in types:
                matched = True
            if (not matched) and category and category in cats:
                matched = True
            if (not matched) and parameter and any(p in parameter for p in params):
                matched = True
            if (not matched) and self._contains_any(text, kws):
                matched = True

            if matched:
                organs.append(organ)
        return organs

    async def _recent_alerts(self, patient_id: str, since: datetime, max_records: int) -> list[dict]:
        cursor = self.db.col("alert_records").find(
            {"patient_id": patient_id, "created_at": {"$gte": since}},
            {
                "_id": 1,
                "rule_id": 1,
                "name": 1,
                "category": 1,
                "alert_type": 1,
                "parameter": 1,
                "severity": 1,
                "value": 1,
                "created_at": 1,
                "extra": 1,
            },
        ).sort("created_at", -1).limit(max_records)
        return [doc async for doc in cursor]

    async def scan_composite_deterioration(self) -> None:
        suppression = self.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        cfg = self.config.yaml_cfg.get("alert_engine", {}).get("composite_deterioration", {})
        window_hours = float(cfg.get("window_hours", 4))
        organ_threshold = int(cfg.get("organ_threshold", 3))
        max_records = int(cfg.get("max_source_alerts", 300))
        min_alerts = int(cfg.get("min_alert_count", 3))
        ignore_categories = [str(x).lower() for x in cfg.get("ignore_categories", ["assessments", "ai_analysis", "composite_deterioration"])]
        ignore_types = [str(x).lower() for x in cfg.get("ignore_alert_types", ["nurse_reminder", "multi_organ_deterioration_trend"])]
        mapping = self._resolve_organ_mapping(cfg)

        patient_cursor = self.db.col("patient").find(
            self._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "deptCode": 1},
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        now = datetime.now()
        since = now - timedelta(hours=max(1.0, window_hours))
        triggered = 0

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)

            alerts = await self._recent_alerts(pid_str, since, max_records=max_records)
            temporal_forecast = await self._build_temporal_risk_forecast(
                patient_doc,
                pid,
                lookback_hours=max(int(window_hours * 2), 12),
                horizons=(4, 8, 12),
                include_history=False,
            )
            temporal_signal = temporal_forecast.get("composite_signal") if isinstance(temporal_forecast, dict) else {}
            if len(alerts) < min_alerts and not temporal_signal.get("enabled"):
                continue

            organ_scores: dict[str, int] = {k: 0 for k in mapping.keys()}
            organ_counts: dict[str, int] = {k: 0 for k in mapping.keys()}
            source_rows: list[dict] = []

            for a in alerts:
                category = str(a.get("category") or "").lower()
                alert_type = str(a.get("alert_type") or "").lower()
                if category in ignore_categories or alert_type in ignore_types:
                    continue

                organs = self._map_alert_to_organs(a, mapping)
                if not organs:
                    continue
                sev_w = _severity_weight(str(a.get("severity") or "warning"))
                for organ in organs:
                    organ_counts[organ] += 1
                    if sev_w > organ_scores[organ]:
                        organ_scores[organ] = sev_w
                source_rows.append(
                    {
                        "alert_type": a.get("alert_type"),
                        "severity": a.get("severity"),
                        "time": a.get("created_at"),
                        "organs": organs,
                    }
                )

            if temporal_signal.get("enabled"):
                temporal_prob = float(temporal_signal.get("probability_4h") or 0.0)
                temporal_risk_level = str(temporal_signal.get("risk_level") or "warning").lower()
                temporal_severity = "critical" if temporal_risk_level == "critical" else "high"
                temporal_organs = [
                    organ for organ in (temporal_signal.get("organs") or [])
                    if organ in organ_scores
                ]
                for organ in temporal_organs[:2]:
                    organ_counts[organ] += 1
                    organ_scores[organ] = max(organ_scores[organ], _severity_weight(temporal_severity))
                source_rows.append(
                    {
                        "alert_type": "temporal_risk_forecast",
                        "severity": temporal_severity,
                        "time": now,
                        "organs": temporal_organs[:2],
                        "probability_4h": round(temporal_prob, 4),
                        "contributors": temporal_signal.get("contributors") or [],
                    }
                )

            if len(source_rows) < min_alerts:
                continue

            involved_organs = [k for k, v in organ_scores.items() if v > 0]
            if len(involved_organs) < organ_threshold:
                continue

            modi = int(sum(organ_scores.values()))
            rule_id = "COMPOSITE_MODI_CRITICAL"
            if await self._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                continue

            alert = await self._create_alert(
                rule_id=rule_id,
                name="多器官恶化趋势(MODI)",
                category="composite_deterioration",
                alert_type="multi_organ_deterioration_trend",
                severity="critical",
                parameter="modi",
                condition={
                    "window_hours": window_hours,
                    "organ_threshold_gte": organ_threshold,
                    "min_alert_count": min_alerts,
                },
                value=modi,
                patient_id=pid_str,
                patient_doc=patient_doc,
                device_id=None,
                source_time=now,
                extra={
                    "modi": modi,
                    "window_hours": window_hours,
                    "organ_count": len(involved_organs),
                    "involved_organs": involved_organs,
                    "organ_scores": organ_scores,
                    "organ_alert_counts": organ_counts,
                    "source_alert_count": len(source_rows),
                    "source_alerts": source_rows[:80],
                    "temporal_risk_signal": temporal_forecast if temporal_signal.get("enabled") else None,
                    "organ_labels_cn": {
                        "respiratory": "呼吸",
                        "circulatory": "循环",
                        "renal": "肾脏",
                        "coagulation": "凝血",
                        "hepatic": "肝脏",
                        "neurologic": "神经",
                    },
                },
            )
            if alert:
                triggered += 1

        if triggered > 0:
            self._log_info("多器官恶化", triggered)
