from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import Any


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except Exception:
        return None


from .scanners import BaseScanner, ScannerSpec


class VentilatorWeaningScanner(BaseScanner):
    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="ventilator",
                interval_key="ventilator",
                default_interval=3600,
                initial_delay=40,
            ),
        )

    async def scan(self) -> None:
        now = datetime.now()

        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {"_id": 1, "name": 1, "hisPid": 1, "hisBed": 1, "dept": 1, "hisDept": 1, "height": 1, "heightCm": 1, "gender": 1, "hisSex": 1, "weight": 1, "bodyWeight": 1, "weightKg": 1, "weight_kg": 1},
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        suppression = self.engine.config.yaml_cfg.get("alert_engine", {}).get("suppression", {})
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))

        post_cfg = self.engine._weaning_cfg()
        extub_hours = int(post_cfg.get("extubation_monitor_hours", 48))
        triggered = 0
        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)

            active_vent_bind = await self.engine._get_active_vent_bind(pid_str)
            device_id = active_vent_bind.get("deviceID") if active_vent_bind else await self.engine._get_device_id_for_patient(patient_doc, ["vent"])
            cap = await self.engine._get_latest_device_cap(device_id) if device_id else None

            if active_vent_bind and cap:
                risk = await self.engine._build_weaning_recommendation(patient_doc=patient_doc, pid_str=pid_str, cap=cap, now=now)
                if risk:
                    await self.engine._persist_weaning_assessment(
                        pid_str=pid_str,
                        patient_doc=patient_doc,
                        now=now,
                        assessment=risk,
                    )
                    sbt = (risk.get("extra") or {}).get("previous_sbt")
                    if isinstance(sbt, dict):
                        await self.engine._persist_sbt_assessment(
                            pid_str=pid_str,
                            patient_doc=patient_doc,
                            now=now,
                            sbt=sbt,
                        )
                    rule_id = risk["rule_id"]
                    if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self.engine._create_alert(
                            rule_id=rule_id,
                            name=risk["name"],
                            category="ventilator",
                            alert_type="weaning",
                            severity=risk["severity"],
                            parameter="weaning_failure_score",
                            condition={"recommendation": risk["recommendation"], "risk_level": risk["risk_level"]},
                            value=risk["risk_score"],
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=device_id,
                            source_time=cap.get("time"),
                            extra=risk["extra"],
                            explanation=risk["explanation"],
                        )
                        if alert:
                            triggered += 1

                fio2_codes = await self._vent_concept_codes("fio2", ["param_FiO2"])
                peep_codes = await self._vent_concept_codes("peep_measured", ["param_vent_measure_peep"]) + await self._vent_concept_codes("peep_set", ["param_vent_peep"])
                pip_codes = await self._vent_concept_codes("pip", ["param_vent_pip"])
                pplat_codes = await self._vent_concept_codes("pplat", ["param_vent_plat_pressure"])
                fio2 = self._snapshot_first(cap, fio2_codes)
                peep = self._snapshot_first(cap, peep_codes)
                pip = self._snapshot_first(cap, pip_codes)
                pplat = self._snapshot_first(cap, pplat_codes)
                pc_codes = await self._vent_concept_codes("pressure_control", ["param_vent_pc"])
                ps_codes = await self._vent_concept_codes("pressure_support", ["param_vent_ps"])
                pc_above_peep = self._snapshot_first(cap, pc_codes + ps_codes)
                vte_codes = await self._vent_concept_codes("vte", ["param_vent_vt"]) + await self._vent_concept_codes("vt_set", ["param_vent_set_vt"])
                rr_codes = await self._vent_concept_codes("rr_measured", ["param_vent_resp"]) + await self._vent_concept_codes("rr_set", ["param_HuXiPinLv"])
                vte = self._snapshot_first(cap, vte_codes)
                rr = self._snapshot_first(cap, rr_codes)
                mode = await self._vent_mode(device_id, cap)

                driving_pressure = None
                approximate = False
                if pplat is not None and peep is not None:
                    driving_pressure = pplat - peep
                elif pip is not None and peep is not None:
                    driving_pressure = pip - peep
                    approximate = True

                if driving_pressure is not None and driving_pressure > 15:
                    rule_id = "VENT_DRIVING_PRESSURE"
                    if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self.engine._create_alert(
                            rule_id=rule_id,
                            name="驱动压偏高",
                            category="ventilator",
                            alert_type="driving_pressure",
                            severity="critical" if driving_pressure > 18 else "warning",
                            parameter="driving_pressure",
                            condition={"operator": ">", "threshold": 15},
                            value=round(driving_pressure, 1),
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=device_id,
                            source_time=cap.get("time"),
                            extra={"pplat": pplat, "pip": pip, "peep": peep, "approximate": approximate},
                        )
                        if alert:
                            triggered += 1

                if pplat is not None and pplat > 30:
                    rule_id = "VENT_PPLAT_HIGH"
                    if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        alert = await self.engine._create_alert(
                            rule_id=rule_id,
                            name="平台压升高",
                            category="ventilator",
                            alert_type="pplat_high",
                            severity="critical",
                            parameter="pplat",
                            condition={"operator": ">", "threshold": 30},
                            value=round(pplat, 1),
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=device_id,
                            source_time=cap.get("time"),
                            extra={"recommendation": "考虑降低潮气量或评估胸壁顺应性"},
                        )
                        if alert:
                            triggered += 1

                pbw = self.engine._predicted_body_weight(patient_doc)
                if vte is not None and pbw and pbw > 0:
                    vt_ml_kg = vte / pbw
                    if vt_ml_kg > 8:
                        rule_id = "VENT_LUNG_PROTECTIVE"
                        if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                            alert = await self.engine._create_alert(
                                rule_id=rule_id,
                                name="肺保护性通气未达标",
                                category="ventilator",
                                alert_type="lung_protective_ventilation",
                                severity="warning",
                                parameter="vt_ml_kg_pbw",
                                condition={"operator": ">", "threshold": 8},
                                value=round(vt_ml_kg, 2),
                                patient_id=pid_str,
                                patient_doc=patient_doc,
                                device_id=device_id,
                                source_time=cap.get("time"),
                                extra={"vte_ml": vte, "predicted_body_weight": pbw},
                            )
                            if alert:
                                triggered += 1

                mp = self._mechanical_power(
                    mode=mode,
                    rr=rr,
                    vte_ml=vte,
                    peep=peep,
                    pip=pip,
                    pplat=pplat,
                    pc_above_peep=pc_above_peep,
                    pbw=pbw,
                )
                if mp and mp["mechanical_power_j_min"] is not None:
                    mech_power = float(mp["mechanical_power_j_min"])
                    mp_per_pbw = _to_float(mp.get("mechanical_power_j_min_kg_pbw"))
                    mp_threshold = float(post_cfg.get("mechanical_power_threshold_j_min", 17))
                    mp_kg_threshold = float(post_cfg.get("mechanical_power_pbw_threshold_j_min_kg", 0.25))
                    if mech_power > mp_threshold or (mp_per_pbw is not None and mp_per_pbw > mp_kg_threshold):
                        rule_id = "VENT_MECHANICAL_POWER"
                        if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                            alert = await self.engine._create_alert(
                                rule_id=rule_id,
                                name="机械功率升高",
                                category="ventilator",
                                alert_type="mechanical_power",
                                severity="high",
                                parameter="mechanical_power",
                                condition={"operator": ">", "threshold": mp_threshold, "pbw_threshold": mp_kg_threshold},
                                value=round(mech_power, 2),
                                patient_id=pid_str,
                                patient_doc=patient_doc,
                                device_id=device_id,
                                source_time=cap.get("time"),
                                extra=mp,
                            )
                            if alert:
                                triggered += 1

            recent_extubation = await self.engine._get_recent_extubation_bind(pid_str, now, hours=extub_hours)
            if recent_extubation and not active_vent_bind:
                extub_time = _parse_dt(recent_extubation.get("unBindTime"))
                vitals = await self.engine._get_latest_vitals_by_patient(pid)
                rr_now = vitals.get("rr") if isinstance(vitals, dict) else None
                spo2_now = vitals.get("spo2") if isinstance(vitals, dict) else None
                accessory = await self.engine._get_accessory_muscle_sign(pid, now, hours=12)
                if rr_now is not None and float(rr_now) > float(post_cfg.get("post_extub_rr_threshold", 30)) and spo2_now is not None and float(spo2_now) < float(post_cfg.get("post_extub_spo2_threshold", 92)):
                    severity = "critical" if accessory else "high"
                    rule_id = "VENT_POST_EXTUBATION_FAILURE_RISK"
                    if not await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
                        evidence_factors = [
                            {"factor": "tachypnea", "weight": 1, "evidence": f"RR {rr_now} 次/分"},
                            {"factor": "hypoxemia", "weight": 1, "evidence": f"SpO₂ {spo2_now}%"},
                        ]
                        if accessory:
                            evidence_factors.append({"factor": "accessory_muscle_use", "weight": 1, "evidence": "存在辅助呼吸肌动用"})
                        explanation = await self.engine._polish_structured_alert_explanation(
                            {
                                "summary": "拔管后48h内出现呼吸恶化信号，存在再插管/NIV 风险。",
                                "evidence": [str(x.get("evidence") or "") for x in evidence_factors],
                                "suggestion": "建议立即评估血气、分泌物负荷与上气道通畅性，尽早决定 NIV/HFNC 或再插管。",
                                "text": "",
                            }
                        )
                        alert = await self.engine._create_alert(
                            rule_id=rule_id,
                            name="拔管后呼吸衰竭风险",
                            category="ventilator",
                            alert_type="post_extubation_failure_risk",
                            severity=severity,
                            parameter="post_extubation_resp_failure",
                            condition={"rr_threshold": 30, "spo2_threshold": 92, "extubation_window_h": extub_hours},
                            value=round(float(rr_now), 1),
                            patient_id=pid_str,
                            patient_doc=patient_doc,
                            device_id=None,
                            source_time=extub_time or now,
                            extra={
                                "extubation_time": extub_time,
                                "hours_since_extubation": round(max(0.0, ((now - extub_time).total_seconds() / 3600.0)) if isinstance(extub_time, datetime) else 0.0, 2),
                                "rr": rr_now,
                                "spo2": spo2_now,
                                "accessory_muscle_use": bool(accessory),
                                "accessory_muscle_record": accessory,
                                "factors": evidence_factors,
                            },
                            explanation=explanation,
                        )
                        if alert:
                            triggered += 1

        if triggered > 0:
            self.engine._log_info("撤机筛查", triggered)

    async def _vent_mode(self, device_id: str | None, cap: dict[str, Any]) -> str:
        params = cap.get("params") if isinstance(cap.get("params"), dict) else {}
        text = " ".join(
            str(value or "")
            for value in (
                cap.get("mode"),
                cap.get("vent_mode"),
                cap.get("param_vent_mode"),
                params.get("param_vent_mode"),
                params.get("vent_mode"),
            )
        ).lower()
        if not text.strip() and device_id:
            text = (await self._latest_vent_mode_text(device_id)).lower()
        return self._classify_vent_mode(text)

    async def _latest_vent_mode_text(self, device_id: str) -> str:
        codes = await self._vent_concept_codes("vent_mode", ["param_HuXiMoShi", "param_vent_mode"])
        cursor = self.engine.db.col("deviceCap").find(
            {"deviceID": str(device_id), "code": {"$in": codes}},
            {"time": 1, "code": 1, "strVal": 1, "value": 1, "fVal": 1, "intVal": 1},
        ).sort("time", -1).limit(20)
        async for doc in cursor:
            for key in ("strVal", "value", "fVal", "intVal"):
                value = doc.get(key)
                if value not in (None, ""):
                    return str(value)
        return ""

    async def _vent_concept_codes(self, concept: str, defaults: list[str]) -> list[str]:
        names = [concept]
        yaml_defaults = []
        if concept == "vent_mode":
            names.extend(["mode"])
            yaml_keys = [("vent_mode", "param_HuXiMoShi"), ("mode", "param_vent_mode")]
        elif concept == "pressure_control":
            yaml_keys = [("pressure_control", "param_vent_pc")]
        elif concept == "pressure_support":
            yaml_keys = [("pressure_support", "param_vent_ps")]
        else:
            yaml_keys = []
        for name, default in yaml_keys:
            try:
                code = self.engine._vent_code(name, default)
            except Exception:
                code = default
            if code:
                yaml_defaults.append(str(code))
        fallback = list(dict.fromkeys([*yaml_defaults, *defaults]))
        if hasattr(self.engine, "_field_mapping_codes"):
            return await self.engine._field_mapping_codes(
                module="respiratory",
                concepts=names,
                source_names=["deviceCap"],
                defaults=fallback,
            )
        return fallback

    def _snapshot_first(self, cap: dict[str, Any], codes: list[str]) -> float | None:
        params = cap.get("params") if isinstance(cap.get("params"), dict) else cap
        for code in codes:
            value = _to_float(params.get(code))
            if value is not None:
                return value
        return None

    def _classify_vent_mode(self, text: str) -> str:
        text = str(text or "").lower()
        if any(token in text for token in ("psv", "pressure support", "压力支持", "spont")):
            return "PSV"
        if any(token in text for token in ("pcv", "pressure control", "压力控制")):
            return "PCV"
        if any(token in text for token in ("vcv", "volume control", "容量控制", "assist control", "a/c", "acv")):
            return "VCV"
        return "unknown"

    def _mechanical_power(
        self,
        *,
        mode: str,
        rr: float | None,
        vte_ml: float | None,
        peep: float | None,
        pip: float | None,
        pplat: float | None,
        pc_above_peep: float | None,
        pbw: float | None,
    ) -> dict[str, Any] | None:
        if rr is None or vte_ml is None or peep is None or vte_ml <= 0:
            return None
        vt_l = float(vte_ml) / 1000.0
        rr_f = float(rr)
        peep_f = float(peep)
        mode_norm = str(mode or "unknown").upper()
        approximate = False
        formula = ""
        elastic_component = None
        dynamic_component = None
        peep_component = 0.098 * rr_f * vt_l * peep_f

        if mode_norm == "VCV":
            pressure_ref = _to_float(pplat) if pplat is not None else _to_float(pip)
            if pressure_ref is None:
                return None
            drive = max(float(pressure_ref) - peep_f, 0.0)
            dynamic_component = 0.098 * rr_f * vt_l * (0.5 * drive)
            elastic_component = dynamic_component
            mechanical_power = peep_component + dynamic_component
            formula = "VCV: 0.098*RR*VT*(PEEP + 0.5*driving_pressure)"
            approximate = pplat is None
        elif mode_norm == "PCV":
            pressure_control = _to_float(pc_above_peep)
            if pressure_control is None and pip is not None:
                pressure_control = max(float(pip) - peep_f, 0.0)
                approximate = True
            if pressure_control is None:
                return None
            dynamic_component = 0.098 * rr_f * vt_l * float(pressure_control)
            elastic_component = dynamic_component
            mechanical_power = peep_component + dynamic_component
            formula = "PCV: 0.098*RR*VT*(PEEP + pressure_control_above_PEEP)"
        elif mode_norm == "PSV":
            pressure_support = _to_float(pc_above_peep)
            if pressure_support is None and pip is not None:
                pressure_support = max(float(pip) - peep_f, 0.0)
                approximate = True
            if pressure_support is None:
                return None
            dynamic_component = 0.098 * rr_f * vt_l * float(pressure_support)
            elastic_component = dynamic_component
            mechanical_power = peep_component + dynamic_component
            formula = "PSV: 0.098*RR*VT*(PEEP + pressure_support_above_PEEP)"
        else:
            if pip is None:
                return None
            drive = max(float(pip) - peep_f, 0.0)
            dynamic_component = 0.098 * rr_f * vt_l * (0.5 * drive)
            elastic_component = dynamic_component
            mechanical_power = peep_component + dynamic_component
            formula = "surrogate: mode_unknown, 0.098*RR*VT*(PEEP + 0.5*(PIP-PEEP))"
            approximate = True

        mp_kg = round(mechanical_power / float(pbw), 4) if pbw and pbw > 0 else None
        return {
            "mode": mode_norm,
            "formula": formula,
            "approximate": approximate,
            "rr": rr,
            "vte_ml": vte_ml,
            "vt_l": round(vt_l, 3),
            "pip": pip,
            "pplat": pplat,
            "peep": peep,
            "pressure_control_or_support": pc_above_peep,
            "predicted_body_weight": pbw,
            "mechanical_power_j_min": round(mechanical_power, 2),
            "mechanical_power_j_min_kg_pbw": mp_kg,
            "components": {
                "peep_static_j_min": round(peep_component, 2),
                "driving_or_support_j_min": round(dynamic_component or 0.0, 2),
                "elastic_dynamic_j_min": round(elastic_component or 0.0, 2),
            },
            "clinical_hint": "请结合通气模式解读；PSV/PCV 使用压力支持/压力控制近似，重点看 MP/PBW 与驱动压共同变化。",
        }
