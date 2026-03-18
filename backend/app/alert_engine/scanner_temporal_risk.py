from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any
import numpy as np
from .scanners import BaseScanner, ScannerSpec


class TemporalRiskScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="temporal_risk_scanner",
                interval_key="temporal_risk_scanner",
                default_interval=900,
                initial_delay=28,
            ),
        )

    async def scan(self) -> None:
        cfg = self.engine._temporal_scanner_cfg()
        lookback_hours = int(cfg.get("lookback_hours", 12))
        grid_minutes = int(cfg.get("grid_minutes", 5))
        horizons = tuple(int(x) for x in (cfg.get("horizons_hours", [4, 12, 24]) or [4, 12, 24]))
        organ_keys = [str(x) for x in (cfg.get("organ_keys", ["respiratory", "circulatory", "renal", "neurologic"]) or [])]
        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "deptCode": 1, "gender": 1, "age": 1, "icuAdmissionTime": 1},
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        suppression = self.engine._cfg("alert_engine", "suppression", default={}) or {}
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        triggered = 0
        now = datetime.now()

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            try:
                sequence, meta_features, context = await self.engine._prepare_temporal_input(
                    patient_doc=patient_doc,
                    pid=pid,
                    lookback_hours=lookback_hours,
                    grid_minutes=grid_minutes,
                )
                result = await asyncio.to_thread(
                    self.engine._get_temporal_model_runtime().predict,
                    sequence=sequence,
                    meta_features=meta_features,
                    organ_keys=organ_keys,
                    horizons=horizons,
                )
            except Exception:
                continue

            if not isinstance(result, dict):
                continue
            probability = float(result.get("probability") or 0.0)
            organ_probabilities = result.get("organ_probabilities") if isinstance(result.get("organ_probabilities"), dict) else {}
            future_probabilities = result.get("future_probabilities") if isinstance(result.get("future_probabilities"), dict) else {}
            payload = {
                "patient_id": pid_str,
                "patient_name": patient_doc.get("name"),
                "bed": patient_doc.get("hisBed"),
                "dept": patient_doc.get("dept") or patient_doc.get("hisDept"),
                "score_type": "temporal_risk_scanner",
                "score": round(probability, 4),
                "risk_level": self.engine._risk_level_from_probability(probability),
                "organ_probabilities": {str(k): round(float(v), 4) for k, v in organ_probabilities.items() if v is not None},
                "future_probabilities": {str(k): round(float(v), 4) for k, v in future_probabilities.items() if v is not None},
                "sequence_shape": list(sequence.shape),
                "input_context": context,
                "model_backend": result.get("backend"),
                "model_path": result.get("model_path"),
                "model_available": bool(result.get("available")),
                "calc_time": now,
                "updated_at": now,
                "month": now.strftime("%Y-%m"),
                "day": now.strftime("%Y-%m-%d"),
            }
            latest = await self.engine.db.col("score_records").find_one(
                {"patient_id": pid_str, "score_type": "temporal_risk_scanner"},
                sort=[("calc_time", -1)],
            )
            if latest:
                await self.engine.db.col("score_records").update_one({"_id": latest["_id"]}, {"$set": payload})
            else:
                payload["created_at"] = now
                await self.engine.db.col("score_records").insert_one(payload)

            prob_4h = float(future_probabilities.get(4) or future_probabilities.get("4") or probability)
            severity = self.engine._risk_level_from_probability(prob_4h)
            if severity not in {"warning", "high", "critical"}:
                continue
            rule_id = f"TEMPORAL_RISK_{severity.upper()}"
            if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                continue
            organ_rank = sorted(
                [(str(k), float(v)) for k, v in organ_probabilities.items() if v is not None],
                key=lambda x: x[1],
                reverse=True,
            )
            top_organs = [name for name, _ in organ_rank[:3]]
            alert = await self.engine._create_alert(
                rule_id=rule_id,
                name="时序模型恶化风险预警",
                category="temporal_model",
                alert_type="temporal_deterioration_risk",
                severity=severity,
                parameter="temporal_probability_4h",
                condition={
                    "lookback_hours": lookback_hours,
                    "grid_minutes": grid_minutes,
                    "horizons": list(horizons),
                },
                value=round(prob_4h, 4),
                patient_id=pid_str,
                patient_doc=patient_doc,
                source_time=now,
                extra={
                    "probability": round(probability, 4),
                    "probability_4h": round(prob_4h, 4),
                    "future_probabilities": payload["future_probabilities"],
                    "organ_probabilities": payload["organ_probabilities"],
                    "top_organs": top_organs,
                    "input_context": context,
                    "runtime": {
                        "available": bool(result.get("available")),
                        "backend": result.get("backend"),
                        "model_path": result.get("model_path"),
                        "reason": result.get("reason"),
                    },
                },
            )
            if alert:
                triggered += 1

        if triggered > 0:
            self.engine._log_info("时序风险扫描", triggered)
