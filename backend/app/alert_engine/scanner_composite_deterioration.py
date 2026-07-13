from __future__ import annotations

from fnmatch import fnmatch
from datetime import datetime, timedelta
from typing import Any
def _severity_weight(severity: str) -> int:
    return {"warning": 1, "high": 2, "critical": 3}.get(str(severity or "").lower(), 1)
from .scanners import BaseScanner, ScannerSpec


class CompositeDeteriorationScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="composite_deterioration",
                interval_key="composite_deterioration",
                default_interval=300,
                initial_delay=49,
            ),
        )

    async def scan(self) -> None:
        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        cfg = self.engine.config.yaml_cfg.get("alert_engine", {}).get("composite_deterioration", {})
        window_hours = float(cfg.get("window_hours", 4))
        organ_threshold = int(cfg.get("organ_threshold", 3))
        max_records = int(cfg.get("max_source_alerts", 300))
        min_alerts = int(cfg.get("min_alert_count", 3))
        ignore_categories = [str(x).lower() for x in cfg.get("ignore_categories", ["assessments", "ai_analysis", "composite_deterioration"])]
        ignore_types = [str(x).lower() for x in cfg.get("ignore_alert_types", ["nurse_reminder", "multi_organ_deterioration_trend"])]
        mapping = self.engine._resolve_organ_mapping(cfg)

        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
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

            alerts = await self.engine._recent_alerts(pid_str, since, max_records=max_records)
            temporal_record = await self.engine._latest_temporal_risk_record(pid_str, hours=max(int(window_hours * 2), 12)) if hasattr(self, "_latest_temporal_risk_record") else None
            temporal_forecast = None
            if temporal_record:
                temporal_org = temporal_record.get("organ_probabilities") if isinstance(temporal_record.get("organ_probabilities"), dict) else {}
                top_organs = [
                    str(k) for k, _ in
                    sorted(((str(k), float(v)) for k, v in temporal_org.items() if v is not None), key=lambda x: x[1], reverse=True)[:3]
                ]
                temporal_prediction_source = str(temporal_record.get("prediction_source") or "unknown")
                temporal_risk_value_type = str(temporal_record.get("risk_value_type") or "")
                temporal_risk_value = temporal_record.get("risk_value")

                # ---- 严格区分 prediction_source 的字段语义 ----
                # trained_model: current_probability / probability_4h / horizon_probabilities
                # rule_estimate: current_risk_score / risk_score_4h / future_risk_scores
                # unavailable / unknown: 不填定量概率，仅保留risk_value元数据
                is_trained = temporal_prediction_source == "trained_model"
                is_rule = temporal_prediction_source == "rule_estimate"
                temporal_enabled = bool(
                    (is_trained and isinstance(temporal_risk_value, (int, float)) and float(temporal_risk_value) >= 0.58)
                    or (is_rule and isinstance(temporal_risk_value, (int, float)) and float(temporal_risk_value) >= 0.58)
                )

                # 构建 temporal_signal（使用风险值，不混淆 score 和 probability）
                future_map = temporal_record.get("future_probabilities") or {}
                temporal_signal = {
                    "enabled": temporal_enabled,
                    "risk_level": str(temporal_record.get("risk_level") or "low"),
                    "organs": top_organs,
                    "contributors": [],
                    "prediction_source": temporal_prediction_source,
                    "risk_value_type": temporal_risk_value_type,
                }
                # trained_model → probability 语义
                if is_trained:
                    temporal_signal["probability_4h"] = float(
                        future_map.get("4") or future_map.get(4)
                        or (temporal_risk_value if temporal_risk_value is not None else 0.0)
                    )
                # rule_estimate → risk_score 语义（禁止用 score 回填 probability 字段）
                elif is_rule:
                    temporal_signal["risk_score_4h"] = float(
                        future_map.get("4") or future_map.get(4)
                        or (temporal_risk_value if temporal_risk_value is not None else 0.0)
                    )
                # unavailable/unknown → 不填定量概率

                temporal_forecast = {
                    "patient_id": pid_str,
                    "organ_risk_scores": temporal_org,
                    "composite_signal": temporal_signal,
                    "prediction_source": temporal_prediction_source,
                    "risk_value": temporal_risk_value,
                    "risk_value_type": temporal_risk_value_type,
                    "model_meta": {
                        "mode": "temporal_risk_scanner",
                        "backend": temporal_record.get("model_backend"),
                        "model_path": temporal_record.get("model_path"),
                        "prediction_source": temporal_prediction_source,
                        "model_name": temporal_record.get("model_name", ""),
                        "model_version": temporal_record.get("model_version", ""),
                        "model_status": temporal_record.get("model_status", ""),
                        "local_validation_status": temporal_record.get("local_validation_status", "not_applicable"),
                        "fallback_used": temporal_record.get("fallback_used", False),
                        "fallback_reason": temporal_record.get("fallback_reason", ""),
                        "risk_value_type": temporal_risk_value_type,
                    },
                }
                # 仅 trained_model 填概率字段
                if is_trained:
                    temporal_forecast["current_probability"] = temporal_risk_value
                    temporal_forecast["horizon_probabilities"] = temporal_record.get("future_probabilities")
                # 仅 rule_estimate 填风险分数字段（禁止用 score 回填 probability 字段）
                elif is_rule:
                    temporal_forecast["current_risk_score"] = temporal_risk_value
                    temporal_forecast["future_risk_scores"] = temporal_record.get("future_probabilities")
                # unavailable / unknown: 不填定量字段
            else:
                temporal_forecast = await self.engine._build_temporal_risk_forecast(
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
            relevant_alerts: list[dict] = []

            for a in alerts:
                category = str(a.get("category") or "").lower()
                alert_type = str(a.get("alert_type") or "").lower()
                if category in ignore_categories or alert_type in ignore_types:
                    continue

                organs = self.engine._map_alert_to_organs(a, mapping)
                if not organs:
                    continue
                sev_w = _severity_weight(str(a.get("severity") or "warning"))
                for organ in organs:
                    organ_counts[organ] += 1
                    if sev_w > organ_scores[organ]:
                        organ_scores[organ] = sev_w
                relevant_alerts.append(a)
                source_rows.append(
                    {
                        "alert_type": a.get("alert_type"),
                        "severity": a.get("severity"),
                        "time": a.get("created_at"),
                        "organs": organs,
                    }
                )

            if temporal_signal.get("enabled"):
                # 统一提取风险数值：trained_model 用 probability_4h，rule_estimate 用 risk_score_4h
                temporal_value = float(
                    temporal_signal.get("probability_4h")
                    or temporal_signal.get("risk_score_4h")
                    or temporal_forecast.get("risk_value")
                    or 0.0
                )
                temporal_risk_level = str(temporal_signal.get("risk_level") or "warning").lower()
                temporal_severity = "critical" if temporal_risk_level == "critical" else "high"
                temporal_organs = [
                    organ for organ in (temporal_signal.get("organs") or [])
                    if organ in organ_scores
                ]
                for organ in temporal_organs[:2]:
                    organ_counts[organ] += 1
                    organ_scores[organ] = max(organ_scores[organ], _severity_weight(temporal_severity))
                # 源行标记风险值及其类型
                source_row_entry: dict = {
                    "alert_type": "temporal_risk_forecast",
                    "severity": temporal_severity,
                    "time": now,
                    "organs": temporal_organs[:2],
                    "contributors": temporal_signal.get("contributors") or [],
                    "prediction_source": temporal_signal.get("prediction_source", ""),
                    "risk_value_type": temporal_signal.get("risk_value_type", ""),
                }
                # 仅 trained_model 填 probability 语义，rule_estimate 填 risk_score 语义
                if temporal_signal.get("prediction_source") == "trained_model":
                    source_row_entry["probability_4h"] = round(temporal_value, 4)
                elif temporal_signal.get("prediction_source") == "rule_estimate":
                    source_row_entry["risk_score_4h"] = round(temporal_value, 4)
                source_rows.append(source_row_entry)

            if len(source_rows) < min_alerts:
                continue

            involved_organs = [k for k, v in organ_scores.items() if v > 0]
            if len(involved_organs) < organ_threshold:
                continue

            modi = int(sum(organ_scores.values()))
            rule_id = "COMPOSITE_MODI_CRITICAL"
            if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                continue
            grouped_alerts = self.engine._aggregate_alert_groups(relevant_alerts)
            clinical_chain = self.engine._match_clinical_chain(relevant_alerts, organ_scores, temporal_signal if isinstance(temporal_signal, dict) else None)
            explanation = None
            if clinical_chain:
                explanation = {
                    "summary": clinical_chain.get("summary"),
                    "evidence": clinical_chain.get("evidence") or [],
                    "suggestion": clinical_chain.get("suggestion"),
                }

            alert = await self.engine._create_alert(
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
                    "clinical_chain": clinical_chain,
                    "aggregated_groups": grouped_alerts,
                    "organ_labels_cn": {
                        "respiratory": "呼吸",
                        "circulatory": "循环",
                        "renal": "肾脏",
                        "coagulation": "凝血",
                        "hepatic": "肝脏",
                        "neurologic": "神经",
                    },
                },
                explanation=explanation,
            )
            if alert:
                triggered += 1

        if triggered > 0:
            self.engine._log_info("多器官恶化", triggered)
