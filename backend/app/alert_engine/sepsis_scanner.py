"""脓毒症筛查扫描器 v2。

三层架构：
  A 层：感染证据 + 器官功能异常 → 筛查检出
  B 层：休克/低灌注评估 → 条件项目触发
  C 层：风险因素 → 个体化建议

qSOFA 不能单独作为确诊依据，也不能单独触发完整治疗 Bundle。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.utils.clinical import _extract_param

from .scanners import BaseScanner, ScannerSpec

logger = logging.getLogger(__name__)


class SepsisScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="sepsis",
                interval_key="sepsis",
                default_interval=300,
                initial_delay=15,
                maturity="validated",
            ),
        )

    async def scan(self) -> None:
        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1,
             "clinicalDiagnosis": 1, "admissionDiagnosis": 1},
        )
        patients = [patient async for patient in patient_cursor]
        if not patients:
            return

        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        triggered = 0
        now = datetime.now()

        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)
            his_pid = patient_doc.get("hisPid")

            # ---- 生命体征 ----
            device_id = await self.engine._get_device_id_for_patient(patient_doc, ["monitor"])
            gcs = await self.engine._get_latest_assessment(pid, "gcs")
            cap_codes = ["param_resp", "param_nibp_s", "param_ibp_s", "param_nibp_m", "param_ibp_m"]
            latest_cap = await self.engine._get_latest_param_snapshot_by_pid(pid, codes=cap_codes)
            if not latest_cap and device_id:
                latest_cap = await self.engine._get_latest_device_cap(device_id, codes=cap_codes)
            if not latest_cap:
                continue

            sbp = self.engine._get_sbp(latest_cap)
            rr = _extract_param(latest_cap, "param_resp")
            map_value = self.engine._get_map(latest_cap)

            # ---- qSOFA ----
            qsofa = self.engine._calc_qsofa(sbp, rr, gcs)
            qsofa_triggered = qsofa >= 2

            # ---- SOFA ----
            sofa = await self.engine._calc_sofa(patient_doc, pid, device_id, his_pid)
            sofa_triggered = False
            if sofa:
                delta = sofa["delta"]
                sofa_triggered = delta >= 2 and (sofa.get("baseline_available") or qsofa_triggered)

            # ---- 感染证据评估 ----
            infection = await self.engine._assess_infection_evidence(
                patient_doc=patient_doc,
                pid_str=pid_str,
                his_pid=his_pid,
                now=now,
            )
            infection_verdict = str(infection.get("verdict") or "unknown")

            # ---- qSOFA 预警（筛查工具，不得称"疑似脓毒症"） ----
            if qsofa_triggered:
                if not await self.engine._is_suppressed(pid_str, "SEPSIS_QSOFA", same_rule_sec, max_per_hour):
                    # qSOFA≥2 是床旁筛查工具，阳性不能直接诊断为脓毒症
                    alert = await self.engine._create_alert(
                        rule_id="SEPSIS_QSOFA",
                        name="qSOFA≥2筛查阳性",
                        category="syndrome",
                        alert_type="qsofa",
                        severity="warning",
                        parameter="qsofa",
                        condition={"qsofa": qsofa, "infection_verdict": infection_verdict},
                        value=qsofa,
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        device_id=device_id,
                        source_time=now,
                        extra={
                            "sbp": sbp, "rr": rr, "gcs": gcs,
                            "infection_evidence": infection,
                            "clinical_note": "qSOFA≥2仅表示存在感染高危风险，不等于脓毒症诊断，需结合临床评估",
                        },
                    )
                    if alert:
                        triggered += 1
                        # qSOFA 单独阳性不生成脓毒症结论，只写入证据
                        await self._bridge_qsofa_evidence(
                            patient_doc, pid_str, alert, qsofa, sbp, rr, gcs, infection_verdict,
                        )

            # ---- SOFA 预警（不可称"脓毒症确认"） ----
            if sofa_triggered:
                if not await self.engine._is_suppressed(pid_str, "SEPSIS_SOFA", same_rule_sec, max_per_hour):
                    # SOFA Δ≥2 表示器官功能恶化，非脓毒症确诊
                    alert = await self.engine._create_alert(
                        rule_id="SEPSIS_SOFA",
                        name="SOFA Δ≥2 器官功能恶化",
                        category="syndrome",
                        alert_type="sofa",
                        severity="high",
                        parameter="sofa",
                        condition={"delta": delta, "score": sofa["score"], "infection_verdict": infection_verdict},
                        value=sofa["score"],
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        device_id=device_id,
                        source_time=now,
                        extra={
                            **sofa,
                            "infection_evidence": infection,
                            "clinical_note": "SOFA Δ≥2表示器官功能恶化，不等同于脓毒症确诊，需临床综合判断",
                        },
                    )
                    if alert:
                        triggered += 1
                        # 只有感染支持时才生成脓毒症病例
                        if infection_verdict in ("supported", "possible"):
                            await self._bridge_sepsis_case(
                                patient_doc, pid_str, alert, "SEPSIS_SOFA",
                                evidence_features=[{
                                    "source_record_id": f"{pid_str}_sofa",
                                    "feature_name": "sofa_delta",
                                    "raw_value": delta,
                                    "raw_unit": "score",
                                    "metadata": {"sofa_score": sofa["score"], "infection_verdict": infection_verdict},
                                }],
                                conclusion_code="SEPSIS_SCREEN_POSITIVE",
                                conclusion_label="脓毒症筛查阳性",
                                infection_verdict=infection_verdict,
                            )
                        else:
                            # 感染不支持，只写入器官功能异常证据
                            await self._bridge_organ_dysfunction(
                                patient_doc, pid_str, alert, delta, sofa, infection_verdict,
                            )

            # ---- 脓毒症筛查下的休克/低灌注评估（必须结合感染证据） ----
            lactate_value = None
            if sofa and isinstance(sofa.get("labs"), dict):
                lac_entry = sofa["labs"].get("lac")
                if isinstance(lac_entry, dict):
                    lactate_value = lac_entry.get("value")
                else:
                    lactate_value = lac_entry

            vasopressor_active = await self.engine._has_vasopressor(pid)

            if vasopressor_active and lactate_value is not None and lactate_value >= 2:
                infection_supported = infection_verdict in ("supported", "possible")
                shock_rule_id = "SEPSIS_SHOCK" if infection_supported else "SHOCK_HYPOPERFUSION_SCREEN"
                shock_name = (
                    "可能脓毒性休克表型，需临床确认"
                    if infection_supported
                    else "休克/低灌注筛查阳性"
                )
                shock_category = "syndrome" if infection_supported else "vital_signs"
                shock_alert_type = "septic_shock" if infection_supported else "shock_hypoperfusion_screen"
                shock_severity = "critical" if infection_supported else "high"

                if not await self.engine._is_suppressed(pid_str, shock_rule_id, same_rule_sec, max_per_hour):
                    alert = await self.engine._create_alert(
                        rule_id=shock_rule_id,
                        name=shock_name,
                        category=shock_category,
                        alert_type=shock_alert_type,
                        severity=shock_severity,
                        parameter="shock",
                        condition={
                            "vasopressor": True,
                            "lactate": lactate_value,
                            "map": map_value,
                            "infection_verdict": infection_verdict,
                            "map_caveat": "使用升压药时MAP可能>65，但休克仍可能存在",
                        },
                        value=lactate_value,
                        patient_id=pid_str,
                        patient_doc=patient_doc,
                        device_id=device_id,
                        source_time=now,
                        extra={
                            "sofa": sofa,
                            "vasopressor_active": True,
                            "map_on_vasopressor": map_value,
                            "volume_status": "unknown",
                            "other_causes_excluded": "unknown",
                            "requires_clinician_confirmation": True,
                            "infection_verdict": infection_verdict,
                            "infection_evidence": infection,
                        },
                    )
                    if alert:
                        triggered += 1
                        if infection_supported:
                            await self._bridge_sepsis_case(
                                patient_doc, pid_str, alert, shock_rule_id,
                                evidence_features=[
                                    {
                                        "source_record_id": f"{pid_str}_lactate",
                                        "feature_name": "lactate",
                                        "raw_value": lactate_value,
                                        "raw_unit": "mmol/L",
                                        "metadata": {"vasopressor": True, "map": map_value, "infection_verdict": infection_verdict},
                                    },
                                ],
                                conclusion_code="SEPTIC_SHOCK_SCREEN",
                                conclusion_label="可能脓毒性休克表型，待临床确认",
                                infection_verdict=infection_verdict,
                            )

            # ---- 休克/低灌注评估 ----
            shock = await self.engine._assess_shock_hypoperfusion(
                patient_doc=patient_doc,
                pid_str=pid_str,
                his_pid=his_pid,
                sbp=sbp,
                map_value=map_value,
                lactate_value=lactate_value,
                sofa=sofa,
                infection_verdict=infection_verdict,
                now=now,
            )

            # ---- 液体复苏风险因素评估 ----
            risk = await self.engine._assess_fluid_risk_factors(
                patient_doc=patient_doc,
                pid_str=pid_str,
                his_pid=his_pid,
                now=now,
            )

            # ---- Bundle Tracker（v2 三层） ----
            tracker = await self.engine._start_or_refresh_sepsis_bundle_tracker_v2(
                patient_doc=patient_doc,
                pid_str=pid_str,
                now=now,
                infection=infection,
                qsofa_triggered=qsofa_triggered,
                qsofa=qsofa,
                sbp=sbp,
                rr=rr,
                gcs=gcs,
                sofa_triggered=sofa_triggered,
                sofa=sofa,
                shock=shock,
                risk=risk,
            )
            if not tracker:
                tracker = await self.engine._get_active_sepsis_bundle_tracker(pid_str)

            triggered += await self.engine._evaluate_sepsis_bundle_tracker_v2(
                tracker=tracker,
                patient_doc=patient_doc,
                pid_str=pid_str,
                his_pid=his_pid,
                device_id=device_id,
                now=now,
                same_rule_sec=same_rule_sec,
                max_per_hour=max_per_hour,
            )

        if triggered > 0:
            self.engine._log_info("脓毒症预警", triggered)

    async def _bridge_qsofa_evidence(
        self, patient_doc: dict, pid_str: str, alert: dict,
        qsofa: int, sbp: float, rr: float, gcs: float,
        infection_verdict: str,
    ) -> None:
        """qSOFA 单独阳性：只写入风险证据，不生成脓毒症结论。"""
        try:
            from app.services.disease_case_bridge import (
                add_or_update_evidence,
                upsert_case_from_scanner,
                ALERT_TO_CASE_RISK,
            )

            alert_id = str(alert.get("_id", ""))
            severity = alert.get("severity", "warning")

            case = await upsert_case_from_scanner(
                patient_id=pid_str,
                disease_code="SEPSIS",
                disease_name="脓毒症",
                encounter_id=pid_str,
                patient_name=patient_doc.get("name", ""),
                bed=patient_doc.get("hisBed", ""),
                dept=patient_doc.get("dept", ""),
                scanner_id="sepsis",
                rule_id="SEPSIS_QSOFA",
                rule_version="Sepsis_v2",
                risk_level=ALERT_TO_CASE_RISK.get(severity, "warning"),
                screening_score=float(qsofa),
                source_alert_id=alert_id,
            )
            if not case:
                return

            case_id = str(case["id"])

            # 写入 qSOFA 证据
            await add_or_update_evidence(
                case_id=case_id,
                patient_id=pid_str,
                disease_code="SEPSIS",
                evidence_type="clinical_score",
                feature_name="qsofa",
                raw_value=qsofa,
                raw_unit="score",
                observed_at=datetime.now(timezone.utc),
                source_collection="vital_signs",
                source_record_id=f"{pid_str}_qsofa_{alert_id}",
                source_field="qsofa",
                rule_id="SEPSIS_QSOFA",
                rule_version="Sepsis_v2",
                matched=True,
                confidence=1.0,
                explanation=f"qSOFA={qsofa}（SBP={sbp}, RR={rr}, GCS={gcs}），感染证据: {infection_verdict}",
            )

            # 不调用 mark_screen_positive，不生成脓毒症结论
            # qSOFA 单独阳性只是风险提示

        except Exception as e:
            logger.error("qSOFA bridge failed: %s", e, exc_info=True)

    async def _bridge_organ_dysfunction(
        self, patient_doc: dict, pid_str: str, alert: dict,
        delta: float, sofa: dict, infection_verdict: str,
    ) -> None:
        """SOFA 升高但感染不支持：只写入器官功能异常证据。"""
        try:
            from app.services.disease_case_bridge import (
                add_or_update_evidence,
                upsert_case_from_scanner,
                ALERT_TO_CASE_RISK,
            )

            alert_id = str(alert.get("_id", ""))
            severity = alert.get("severity", "high")

            case = await upsert_case_from_scanner(
                patient_id=pid_str,
                disease_code="SEPSIS",
                disease_name="脓毒症",
                encounter_id=pid_str,
                patient_name=patient_doc.get("name", ""),
                bed=patient_doc.get("hisBed", ""),
                dept=patient_doc.get("dept", ""),
                scanner_id="sepsis",
                rule_id="SEPSIS_SOFA",
                rule_version="Sepsis_v2",
                risk_level=ALERT_TO_CASE_RISK.get(severity, "warning"),
                screening_score=sofa.get("score"),
                source_alert_id=alert_id,
            )
            if not case:
                return

            case_id = str(case["id"])

            await add_or_update_evidence(
                case_id=case_id,
                patient_id=pid_str,
                disease_code="SEPSIS",
                evidence_type="clinical_score",
                feature_name="sofa_delta",
                raw_value=delta,
                raw_unit="score",
                observed_at=datetime.now(timezone.utc),
                source_collection="clinical_assessment",
                source_record_id=f"{pid_str}_sofa_{alert_id}",
                source_field="sofa",
                rule_id="SEPSIS_SOFA",
                rule_version="Sepsis_v2",
                matched=True,
                confidence=1.0,
                explanation=f"SOFA Δ={delta}（总分={sofa.get('score')}），感染证据: {infection_verdict}。器官功能异常，非脓毒症确诊。",
            )

            # 不生成脓毒症结论，不进入 pending_review

        except Exception as e:
            logger.error("Organ dysfunction bridge failed: %s", e, exc_info=True)

    async def _bridge_sepsis_case(
        self, patient_doc: dict, pid_str: str, alert: dict,
        rule_id: str, evidence_features: list[dict],
        conclusion_code: str, conclusion_label: str,
        infection_verdict: str,
    ) -> None:
        """脓毒症筛查阳性或可能脓毒性休克：创建病例、证据、结论，进入 pending_review。"""
        try:
            from app.services.disease_case_bridge import (
                add_or_update_evidence,
                mark_screen_positive,
                upsert_case_from_scanner,
                add_conclusion,
                ALERT_TO_CASE_RISK,
            )

            alert_id = str(alert.get("_id", ""))
            severity = alert.get("severity", "warning")

            case = await upsert_case_from_scanner(
                patient_id=pid_str,
                disease_code="SEPSIS",
                disease_name="脓毒症",
                encounter_id=pid_str,
                patient_name=patient_doc.get("name", ""),
                bed=patient_doc.get("hisBed", ""),
                dept=patient_doc.get("dept", ""),
                scanner_id="sepsis",
                rule_id=rule_id,
                rule_version="Sepsis_v2",
                risk_level=ALERT_TO_CASE_RISK.get(severity, "warning"),
                screening_score=alert.get("value"),
                source_alert_id=alert_id,
            )
            if not case:
                return

            case_id = str(case["id"])

            # 写入证据
            evidence_ids: list[str] = []
            for feat in evidence_features:
                eid = await add_or_update_evidence(
                    case_id=case_id,
                    patient_id=pid_str,
                    disease_code="SEPSIS",
                    evidence_type=feat.get("evidence_type", "clinical_score"),
                    feature_name=feat["feature_name"],
                    raw_value=feat["raw_value"],
                    raw_unit=feat.get("raw_unit", ""),
                    observed_at=feat.get("observed_at") or datetime.now(timezone.utc),
                    source_collection=feat.get("source_collection", "vital_signs"),
                    source_record_id=feat["source_record_id"],
                    source_field=feat.get("source_field", ""),
                    rule_id=rule_id,
                    rule_version="Sepsis_v2",
                    matched=True,
                    confidence=1.0,
                    explanation=feat.get("explanation", ""),
                )
                evidence_ids.append(eid)

            # 添加结论
            await add_conclusion(
                case_id=case_id,
                patient_id=pid_str,
                conclusion_code=conclusion_code,
                conclusion_label=conclusion_label,
                conclusion_level="screening",
                supporting_evidence_ids=evidence_ids,
                rule_id=rule_id,
                rule_version="Sepsis_v2",
                confidence=0.7,
                detail={"infection_verdict": infection_verdict},
            )

            # 标记筛阳（会自动进入 pending_review）
            await mark_screen_positive(
                case_id=case_id,
                risk_level=ALERT_TO_CASE_RISK.get(severity, "warning"),
                screening_score=alert.get("value"),
                source_alert_id=alert_id,
            )

        except Exception as e:
            logger.error("Sepsis case bridge failed: %s", e, exc_info=True)
