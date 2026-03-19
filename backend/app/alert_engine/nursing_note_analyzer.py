"""Heuristic nursing note analysis for early clinical signal extraction."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


class NursingNoteAnalyzerMixin:
    def _nursing_note_cfg(self) -> dict[str, Any]:
        cfg = self.config.yaml_cfg.get("alert_engine", {}).get("nursing_note_analyzer", {})
        return cfg if isinstance(cfg, dict) else {}

    def _nursing_note_level(self, score: float | int | None) -> str:
        value = float(score or 0.0)
        if value >= 8:
            return "critical"
        if value >= 5:
            return "high"
        if value >= 3:
            return "medium"
        return "low"

    def _nursing_note_signal_catalog(self) -> list[dict[str, Any]]:
        return [
            {
                "code": "perf_clammy_pale",
                "label": "低灌注前驱信号",
                "domain": "hemodynamic",
                "weight": 3.0,
                "severity": "high",
                "keywords": ["出冷汗", "冷汗", "面色苍白", "四肢湿冷", "末梢凉", "皮肤湿冷", "灌注差"],
                "suggestion": "尽快复核 MAP、末梢灌注、尿量与乳酸趋势。",
            },
            {
                "code": "mental_status_change",
                "label": "意识状态波动",
                "domain": "neurologic",
                "weight": 2.5,
                "severity": "medium",
                "keywords": ["烦躁", "嗜睡", "意识模糊", "定向力差", "反应迟钝", "谵妄", "躁动", "意识波动"],
                "suggestion": "结合 GCS/RASS/CAM-ICU 复核神经系统与镇静镇痛目标。",
            },
            {
                "code": "resp_distress_note",
                "label": "呼吸窘迫文字线索",
                "domain": "respiratory",
                "weight": 2.5,
                "severity": "high",
                "keywords": ["呼吸急促", "憋喘", "三凹征", "紫绀", "端坐呼吸", "喘憋", "气促明显"],
                "suggestion": "联动血氧、呼吸频率、血气和氧疗/通气支持强度。",
            },
            {
                "code": "skin_breakdown",
                "label": "皮肤完整性风险",
                "domain": "nursing",
                "weight": 1.5,
                "severity": "medium",
                "keywords": ["压红", "压疮", "皮肤破损", "渗液", "水肿明显", "皮肤完整性受损"],
                "suggestion": "复核翻身减压、皮肤保护和营养支持方案。",
            },
            {
                "code": "family_distress",
                "label": "家属沟通异常",
                "domain": "communication",
                "weight": 1.0,
                "severity": "low",
                "keywords": ["家属焦虑", "家属担忧", "拒绝", "沟通困难", "依从性差", "配合欠佳"],
                "suggestion": "尽快补充沟通记录，必要时联动医生完成风险告知。",
            },
            {
                "code": "pain_escalation",
                "label": "疼痛/舒适度恶化",
                "domain": "comfort",
                "weight": 1.5,
                "severity": "medium",
                "keywords": ["疼痛加重", "疼痛明显", "无法耐受", "不适明显", "呻吟", "疼痛评分高"],
                "suggestion": "复核镇痛策略与侵袭性操作后评估频次。",
            },
        ]

    async def analyze_nursing_notes(
        self,
        patient_doc: dict[str, Any],
        patient_id: str,
        *,
        hours: int = 12,
        now: datetime | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        now = now or datetime.now()
        context = {}
        if hasattr(self, "_collect_nursing_context"):
            try:
                context = await self._collect_nursing_context(patient_doc, patient_id, hours=hours)
            except Exception:
                context = {}
        records = context.get("records") if isinstance(context.get("records"), list) else []
        plan_info = context.get("plans") if isinstance(context.get("plans"), dict) else {}
        matched: list[dict[str, Any]] = []
        score = 0.0
        record_hits: dict[str, set[str]] = {}
        catalog = self._nursing_note_signal_catalog()

        for row in records[:10]:
            text = str(row.get("text") or "").strip()
            if not text:
                continue
            lower = text.lower()
            row_time = row.get("time")
            for spec in catalog:
                if any(str(keyword).lower() in lower for keyword in spec["keywords"]):
                    bucket = record_hits.setdefault(spec["code"], set())
                    if text in bucket:
                        continue
                    bucket.add(text)
                    score += float(spec["weight"])
                    matched.append(
                        {
                            "code": spec["code"],
                            "label": spec["label"],
                            "domain": spec["domain"],
                            "severity": spec["severity"],
                            "weight": spec["weight"],
                            "text": text[:160],
                            "time": row_time,
                            "suggestion": spec["suggestion"],
                        }
                    )

        pending_count = int(plan_info.get("pending_count") or 0)
        delayed_count = int(plan_info.get("delayed_count") or 0)
        if delayed_count > 0:
            score += min(2.0, delayed_count * 0.5)
            matched.append(
                {
                    "code": "delayed_nursing_execution",
                    "label": "护理执行延迟",
                    "domain": "workflow",
                    "severity": "medium" if delayed_count < 3 else "high",
                    "weight": min(2.0, delayed_count * 0.5),
                    "text": f"近 {hours}h 延迟执行 {delayed_count} 条",
                    "time": now,
                    "suggestion": "复核护理任务分配与优先级，必要时补充人力。",
                }
            )

        level = self._nursing_note_level(score)
        summary = "未见显著护理文本异常信号"
        if matched:
            labels = "、".join(dict.fromkeys(item["label"] for item in matched[:4]))
            summary = f"护理记录提示 {labels}"
        result = {
            "patient_id": patient_id,
            "patient_name": patient_doc.get("name") or patient_doc.get("hisName"),
            "bed": patient_doc.get("hisBed") or patient_doc.get("bed"),
            "dept": patient_doc.get("dept") or patient_doc.get("hisDept"),
            "score_type": "nursing_note_signal_analysis",
            "analysis_window_hours": hours,
            "signal_score": round(score, 2),
            "risk_level": level,
            "summary": summary,
            "matched_signals": matched[:12],
            "signal_labels": list(dict.fromkeys(item["label"] for item in matched))[:8],
            "suggestions": list(dict.fromkeys(item["suggestion"] for item in matched if str(item.get("suggestion") or "").strip()))[:6],
            "nursing_plan_summary": {
                "pending_count": pending_count,
                "delayed_count": delayed_count,
                "planned_count": int(plan_info.get("planned_count") or 0),
                "executed_count": int(plan_info.get("executed_count") or 0),
            },
            "calc_time": now,
            "updated_at": now,
            "month": now.strftime("%Y-%m"),
            "day": now.strftime("%Y-%m-%d"),
        }
        if persist:
            latest = await self.db.col("score_records").find_one(
                {
                    "patient_id": patient_id,
                    "score_type": "nursing_note_signal_analysis",
                    "calc_time": {"$gte": now - timedelta(minutes=90)},
                },
                sort=[("calc_time", -1)],
            )
            if latest:
                await self.db.col("score_records").update_one({"_id": latest["_id"]}, {"$set": result})
                result["_id"] = latest["_id"]
            else:
                insert = await self.db.col("score_records").insert_one(result)
                result["_id"] = insert.inserted_id
        return result

    async def latest_nursing_note_analysis(self, patient_id: str, *, hours: int = 24) -> dict[str, Any] | None:
        since = datetime.now() - timedelta(hours=max(1, hours))
        return await self.db.col("score_records").find_one(
            {
                "patient_id": patient_id,
                "score_type": "nursing_note_signal_analysis",
                "calc_time": {"$gte": since},
            },
            sort=[("calc_time", -1)],
        )

    async def scan_nursing_note_signals(self) -> list[dict[str, Any]]:
        now = datetime.now()
        hours = int(self._nursing_note_cfg().get("analysis_window_hours", 12) or 12)
        rows: list[dict[str, Any]] = []
        cursor = self.db.col("patient").find({"status": "admitted"}, {"_id": 1, "name": 1, "hisName": 1, "hisBed": 1, "bed": 1, "dept": 1, "hisDept": 1})
        async for patient_doc in cursor:
            pid = str(patient_doc.get("_id") or "")
            if not pid:
                continue
            try:
                rows.append(await self.analyze_nursing_notes(patient_doc, pid, hours=hours, now=now, persist=True))
            except Exception:
                continue
        return rows
