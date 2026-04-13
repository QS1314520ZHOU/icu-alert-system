from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from .scanners import BaseScanner, ScannerSpec


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except Exception:
        return None


class BetaBlockerAdvisorScanner(BaseScanner):
    """脓毒症相关 β 受体阻滞剂辅助决策。"""

    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="beta_blocker_advisor",
                interval_key="beta_blocker_advisor",
                default_interval=3600,
                initial_delay=109,
            ),
        )

    def is_enabled(self) -> bool:
        return super().is_enabled() and bool(self._cfg().get("enabled", True))

    def interval_seconds(self) -> int:
        value = self._cfg().get("scan_interval")
        try:
            return max(300, int(value))
        except (TypeError, ValueError):
            return super().interval_seconds()

    def _cfg(self) -> dict[str, Any]:
        cfg = self.engine._cfg("alert_engine", "beta_blocker_advisor", default={}) or {}
        return cfg if isinstance(cfg, dict) else {}

    async def scan(self, patient_id: str | None = None) -> list[dict[str, Any]]:
        patients = await self._target_patients(patient_id)
        if not patients:
            return []
        suppression = self.engine._cfg("alert_engine", "suppression", default={}) or {}
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        now = datetime.now()
        alerts: list[dict[str, Any]] = []
        for patient_doc in patients:
            alerts.extend(await self._scan_patient(patient_doc=patient_doc, now=now, same_rule_sec=same_rule_sec, max_per_hour=max_per_hour))
        if alerts:
            self.engine._log_info("β阻滞剂辅助决策", len(alerts))
        return alerts

    async def _target_patients(self, patient_id: str | None) -> list[dict[str, Any]]:
        projection = {
            "_id": 1,
            "name": 1,
            "hisPid": 1,
            "hisBed": 1,
            "dept": 1,
            "hisDept": 1,
            "gender": 1,
            "hisSex": 1,
            "age": 1,
            "hisAge": 1,
            "clinicalDiagnosis": 1,
            "admissionDiagnosis": 1,
            "weight": 1,
            "bodyWeight": 1,
            "body_weight": 1,
            "weightKg": 1,
            "weight_kg": 1,
        }
        if patient_id:
            patient_doc, _ = await self.engine._load_patient(patient_id)
            return [patient_doc] if isinstance(patient_doc, dict) else []
        cursor = self.engine.db.col("patient").find(self.engine._active_patient_query(), projection)
        return [row async for row in cursor]

    async def _scan_patient(self, *, patient_doc: dict[str, Any], now: datetime, same_rule_sec: int, max_per_hour: int) -> list[dict[str, Any]]:
        patient_id = patient_doc.get("_id")
        if not patient_id:
            return []
        patient_id_str = str(patient_id)
        assessment = await self._build_assessment(patient_doc=patient_doc, patient_id=patient_id, now=now)
        record = await self._persist_assessment(patient_doc=patient_doc, assessment=assessment, now=now)
        assessment["record_id"] = record.get("_id")
        if assessment.get("contraindications"):
            return []
        severity = assessment.get("severity")
        if severity not in {"warning", "high"}:
            return []
        rule_id = "BETA_BLOCKER_ADVISOR_HIGH" if severity == "high" else "BETA_BLOCKER_ADVISOR_WARNING"
        if await self.engine._is_suppressed(patient_id_str, rule_id, same_rule_sec, max_per_hour):
            return []
        alert = await self.engine._create_alert(
            rule_id=rule_id,
            name=assessment.get("title"),
            category="hemodynamic",
            alert_type="beta_blocker_advisor",
            severity=severity,
            parameter="beta_blocker_candidate",
            condition={"sepsis_confirmed": assessment.get("sepsis_confirmed"), "tachycardia_sustained": assessment.get("tachycardia_sustained")},
            value=assessment.get("hr_latest"),
            patient_id=patient_id_str,
            patient_doc=patient_doc,
            device_id=None,
            source_time=now,
            explanation={
                "summary": assessment.get("summary"),
                "evidence": assessment.get("evidence") or [],
                "suggestion": assessment.get("suggestion"),
                "text": "",
            },
            extra={"detail": assessment},
        )
        return [alert] if alert else []

    async def _build_assessment(self, *, patient_doc: dict[str, Any], patient_id: Any, now: datetime) -> dict[str, Any]:
        cfg = self._cfg()
        patient_id_str = str(patient_id)
        his_pid = str(patient_doc.get("hisPid") or "").strip()
        sepsis_confirmed = await self._sepsis_confirmed(patient_id_str, now)
        hr_series = await self.engine._get_param_series_by_pid(patient_id, "param_HR", now - timedelta(hours=24), prefer_device_types=["monitor"], limit=1200)
        hr_values_2h = [float(row.get("value")) for row in hr_series if isinstance(row.get("time"), datetime) and row["time"] >= now - timedelta(hours=2) and row.get("value") is not None]
        hr_values_24h = [float(row.get("value")) for row in hr_series if row.get("value") is not None]
        hr_threshold = float(cfg.get("hr_threshold", 95) or 95)
        tachycardia_sustained = bool(hr_values_2h and len([value for value in hr_values_2h if value > hr_threshold]) >= max(2, int(len(hr_values_2h) * float(cfg.get("tachy_ratio", 0.8) or 0.8))))
        hr_latest = hr_values_2h[-1] if hr_values_2h else (hr_values_24h[-1] if hr_values_24h else None)

        labs = await self.engine._get_latest_labs_map(his_pid, lookback_hours=72) if his_pid else {}
        trop_value = _to_float(((labs.get("trop") or {}).get("value")) if isinstance(labs.get("trop"), dict) else None)
        bnp_value = _to_float(((labs.get("bnp") or {}).get("value")) if isinstance(labs.get("bnp"), dict) else None)
        myocardial_injury = bool((trop_value is not None and trop_value > float(cfg.get("troponin_upper_limit", 0.04) or 0.04)) or (bnp_value is not None and bnp_value > float(cfg.get("bnp_threshold", 300) or 300)))

        map_series = await self.engine._get_map_series(patient_id, now - timedelta(hours=4)) if hasattr(self.engine, "_get_map_series") else []
        map_values = [float(row.get("value")) for row in map_series if row.get("value") is not None]
        map_latest = map_values[-1] if map_values else None
        current_vasopressors = await self.engine._get_current_vasopressor_snapshot(patient_id, patient_doc, hours=8, max_items=4)
        nurse_cfg = self.engine.config.yaml_cfg.get("nurse_reminders", {}).get("early_mobility", {})
        norepi_keywords = nurse_cfg.get("norepi_keywords", ["去甲肾上腺素", "norepinephrine", "noradrenaline", "去甲"])
        weight_kg = self.engine._get_patient_weight(patient_doc)
        norepi_series = await self.engine._get_norepi_dose_series(patient_id_str, now, 8, norepi_keywords, weight_kg)
        norepi_latest = norepi_series[-1]["dose_ug_kg_min"] if norepi_series else None
        norepi_tapering = self.engine._is_series_tapering(norepi_series, float(cfg.get("norepi_taper_ratio", 0.1) or 0.1)) if norepi_series else False
        norepi_stable = bool(norepi_series and max(point["dose_ug_kg_min"] for point in norepi_series) <= float(cfg.get("norepi_threshold", 0.2) or 0.2))
        hemodynamic_stable = bool((map_latest is not None and map_latest >= float(cfg.get("map_threshold", 65) or 65)) or (norepi_latest is not None and norepi_latest <= float(cfg.get("norepi_threshold", 0.2) or 0.2) and norepi_stable))

        correctable_causes = await self._correctable_causes(patient_doc=patient_doc, patient_id=patient_id, now=now, map_latest=map_latest)
        contraindications = await self._contraindications(patient_doc=patient_doc, patient_id=patient_id, now=now, hr_values_24h=hr_values_24h)

        severity = None
        title = ""
        summary = ""
        suggestion = ""
        if sepsis_confirmed and tachycardia_sustained:
            severity = "warning"
            title = "持续窦性心动过速，建议评估β受体阻滞剂指征"
            summary = "脓毒症背景下持续心动过速，建议在排除可纠正原因后评估短效 β 受体阻滞剂指征。"
            suggestion = "请先排查低血容量、疼痛、发热与低氧等可纠正原因，再评估是否适合使用短效 β 受体阻滞剂。"
        if sepsis_confirmed and tachycardia_sustained and myocardial_injury and not correctable_causes and not contraindications:
            severity = "high"
            title = "脓毒症心肌损伤伴持续心动过速，建议考虑β受体阻滞剂"
            summary = "患者存在脓毒症、持续心动过速及心肌损伤标志物升高，符合 β 受体阻滞剂辅助决策高风险人群。"
            suggestion = "建议评估短效 β 受体阻滞剂（如艾司洛尔）适应证，并严密监测 MAP、心率和灌注指标。"
        if severity == "high" and hemodynamic_stable and norepi_tapering:
            start_low = float(cfg.get("esmolol_start_ug_kg_min", 25) or 25)
            start_high = float(cfg.get("esmolol_start_high_ug_kg_min", 50) or 50)
            target_low = int(cfg.get("target_hr_low", 80) or 80)
            target_high = int(cfg.get("target_hr_high", 94) or 94)
            summary = "患者已满足脓毒症心肌损伤伴持续心动过速且血流动力学相对稳定的场景，可进入 β 受体阻滞剂精细化评估。"
            suggestion = f"可考虑艾司洛尔 {int(start_low)}-{int(start_high)} μg/kg/min 起始，目标 HR {target_low}-{target_high} 次/分，并每 15-30 分钟复评 MAP、NE 剂量与末梢灌注。"

        evidence = []
        if sepsis_confirmed:
            evidence.append("近24h存在脓毒症相关告警")
        if hr_latest is not None:
            evidence.append(f"HR {round(hr_latest, 1)} bpm，2h 持续高于 {int(hr_threshold)}")
        if trop_value is not None:
            evidence.append(f"肌钙蛋白 {trop_value}")
        if bnp_value is not None:
            evidence.append(f"BNP {bnp_value}")
        if map_latest is not None:
            evidence.append(f"MAP {round(map_latest, 1)} mmHg")
        if norepi_latest is not None:
            evidence.append(f"NE {round(float(norepi_latest), 4)} μg/kg/min")
        if correctable_causes:
            evidence.append("可纠正原因：" + "、".join(correctable_causes))
        return {
            "sepsis_confirmed": sepsis_confirmed,
            "tachycardia_sustained": tachycardia_sustained,
            "hr_latest": round(hr_latest, 1) if hr_latest is not None else None,
            "myocardial_injury": myocardial_injury,
            "troponin": trop_value,
            "bnp": bnp_value,
            "hemodynamic_stable": hemodynamic_stable,
            "map_latest": map_latest,
            "norepi_latest_ug_kg_min": norepi_latest,
            "norepi_tapering": norepi_tapering,
            "current_vasopressors": current_vasopressors,
            "correctable_causes": correctable_causes,
            "contraindications": contraindications,
            "severity": severity,
            "title": title,
            "summary": summary,
            "suggestion": suggestion,
            "evidence": evidence[:6],
        }

    async def _sepsis_confirmed(self, patient_id: str, now: datetime) -> bool:
        since = now - timedelta(hours=24)
        alert = await self.engine.db.col("alert_records").find_one(
            {
                "patient_id": patient_id,
                "created_at": {"$gte": since},
                "$or": [
                    {"rule_id": {"$in": ["SEPSIS_QSOFA", "SEPSIS_SOFA", "SEPSIS_SHOCK"]}},
                    {"alert_type": {"$in": ["qsofa", "sofa", "septic_shock"]}},
                ],
            },
            sort=[("created_at", -1)],
        )
        return bool(alert)

    async def _correctable_causes(self, *, patient_doc: dict[str, Any], patient_id: Any, now: datetime, map_latest: float | None) -> list[str]:
        cfg = self._cfg()
        reasons: list[str] = []
        temp_snapshot = await self.engine._get_latest_param_snapshot_by_pid(patient_id, codes=["param_T"], lookback_minutes=180)
        temp = _to_float(((temp_snapshot or {}).get("params") or {}).get("param_T"))
        if temp is not None and temp >= float(cfg.get("fever_threshold", 38.3) or 38.3):
            reasons.append("发热")
        cpot = await self.engine._get_latest_assessment(patient_id, "cpot")
        bps = await self.engine._get_latest_assessment(patient_id, "bps")
        if (cpot is not None and cpot >= float(cfg.get("cpot_threshold", 3) or 3)) or (bps is not None and bps >= float(cfg.get("bps_threshold", 5) or 5)):
            reasons.append("疼痛未充分控制")
        cursor = self.engine.db.col("alert_records").find(
            {"patient_id": str(patient_id), "created_at": {"$gte": now - timedelta(hours=12)}},
            {"alert_type": 1, "rule_id": 1, "name": 1},
        ).sort("created_at", -1).limit(30)
        recent_alerts = [row async for row in cursor]
        if any(str(row.get("alert_type") or "") in {"gi_bleeding", "active_bleeding_risk", "fluid_responsiveness"} for row in recent_alerts):
            reasons.append("低血容量/失血待排查")
        if map_latest is not None and map_latest < float(cfg.get("map_threshold", 65) or 65):
            reasons.append("灌注尚未完全稳定")
        return reasons

    async def _contraindications(self, *, patient_doc: dict[str, Any], patient_id: Any, now: datetime, hr_values_24h: list[float]) -> list[str]:
        cfg = self._cfg()
        reasons: list[str] = []
        diagnosis_blob = " ".join(str(patient_doc.get(key) or "") for key in ("clinicalDiagnosis", "admissionDiagnosis")).lower()
        if any(keyword in diagnosis_blob for keyword in [str(item).lower() for item in cfg.get("bronchospasm_keywords", ["哮喘", "支气管痉挛", "bronchospasm", "asthma"]) if str(item).strip()]):
            reasons.append("活动性支气管痉挛/哮喘")
        if hr_values_24h and min(hr_values_24h) < float(cfg.get("brady_history_threshold", 60) or 60):
            reasons.append("24h 内曾出现 HR < 60 bpm")
        av_block_events = await self.engine._get_recent_text_events(patient_id, cfg.get("av_block_keywords", ["二度房室传导阻滞", "三度房室传导阻滞", "av block", "ii度房室"]), hours=24, limit=200)
        if av_block_events:
            reasons.append("存在房室传导阻滞线索")
        ci_series = await self.engine._get_param_series_by_pid(patient_id, str(cfg.get("cardiac_index_code", "param_ci")), now - timedelta(hours=24), prefer_device_types=["monitor"], limit=200)
        ci_values = [_to_float(item.get("value")) for item in ci_series]
        ci_values = [float(value) for value in ci_values if value is not None]
        if ci_values and min(ci_values) < float(cfg.get("cardiac_index_threshold", 2.0) or 2.0):
            reasons.append("心源性休克/CI 过低")
        docs = await self.engine._get_recent_drug_docs_window(patient_id, hours=24, limit=200)
        ccb_keywords = [str(item).lower() for item in cfg.get("ccb_keywords", ["地尔硫卓", "维拉帕米", "diltiazem", "verapamil"]) if str(item).strip()]
        text_blob = " ".join(" ".join(str(doc.get(key) or "") for key in ("drugName", "orderName", "drugSpec")).lower() for doc in docs)
        if any(keyword in text_blob for keyword in ccb_keywords):
            reasons.append("当前使用非二氢吡啶类钙拮抗剂")
        return reasons

    async def _persist_assessment(self, *, patient_doc: dict[str, Any], assessment: dict[str, Any], now: datetime) -> dict[str, Any]:
        patient_id_str = str(patient_doc.get("_id") or "")
        doc = {
            "patient_id": patient_id_str,
            "patient_name": patient_doc.get("name") or "",
            "bed": patient_doc.get("hisBed") or "",
            "dept": patient_doc.get("dept") or patient_doc.get("hisDept") or "",
            "score_type": "beta_blocker_advisor",
            "assessment": assessment,
            "severity": assessment.get("severity"),
            "summary": assessment.get("summary"),
            "calc_time": now,
            "updated_at": now,
            "month": now.strftime("%Y-%m"),
            "day": now.strftime("%Y-%m-%d"),
        }
        result = await self.engine.db.col("score").insert_one(doc)
        doc["_id"] = result.inserted_id
        await self.engine.db.col("patient").update_one(
            {"_id": patient_doc.get("_id")},
            {
                "$set": {
                    "current_profile.beta_blocker_advisor": {
                        "severity": assessment.get("severity"),
                        "summary": assessment.get("summary"),
                        "contraindications": assessment.get("contraindications") or [],
                        "updated_at": now,
                        "record_id": result.inserted_id,
                    }
                }
            },
        )
        return doc
