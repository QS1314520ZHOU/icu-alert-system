"""ICU senior physician ward round document generation service."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from bson import ObjectId

from app.services.llm_runtime import LLMRuntimeUnavailableError, call_llm_chat

logger = logging.getLogger("icu-alert")
API_TZ = ZoneInfo("Asia/Shanghai")

WARD_ROUND_PROMPT_VERSION = "ward_round_v2"

ROUND_LEVELS = {
    "attending_first": "主治医师首次查房",
    "attending": "主治医师查房",
    "associate_chief": "副主任医师查房",
    "chief": "主任医师查房",
}

WARD_ROUND_SYSTEM_PROMPT = """你是三甲医院重症医学科（ICU）的上级医师，负责撰写"上级医师查房记录"。
你的输出将作为正式病历草稿，由执业医师审核签字后归档。撰写依据为卫生部《病历书写基本规范》第二十二条：上级医师查房记录应包含对病情、诊断、鉴别诊断、当前诊疗措施疗效的分析，以及下一步诊疗意见。

========== 三条铁律（最高优先级，违反即作废）==========

【铁律一·数值零编造】
生命体征、化验值、用药剂量、出入量、留置天数等一切数字，必须逐字引用"结构化数据"中真实存在的值。禁止创造、修改、推算、四舍五入、凭经验补全。结构化数据里没有的数字，绝对不许出现在正文中。

【铁律二·缺失即省略，禁止占位灌水】
结构化数据中没有的项，直接不写。严禁输出"未提供""暂无数据""待确认""待查房补充""待医生确认"之类的空壳话术。若某一系统几乎无数据，就不要为它单独成段；只在"查房后指示"中用病历语言点明需床旁核实的关键评估方向（例如"建议床旁评估镇静深度并完善RASS/CAM-ICU"）。绝不允许把每个模块都写成"待录入"的清单，那不是病历。

【铁律三·只用病历语言】
禁止口语、感叹、闲聊、网络用语、思维残留（如"感觉""呢""吧""我认为""嗯""好的"等）。禁止 Markdown、标题、项目符号、编号、表情符号。全文为连续中文叙事段落。如发现自身输出含上述杂质，必须重写。

========== 针对性原则（不同患者写的项目天然不同）==========

只写与该患者当前病情相关、具有临床意义的内容：异常值、有变化趋势的指标、与当前诊断或治疗直接相关的项目。正常且无意义的项不必罗列。这正是"为什么每个患者写的项目不一样"的根本原因，病情驱动，而非模板填空。

各器官系统的关注重点（仅在该系统有真实数据时才写）：
1) 神经：意识/GCS、瞳孔、镇静深度(RASS)、谵妄(CAM-ICU)、镇痛镇静目标。
2) 呼吸/氧合：呼吸支持方式与参数(FiO2/PEEP/PS/潮气量)、血气、氧合指数(P/F)、脱机/拔管评估；证据不足时不下ARDS等确定性结论。
3) 循环/灌注：HR、MAP、血压、乳酸、尿量、升压药名称与剂量、末梢灌注；明确MAP目标与药物滴定方向。
4) 肾脏/液体：肌酐、尿素、尿量、电解质、CRRT状态与参数、24h净平衡；明确液体目标。
5) 消化/营养：肠内/肠外营养量、热卡与蛋白目标、胃肠耐受、误吸风险。
6) 感染：体温、WBC/NEUT%/CRP/PCT、培养结果、抗菌方案与疗程天数、降阶梯评估。
7) 血液/凝血：PLT、PT/INR/APTT/Fib、活动性出血、抗凝/溶栓用药、VTE风险与预防。
8) 内分泌/代谢：血糖趋势、胰岛素/激素用药、血糖目标。
9) 管路/装置：各管路名称与留置天数、固定/通畅/穿刺点情况、适应证与拔除评估。
10) 今日目标/夜间预案：基于真实病情归纳当日可执行目标与夜间恶化处置方向。

========== 数据稀疏时的处理（极重要）==========

若结构化数据严重不足（如仅有管路天数和个别事件），不要用模板把十个系统逐条填满。正确做法是：用现有真实信息（诊断、ICU天数、管路留置情况、近24h关键事件等）写一段简短但真实的客观描述与病情分析，然后在"查房后指示"中以专业病历语言指出需床旁核实/完善的关键评估方向。宁可写得短而真实，也不能写得长而空洞。

========== 输出结构（连续叙事，不分小标题，不编号）==========

正文按以下顺序自然成段：
(1) 抬头：{日期 时间} {查房级别}查房：
(2) 客观现状：患者基本情况、当前主要支持手段、生命体征与重要客观所见
(3) 重要辅助检查及趋势：仅写有临床意义的化验/检查及其变化
(4) 病情分析：对当前病情、诊疗疗效的分析判断
(5) 查房后指示：下一步诊疗意见，自然成段叙述（不要用1、2、3编号）
(6) 末尾：查房医师姓名与专业技术职务

========== 输出格式（严格 JSON，不输出任何其他内容）==========

{
  "document_text": "完整查房记录正文（连续中文叙事，含上述六部分）",
  "key_facts_used": ["实际引用到的真实数值或事实，如 '气管插管留置37天'、'乳酸1.7mmol/L'、'诊断:急性心力衰竭'"]
}

document_text 中出现的每一个数字，都必须能在 key_facts_used 中找到对应来源。若做不到，说明你编造了数字，必须删除该数字或整句。"""

WARD_ROUND_USER_TEMPLATE = """请根据以下结构化数据，撰写一份"上级医师查房记录"。
严格遵守系统设定的三条铁律：数值零编造、缺失即省略、只用病历语言。
数据中没有的内容不要写，不要出现任何占位语。

【查房元信息】
查房级别：{round_level}
查房医师：{doctor}
查房时间：{round_time}
数据时间窗：近 {hours} 小时（锚点时间 {anchor_time}）

【患者基本信息】
{patient_basic}

【当前生命体征 latest_vitals】
{latest_vitals}

【24小时趋势 trend_24h】
{trend_24h}

【近24小时化验 labs_24h】
{labs_24h}

【近24小时用药 drugs_24h】
{drugs_24h}

【近24小时告警/事件 alerts_24h】
{alerts_24h}

【呼吸支持 respiratory】
{respiratory}

【管路/装置】
{devices}

【评分 recent_scores】
{recent_scores}

【临床推理/问题列表 clinical_reasoning】
{clinical_reasoning}

要求：
- 只写以上数据真实存在的内容，缺失项一律省略，禁止占位灌水。
- 数字必须逐字引用，禁止编造或推算。
- 若数据严重不足，写简短真实的现状与分析，并在查房后指示中点明需床旁核实/完善的关键评估方向。
- 输出严格按系统设定的 JSON 格式，不要输出任何额外说明。"""


class WardRoundGenerator:
    """Generate audited senior physician ward round drafts."""

    def __init__(self, *, db, config, alert_engine, rag_service=None, ai_handoff_service=None, document_generator=None) -> None:
        self.db = db
        self.config = config
        self.alert_engine = alert_engine
        self.rag_service = rag_service
        self.ai_handoff_service = ai_handoff_service
        self.doc_gen = document_generator

    async def _extract(self, patient_id: str, time_range: dict | None) -> dict | None:
        required = [
            "patient",
            "latest_vitals",
            "trend_24h",
            "labs_24h",
            "drugs_24h",
            "alerts_24h",
            "respiratory",
            "devices",
            "clinical_reasoning",
            "recent_scores",
        ]
        if self.doc_gen is not None and hasattr(self.doc_gen, "extract_structured_data"):
            return await self.doc_gen.extract_structured_data(patient_id, required, time_range)
        try:
            patient = await self.db.col("patient").find_one({"_id": ObjectId(patient_id)})
        except Exception:
            patient = None
        if not patient:
            return None
        return {
            "patient": {
                "id": patient_id,
                "name": patient.get("name") or "",
                "bed": patient.get("hisBed") or patient.get("bed") or "",
                "dept": patient.get("dept") or patient.get("hisDept") or "",
                "diagnosis": patient.get("clinicalDiagnosis") or patient.get("admissionDiagnosis") or "",
            },
            "latest_vitals": {},
            "labs_24h": [],
            "drugs_24h": [],
            "alerts_24h": [],
            "respiratory": {},
            "devices": [],
            "recent_scores": [],
            "clinical_reasoning": {},
            "trend_24h": {},
        }

    @staticmethod
    def _fmt(obj: Any) -> str:
        if obj in (None, {}, []):
            return "（无）"
        return json.dumps(obj, ensure_ascii=False, default=str, indent=2)

    def _build_user_prompt(self, sd: dict, round_level: str, doctor: str, round_time: str, hours: int) -> str:
        return WARD_ROUND_USER_TEMPLATE.format(
            round_level=ROUND_LEVELS.get(round_level, round_level),
            doctor=doctor or "（未指定）",
            round_time=round_time,
            hours=hours,
            anchor_time=round_time,
            patient_basic=self._fmt(sd.get("patient")),
            latest_vitals=self._fmt(sd.get("latest_vitals")),
            trend_24h=self._fmt(sd.get("trend_24h")),
            labs_24h=self._fmt((sd.get("labs_24h") or [])[:30]),
            drugs_24h=self._fmt((sd.get("drugs_24h") or [])[:30]),
            alerts_24h=self._fmt([
                {
                    "name": a.get("name") or a.get("alert_type"),
                    "severity": a.get("severity"),
                    "value": a.get("value"),
                    "time": a.get("created_at"),
                }
                for a in (sd.get("alerts_24h") or [])[:20]
                if isinstance(a, dict)
            ]),
            respiratory=self._fmt(sd.get("respiratory")),
            devices=self._fmt((sd.get("devices") or [])[:30]),
            recent_scores=self._fmt([
                {
                    "type": s.get("score_type"),
                    "score": s.get("score"),
                    "risk": s.get("risk_level"),
                    "summary": s.get("summary"),
                }
                for s in (sd.get("recent_scores") or [])[:20]
                if isinstance(s, dict)
            ]),
            clinical_reasoning=self._fmt(sd.get("clinical_reasoning")),
        )

    @staticmethod
    def _collect_numbers(value: Any) -> set[str]:
        return set(re.findall(r"\d+\.?\d*", str(value)))

    def _audit_numbers(self, document_text: str, sd: dict, round_time: str) -> dict:
        allowed: set[str] = set()

        def collect(value: Any) -> None:
            allowed.update(self._collect_numbers(value))

        for value in (sd.get("latest_vitals") or {}).values():
            collect(value)
        for item in sd.get("labs_24h") or []:
            if isinstance(item, dict):
                for key in ("result", "resultValue", "value"):
                    collect(item.get(key) or "")
        for item in sd.get("drugs_24h") or []:
            if isinstance(item, dict):
                collect(item.get("dose") or "")
        for item in sd.get("alerts_24h") or []:
            if isinstance(item, dict):
                collect(item.get("value") or "")
        for item in sd.get("recent_scores") or []:
            if isinstance(item, dict):
                collect(item.get("score") or "")
        collect(sd.get("respiratory") or {})
        collect(sd.get("devices") or [])

        date_tokens = set(re.findall(r"\d+", round_time or ""))
        found = re.findall(r"\d+\.?\d*", document_text or "")
        violations = sorted({
            number
            for number in found
            if number not in allowed and number not in date_tokens and len(number) >= 2
        })
        return {
            "status": "blocked" if violations else "ok",
            "hallucinated_numbers": violations,
            "allowed_count": len(allowed),
        }

    def _fallback_text(self, sd: dict, round_level: str, doctor: str, round_time: str) -> str:
        vitals = sd.get("latest_vitals") or {}
        vital_map = [
            ("体温", "temp", "℃"),
            ("心率", "hr", "次/分"),
            ("呼吸", "rr", "次/分"),
            ("血压", None, "mmHg"),
            ("SpO2", "spo2", "%"),
            ("CVP", "cvp", "mmHg"),
        ]
        parts = []
        for label, key, unit in vital_map:
            if label == "血压":
                sbp, dbp = vitals.get("sbp"), vitals.get("dbp")
                if sbp is not None and dbp is not None:
                    parts.append(f"血压 {sbp}/{dbp}mmHg")
                continue
            value = vitals.get(key)
            if value is not None:
                parts.append(f"{label} {value}{unit}")
        vital_text = "，".join(parts) if parts else "生命体征详见监护记录"

        labs = []
        for item in (sd.get("labs_24h") or [])[:8]:
            if not isinstance(item, dict):
                continue
            name = item.get("itemCnName") or item.get("itemName") or item.get("name")
            value = item.get("result") or item.get("resultValue") or item.get("value")
            unit = item.get("unit") or ""
            flag = item.get("flag") or ""
            if name and value not in (None, ""):
                suffix = f"（{flag}）" if flag else ""
                labs.append(f"{name} {value}{unit}{suffix}")
        lab_text = f"辅助检查：{'，'.join(labs)}。" if labs else ""

        level_cn = ROUND_LEVELS.get(round_level, round_level)
        signature = doctor or "查房医师"
        return (
            f"{round_time} {level_cn}查房：患者目前情况，{vital_text}。"
            f"{lab_text}"
            "（本段为结构化数据模板生成的草稿，因AI生成内容未通过数值核验或服务不可用而回退，"
            "病情分析与诊疗意见请由查房医师补充并核对。）\n"
            f"{signature}"
        )

    async def _persist(
        self,
        *,
        patient_id: str,
        sd: dict,
        document_text: str,
        key_facts_used: list[str],
        audit: dict,
        degraded: bool,
        round_level: str,
        doctor: str,
        generated_at: datetime,
        model: str,
    ) -> dict:
        patient = sd.get("patient") or {}
        title = ROUND_LEVELS.get(round_level, "上级医师查房记录")
        payload = {
            "patient_id": str(patient_id),
            "patient_name": patient.get("name"),
            "bed": patient.get("bed"),
            "dept": patient.get("dept"),
            "score_type": "clinical_document",
            "doc_type": "ward_round",
            "round_level": round_level,
            "doctor": doctor,
            "title": title,
            "summary": document_text[:180],
            "document": {
                "title": title,
                "document_text": document_text,
                "key_facts_used": key_facts_used,
                "number_audit": audit,
                "degraded": degraded,
            },
            "structured_data": sd,
            "prompt_version": WARD_ROUND_PROMPT_VERSION,
            "model": model,
            "status": "draft",
            "calc_time": generated_at,
            "updated_at": generated_at,
            "month": generated_at.strftime("%Y-%m"),
            "day": generated_at.strftime("%Y-%m-%d"),
        }
        res = await self.db.col("score").insert_one(payload)
        payload["_id"] = res.inserted_id
        return payload

    async def generate(
        self,
        patient_id: str,
        *,
        round_level: str = "attending",
        doctor: str = "",
        hours: int = 24,
        time_range: dict | None = None,
    ) -> dict | None:
        hours = min(max(int(hours or 24), 8), 48)
        if time_range is None:
            time_range = {"hours": hours}

        sd = await self._extract(patient_id, time_range)
        if not sd:
            return None

        generated_at = datetime.now(API_TZ)
        round_time = generated_at.strftime("%Y-%m-%d %H:%M")
        user_prompt = self._build_user_prompt(sd, round_level, doctor, round_time, hours)

        document_text = ""
        key_facts_used: list[str] = []
        degraded = False
        model = "medical"
        try:
            result = await call_llm_chat(
                cfg=self.config,
                system_prompt=WARD_ROUND_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                model="medical",
                temperature=0.1,
                max_tokens=2000,
                timeout_seconds=60,
                response_format={"type": "json_object"},
            )
            model = str(result.get("model") or model)
            parsed = self._parse_json(str(result.get("text") or ""))
            document_text = str((parsed or {}).get("document_text") or "").strip()
            key_facts_used = [
                str(item).strip()
                for item in ((parsed or {}).get("key_facts_used") or [])
                if str(item).strip()
            ][:20]
        except LLMRuntimeUnavailableError as exc:
            logger.warning("ward_round LLM unavailable patient_id=%s: %s", patient_id, exc)
        except Exception as exc:
            logger.error("ward_round LLM error patient_id=%s: %s", patient_id, exc)

        audit = self._audit_numbers(document_text, sd, round_time) if document_text else {
            "status": "blocked",
            "hallucinated_numbers": [],
            "allowed_count": 0,
        }

        if audit["status"] == "blocked":
            logger.warning(
                "ward_round number audit blocked patient_id=%s violations=%s",
                patient_id,
                audit.get("hallucinated_numbers"),
            )
            document_text = self._fallback_text(sd, round_level, doctor, round_time)
            key_facts_used = []
            degraded = True

        record = await self._persist(
            patient_id=patient_id,
            sd=sd,
            document_text=document_text,
            key_facts_used=key_facts_used,
            audit=audit,
            degraded=degraded,
            round_level=round_level,
            doctor=doctor,
            generated_at=generated_at,
            model=model,
        )
        return record

    @staticmethod
    def _parse_json(text: str) -> dict | None:
        content = str(text or "").strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content, flags=re.IGNORECASE)
            content = re.sub(r"\s*```$", "", content)
        match = re.search(r"\{[\s\S]*\}", content)
        if match:
            content = match.group(0)
        try:
            data = json.loads(content)
            return data if isinstance(data, dict) else None
        except Exception:
            return None
