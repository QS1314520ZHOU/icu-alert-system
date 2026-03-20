"""影像学报告文本提取与告警关联。"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any


class ImagingReportAnalyzerMixin:
    def _imaging_report_cfg(self) -> dict[str, Any]:
        cfg = self.config.yaml_cfg.get("alert_engine", {}).get("imaging_report_analyzer", {})
        return cfg if isinstance(cfg, dict) else {}

    def _imaging_report_time(self, doc: dict[str, Any]) -> datetime | None:
        if not isinstance(doc, dict):
            return None
        for key in ("reportTime", "authTime", "examTime", "collectTime", "requestTime", "time"):
            value = doc.get(key)
            if isinstance(value, datetime):
                return value
            if value in (None, ""):
                continue
            try:
                return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except Exception:
                continue
        return None

    def _imaging_report_title(self, doc: dict[str, Any]) -> str:
        return " / ".join(
            [
                str(doc.get("examName") or "").strip(),
                str(doc.get("title") or "").strip(),
                str(doc.get("bodyParts") or "").strip(),
            ]
        ).strip(" /")

    def _patient_imaging_window(self, patient_doc: dict[str, Any], *, fallback_hours: int) -> tuple[datetime | None, datetime | None]:
        admission = None
        discharge = None
        for key in ("icuAdmissionTime", "admissionTime", "admitTime", "inTime", "createTime"):
            value = patient_doc.get(key)
            if isinstance(value, datetime):
                admission = value
                break
            if value in (None, ""):
                continue
            try:
                admission = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                break
            except Exception:
                continue
        for key in ("dischargeTime", "outTime", "leaveTime", "deathTime", "updatedAt", "updateTime"):
            value = patient_doc.get(key)
            if isinstance(value, datetime):
                discharge = value
                break
            if value in (None, ""):
                continue
            try:
                discharge = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                break
            except Exception:
                continue
        now = datetime.now()
        if admission is None:
            return now - timedelta(hours=max(1, fallback_hours)), now
        start = admission - timedelta(hours=48)
        if discharge is None:
            return start, now + timedelta(hours=12)
        return start, discharge + timedelta(hours=24)

    def _imaging_report_text(self, doc: dict[str, Any]) -> str:
        return "\n".join(
            str(doc.get(key) or "").strip()
            for key in ("conclusion", "diagnose", "reportDesc")
            if str(doc.get(key) or "").strip()
        ).strip()

    def _is_chest_imaging_report(self, doc: dict[str, Any]) -> bool:
        haystack = " ".join(
            str(doc.get(key) or "")
            for key in ("examName", "title", "bodyParts", "conclusion", "diagnose", "reportDesc")
        ).lower()
        if not haystack:
            return False
        include_keywords = [
            "胸",
            "肺",
            "胸片",
            "床旁",
            "x线",
            "dr",
            "ct",
            "胸腔",
            "胸膜",
            "气胸",
        ]
        exclude_keywords = [
            "心电事件",
            "holter",
            "动态心电",
            "胃镜",
            "肠镜",
        ]
        if any(keyword in haystack for keyword in exclude_keywords):
            return False
        if not any(keyword in haystack for keyword in include_keywords):
            return False

        preferred_modalities = [
            "胸片",
            "床旁胸片",
            "胸部dr",
            "dr",
            "x线",
            "胸部ct",
            "ct平扫",
            "胸腔积液彩超",
            "胸部彩超",
            "肺部彩超",
            "胸部超声",
            "胸腔超声",
        ]
        preferred_regions = [
            "胸部",
            "胸腔",
            "肺",
            "胸膜",
        ]
        exam_name = " ".join(str(doc.get(key) or "") for key in ("examName", "title")).lower()
        body_parts = str(doc.get("bodyParts") or "").lower()
        if any(item in exam_name for item in preferred_modalities):
            return True
        if any(item in body_parts for item in preferred_regions) and any(item in haystack for item in ("dr", "x线", "ct", "超声", "彩超", "床旁")):
            return True
        return "胸腔积液" in exam_name or "胸部ct平扫" in exam_name

    def _split_imaging_sentences(self, text: str) -> list[str]:
        if not text:
            return []
        chunks = re.split(r"[\r\n]+|[。；;]", text)
        sentences: list[str] = []
        for chunk in chunks:
            sentence = re.sub(r"\s+", " ", str(chunk or "")).strip(" |")
            if len(sentence) < 2:
                continue
            sentences.append(sentence)
        return sentences

    def _imaging_signal_specs(self) -> list[dict[str, Any]]:
        return [
            {
                "code": "pulmonary_infiltrate_progression",
                "label": "肺部渗出/浸润较前增多",
                "severity": "high",
                "module_tags": ["ards", "fluid"],
                "keywords": [],
                "suggestion": "建议结合氧合、肺顺应性和感染/容量状态复核肺部恶化原因。",
            },
            {
                "code": "pulmonary_infiltrate_present",
                "label": "肺部渗出/浸润影",
                "severity": "warning",
                "module_tags": ["ards"],
                "keywords": [],
                "suggestion": "建议结合氧合与通气支持强度判断是否存在 ARDS / 肺部感染进展。",
            },
            {
                "code": "pneumothorax",
                "label": "气胸",
                "severity": "critical",
                "module_tags": ["ards", "device"],
                "keywords": [
                    "气胸",
                    "液气胸",
                ],
                "suggestion": "建议立即结合呼吸机参数、床旁超声和体征评估是否需紧急处置。",
            },
            {
                "code": "pleural_effusion_progression",
                "label": "胸腔积液增加",
                "severity": "high",
                "module_tags": ["fluid", "ards"],
                "keywords": [],
                "suggestion": "建议结合液体平衡、超声和氧合变化评估容量负荷与引流需求。",
            },
            {
                "code": "pleural_effusion_present",
                "label": "胸腔积液",
                "severity": "warning",
                "module_tags": ["fluid"],
                "keywords": [],
                "suggestion": "建议结合液体平衡和呼吸状态持续复评胸腔积液变化。",
            },
        ]

    def _match_line_malposition(self, sentence: str) -> bool:
        text = str(sentence or "").lower()
        if not text:
            return False
        line_terms = ["导管", "picc", "cvc", "中心静脉", "胃管", "气管插管", "引流管", "胸管", "导丝", "尖端", "管端"]
        issue_terms = ["位置异常", "位置不佳", "位置偏高", "位置偏低", "过深", "过浅", "异位", "误入", "需调整", "建议调整", "退出", "重新定位", "不在位"]
        return any(term in text for term in line_terms) and any(term in text for term in issue_terms)

    def _match_pleural_effusion_present(self, sentence: str) -> bool:
        text = str(sentence or "").lower()
        if not text:
            return False
        direct_terms = ["胸腔积液", "胸水", "液气胸", "胸膜腔积液"]
        if any(term in text for term in direct_terms):
            return True
        if "心包积液" in text:
            return False
        return "积液" in text and any(term in text for term in ["胸腔", "胸膜", "胸部"])

    def _match_pleural_effusion_progression(self, sentence: str) -> bool:
        text = str(sentence or "").lower()
        progression_terms = ["较前增多", "较前增加", "增多", "增加", "加重", "进展"]
        return self._match_pleural_effusion_present(text) and any(term in text for term in progression_terms)

    def _match_pulmonary_infiltrate_present(self, sentence: str) -> bool:
        text = str(sentence or "").lower()
        parenchymal_terms = ["渗出", "浸润", "斑片影", "条絮状", "磨玻璃", "实变", "肺炎", "炎症", "肺水肿", "不张"]
        return any(term in text for term in parenchymal_terms) and any(term in text for term in ["肺", "双肺", "肺部", "肺野", "下叶", "上叶"])

    def _match_pulmonary_infiltrate_progression(self, sentence: str) -> bool:
        text = str(sentence or "").lower()
        progression_terms = ["较前增多", "较前增加", "增多", "增加", "加重", "进展"]
        return self._match_pulmonary_infiltrate_present(text) and any(term in text for term in progression_terms)

    def _match_imaging_signal(self, code: str, sentence: str, keywords: list[str]) -> bool:
        if code == "pleural_effusion_present":
            return self._match_pleural_effusion_present(sentence)
        if code == "pleural_effusion_progression":
            return self._match_pleural_effusion_progression(sentence)
        if code == "pulmonary_infiltrate_present":
            return self._match_pulmonary_infiltrate_present(sentence)
        if code == "pulmonary_infiltrate_progression":
            return self._match_pulmonary_infiltrate_progression(sentence)
        lower = str(sentence or "").lower()
        return any(keyword in lower for keyword in keywords)

    async def _fetch_recent_chest_imaging_reports(
        self,
        patient_doc: dict[str, Any],
        *,
        hours: int = 96,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        his_pid = str(patient_doc.get("hisPid") or patient_doc.get("hisPID") or "").strip()
        if not his_pid:
            return []
        window_start, window_end = self._patient_imaging_window(patient_doc, fallback_hours=hours)
        report_time_query: dict[str, Any] = {}
        if window_start is not None:
            report_time_query["$gte"] = window_start
        if window_end is not None:
            report_time_query["$lte"] = window_end
        query: dict[str, Any] = {"pid": his_pid}
        if report_time_query:
            query["reportTime"] = report_time_query
        cursor = self.db.dc_col("VI_ICU_REPORT").find(
            query
        ).sort("reportTime", -1).limit(max(1, limit))
        docs = [doc async for doc in cursor]
        return [doc for doc in docs if self._is_chest_imaging_report(doc)]

    def _select_imaging_signals(
        self,
        analysis: dict[str, Any] | None,
        *,
        module_tags: set[str],
        max_items: int = 3,
    ) -> list[dict[str, Any]]:
        signals = (analysis or {}).get("matched_signals") if isinstance((analysis or {}).get("matched_signals"), list) else []
        selected: list[dict[str, Any]] = []
        for row in signals:
            tags = {str(tag).strip() for tag in (row.get("module_tags") or []) if str(tag).strip()}
            if tags.intersection(module_tags):
                selected.append(row)
        return selected[:max(1, max_items)]

    def _format_imaging_evidence_lines(self, signals: list[dict[str, Any]], *, max_items: int = 3) -> list[str]:
        lines: list[str] = []
        for row in signals[:max(1, max_items)]:
            sentence = str(row.get("sentence") or row.get("label") or "").strip()
            title = str(row.get("exam_name") or "影像报告").strip()
            if sentence:
                lines.append(f"影像：{title}提示{sentence}")
        return lines

    def _build_imaging_summary(self, signals: list[dict[str, Any]]) -> str:
        labels = [str(item.get("label") or "").strip() for item in signals if str(item.get("label") or "").strip()]
        if not labels:
            return "未见明确胸部影像异常线索"
        deduped = list(dict.fromkeys(labels))
        return "影像提示" + "、".join(deduped[:4])

    async def analyze_imaging_reports(
        self,
        patient_doc: dict[str, Any],
        patient_id: str,
        *,
        hours: int = 96,
        now: datetime | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        now = now or datetime.now()
        reports = await self._fetch_recent_chest_imaging_reports(patient_doc, hours=hours, limit=12)
        matched: list[dict[str, Any]] = []
        seen_pairs: set[tuple[str, str]] = set()
        catalog = self._imaging_signal_specs()

        for report in reports[:10]:
            report_id = str(report.get("reportID") or report.get("orderID") or report.get("_id") or "")
            report_time = self._imaging_report_time(report)
            exam_name = self._imaging_report_title(report) or "胸部影像"
            for sentence in self._split_imaging_sentences(self._imaging_report_text(report)):
                lower = sentence.lower()
                for spec in catalog:
                    if self._match_imaging_signal(spec["code"], lower, spec["keywords"]):
                        key = (spec["code"], sentence)
                        if key in seen_pairs:
                            continue
                        seen_pairs.add(key)
                        matched.append(
                            {
                                "code": spec["code"],
                                "label": spec["label"],
                                "severity": spec["severity"],
                                "sentence": sentence[:160],
                                "report_time": report_time,
                                "report_id": report_id,
                                "exam_name": exam_name,
                                "module_tags": spec["module_tags"],
                                "suggestion": spec["suggestion"],
                            }
                        )

                if self._match_line_malposition(sentence):
                    key = ("line_position_abnormal", sentence)
                    if key not in seen_pairs:
                        seen_pairs.add(key)
                        matched.append(
                            {
                                "code": "line_position_abnormal",
                                "label": "导管位置异常",
                                "severity": "high",
                                "sentence": sentence[:160],
                                "report_time": report_time,
                                "report_id": report_id,
                                "exam_name": exam_name,
                                "module_tags": ["device"],
                                "suggestion": "建议尽快结合床旁定位/复查影像确认导管末端位置并调整。",
                            }
                        )

        severity_rank = {"critical": 3, "high": 2, "warning": 1}
        matched.sort(
            key=lambda row: (
                -(severity_rank.get(str(row.get("severity") or ""), 0)),
                row.get("report_time") or datetime.min,
            ),
            reverse=False,
        )
        matched = sorted(
            matched,
            key=lambda row: (
                row.get("report_time") or datetime.min,
                severity_rank.get(str(row.get("severity") or ""), 0),
            ),
            reverse=True,
        )[:12]

        result = {
            "patient_id": patient_id,
            "patient_name": patient_doc.get("name") or patient_doc.get("hisName"),
            "bed": patient_doc.get("hisBed") or patient_doc.get("bed"),
            "dept": patient_doc.get("dept") or patient_doc.get("hisDept"),
            "score_type": "imaging_report_signal_analysis",
            "analysis_window_hours": hours,
            "report_count": len(reports),
            "latest_report_time": self._imaging_report_time(reports[0]) if reports else None,
            "summary": self._build_imaging_summary(matched),
            "matched_signals": matched,
            "signal_labels": list(dict.fromkeys(str(item.get("label") or "") for item in matched if str(item.get("label") or "").strip()))[:8],
            "suggestions": list(dict.fromkeys(str(item.get("suggestion") or "") for item in matched if str(item.get("suggestion") or "").strip()))[:6],
            "report_titles": list(dict.fromkeys(self._imaging_report_title(doc) for doc in reports if self._imaging_report_title(doc)))[:6],
            "calc_time": now,
            "updated_at": now,
            "month": now.strftime("%Y-%m"),
            "day": now.strftime("%Y-%m-%d"),
        }

        if persist:
            latest = await self.db.col("score_records").find_one(
                {
                    "patient_id": patient_id,
                    "score_type": "imaging_report_signal_analysis",
                    "calc_time": {"$gte": now - timedelta(hours=8)},
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

    async def latest_imaging_report_analysis(
        self,
        patient_id: str,
        *,
        hours: int = 96,
    ) -> dict[str, Any] | None:
        since = datetime.now() - timedelta(hours=max(1, hours))
        return await self.db.col("score_records").find_one(
            {
                "patient_id": patient_id,
                "score_type": "imaging_report_signal_analysis",
                "calc_time": {"$gte": since},
            },
            sort=[("calc_time", -1)],
        )

    async def get_imaging_report_analysis(
        self,
        patient_doc: dict[str, Any],
        patient_id: str,
        *,
        hours: int = 96,
        max_age_hours: int = 8,
        persist_if_refresh: bool = False,
    ) -> dict[str, Any]:
        cached = await self.latest_imaging_report_analysis(patient_id, hours=max(hours, max_age_hours))
        if cached:
            calc_time = cached.get("calc_time")
            if isinstance(calc_time, datetime) and calc_time >= datetime.now() - timedelta(hours=max(1, max_age_hours)):
                return cached
        return await self.analyze_imaging_reports(
            patient_doc,
            patient_id,
            hours=hours,
            now=datetime.now(),
            persist=persist_if_refresh,
        )

    async def _link_imaging_findings_to_active_alerts(
        self,
        *,
        patient_id: str,
        analysis: dict[str, Any],
        now: datetime | None = None,
    ) -> int:
        now = now or datetime.now()
        if not ((analysis or {}).get("matched_signals") or []):
            return 0
        mapping = {
            "ards": {"ards"},
            "fluid_balance": {"fluid"},
            "fluid_deresuscitation": {"fluid"},
            "fluid_responsiveness_lost": {"fluid"},
            "cvc_review": {"device"},
            "foley_review": {"device"},
            "ett_extubation_delay": {"device"},
            "device_position_abnormal": {"device"},
        }
        updated = 0
        cursor = self.db.col("alert_records").find(
            {
                "patient_id": patient_id,
                "is_active": True,
                "created_at": {"$gte": now - timedelta(hours=96)},
                "alert_type": {"$in": list(mapping.keys())},
            }
        )
        async for alert in cursor:
            tags = mapping.get(str(alert.get("alert_type") or ""), set())
            selected = self._select_imaging_signals(analysis, module_tags=tags, max_items=3)
            if not selected:
                continue
            evidence_lines = self._format_imaging_evidence_lines(selected, max_items=3)
            extra = dict(alert.get("extra") or {}) if isinstance(alert.get("extra"), dict) else {}
            existing_ids = {
                str(item.get("report_id") or "")
                for item in ((extra.get("imaging_findings") or {}).get("matched_signals") or [])
                if isinstance(item, dict)
            }
            new_ids = {str(item.get("report_id") or "") for item in selected if str(item.get("report_id") or "")}
            if existing_ids and new_ids and new_ids.issubset(existing_ids):
                continue

            explanation = dict(alert.get("explanation") or {}) if isinstance(alert.get("explanation"), dict) else {}
            evidence = explanation.get("evidence") if isinstance(explanation.get("evidence"), list) else []
            merged_evidence = list(dict.fromkeys([*(str(item).strip() for item in evidence if str(item).strip()), *evidence_lines]))[:6]
            if explanation:
                explanation["evidence"] = merged_evidence
                explanation["text"] = self._format_structured_explanation_text(explanation)

            extra["imaging_findings"] = {
                "summary": self._build_imaging_summary(selected),
                "matched_signals": selected,
                "linked_at": now,
            }
            update_doc: dict[str, Any] = {"extra": extra, "updated_at": now}
            if explanation:
                update_doc["explanation"] = explanation
                update_doc["explanation_text"] = explanation.get("text")
            await self.db.col("alert_records").update_one({"_id": alert["_id"]}, {"$set": update_doc})
            updated += 1
        return updated

    async def scan_imaging_report_signals(self) -> list[dict[str, Any]]:
        now = datetime.now()
        cfg = self._imaging_report_cfg()
        hours = int(cfg.get("analysis_window_hours", 96) or 96)
        rows: list[dict[str, Any]] = []
        linked_alerts = 0
        cursor = self.db.col("patient").find(
            self._active_patient_query(),
            {"_id": 1, "name": 1, "hisName": 1, "hisPid": 1, "hisPID": 1, "hisBed": 1, "bed": 1, "dept": 1, "hisDept": 1},
        )
        async for patient_doc in cursor:
            pid = str(patient_doc.get("_id") or "")
            if not pid:
                continue
            try:
                analysis = await self.analyze_imaging_reports(patient_doc, pid, hours=hours, now=now, persist=True)
                rows.append(analysis)
                linked_alerts += await self._link_imaging_findings_to_active_alerts(patient_id=pid, analysis=analysis, now=now)
            except Exception:
                continue
        if linked_alerts > 0:
            self._log_info("影像告警关联", linked_alerts)
        return rows
