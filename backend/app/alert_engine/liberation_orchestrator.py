"""Liberation 方向建议编排器 — 每日产出单患者 Liberation 方向建议，对齐 eCASH / ABCDEF bundle。"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger("icu-alert")


class LiberationOrchestratorMixin:
    """基于确定性规则产出每日 Liberation 方向建议。

    direction 由纯规则决定，LLM 仅可润色 extra.narrative。
    """

    # ------------------------------------------------------------------
    # 配置
    # ------------------------------------------------------------------
    def _lib_cfg(self) -> dict:
        cfg = self.config.yaml_cfg.get("alert_engine", {}).get("liberation_orchestrator", {})
        return cfg if isinstance(cfg, dict) else {}

    # ------------------------------------------------------------------
    # 数据快照采集
    # ------------------------------------------------------------------
    async def _collect_liberation_snapshot(
        self, patient_doc: dict
    ) -> dict[str, Any]:
        """采集判定所需的全部原始数据，返回统一快照。"""
        pid = patient_doc.get("_id")
        now = datetime.now()
        if not pid:
            return {"error": "no_pid", "now": now}

        pid_str = str(pid)
        his_pid = patient_doc.get("hisPid")
        cfg = self._lib_cfg()

        # ── 镇静 / 镇痛 (复用 eCASH) ──
        ecash: dict[str, Any] = {}
        if hasattr(self, "get_ecash_status"):
            try:
                ecash = await self.get_ecash_status(patient_doc)
            except Exception:
                ecash = {}
        sedation = ecash.get("sedation") or {}
        analgesia = ecash.get("analgesia") or {}
        delirium_ecash = ecash.get("delirium") or {}

        # ── RASS ──
        rass_actual = sedation.get("latest_rass")
        if rass_actual is None:
            rass_val = await self._get_latest_assessment(pid, "rass")
            rass_actual = float(rass_val) if rass_val is not None else None
        rass_series = await self._get_assessment_series(pid, "rass", hours=6)
        rass_trend_per_h = self._series_delta_per_hour(rass_series) if rass_series else 0.0

        target_range = cfg.get("rass_target_range")
        if not isinstance(target_range, list) or len(target_range) != 2:
            target_range = sedation.get("target_rass_range") or [
                float(cfg.get("rass_target_low", -2)),
                float(cfg.get("rass_target_high", 0)),
            ]
        rass_target_low = float(target_range[0])
        rass_target_high = float(target_range[1])

        # ── CAM-ICU ──
        cam_status = await self._get_latest_cam_icu_status(pid, lookback_hours=48)
        cam_positive = cam_status.get("positive") if cam_status else None
        cam_assessable = cam_status.get("assessable") if cam_status else None
        if cam_positive is True:
            cam_label = "+"
        elif cam_positive is False:
            cam_label = "-"
        else:
            cam_label = "未评估"

        # ── 谵妄风险评分 ──
        delirium_risk_score: float | None = None
        if hasattr(self, "_calc_delirium_risk_score"):
            try:
                delirium_risk_score = await self._calc_delirium_risk_score(patient_doc, pid)
            except Exception:
                delirium_risk_score = None
        delirium_high_threshold = float(cfg.get("delirium_high_threshold", 4))

        # ── 镇静药 ──
        sedative_kw = self._get_cfg_list(
            ("alert_engine", "drug_mapping", "sedatives"),
            ["咪达唑仑", "丙泊酚", "右美托咪定", "地西泮", "劳拉西泮"],
        )
        current_sedatives = sedation.get("current_sedatives") or []
        if not current_sedatives:
            recent_drugs = await self._get_recent_drugs(pid, hours=24)
            current_sedatives = self._dedupe_names(recent_drugs) if hasattr(self, "_dedupe_names") else recent_drugs
            current_sedatives = [
                d for d in current_sedatives
                if self._match_name_keywords(d, sedative_kw)
            ]

        # 镇静药剂量趋势（用 _find_recent_drug_docs 取近12h文档，比较前后半段数量/频率）
        sed_dose_trend = "stable"
        if hasattr(self, "_find_recent_drug_docs"):
            try:
                docs_12h = await self._find_recent_drug_docs(pid, sedative_kw, hours=12)
                if docs_12h and len(docs_12h) >= 4:
                    mid = len(docs_12h) // 2
                    first_half = docs_12h[:mid]
                    second_half = docs_12h[mid:]
                    if len(second_half) > len(first_half) * 1.3:
                        sed_dose_trend = "up"
                    elif len(second_half) < len(first_half) * 0.7:
                        sed_dose_trend = "down"
            except Exception:
                pass

        # ── 呼吸机 / SBT / 脱机 ──
        device_id = await self._get_device_id(pid)
        cap: dict = {}
        if device_id:
            cap = await self._get_latest_device_cap(device_id) or {}

        fio2 = self._vent_param(cap, "fio2", "param_FiO2")
        peep = self._vent_param_priority(
            cap, ["peep_measured", "peep_set"],
            ["param_vent_measure_peep", "param_vent_peep"],
        )
        rr = self._vent_param_priority(
            cap, ["rr_measured", "rr_set"],
            ["param_vent_resp", "param_HuXiPinLv"],
        )
        vte = self._vent_param_priority(
            cap, ["vte", "vt_set"],
            ["param_vent_vt", "param_vent_set_vt"],
        )
        rsbi = self._calc_rsbi(rr, vte) if hasattr(self, "_calc_rsbi") else None

        pf_snapshot: dict = {}
        if hasattr(self, "_get_pf_snapshot"):
            try:
                pf_snapshot = await self._get_pf_snapshot(his_pid, cap, now)
            except Exception:
                pf_snapshot = {}
        pf_ratio = pf_snapshot.get("pf_ratio")

        sbt_result: dict | None = None
        if hasattr(self, "_get_recent_sbt_result"):
            try:
                sbt_result = await self._get_recent_sbt_result(pid, now, hours=72)
            except Exception:
                sbt_result = None

        # SBT 候选判定
        pf_ready = float(cfg.get("oxygenation_pf_ready", 200))
        peep_ready = float(cfg.get("oxygenation_peep_ready", 8))
        fio2_ready = float(cfg.get("oxygenation_fio2_ready", 40))
        rass_sbt_min = float(cfg.get("rass_sbt_min", -2))
        rass_sbt_max = float(cfg.get("rass_sbt_max", 1))

        fio2_pct = fio2
        if fio2_pct is not None and fio2_pct <= 1:
            fio2_pct = fio2_pct * 100

        sbt_gate_ok = True
        sbt_gate_failures: list[str] = []
        if pf_ratio is not None and pf_ratio < pf_ready:
            sbt_gate_ok = False
            sbt_gate_failures.append(f"P/F {pf_ratio:.0f} < {pf_ready}")
        if peep is not None and peep > peep_ready:
            sbt_gate_ok = False
            sbt_gate_failures.append(f"PEEP {peep:.0f} > {peep_ready}")
        if fio2_pct is not None and fio2_pct > fio2_ready:
            sbt_gate_ok = False
            sbt_gate_failures.append(f"FiO₂ {fio2_pct:.0f}% > {fio2_ready}%")
        if rass_actual is not None and not (rass_sbt_min <= rass_actual <= rass_sbt_max):
            sbt_gate_ok = False
            sbt_gate_failures.append(f"RASS {rass_actual:.0f} 不在 [{rass_sbt_min},{rass_sbt_max}]")

        # 近期 SBT 失败排除
        sbt_recently_failed = False
        if isinstance(sbt_result, dict) and sbt_result.get("passed") is False:
            sbt_recently_failed = True
            sbt_gate_ok = False
            sbt_gate_failures.append("近72h SBT 失败")

        sbt_candidate = sbt_gate_ok and bool(cap)

        # ── 人机不同步 ──
        asynchrony: dict | None = None
        if hasattr(self, "_latest_ventilator_asynchrony_assessment"):
            try:
                asynchrony = await self._latest_ventilator_asynchrony_assessment(pid_str, hours=4)
            except Exception:
                asynchrony = None
        asynchrony_ai = None
        asynchrony_severity = ""
        if isinstance(asynchrony, dict):
            ai_raw = asynchrony.get("ai_index")
            asynchrony_ai = float(ai_raw) if ai_raw is not None else None
            asynchrony_severity = str(asynchrony.get("severity") or "").lower()

        asynchrony_gate = float(cfg.get("asynchrony_gate_ai_percent", 10))
        asynchrony_high = float(cfg.get("asynchrony_high_ai_percent", 20))
        has_significant_asynchrony = (
            (asynchrony_ai is not None and asynchrony_ai >= asynchrony_gate)
            or asynchrony_severity in {"high", "critical"}
        )
        has_severe_asynchrony = (
            (asynchrony_ai is not None and asynchrony_ai >= asynchrony_high)
            or asynchrony_severity == "critical"
        )

        # ── 颅高压 ──
        has_icp_hypertension = False
        try:
            icp_events = await self._get_recent_text_events(
                pid, ["颅内压", "颅高压", "ICP增高", "ICP升高"], hours=12, limit=100
            )
            if icp_events:
                neg_kw = ["无", "未见", "正常", "否认"]
                for ev in icp_events:
                    text = " ".join(str(ev.get(k) or "") for k in ("code", "strVal", "value", "remark")).lower()
                    if any(k in text for k in neg_kw):
                        continue
                    has_icp_hypertension = True
                    break
        except Exception:
            pass

        # ── 躁动 (RASS > +2) ──
        has_agitation = rass_actual is not None and rass_actual > float(cfg.get("agitation_rass_threshold", 2))

        # ── 活动等级 ──
        last_activity_time = None
        if hasattr(self, "_get_last_activity_time"):
            try:
                activity_kw = ["早期活动", "下床", "站立", "行走", "康复", "活动", "被动活动", "主动活动"]
                last_activity_time = await self._get_last_activity_time(pid_str, now, lookback_hours=72, keywords=activity_kw)
            except Exception:
                pass

        # ── 昼夜 ──
        is_night = self._is_night_window(now) if hasattr(self, "_is_night_window") else False

        # ── 汇总快照 ──
        snapshots = {
            "sedation": {
                "rass_actual": rass_actual,
                "rass_target": [rass_target_low, rass_target_high],
                "rass_trend_per_h": round(rass_trend_per_h, 2) if rass_trend_per_h else 0.0,
                "current_sedatives": current_sedatives,
                "sed_dose_trend": sed_dose_trend,
                "ecash_status": sedation.get("status"),
            },
            "ventilation": {
                "fio2": fio2,
                "peep": peep,
                "rr": rr,
                "vte_ml": vte,
                "rsbi": rsbi,
                "pf_ratio": pf_ratio,
                "pf_trend": pf_snapshot.get("trend"),
                "sbt_result": sbt_result,
                "sbt_candidate": sbt_candidate,
                "sbt_gate_failures": sbt_gate_failures,
                "asynchrony_ai": asynchrony_ai,
                "asynchrony_severity": asynchrony_severity,
            },
            "delirium": {
                "cam_icu_positive": cam_positive,
                "cam_icu_assessable": cam_assessable,
                "cam_label": cam_label,
                "risk_score": delirium_risk_score,
                "ecash_status": delirium_ecash.get("status"),
            },
            "mobility": {
                "last_activity_time": last_activity_time.isoformat() if last_activity_time else None,
            },
            "circadian": {
                "is_night": is_night,
            },
        }

        return {
            "now": now,
            "pid": pid,
            "pid_str": pid_str,
            "his_pid": his_pid,
            "device_id": device_id,
            "rass_actual": rass_actual,
            "rass_target_low": rass_target_low,
            "rass_target_high": rass_target_high,
            "rass_trend_per_h": rass_trend_per_h,
            "cam_positive": cam_positive,
            "cam_label": cam_label,
            "delirium_risk_score": delirium_risk_score,
            "delirium_high_threshold": delirium_high_threshold,
            "current_sedatives": current_sedatives,
            "sed_dose_trend": sed_dose_trend,
            "pf_ratio": pf_ratio,
            "peep": peep,
            "fio2": fio2,
            "fio2_pct": fio2_pct,
            "rsbi": rsbi,
            "sbt_candidate": sbt_candidate,
            "sbt_gate_failures": sbt_gate_failures,
            "sbt_recently_failed": sbt_recently_failed,
            "has_significant_asynchrony": has_significant_asynchrony,
            "has_severe_asynchrony": has_severe_asynchrony,
            "asynchrony_ai": asynchrony_ai,
            "asynchrony_severity": asynchrony_severity,
            "has_icp_hypertension": has_icp_hypertension,
            "has_agitation": has_agitation,
            "is_night": is_night,
            "last_activity_time": last_activity_time,
            "snapshots": snapshots,
        }

    # ------------------------------------------------------------------
    # 方向判定
    # ------------------------------------------------------------------
    def _determine_liberation_direction(
        self, snap: dict[str, Any]
    ) -> dict[str, Any]:
        """根据快照数据执行优先级规则表，返回 {direction, evidence, trade_offs}。"""
        evidence: list[dict[str, Any]] = []
        trade_offs: list[str] = []

        rass_actual = snap.get("rass_actual")
        rass_target_low = snap.get("rass_target_low", -2)
        rass_target_high = snap.get("rass_target_high", 0)
        delirium_risk_score = snap.get("delirium_risk_score")
        delirium_high_threshold = snap.get("delirium_high_threshold", 4)
        cam_positive = snap.get("cam_positive")
        sed_dose_trend = snap.get("sed_dose_trend", "stable")
        has_severe_asynchrony = snap.get("has_severe_asynchrony", False)
        has_significant_asynchrony = snap.get("has_significant_asynchrony", False)
        has_icp_hypertension = snap.get("has_icp_hypertension", False)
        has_agitation = snap.get("has_agitation", False)
        sbt_candidate = snap.get("sbt_candidate", False)
        sbt_gate_failures = snap.get("sbt_gate_failures", [])
        is_night = snap.get("is_night", False)
        pf_ratio = snap.get("pf_ratio")
        peep = snap.get("peep")
        fio2_pct = snap.get("fio2_pct")
        asynchrony_ai = snap.get("asynchrony_ai")
        current_sedatives = snap.get("current_sedatives", [])

        # ── collect evidence ──
        if rass_actual is not None:
            evidence.append({"factor": "RASS", "value": rass_actual, "implies": "镇静深度评估"})
        if snap.get("cam_label"):
            evidence.append({"factor": "CAM-ICU", "value": snap["cam_label"], "implies": "谵妄状态"})
        if delirium_risk_score is not None:
            evidence.append({"factor": "谵妄风险评分", "value": delirium_risk_score, "implies": "谵妄风险"})
        if pf_ratio is not None:
            evidence.append({"factor": "P/F比值", "value": round(pf_ratio, 1), "implies": "氧合状态"})
        if peep is not None:
            evidence.append({"factor": "PEEP", "value": peep, "implies": "呼吸机设置"})
        if fio2_pct is not None:
            evidence.append({"factor": "FiO₂", "value": round(fio2_pct, 1), "implies": "呼吸机设置"})
        if asynchrony_ai is not None:
            evidence.append({"factor": "人机不同步AI指数", "value": asynchrony_ai, "implies": "人机同步性"})
        if current_sedatives:
            evidence.append({"factor": "当前镇静药", "value": len(current_sedatives), "implies": "镇静负荷"})
        if sed_dose_trend == "up":
            evidence.append({"factor": "镇静药剂量趋势", "value": "上升", "implies": "镇静加深"})

        # ── 规则1: maintain_sedation (最高优先级) ──
        maintain_reasons: list[str] = []
        if delirium_risk_score is not None and delirium_risk_score >= delirium_high_threshold:
            maintain_reasons.append(f"谵妄高风险(评分{delirium_risk_score:.1f}≥{delirium_high_threshold})")
        if cam_positive is True:
            maintain_reasons.append("CAM-ICU阳性")
        if sed_dose_trend == "up" and current_sedatives:
            maintain_reasons.append("镇静药剂量上升趋势")
        if has_severe_asynchrony:
            maintain_reasons.append(f"严重人机不同步(AI {asynchrony_ai}%, severity={snap.get('asynchrony_severity')})")

        if maintain_reasons:
            # 检查与其他方向的冲突
            if rass_actual is not None and rass_actual < rass_target_low and not has_icp_hypertension and not has_agitation:
                trade_offs.append(
                    f"RASS {rass_actual:.0f} 深于目标[{rass_target_low},{rass_target_high}]，适合唤醒，但{'；'.join(maintain_reasons)}"
                )
            if sbt_candidate:
                trade_offs.append("氧合/呼吸机参数达SBT阈值，但" + "；".join(maintain_reasons))
            return {
                "direction": "maintain_sedation",
                "evidence": evidence,
                "trade_offs": trade_offs,
                "_maintain_reasons": maintain_reasons,
            }

        # ── 规则2: lean_awakening ──
        lean_ok = False
        lean_reasons: list[str] = []
        if rass_actual is not None and rass_actual < rass_target_low:
            lean_ok = True
            lean_reasons.append(f"RASS {rass_actual:.0f} 深于目标下限 {rass_target_low}")
        if has_icp_hypertension:
            lean_ok = False
            trade_offs.append("RASS偏深适合唤醒，但存在颅高压")
        if has_agitation:
            lean_ok = False
            trade_offs.append(f"RASS偏深但存在躁动(RASS>{snap.get('rass_actual')})")
        if has_significant_asynchrony and not has_severe_asynchrony:
            lean_reasons.append(f"存在轻中度人机不同步(AI {asynchrony_ai}%)")
            trade_offs.append("RASS偏深适合唤醒，但存在人机不同步需同步关注")

        if lean_ok and not has_icp_hypertension and not has_agitation:
            evidence.append({"factor": "唤醒评估", "value": "适合", "implies": "lean_awakening"})
            # 检查与 SBT 的冲突
            if sbt_candidate:
                trade_offs.append("同时满足SBT条件，建议唤醒稳定后再推进SBT")
            return {
                "direction": "lean_awakening",
                "evidence": evidence,
                "trade_offs": trade_offs,
            }

        # ── 规则3: advance_sbt ──
        if sbt_candidate and not is_night:
            if rass_actual is not None:
                evidence.append({"factor": "RASS适宜性", "value": f"{rass_actual:.0f}∈[{rass_target_low},{rass_target_high}]", "implies": "advance_sbt"})
            evidence.append({"factor": "SBT候选", "value": True, "implies": "advance_sbt"})
            return {
                "direction": "advance_sbt",
                "evidence": evidence,
                "trade_offs": trade_offs,
            }

        if sbt_candidate and is_night:
            trade_offs.append("已达SBT条件但处于夜间，建议日间推进")

        # ── 规则4: hold_and_optimize (兜底) ──
        missing: list[str] = []
        if rass_actual is None:
            missing.append("RASS")
        if snap.get("cam_label") == "未评估":
            missing.append("CAM-ICU")
        if pf_ratio is None and peep is None:
            missing.append("呼吸机参数")
        if missing:
            trade_offs.append(f"关键数据缺失: {', '.join(missing)}")

        if sbt_gate_failures:
            trade_offs.append(f"SBT条件未满足: {'；'.join(sbt_gate_failures)}")

        # 检查矛盾
        if (rass_actual is not None and rass_actual < rass_target_low) and has_significant_asynchrony:
            trade_offs.append(f"RASS偏深(适合唤醒)但存在人机不同步(AI {asynchrony_ai}%)")

        return {
            "direction": "hold_and_optimize",
            "evidence": evidence,
            "trade_offs": trade_offs,
        }

    # ------------------------------------------------------------------
    # 构建 extra
    # ------------------------------------------------------------------
    async def get_liberation_daily_advice(
        self, patient_doc: dict
    ) -> dict[str, Any] | None:
        """采集数据 → 规则判定 → 构建 extra，返回完整 extra dict 或 None。"""
        snap = await self._collect_liberation_snapshot(patient_doc)
        if snap.get("error"):
            return None

        cfg = self._lib_cfg()
        result = self._determine_liberation_direction(snap)

        rass_actual = snap.get("rass_actual")
        target_range = [snap["rass_target_low"], snap["rass_target_high"]]

        extra: dict[str, Any] = {
            "direction": result["direction"],
            "rass_target": target_range,
            "rass_actual": round(rass_actual, 1) if rass_actual is not None else None,
            "cam_icu": snap.get("cam_label", "未评估"),
            "sbt_candidate": snap.get("sbt_candidate", False),
            "evidence": result["evidence"],
            "trade_offs": result["trade_offs"],
            "snapshots": snap["snapshots"],
        }

        # ── 可选 LLM 润色叙述 ──
        llm_enabled = bool(cfg.get("llm_narrative", False))
        if llm_enabled and hasattr(self, "_safe_llm_call"):
            narrative = await self._generate_liberation_narrative(extra)
            if narrative:
                extra["narrative"] = narrative

        return extra

    async def _generate_liberation_narrative(self, extra: dict[str, Any]) -> str | None:
        """调用 LLM 生成叙述文本（仅润色，不改变 direction/evidence/trade_offs）。"""
        try:
            from ..llm import call_llm_chat
        except Exception:
            return None

        direction = extra.get("direction", "")
        evidence_str = "; ".join(
            f"{e['factor']}={e.get('value')}" for e in extra.get("evidence", [])[:6]
        )
        trade_offs_str = "; ".join(extra.get("trade_offs", []) or [])

        system_prompt = (
            "你是一位 ICU 临床决策支持助手。根据以下 Liberation 方向建议数据，"
            "用简洁的中文写出 2-3 句临床叙述。不要改变方向标签或证据内容，"
            "仅做文字润色。不要添加新的临床建议。"
        )
        user_prompt = (
            f"方向: {direction}\n"
            f"证据: {evidence_str}\n"
            f"权衡: {trade_offs_str}\n"
            f"RASS: {extra.get('rass_actual')}, CAM-ICU: {extra.get('cam_icu')}, "
            f"SBT候选: {extra.get('sbt_candidate')}"
        )

        result = await self._safe_llm_call(
            call_llm_chat(system_prompt, user_prompt, timeout=30),
            fallback=None,
            timeout=35,
        )
        if isinstance(result, str) and result.strip():
            return result.strip()[:500]
        return None

    # ------------------------------------------------------------------
    # 每日去重签名
    # ------------------------------------------------------------------
    @staticmethod
    def _liberation_day_signature(pid_str: str, now: datetime) -> str:
        """生成 patient_id + day 维度的去重签名。"""
        day_str = now.strftime("%Y-%m-%d")
        raw = f"{pid_str}|LIBERATION_DAILY_ADVICE|{day_str}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]
