"""主动管理闭环引擎。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4


class ProactiveManagementEngineMixin:
    def _proactive_management_cfg(self) -> dict:
        cfg = self._cfg("alert_engine", "proactive_management", default={}) or {}
        return cfg if isinstance(cfg, dict) else {}

    def _series_snapshot(self, series: list[dict]) -> dict[str, Any]:
        if not series:
            return {"points": 0, "latest": None, "delta": None, "trend": "insufficient"}
        values = [float(item["value"]) for item in series if item.get("value") is not None]
        if not values:
            return {"points": 0, "latest": None, "delta": None, "trend": "insufficient"}
        latest = values[-1]
        first = values[0]
        delta = round(latest - first, 3)
        trend = "stable" if abs(delta) < 1e-6 else ("up" if delta > 0 else "down")
        return {
            "points": len(values),
            "latest": round(latest, 3),
            "delta": delta,
            "trend": trend,
            "start_time": series[0].get("time"),
            "end_time": series[-1].get("time"),
        }

    def _normalize_horizon_probabilities(self, horizon_probs: Any) -> dict[str, float]:
        normalized: dict[str, float] = {}
        if isinstance(horizon_probs, list):
            for item in horizon_probs:
                if not isinstance(item, dict):
                    continue
                hours = item.get("offset_hours")
                probability = item.get("probability")
                if hours is None or probability is None:
                    continue
                normalized[str(int(hours))] = float(probability)
        elif isinstance(horizon_probs, dict):
            for key, value in horizon_probs.items():
                if value is None:
                    continue
                normalized[str(key)] = float(value)
        return normalized

    async def _collect_recent_labs(self, patient_doc: dict, hours: int = 24) -> dict[str, dict[str, Any]]:
        his_pid = patient_doc.get("hisPid")
        if not his_pid:
            return {}
        since = datetime.now() - timedelta(hours=max(hours, 1))
        tracked = list(self._proactive_management_cfg().get("tracked_labs", ["lac", "cr", "wbc", "plt", "tbil", "inr"]))
        results: dict[str, dict[str, Any]] = {}
        for key in tracked:
            series = await self._get_lab_series(his_pid, str(key), since, limit=80)
            if not series:
                continue
            latest = series[-1]
            previous = series[-2] if len(series) >= 2 else None
            results[str(key)] = {
                "value": latest.get("value"),
                "time": latest.get("time"),
                "unit": latest.get("unit"),
                "delta": round(float(latest.get("value")) - float(previous.get("value")), 3) if previous and previous.get("value") is not None else None,
            }
        return results

    async def _get_active_drug_profile(self, pid, hours: int = 24) -> dict[str, Any]:
        docs = await self._get_recent_drug_docs_window(pid, hours=hours, limit=300)
        category_keywords = {
            "vasopressors": ["去甲肾上腺素", "肾上腺素", "多巴胺", "去氧肾上腺素", "血管加压素", "norepinephrine", "epinephrine"],
            "sedatives": ["丙泊酚", "咪达唑仑", "右美托咪定", "芬太尼", "propofol", "midazolam", "dexmedetomidine", "fentanyl"],
            "anticoagulants": ["肝素", "依诺肝素", "华法林", "利伐沙班", "阿哌沙班", "heparin", "enoxaparin"],
            "nephrotoxins": ["万古霉素", "阿米卡星", "庆大霉素", "两性霉素", "他克莫司", "vancomycin", "amikacin", "gentamicin"],
            "broad_antibiotics": ["美罗培南", "亚胺培南", "哌拉西林", "头孢哌酮", "meropenem", "imipenem", "piperacillin"],
        }
        summary: dict[str, Any] = {
            "recent_orders": [],
            "category_hits": {key: 0 for key in category_keywords},
            "active_flags": {},
        }
        for doc in docs[-20:]:
            summary["recent_orders"].append(
                {
                    "name": doc.get("drugName") or doc.get("orderName") or "",
                    "time": doc.get("_event_time"),
                    "route": doc.get("route") or doc.get("routeName") or "",
                }
            )
        for category, keywords in category_keywords.items():
            hits = [doc for doc in docs if any(keyword.lower() in self._drug_text(doc).lower() for keyword in keywords)]
            summary["category_hits"][category] = len(hits)
            summary["active_flags"][category] = bool(hits)
        return summary

    async def get_patient_trajectory(self, patient_doc: dict, pid, hours: int = 6) -> dict[str, Any]:
        since = datetime.now() - timedelta(hours=max(hours, 1))
        code_map = {
            "hr": "param_HR",
            "map": "param_ibp_m",
            "spo2": "param_spo2",
            "rr": "param_resp",
            "temp": str(self._cfg("vital_signs", "temperature", "code", default="param_T")),
        }
        map_series = await self._get_param_series_by_pid(pid, code_map["map"], since, prefer_device_types=["monitor"], limit=240)
        if not map_series:
            map_series = await self._get_param_series_by_pid(pid, "param_nibp_m", since, prefer_device_types=["monitor"], limit=240)
        series = {
            "hr": await self._get_param_series_by_pid(pid, code_map["hr"], since, prefer_device_types=["monitor"], limit=240),
            "map": map_series,
            "spo2": await self._get_param_series_by_pid(pid, code_map["spo2"], since, prefer_device_types=["monitor"], limit=240),
            "rr": await self._get_param_series_by_pid(pid, code_map["rr"], since, prefer_device_types=["monitor"], limit=240),
            "temp": await self._get_param_series_by_pid(pid, code_map["temp"], since, prefer_device_types=["monitor"], limit=240),
        }
        pid_str = self._pid_str(pid)
        recent_alerts = await self._recent_alerts(pid_str, since, max_records=40) if hasattr(self, "_recent_alerts") else []
        return {
            "hours": hours,
            "vitals": {key: self._series_snapshot(rows) for key, rows in series.items()},
            "recent_alert_count": len(recent_alerts),
            "high_alert_count": sum(1 for row in recent_alerts if str(row.get("severity") or "").lower() in {"high", "critical"}),
            "recent_alerts": [
                {
                    "alert_type": row.get("alert_type"),
                    "severity": row.get("severity"),
                    "created_at": row.get("created_at"),
                }
                for row in recent_alerts[:10]
            ],
        }

    def _build_proactive_recommendations(
        self,
        *,
        risk_profile: dict[str, Any],
        trajectory: dict[str, Any],
        labs_recent: dict[str, dict[str, Any]],
        drugs_active: dict[str, Any],
        devices_status: dict[str, Any],
    ) -> list[dict[str, Any]]:
        interventions: list[dict[str, Any]] = []

        def add_intervention(title: str, rationale: str, actions: list[str], priority: str = "high", owner: str = "doctor") -> None:
            interventions.append(
                {
                    "intervention_id": uuid4().hex[:12],
                    "title": title,
                    "priority": priority,
                    "owner": owner,
                    "rationale": rationale,
                    "actions": actions[:4],
                    "status": "pending",
                    "adopted": None,
                    "created_at": datetime.now(),
                    "baseline_probability": risk_profile.get("deterioration_probability"),
                }
            )

        vitals = trajectory.get("vitals") if isinstance(trajectory.get("vitals"), dict) else {}
        map_latest = ((vitals.get("map") or {}).get("latest"))
        spo2_latest = ((vitals.get("spo2") or {}).get("latest"))
        rr_latest = ((vitals.get("rr") or {}).get("latest"))
        lactate = (labs_recent.get("lac") or {}).get("value")

        if map_latest is not None and float(map_latest) < 65:
            add_intervention("循环灌注预防性评估", f"当前 MAP {map_latest} mmHg，存在低灌注进展风险。", ["复核容量反应性与液体平衡", "评估血管活性药物目标 MAP", "30-60 分钟内复测 MAP/乳酸"], priority="critical")
        if lactate is not None and float(lactate) >= 2.0:
            add_intervention("乳酸清除追踪", f"乳酸 {lactate}，提示组织灌注或代谢压力增加。", ["2-4 小时内复查乳酸", "结合 MAP、尿量与皮温评估灌注", "若持续上升请升级循环评估"])
        if spo2_latest is not None and float(spo2_latest) < 92:
            add_intervention("氧合支持优化", f"当前 SpO2 {spo2_latest}% ，需提前预防呼吸衰竭加重。", ["复核氧疗/通气参数", "评估痰液潴留与气道护理", "必要时复查血气或肺部影像"], owner="doctor+nurse")
        if rr_latest is not None and float(rr_latest) >= 28:
            add_intervention("呼吸功增加预警处理", f"呼吸频率 {rr_latest}/min，提示呼吸负荷增加。", ["评估疲劳、镇静及通气同步", "复核疼痛/焦虑与代谢性诱因", "加强 1-2 小时内趋势监测"])
        if bool((drugs_active.get("active_flags") or {}).get("vasopressors")):
            add_intervention("血流动力学目标管理", "近期存在升压药使用，需结合风险趋势做预防性剂量与灌注复盘。", ["确认当前目标 MAP 与去甲肾上腺素剂量", "联动尿量/乳酸/末梢灌注复评", "若需求上升请提前升级评估"])

        for device in (devices_status.get("devices") or []):
            if device.get("can_remove"):
                label = {"cvc": "中心静脉导管", "foley": "导尿管", "ett": "人工气道"}.get(str(device.get("type")), "侵入性装置")
                add_intervention(f"{label}去留复核", f"{label}已留置 {device.get('line_days')} 天，存在装置相关并发症风险。", ["核对当前适应证是否仍存在", "如无明确指征则尽早拔除", "拔除后继续追踪感染/排尿/气道结局"], priority="medium")

        if not interventions:
            add_intervention("强化趋势复盘", "已识别中低度风险累积，但暂未出现单一高危驱动项。", ["维持 2-4 小时重点趋势复盘", "复核新化验与新医嘱", "如风险继续上升则升级为主动干预"], priority="medium")
        return interventions[:6]

    async def _evaluate_proactive_risk(
        self,
        *,
        patient_doc: dict,
        pid,
        trajectory: dict[str, Any],
        labs_recent: dict[str, dict[str, Any]],
        drugs_active: dict[str, Any],
        devices_status: dict[str, Any],
    ) -> dict[str, Any]:
        cfg = self._proactive_management_cfg()
        forecast = await self._build_temporal_risk_forecast(patient_doc, pid, lookback_hours=int(cfg.get("lookback_hours", 6) or 6), horizons=(2, 4, 6), include_history=False)
        horizon_probs = self._normalize_horizon_probabilities(forecast.get("horizon_probabilities"))
        current_prob = float(forecast.get("current_probability") or 0.0)
        prob_4h = float(horizon_probs.get("4") or current_prob)
        probability = max(current_prob, prob_4h)
        drivers: list[dict[str, Any]] = []

        def add_driver(key: str, label: str, weight: float, evidence: str) -> None:
            nonlocal probability
            probability = self._clamp(probability + weight, 0.0, 0.98)
            drivers.append({"key": key, "label": label, "weight": round(weight, 3), "evidence": evidence})

        vitals = trajectory.get("vitals") if isinstance(trajectory.get("vitals"), dict) else {}
        map_row = vitals.get("map") or {}
        spo2_row = vitals.get("spo2") or {}
        rr_row = vitals.get("rr") or {}
        hr_row = vitals.get("hr") or {}

        if map_row.get("latest") is not None and float(map_row["latest"]) < 65:
            add_driver("map_low", "平均动脉压偏低", 0.10, f"MAP {map_row['latest']} mmHg")
        if map_row.get("delta") is not None and float(map_row["delta"]) <= -8:
            add_driver("map_downtrend", "血压呈下降趋势", 0.05, f"6h MAP变化 {map_row['delta']}")
        if spo2_row.get("latest") is not None and float(spo2_row["latest"]) < 92:
            add_driver("spo2_low", "氧合下降", 0.08, f"SpO2 {spo2_row['latest']}%")
        if rr_row.get("latest") is not None and float(rr_row["latest"]) >= 28:
            add_driver("rr_high", "呼吸频率增快", 0.06, f"RR {rr_row['latest']}/min")
        if hr_row.get("latest") is not None and float(hr_row["latest"]) >= 120:
            add_driver("hr_high", "心率增快", 0.04, f"HR {hr_row['latest']}/min")

        lactate = (labs_recent.get("lac") or {}).get("value")
        if lactate is not None and float(lactate) >= 4:
            add_driver("lactate_high", "乳酸明显升高", 0.15, f"乳酸 {lactate}")
        elif lactate is not None and float(lactate) >= 2:
            add_driver("lactate_up", "乳酸升高", 0.08, f"乳酸 {lactate}")

        creatinine = (labs_recent.get("cr") or {}).get("value")
        if creatinine is not None and float(creatinine) >= 150:
            add_driver("creatinine_high", "肾功能恶化风险", 0.05, f"肌酐 {creatinine}")

        platelets = (labs_recent.get("plt") or {}).get("value")
        if platelets is not None and float(platelets) < 100:
            add_driver("platelet_low", "血小板偏低", 0.05, f"PLT {platelets}")

        if bool((drugs_active.get("active_flags") or {}).get("vasopressors")):
            add_driver("vasopressor_active", "正在使用升压药", 0.08, "存在血流动力学支持需求")
        if bool((drugs_active.get("active_flags") or {}).get("nephrotoxins")):
            add_driver("nephrotoxin_active", "近期存在肾毒性药物", 0.03, "需结合肾功能动态管理")

        max_device_risk = str(devices_status.get("max_risk") or "low").lower()
        if max_device_risk == "high":
            add_driver("device_high_risk", "侵入性装置风险高", 0.06, "需尽早完成去留评估")
        elif max_device_risk == "medium":
            add_driver("device_medium_risk", "侵入性装置风险中等", 0.03, "建议完成装置必要性复核")

        high_alert_count = int(trajectory.get("high_alert_count") or 0)
        if high_alert_count >= 3:
            add_driver("alert_cluster", "近期高等级告警聚集", 0.08, f"6h 内高等级告警 {high_alert_count} 条")
        elif high_alert_count >= 1:
            add_driver("recent_high_alert", "近期存在高等级告警", 0.04, f"6h 内高等级告警 {high_alert_count} 条")

        probability = round(self._clamp(probability, 0.0, 0.98), 4)
        return {
            "generated_at": datetime.now(),
            "deterioration_probability": probability,
            "risk_level": self._risk_level_from_probability(probability),
            "forecast": {
                "current_probability": current_prob,
                "horizon_probabilities": horizon_probs,
                "summary": forecast.get("summary") or "",
                "organ_risk_scores": forecast.get("organ_risk_scores") or {},
                "top_contributors": forecast.get("top_contributors") or [],
            },
            "drivers": drivers[:8],
        }

    async def generate_proactive_plan(self, patient_doc: dict, risk_profile: dict[str, Any]) -> dict[str, Any]:
        pid = patient_doc.get("_id")
        cfg = self._proactive_management_cfg()
        trajectory = await self.get_patient_trajectory(patient_doc, pid, hours=int(cfg.get("trajectory_hours", 6) or 6))
        labs_recent = await self._collect_recent_labs(patient_doc, hours=int(cfg.get("lab_window_hours", 24) or 24))
        drugs_active = await self._get_active_drug_profile(pid, hours=int(cfg.get("drug_window_hours", 24) or 24))
        devices_status = await self._device_management_summary(patient_doc)
        interventions = self._build_proactive_recommendations(risk_profile=risk_profile, trajectory=trajectory, labs_recent=labs_recent, drugs_active=drugs_active, devices_status=devices_status)
        summary = f"未来 2-6 小时恶化概率约 {round(float(risk_profile.get('deterioration_probability') or 0) * 100, 1)}%，建议优先处理 {interventions[0].get('title') if interventions else '风险复盘'}。"
        return {
            "plan_id": uuid4().hex[:16],
            "patient_id": self._pid_str(pid),
            "generated_at": datetime.now(),
            "risk_profile": risk_profile,
            "trajectory": trajectory,
            "labs_recent": labs_recent,
            "drugs_active": drugs_active,
            "devices_status": devices_status,
            "interventions": interventions,
            "summary": summary,
            "status": "active",
        }

    async def _persist_proactive_management_plan(self, patient_doc: dict, plan: dict[str, Any], now: datetime) -> dict[str, Any]:
        cfg = self._proactive_management_cfg()
        persist_window_minutes = int(cfg.get("persist_window_minutes", 20) or 20)
        pid_str = str(plan.get("patient_id") or "")
        payload = {
            "patient_id": pid_str,
            "patient_name": patient_doc.get("name"),
            "bed": patient_doc.get("hisBed") or patient_doc.get("bed"),
            "dept": patient_doc.get("dept") or patient_doc.get("hisDept"),
            "score_type": "proactive_management",
            "score": plan.get("risk_profile", {}).get("deterioration_probability"),
            "risk_level": plan.get("risk_profile", {}).get("risk_level"),
            "plan_id": plan.get("plan_id"),
            "summary": plan.get("summary"),
            "risk_profile": plan.get("risk_profile"),
            "trajectory": plan.get("trajectory"),
            "labs_recent": plan.get("labs_recent"),
            "drugs_active": plan.get("drugs_active"),
            "devices_status": plan.get("devices_status"),
            "interventions": plan.get("interventions") or [],
            "status": plan.get("status") or "active",
            "calc_time": now,
            "updated_at": now,
            "month": now.strftime("%Y-%m"),
            "day": now.strftime("%Y-%m-%d"),
        }
        latest = await self.db.col("score_records").find_one({"patient_id": pid_str, "score_type": "proactive_management", "calc_time": {"$gte": now - timedelta(minutes=max(persist_window_minutes, 1))}}, sort=[("calc_time", -1)])
        if latest:
            await self.db.col("score_records").update_one({"_id": latest["_id"]}, {"$set": payload})
            payload["_id"] = latest["_id"]
        else:
            res = await self.db.col("score_records").insert_one(payload)
            payload["_id"] = res.inserted_id
        return payload

    async def _latest_proactive_management_record(self, patient_id: str, hours: int = 24) -> dict | None:
        since = datetime.now() - timedelta(hours=max(hours, 1))
        return await self.db.col("score_records").find_one({"patient_id": str(patient_id), "score_type": "proactive_management", "calc_time": {"$gte": since}}, sort=[("calc_time", -1)])

    async def continuous_risk_assessment(self, patient_id) -> dict[str, Any] | None:
        patient_doc, pid_str = await self._load_patient(patient_id)
        if not patient_doc:
            return None
        cfg = self._proactive_management_cfg()
        trajectory = await self.get_patient_trajectory(patient_doc, patient_doc.get("_id"), hours=int(cfg.get("trajectory_hours", 6) or 6))
        labs_recent = await self._collect_recent_labs(patient_doc, hours=int(cfg.get("lab_window_hours", 24) or 24))
        drugs_active = await self._get_active_drug_profile(patient_doc.get("_id"), hours=int(cfg.get("drug_window_hours", 24) or 24))
        devices_status = await self._device_management_summary(patient_doc)
        risk_profile = await self._evaluate_proactive_risk(patient_doc=patient_doc, pid=patient_doc.get("_id"), trajectory=trajectory, labs_recent=labs_recent, drugs_active=drugs_active, devices_status=devices_status)
        trigger_probability = float(cfg.get("trigger_probability", 0.3) or 0.3)
        if float(risk_profile.get("deterioration_probability") or 0.0) < trigger_probability:
            return {
                "patient_id": pid_str,
                "generated_at": datetime.now(),
                "risk_profile": risk_profile,
                "trajectory": trajectory,
                "labs_recent": labs_recent,
                "drugs_active": drugs_active,
                "devices_status": devices_status,
                "interventions": [],
                "summary": "当前未达到主动管理触发阈值，建议继续连续监测。",
                "status": "monitoring",
            }
        return await self.generate_proactive_plan(patient_doc, risk_profile)

    async def track_intervention_effectiveness(
        self,
        patient_id,
        intervention_id: str,
        *,
        record_id=None,
        status: str | None = None,
        adopted: bool | None = None,
        note: str | None = None,
        actor: str | None = None,
    ) -> dict[str, Any] | None:
        patient_doc, pid_str = await self._load_patient(patient_id)
        if not patient_doc:
            return None
        record = await self.db.col("score_records").find_one({"_id": record_id, "patient_id": pid_str, "score_type": "proactive_management"}) if record_id is not None else None
        if not record:
            record = await self._latest_proactive_management_record(pid_str, hours=72)
        if not record:
            return None

        interventions = list(record.get("interventions") or [])
        target = next((item for item in interventions if str(item.get("intervention_id") or "") == str(intervention_id)), None)
        if target is None:
            return None

        now = datetime.now()
        if status:
            target["status"] = str(status).strip().lower()
        if adopted is not None:
            target["adopted"] = bool(adopted)
            target["adopted_at"] = now
        if note:
            target["note"] = str(note).strip()
        if actor:
            target["actor"] = str(actor).strip()

        latest_plan = await self.continuous_risk_assessment(pid_str)
        latest_probability = float((((latest_plan or {}).get("risk_profile") or {}).get("deterioration_probability")) or 0.0)
        baseline_probability = float(target.get("baseline_probability") or record.get("score") or latest_probability)
        delta = round(latest_probability - baseline_probability, 4)
        effect = "improving" if delta <= -0.08 else ("worsening" if delta >= 0.08 else "stable")
        target["effectiveness"] = {
            "evaluated_at": now,
            "baseline_probability": baseline_probability,
            "latest_probability": latest_probability,
            "delta": delta,
            "effect": effect,
        }

        await self.db.col("score_records").update_one({"_id": record["_id"]}, {"$set": {"interventions": interventions, "updated_at": now, "last_intervention_feedback_at": now}})
        return await self.db.col("score_records").find_one({"_id": record["_id"]})

    async def scan_proactive_management(self) -> None:
        from .scanner_proactive_management import ProactiveManagementScanner

        await ProactiveManagementScanner(self).scan()
