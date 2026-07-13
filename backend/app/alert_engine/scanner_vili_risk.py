"""
呼吸机相关肺损伤风险扫描器。

检测可能导致呼吸机相关肺损伤的高风险通气模式:
- 双触发 (double triggering) 导致潮气量叠加
- 高潮气量 (VTe/PBW > 8 mL/kg)
- 高驱动压 (driving pressure > 15 cmH2O)
- 高平台压 (plateau pressure > 30 cmH2O)

重要约束:
- 本扫描器独立于 ARDS 氧合筛查，不修改 ARDS oxygenation_grade
- 告警名称使用"肺保护通气偏离风险"，不表达为已发生 VILI
- VTe/PBW 仅在身高/PBW 输入可靠时计算，不使用默认体重
- 通过 clinical_episode_id 与 ARDS 筛查关联
- 建议文案提示复核双触发原因和肺保护参数后个体化调整
"""
from __future__ import annotations

import math
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
    except (TypeError, ValueError):
        return None


def _format_number(value: object, digits: int = 1) -> str:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "-"
    if not math.isfinite(num):
        return "-"
    rounded = round(num, digits)
    if digits <= 0 or abs(rounded - round(rounded)) < 1e-9:
        return str(int(round(rounded)))
    return f"{rounded:.{digits}f}".rstrip("0").rstrip(".")


class ViliRiskScanner(BaseScanner):
    """呼吸机相关肺损伤风险扫描器。"""

    def __init__(self, engine) -> None:
        super().__init__(
            engine,
            ScannerSpec(
                name="vili_risk",
                interval_key="vili_risk",
                default_interval=600,
                initial_delay=40,
            ),
        )

    def _vili_cfg(self) -> dict[str, Any]:
        cfg = self.engine._cfg("alert_engine", "vili_risk", default={})
        return cfg if isinstance(cfg, dict) else {}

    # ── 主扫描入口 ────────────────────────────────────────────

    async def scan(self) -> None:
        patient_cursor = self.engine.db.col("patient").find(
            self.engine._active_patient_query(),
            {
                "_id": 1, "name": 1, "hisPid": 1, "hisBed": 1,
                "dept": 1, "hisDept": 1,
                "gender": 1, "hisSex": 1, "height": 1, "heightCm": 1,
            },
        )
        patients = [p async for p in patient_cursor]
        if not patients:
            return

        triggered = 0
        for patient_doc in patients:
            pid = patient_doc.get("_id")
            if not pid:
                continue
            pid_str = str(pid)

            result = await self._assess_vili_risk(patient_doc, pid_str)
            if result is None:
                continue

            alert = await self._create_vili_alert(patient_doc, pid_str, result)
            if alert:
                triggered += 1

        if triggered > 0:
            self.engine._log_info("肺保护通气偏离风险", triggered)

    # ── VILI 风险评估 ─────────────────────────────────────────

    async def _assess_vili_risk(
        self, patient_doc: dict, pid_str: str,
    ) -> dict[str, Any] | None:
        """评估呼吸机相关肺损伤风险。"""
        cfg = self._vili_cfg()
        now = datetime.now()

        # 获取呼吸机设备
        device_id = await self.engine._get_device_id_for_patient(patient_doc, ["vent"])
        if not device_id:
            return None

        cap = await self.engine._get_latest_device_cap(device_id)
        if not cap:
            return None

        # 获取近期人机不同步评估
        recent_asynchrony = None
        if hasattr(self.engine, "_latest_ventilator_asynchrony_assessment"):
            try:
                recent_asynchrony = await self.engine._latest_ventilator_asynchrony_assessment(
                    pid_str, hours=4,
                )
            except Exception:
                pass

        asynchrony_type = str((recent_asynchrony or {}).get("dominant_type") or "")
        asynchrony_ai = _to_float((recent_asynchrony or {}).get("ai_index"))
        asynchrony_label = str((recent_asynchrony or {}).get("dominant_label") or "")

        # 获取呼吸机参数
        fio2_raw = self.engine._vent_param(cap, "fio2", "param_FiO2")
        peep = self.engine._vent_param_priority(cap, ["peep_measured", "peep_set"], ["param_vent_measure_peep", "param_vent_peep"])
        vt_actual = self.engine._vent_param_priority(cap, ["vte", "vt_set"], ["param_vent_vt", "param_vent_set_vt"])
        pip = self.engine._vent_param(cap, "pip", "param_vent_pip")
        pplat = self.engine._vent_param(cap, "pplat", "param_vent_plat_pressure")

        # 计算驱动压
        driving_pressure = None
        if pplat is not None and peep is not None:
            driving_pressure = round(float(pplat) - float(peep), 1)

        # 计算 VTe/PBW（仅在身高可靠时）
        vt_ml_kg = None
        pbw = None
        if hasattr(self.engine, "_predicted_body_weight"):
            try:
                pbw = self.engine._predicted_body_weight(patient_doc)
            except Exception:
                pbw = None

        if vt_actual is not None and pbw is not None:
            # 验证 PBW 合理性（基于患者提供的性别+身高计算）
            # 不在此处做默认值替换
            if pbw > 20 and pbw < 150:
                vt_ml_kg = round(float(vt_actual) / float(pbw), 2)

        # 收集证据
        evidence: list[str] = []
        risk_factors: list[str] = []
        risk_score = 0

        # 双触发检查
        double_triggering = asynchrony_type == "double_triggering"
        if double_triggering and asynchrony_ai is not None:
            evidence.append(f"双触发 AI {_format_number(asynchrony_ai, 1)}%")
            risk_factors.append("double_triggering")
            risk_score += 2 if asynchrony_ai >= 20 else 1

        # 高 VT 检查
        vt_threshold = float(cfg.get("vt_ml_kg_warning", 8.0) or 8.0)
        vt_critical = float(cfg.get("vt_ml_kg_critical", 10.0) or 10.0)
        high_vt = vt_ml_kg is not None and vt_ml_kg > vt_threshold
        if high_vt:
            evidence.append(f"VTe/PBW {_format_number(vt_ml_kg, 2)} mL/kg")
            risk_factors.append("high_vt")
            if vt_ml_kg >= vt_critical:
                risk_score += 2
            else:
                risk_score += 1

        # 驱动压检查
        dp_warning = float(cfg.get("driving_pressure_warning", 15.0) or 15.0)
        high_dp = driving_pressure is not None and driving_pressure > dp_warning
        if high_dp:
            evidence.append(f"驱动压 {_format_number(driving_pressure, 1)} cmH₂O")
            risk_factors.append("high_driving_pressure")
            risk_score += 1

        # 平台压检查
        pp_warning = float(cfg.get("plateau_pressure_warning", 30.0) or 30.0)
        high_pp = pplat is not None and pplat > pp_warning
        if high_pp:
            evidence.append(f"平台压 {_format_number(pplat, 1)} cmH₂O")
            risk_factors.append("high_plateau_pressure")
            risk_score += 1

        # 需要至少一个风险因素
        if not risk_factors:
            return None

        # 确定风险等级
        if risk_score >= 3:
            risk_level = "high"
            severity = "high"
        elif risk_score >= 2:
            risk_level = "elevated"
            severity = "warning"
        else:
            risk_level = "notable"
            severity = "warning"

        # 生成建议（个体化，不直接要求固定方案）
        suggestion = self._build_suggestion(
            double_triggering=double_triggering,
            high_vt=high_vt,
            high_dp=high_dp,
            high_pp=high_pp,
            vt_ml_kg=vt_ml_kg,
            driving_pressure=driving_pressure,
            pplat=pplat,
            asynchrony_ai=asynchrony_ai,
        )

        return {
            "assessment_type": "ventilator_induced_lung_injury_risk",
            "risk_level": risk_level,
            "double_triggering": double_triggering,
            "asynchrony_type": asynchrony_type if double_triggering else None,
            "asynchrony_index": round(float(asynchrony_ai), 1) if asynchrony_ai is not None else None,
            "asynchrony_label": asynchrony_label if double_triggering else None,
            "vte_ml_per_kg_pbw": vt_ml_kg,
            "vt_actual_ml": _to_float(vt_actual),
            "pbw_kg": pbw,
            "driving_pressure": driving_pressure,
            "plateau_pressure": _to_float(pplat),
            "peep": _to_float(peep),
            "pip": _to_float(pip),
            "evidence": evidence,
            "risk_factors": risk_factors,
            "suggestion": suggestion,
        }

    def _build_suggestion(
        self, *,
        double_triggering: bool,
        high_vt: bool,
        high_dp: bool,
        high_pp: bool,
        vt_ml_kg: float | None,
        driving_pressure: float | None,
        pplat: float | None,
        asynchrony_ai: float | None,
    ) -> str:
        """生成个体化建议，提示复核后调整，不直接要求固定措施。"""
        parts: list[str] = []

        if double_triggering and high_vt:
            parts.append(
                "检测到双触发叠加高潮气量，提示可能存在人机不同步导致VT叠加。"
                "建议：① 复核双触发原因（触发灵敏度、吸气流速、镇静深度、疼痛/焦虑/酸中毒等）；"
                "② 评估是否需调整通气模式或参数以减少不同步；"
                "③ 结合呼气VT和平台压复核肺保护通气目标"
            )
        elif double_triggering:
            parts.append(
                f"检测到双触发（AI {_format_number(asynchrony_ai, 1)}%），建议复核不同步原因后个体化调整通气参数"
            )
        elif high_vt:
            parts.append(
                f"当前VTe/PBW {_format_number(vt_ml_kg, 2)} mL/kg，超过肺保护通气目标(6-8 mL/kg PBW)。"
                "建议复核VT设定并排查导致额外VT的原因"
            )

        if high_dp and driving_pressure is not None:
            parts.append(
                f"驱动压 {_format_number(driving_pressure, 1)} cmH₂O 偏高，"
                "建议评估肺顺应性变化并复核PEEP与VT设定"
            )

        if high_pp and pplat is not None:
            parts.append(
                f"平台压 {_format_number(pplat, 1)} cmH₂O 偏高，"
                "建议复核气道阻力、胸壁顺应性及PEEP设定，目标平台压 ≤ 30 cmH₂O"
            )

        if not parts:
            parts.append("建议复核呼吸机参数和肺保护通气策略。")

        return "；".join(parts)

    # ── 告警生成 ──────────────────────────────────────────────

    async def _create_vili_alert(
        self, patient_doc: dict, pid_str: str, assessment: dict,
    ) -> dict | None:
        """生成 VILI 风险告警。"""
        risk_level = assessment["risk_level"]
        severity = "high" if risk_level == "high" else "warning"

        # 按风险等级区分 rule_id
        rule_id = f"VILI_RISK_{risk_level.upper()}"

        suppression = self.engine._cfg("alert_engine", "suppression", default={}) or {}
        same_rule_sec = int(suppression.get("same_rule_same_patient_seconds", 1800))
        max_per_hour = int(suppression.get("max_alerts_per_patient_per_hour", 10))
        if await self.engine._is_suppressed(pid_str, rule_id, same_rule_sec, max_per_hour):
            return None

        # 生成 clinical_episode_id 与 ARDS 筛查关联
        clinical_episode_id = f"resp_ep_{pid_str}"

        # 查找最近的 ARDS 氧合筛查告警
        linked_ards_screen = None
        try:
            recent_ards = await self.engine.db.col("alert_records").find_one(
                {
                    "patient_id": pid_str,
                    "alert_type": "ards_oxygenation_screen",
                    "created_at": {"$gte": datetime.now() - timedelta(hours=24)},
                },
                sort=[("created_at", -1)],
            )
            if recent_ards:
                linked_ards_screen = {
                    "alert_id": str(recent_ards.get("_id")),
                    "oxygenation_grade": (
                        (recent_ards.get("extra") or {}).get("assessment") or {}
                    ).get("oxygenation_grade"),
                }
        except Exception:
            pass

        # 构建告警名称
        name = self._build_alert_name(assessment)

        device_id = await self.engine._get_device_id_for_patient(patient_doc, ["vent"])

        explanation = await self.engine._polish_structured_alert_explanation({
            "summary": (
                f"{name}，证据: {'; '.join(assessment['evidence'][:4])}。"
            ),
            "evidence": assessment["evidence"],
            "suggestion": assessment["suggestion"],
            "text": "",
        })

        condition = {
            "risk_factors": assessment["risk_factors"],
            "vte_ml_per_kg_pbw": assessment["vte_ml_per_kg_pbw"],
        }

        alert = await self.engine._create_alert(
            rule_id=rule_id,
            name=name,
            category="ventilator",
            alert_type="ventilator_lung_injury_risk",
            severity=severity,
            parameter="vili_risk",
            condition=condition,
            value=assessment.get("vte_ml_per_kg_pbw"),
            patient_id=pid_str,
            patient_doc=patient_doc,
            device_id=device_id,
            source_time=datetime.now(),
            explanation=explanation,
            extra={
                "assessment": assessment,
                "clinical_episode_id": clinical_episode_id,
                "linked_ards_screen": linked_ards_screen,
            },
        )
        return alert

    def _build_alert_name(self, assessment: dict) -> str:
        """生成告警名称（表达为风险/偏离，非已发生的VILI）。"""
        factors = assessment.get("risk_factors", [])
        if "double_triggering" in factors and "high_vt" in factors:
            return "肺保护通气偏离风险—双触发叠加高VT"
        elif "double_triggering" in factors:
            return "肺保护通气偏离风险—双触发"
        elif "high_vt" in factors and "high_driving_pressure" in factors:
            return "肺损伤高风险通气模式—高VT合并高驱动压"
        elif "high_vt" in factors:
            return "肺保护通气偏离风险—高潮气量"
        elif "high_driving_pressure" in factors:
            return "肺损伤高风险通气模式—高驱动压"
        elif "high_plateau_pressure" in factors:
            return "肺损伤高风险通气模式—高平台压"
        return "肺保护通气偏离风险"
