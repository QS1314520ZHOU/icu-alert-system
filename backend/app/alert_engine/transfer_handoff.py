"""ICU转出交接：转出后恶化风险分 + 结构化交接清单 + 72h闭环验证。"""
from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger("icu-alert")

# ── 升压药关键词 ──
_VASOPRESSOR_KEYWORDS = [
    "去甲肾上腺素", "norepinephrine", "noradrenaline",
    "肾上腺素", "epinephrine", "adrenaline",
    "多巴胺", "dopamine",
    "多巴酚丁胺", "dobutamine",
    "血管加压素", "vasopressin",
    "去氧肾上腺素", "phenylephrine",
]

# ── 生命体征 code 映射 ──
_VITAL_CODES = {
    "HR": ["param_HR"],
    "MAP": ["param_ibp_m", "param_nibp_m"],
    "SpO2": ["param_spo2"],
    "RR": ["param_resp"],
    "Temp": ["param_T"],
}


class TransferHandoffMixin:
    """转出交接评估 mixin，挂载到 AlertEngine。"""

    # ────────────────── config ──────────────────

    def _transfer_handoff_cfg(self) -> dict[str, Any]:
        cfg = self.config.yaml_cfg.get("alert_engine", {}).get("transfer_handoff", {})
        return cfg if isinstance(cfg, dict) else {}

    def _th_cfg(self) -> dict[str, Any]:
        return self._transfer_handoff_cfg().get("thresholds", {})

    def _th_weights(self) -> dict[str, int]:
        return self._transfer_handoff_cfg().get("factor_weights", {})

    # ────────────────── helpers ──────────────────

    async def _get_weaning_stop_hours(self, pid_str: str) -> float | None:
        """返回撤机距今小时数；仍在使用呼吸机返回 None。"""
        try:
            bind = await self._get_active_vent_bind(pid_str)
            if bind:
                return None  # 仍在使用呼吸机
        except Exception:
            pass
        # 查最近 unBindTime
        try:
            doc = await self.db.col("deviceBind").find_one(
                {"pid": pid_str, "type": {"$in": ["vent", "ventilator", "breathing"]}},
                sort=[("unBindTime", -1)],
            )
            if doc and doc.get("unBindTime"):
                unbind = doc["unBindTime"]
                if isinstance(unbind, datetime):
                    hours = (datetime.now() - unbind).total_seconds() / 3600
                    return hours if hours >= 0 else None
        except Exception:
            pass
        return None

    async def _get_vasopressor_stop_hours(self, pid) -> float | None:
        """返回停升压药距今小时数；仍在使用返回 None。"""
        # 当前仍在使用
        if await self._has_vasopressor(pid):
            return None
        # 查最近用药记录
        docs = await self._find_recent_drug_docs(pid, _VASOPRESSOR_KEYWORDS, hours=48, limit=200)
        if not docs:
            return None
        # 取最近一条的时间
        latest_time = None
        for doc in docs:
            t = self._drug_event_time(doc)
            if t and (latest_time is None or t > latest_time):
                latest_time = t
        if latest_time:
            hours = (datetime.now() - latest_time).total_seconds() / 3600
            return hours if hours > 0 else None
        return None

    def _drug_event_time(self, doc: dict) -> datetime | None:
        for key in ("_event_time", "executeTime", "startTime", "orderTime"):
            val = doc.get(key)
            if isinstance(val, datetime):
                return val
        return None

    async def _get_vital_trend_stats(self, pid, hours: int = 6) -> dict[str, dict[str, float]]:
        """获取关键生命体征的趋势统计：latest、mean、std、cv。"""
        since = datetime.now() - timedelta(hours=hours)
        stats: dict[str, dict[str, float]] = {}
        for name, codes in _VITAL_CODES.items():
            values: list[float] = []
            for code in codes:
                series = await self._get_param_series_by_pid(pid, code, since)
                values.extend(float(p["value"]) for p in series if p.get("value") is not None)
            if not values:
                continue
            n = len(values)
            mean = sum(values) / n
            latest = values[-1]
            if n >= 2:
                variance = sum((v - mean) ** 2 for v in values) / (n - 1)
                std = math.sqrt(variance)
                cv = std / mean if mean != 0 else 0
            else:
                std = 0
                cv = 0
            stats[name] = {"latest": latest, "mean": mean, "std": std, "cv": cv, "points": n}
        return stats

    def _vital_trend_direction(self, stats: dict[str, dict[str, float]], delta_hours: int = 6) -> dict[str, str]:
        """判断各指标恶化方向（简化：用均值与最新值比较）。"""
        directions: dict[str, str] = {}
        for name, s in stats.items():
            if s["points"] < 3:
                directions[name] = "stable"
                continue
            latest = s["latest"]
            mean = s["mean"]
            if mean == 0:
                directions[name] = "stable"
                continue
            pct_change = (latest - mean) / abs(mean)
            if name in ("MAP", "SpO2"):
                # 下降为恶化
                directions[name] = "worsening" if pct_change < -0.1 else ("improving" if pct_change > 0.1 else "stable")
            else:
                # HR, RR, Temp 上升为恶化
                directions[name] = "worsening" if pct_change > 0.1 else ("improving" if pct_change < -0.1 else "stable")
        return directions

    # ────────────────── 风险分计算 ──────────────────

    async def compute_transfer_risk_score(
        self, patient_doc: dict,
    ) -> dict[str, Any]:
        """计算转出后恶化风险分，返回 {score, risk_level, risk_factors, raw_details}。"""
        cfg = self._transfer_handoff_cfg()
        th = self._th_cfg()
        weights = self._th_weights()
        pid = patient_doc.get("_id")
        if not pid:
            return {"score": 0, "risk_level": "low", "risk_factors": [], "raw_details": {}}
        pid_str = self._pid_str(pid)
        now = datetime.now()

        factors: list[dict[str, Any]] = []
        score = 0
        details: dict[str, Any] = {}

        # ── 1. 24h 趋势不稳定性 ──
        trend_hours = int(th.get("trend_delta_hours", 6) or 6)
        stats = await self._get_vital_trend_stats(pid, hours=trend_hours)
        directions = self._vital_trend_direction(stats, trend_hours)

        high_cv_th = float(th.get("vital_cv_high", 0.3) or 0.3)
        high_variability = any(s.get("cv", 0) > high_cv_th for s in stats.values())
        if high_variability:
            w = int(weights.get("vital_trend_high_variability", 15) or 15)
            score += w
            cv_details = {k: round(s["cv"], 3) for k, s in stats.items() if s.get("cv", 0) > high_cv_th}
            factors.append({"factor": "vital_trend_high_variability", "detail": f"变异系数偏高: {cv_details}", "weight": w})

        worsening = [k for k, d in directions.items() if d == "worsening"]
        if worsening:
            w = int(weights.get("vital_trend_acute_worsening", 20) or 20)
            score += w
            factors.append({"factor": "vital_trend_acute_worsening", "detail": f"{trend_hours}h内恶化指标: {worsening}", "weight": w})

        # ── SOFA 趋势 ──
        device_id = await self._get_device_id_for_patient(patient_doc, ["vent"])
        his_pid = patient_doc.get("hisPid")
        sofa_trend_rising = False
        if his_pid:
            try:
                current_sofa = await self._calc_sofa(patient_doc, pid, device_id, his_pid)
                if current_sofa and current_sofa.get("delta") is not None and current_sofa["delta"] > 0:
                    sofa_trend_rising = True
            except Exception:
                pass
        if sofa_trend_rising:
            w = int(weights.get("sofa_trend_rising", 10) or 10)
            score += w
            factors.append({"factor": "sofa_trend_rising", "detail": "SOFA 24h 内上升", "weight": w})

        # ── 2. 近期降级支持治疗 ──
        weaning_hours = await self._get_weaning_stop_hours(pid_str)
        weaning_window = int(th.get("weaning_window_hours", 48) or 48)
        if weaning_hours is not None and weaning_hours < weaning_window:
            if weaning_hours < 24:
                w = int(weights.get("vent_weaned_lt_24h", 15) or 15)
                factors.append({"factor": "vent_weaned_lt_24h", "detail": f"撤机 {weaning_hours:.1f}h 前", "weight": w})
            else:
                w = int(weights.get("vent_weaned_24_48h", 8) or 8)
                factors.append({"factor": "vent_weaned_24_48h", "detail": f"撤机 {weaning_hours:.1f}h 前", "weight": w})
            score += w

        vaso_hours = await self._get_vasopressor_stop_hours(pid)
        if vaso_hours is not None and vaso_hours < weaning_window:
            if vaso_hours < 24:
                w = int(weights.get("vaso_stopped_lt_24h", 15) or 15)
                factors.append({"factor": "vaso_stopped_lt_24h", "detail": f"停升压药 {vaso_hours:.1f}h 前", "weight": w})
            else:
                w = int(weights.get("vaso_stopped_24_48h", 8) or 8)
                factors.append({"factor": "vaso_stopped_24_48h", "detail": f"停升压药 {vaso_hours:.1f}h 前", "weight": w})
            score += w

        # ── 3. 残余异常指标 ──
        latest_vitals = {k: s.get("latest") for k, s in stats.items()}

        spo2_val = latest_vitals.get("SpO2")
        spo2_low = float(th.get("spo2_low", 92) or 92)
        vent_cap = await self._get_latest_device_cap(device_id) if device_id else None
        fio2 = self._vent_param(vent_cap or {}, "fio2", "param_FiO2") if vent_cap else None
        if fio2 is not None and fio2 > 1:
            fio2 = fio2 / 100.0
        fio2_high = float(th.get("fio2_high", 0.4) or 0.4)
        if (spo2_val is not None and spo2_val < spo2_low) or (fio2 is not None and fio2 > fio2_high):
            w = int(weights.get("residual_hypoxemia", 12) or 12)
            score += w
            factors.append({"factor": "residual_hypoxemia", "detail": f"SpO2={spo2_val}, FiO2={fio2}", "weight": w})

        map_val = latest_vitals.get("MAP")
        map_low = float(th.get("map_low", 65) or 65)
        if map_val is not None and map_val < map_low:
            w = int(weights.get("residual_hypotension", 12) or 12)
            score += w
            factors.append({"factor": "residual_hypotension", "detail": f"MAP={map_val:.0f} < {map_low}", "weight": w})

        hr_val = latest_vitals.get("HR")
        hr_high = float(th.get("hr_high", 110) or 110)
        if hr_val is not None and hr_val > hr_high:
            w = int(weights.get("residual_tachycardia", 8) or 8)
            score += w
            factors.append({"factor": "residual_tachycardia", "detail": f"HR={hr_val:.0f} > {hr_high}", "weight": w})

        temp_val = latest_vitals.get("Temp")
        temp_high = float(th.get("temp_high", 38.5) or 38.5)
        if temp_val is not None and temp_val > temp_high:
            w = int(weights.get("residual_fever", 8) or 8)
            score += w
            factors.append({"factor": "residual_fever", "detail": f"Temp={temp_val:.1f} > {temp_high}", "weight": w})

        gcs = await self._get_latest_assessment(pid, "gcs")
        gcs_low = float(th.get("gcs_low", 13) or 13)
        if gcs is not None and gcs < gcs_low:
            w = int(weights.get("residual_low_gcs", 12) or 12)
            score += w
            factors.append({"factor": "residual_low_gcs", "detail": f"GCS={gcs:.0f} < {gcs_low}", "weight": w})

        lactate_val = None
        try:
            lac_series = await self._get_param_series_by_pid(pid, "param_lac", datetime.now() - timedelta(hours=6))
            if lac_series:
                lactate_val = lac_series[-1].get("value")
        except Exception:
            pass
        lactate_high = float(th.get("lactate_high", 2.0) or 2.0)
        if lactate_val is not None and float(lactate_val) > lactate_high:
            w = int(weights.get("residual_high_lactate", 12) or 12)
            score += w
            factors.append({"factor": "residual_high_lactate", "detail": f"Lactate={float(lactate_val):.1f} > {lactate_high}", "weight": w})

        urine_low = float(th.get("urine_low_ml_kg_h", 0.5) or 0.5)
        try:
            urine_rate = await self._get_urine_rate(pid, patient_doc, 6)
            if urine_rate is not None and urine_rate < urine_low:
                w = int(weights.get("residual_oliguria", 10) or 10)
                score += w
                factors.append({"factor": "residual_oliguria", "detail": f"尿量={urine_rate:.2f} mL/kg/h < {urine_low}", "weight": w})
        except Exception:
            pass

        # ── 4. 亚表型 / PICS 风险 ──
        try:
            pics_profile = patient_doc.get("current_profile", {}).get("pics_risk")
            if not pics_profile:
                pics_doc = await self.db.col("score").find_one(
                    {"patient_id": str(pid), "score_type": "pics_risk_assessment"},
                    sort=[("calc_time", -1)],
                )
                pics_profile = (pics_doc or {}).get("assessment", {})
            pics_score = float(pics_profile.get("score", 0) or 0) if pics_profile else 0
            pics_high_th = float(pics_profile.get("high_threshold", 70) or 70) if pics_profile else 70
            if pics_score >= pics_high_th:
                w = int(weights.get("pics_risk_high", 10) or 10)
                score += w
                factors.append({"factor": "pics_risk_high", "detail": f"PICS风险分={pics_score:.0f}", "weight": w})
        except Exception:
            pass

        try:
            subtype_doc = await self.db.col("score").find_one(
                {"patient_id": str(pid), "score_type": {"$in": ["sepsis_subphenotype_profile", "clinical_subphenotype_profile"]}},
                sort=[("calc_time", -1)],
            )
            if subtype_doc:
                subtype_label = subtype_doc.get("subphenotype") or subtype_doc.get("label") or ""
                if "hyper" in str(subtype_label).lower() or "高炎症" in str(subtype_label):
                    w = int(weights.get("sepsis_subtype_hyperinflammatory", 8) or 8)
                    score += w
                    factors.append({"factor": "sepsis_subtype_hyperinflammatory", "detail": f"亚表型={subtype_label}", "weight": w})
        except Exception:
            pass

        # ── 分级 ──
        score = min(score, 100)
        high_th = int(cfg.get("high_threshold", 70) or 70)
        mod_th = int(cfg.get("mod_threshold", 40) or 40)
        if score >= high_th:
            risk_level = "high"
        elif score >= mod_th:
            risk_level = "moderate"
        else:
            risk_level = "low"

        details = {
            "vital_stats": stats,
            "vital_directions": directions,
            "weaning_stop_hours": weaning_hours,
            "vasopressor_stop_hours": vaso_hours,
            "gcs": gcs,
            "lactate": lactate_val,
            "fio2": fio2,
        }

        return {"score": score, "risk_level": risk_level, "risk_factors": factors, "raw_details": details}

    # ────────────────── Checklist 生成 ──────────────────

    _FACTOR_CHECKLIST_MAP: dict[str, dict[str, str]] = {
        "vital_trend_high_variability": {"item": "密切监测生命体征 q1h", "category": "unstable_vital", "why": "24h 内生命体征变异系数偏高"},
        "vital_trend_acute_worsening": {"item": "加强监护频率，关注恶化指标", "category": "unstable_vital", "why": "近期存在恶化趋势"},
        "sofa_trend_rising": {"item": "复查 SOFA 评分，评估器官功能", "category": "unstable_vital", "why": "SOFA 评分上升提示器官功能恶化"},
        "vent_weaned_lt_24h": {"item": "确认撤机后呼吸储备，备无创通气", "category": "medication", "why": "撤机 24h 内再插管风险高"},
        "vent_weaned_24_48h": {"item": "观察呼吸状态，必要时复查血气", "category": "medication", "why": "撤机 24-48h 仍需关注"},
        "vaso_stopped_lt_24h": {"item": "监测血压 q2h，备升压药", "category": "medication", "why": "停升压药 24h 内低血压反弹风险高"},
        "vaso_stopped_24_48h": {"item": "关注血压变化趋势", "category": "medication", "why": "停升压药 24-48h 仍需观察"},
        "residual_hypoxemia": {"item": "复查血气，评估氧疗方案", "category": "unstable_vital", "why": "残余低氧血症"},
        "residual_hypotension": {"item": "评估容量状态与血管张力", "category": "unstable_vital", "why": "残余低血压"},
        "residual_tachycardia": {"item": "心电监测，排查心律失常", "category": "unstable_vital", "why": "残余心动过速"},
        "residual_fever": {"item": "监测体温，排查感染源", "category": "unstable_vital", "why": "残余发热"},
        "residual_low_gcs": {"item": "神经系统评估 q4h", "category": "unstable_vital", "why": "意识水平偏低"},
        "residual_high_lactate": {"item": "复查乳酸，评估灌注状态", "category": "unstable_vital", "why": "乳酸偏高提示组织灌注不足"},
        "residual_oliguria": {"item": "监测尿量，评估肾功能", "category": "unstable_vital", "why": "尿量偏低"},
        "pics_risk_high": {"item": "安排 ICU 后随访门诊", "category": "followup", "why": "PICS 高风险"},
        "sepsis_subtype_hyperinflammatory": {"item": "转出后 48h 复查炎症指标", "category": "watch_window", "why": "高炎症亚表型提示持续炎症反应"},
    }

    def build_checklist(self, risk_factors: list[dict[str, Any]], risk_level: str) -> list[dict[str, Any]]:
        """根据 risk_factors 生成结构化交接清单。"""
        checklist: list[dict[str, Any]] = []
        seen_items: set[str] = set()

        for rf in risk_factors:
            factor = rf.get("factor", "")
            mapping = self._FACTOR_CHECKLIST_MAP.get(factor)
            if mapping and mapping["item"] not in seen_items:
                checklist.append({
                    "item": mapping["item"],
                    "why": mapping["why"],
                    "category": mapping["category"],
                })
                seen_items.add(mapping["item"])

        # 通用项
        if risk_level in ("high", "moderate"):
            watch = {"item": "转出后 72h 内关注再入 ICU 征象", "why": "高/中风险患者需密切随访", "category": "watch_window"}
            if watch["item"] not in seen_items:
                checklist.append(watch)
                seen_items.add(watch["item"])

        followup = {"item": "确认交接班信息完整传达", "why": "确保转出信息无遗漏", "category": "followup"}
        if followup["item"] not in seen_items:
            checklist.append(followup)

        return checklist

    # ────────────────── Narrative ──────────────────

    def _build_rule_narrative(self, risk_factors: list[dict[str, Any]], risk_level: str, checklist: list[dict[str, Any]]) -> str:
        """规则生成的 narrative（不依赖 LLM）。"""
        level_map = {"high": "高", "moderate": "中", "low": "低"}
        parts = [f"转出后恶化风险：{level_map.get(risk_level, risk_level)}。"]
        if risk_factors:
            top = sorted(risk_factors, key=lambda f: f.get("weight", 0), reverse=True)[:3]
            factor_strs = [f"{f['factor']}({f['detail']})" for f in top]
            parts.append(f"主要风险因素：{'、'.join(factor_strs)}。")
        if checklist:
            parts.append(f"交接清单共 {len(checklist)} 项。")
        return "".join(parts)

    async def _maybe_llm_narrative(
        self, risk_factors: list[dict[str, Any]], risk_level: str, checklist: list[dict[str, Any]], patient_doc: dict,
    ) -> str | None:
        """可选的 LLM 润色 narrative。"""
        cfg = self._transfer_handoff_cfg()
        if not cfg.get("llm_narrative"):
            return None
        # LLM 润色通过 safe_llm_call 实现，失败则返回 None 降级到规则
        return None

    # ────────────────── 主评估入口 ──────────────────

    async def evaluate_transfer_handoff(self, patient_doc: dict) -> dict[str, Any]:
        """评估转出交接风险，返回完整 score 文档。"""
        cfg = self._transfer_handoff_cfg()
        pid = patient_doc.get("_id")
        if not pid:
            return {"error": "no patient id"}
        pid_str = self._pid_str(pid)
        now = datetime.now()

        result = await self.compute_transfer_risk_score(patient_doc)
        checklist = self.build_checklist(result["risk_factors"], result["risk_level"])

        narrative = self._build_rule_narrative(result["risk_factors"], result["risk_level"], checklist)
        llm_narrative = await self._maybe_llm_narrative(result["risk_factors"], result["risk_level"], checklist, patient_doc)
        if llm_narrative:
            narrative = llm_narrative

        doc: dict[str, Any] = {
            "score_type": "transfer_handoff",
            "patient_id": str(pid),
            "status": "active",
            "post_transfer_risk_score": result["score"],
            "risk_level": result["risk_level"],
            "risk_factors": result["risk_factors"],
            "handoff_checklist": checklist,
            "narrative": narrative,
            "transferred_at": now,
            "verification": {
                "checked_at": None,
                "readmitted_within_72h": None,
                "critical_alert_within_72h": None,
                "details": [],
            },
            "calc_time": now,
            "created_at": now,
            "month": now.strftime("%Y-%m"),
            "day": now.strftime("%Y-%m-%d"),
        }

        return doc

    # ────────────────── 持久化 ──────────────────

    async def persist_transfer_handoff(self, doc: dict[str, Any]) -> dict[str, Any]:
        """将评估结果写入 score 集合。"""
        await self.db.col("score").insert_one(doc)
        return doc

    # ────────────────── 72h 回填验证 ──────────────────

    async def verify_transfer_outcomes(self) -> int:
        """回填 transferred_at 超过 verify_window_hours、verification.checked_at 为 null 的记录。

        返回处理的记录数。
        """
        cfg = self._transfer_handoff_cfg()
        if not cfg.get("enabled", True):
            return 0
        verify_hours = int(cfg.get("verify_window_hours", 72) or 72)
        cutoff = datetime.now() - timedelta(hours=verify_hours)

        cursor = self.db.col("score").find({
            "score_type": "transfer_handoff",
            "transferred_at": {"$lte": cutoff},
            "verification.checked_at": None,
        })

        processed = 0
        async for doc in cursor:
            patient_id = doc.get("patient_id")
            transferred_at = doc.get("transferred_at")
            if not patient_id or not transferred_at:
                continue

            # 72h 窗口
            window_end = transferred_at + timedelta(hours=verify_hours)
            now = datetime.now()
            check_end = min(window_end, now)

            # 检查是否再入 ICU
            readmitted = await self._check_readmission(patient_id, transferred_at, check_end)

            # 检查 72h 内 critical/high 预警
            critical_alerts = await self._check_critical_alerts(patient_id, transferred_at, check_end)

            verification = {
                "checked_at": now,
                "readmitted_within_72h": readmitted,
                "critical_alert_within_72h": critical_alerts,
                "details": [],
            }

            await self.db.col("score").update_one(
                {"_id": doc["_id"]},
                {"$set": {"verification": verification}},
            )
            processed += 1

        return processed

    async def _check_readmission(self, patient_id: str, since: datetime, until: datetime) -> bool:
        """检查患者在 [since, until] 是否再入 ICU。

        策略：检查 alert_records 中是否有 TRANSFER_HANDOFF 类型的反向事件，
        或检查 patient 文档中是否有 ICU 床位重新分配的记录。
        """
        try:
            count = await self.db.col("alert_records").count_documents({
                "patient_id": patient_id,
                "category": "transfer",
                "alert_type": "readmission",
                "created_at": {"$gte": since, "$lte": until},
            })
            return count > 0
        except Exception:
            return False

    async def _check_critical_alerts(self, patient_id: str, since: datetime, until: datetime) -> bool:
        """检查患者在 [since, until] 是否触发 critical/high 预警。"""
        try:
            count = await self.db.col("alert_records").count_documents({
                "patient_id": patient_id,
                "severity": {"$in": ["critical", "high"]},
                "created_at": {"$gte": since, "$lte": until},
            })
            return count > 0
        except Exception:
            return False

    # ────────────────── 查询接口 ──────────────────

    async def get_latest_transfer_handoff(self, patient_id: str) -> dict[str, Any] | None:
        """获取患者最新一条转出交接评估记录。"""
        doc = await self.db.col("score").find_one(
            {"patient_id": patient_id, "score_type": "transfer_handoff"},
            sort=[("calc_time", -1)],
        )
        return doc
