"""语音查房：四级流水线（ASR → 去填充词 → LLM 纠错 → 结构化），含数值安全保护。"""
from __future__ import annotations

import difflib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import asyncio
import yaml

from app.services.asr_client import ASRClient
from app.services.llm_runtime import call_llm_chat
from app.utils.runtime_paths import package_root

logger = logging.getLogger("icu-alert")

# 数字+可选单位的抽取：保护剂量/数值不被 LLM 篡改
# 只匹配 ASCII 字母单位（mg/ml/mmol 等），不匹配 ℃/% 等符号和中文单位
# 这样 "38.5℃" → "38.5"，"120次/分" → "120"，"0.2μg/kg/min" → "0.2μg/kg/min"
_CJK = r"[一-鿿]"
_NUM_PATTERN = re.compile(
    r"\d+(?:\.\d+)?\s*"
    r"(?:[a-zA-Zμ][a-zA-Zμ/\-]*[a-zA-Zμ]|[a-zA-Zμ])?",
    re.IGNORECASE,
)

# 结构化 suspect 的类型常量
SUSPECT_TYPE_DRUG = "drug_confusable"
SUSPECT_TYPE_NUMBER = "number_override"
SUSPECT_TYPE_DIALECT = "dialect_uncertain"


def _normalize_drug_confusables(raw: list[Any]) -> list[dict[str, Any]]:
    """
    将 drug_confusables 统一为 list[dict{names: list[str], note: str}]。
    加载时跑一次，运行时下游只面对一种格式。
    支持旧格式 list[str]（如 ["多巴胺", "多巴酚丁胺"]）自动转换。
    """
    result: list[dict[str, Any]] = []
    for entry in raw:
        if isinstance(entry, list):
            result.append({"names": [str(n) for n in entry], "note": ""})
        elif isinstance(entry, dict):
            names = entry.get("names") or entry.get("wrong") or []
            note = str(entry.get("note") or "")
            result.append({"names": [str(n) for n in names], "note": note})
    return result


class VoiceRoundingService:
    def __init__(self, db, config):
        self.db = db
        self.config = config
        self.cfg = self._load_cfg()
        self.asr = ASRClient(self.cfg.get("asr", {}))
        self._hints_lock = asyncio.Lock()
        self.correction_hints = self._load_correction_hints()

    def _load_cfg(self) -> dict[str, Any]:
        """读取 voice_rounding 配置段，与 BaseEngine._cfg 读取方式一致。"""
        try:
            cfg = self.config.yaml_cfg.get("voice_rounding", {})
        except Exception:
            cfg = {}
        return cfg if isinstance(cfg, dict) else {}

    def _load_correction_hints(self) -> dict[str, Any]:
        """
        加载渝普口音 + ICU 术语纠错提示配置。
        优先从配置段指定路径读取，否则从默认位置读取。
        drug_confusables 在加载时归一化为统一格式。
        """
        hints_path = self.cfg.get("correction_hints_path")
        if not hints_path:
            hints_path = str(package_root() / "config" / "voice_rounding" / "correction_hints.yaml")
        try:
            path = Path(hints_path)
            if path.exists():
                with path.open("r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                if not isinstance(data, dict):
                    data = {}
                # 归一化 drug_confusables：加载时统一为 list[dict{names, note}]
                data["drug_confusables"] = _normalize_drug_confusables(
                    data.get("drug_confusables") or []
                )
                logger.info(
                    "已加载纠错提示: %s (%d accent, %d dialect, %d drug confusable)",
                    hints_path,
                    len(data.get("accent_errors") or []),
                    len(data.get("dialect_phrases") or []),
                    len(data.get("drug_confusables") or []),
                )
                return data
            else:
                logger.warning("纠错提示文件不存在: %s，使用空表降级", hints_path)
        except Exception:
            logger.warning("纠错提示文件加载失败: %s", hints_path, exc_info=True)
        return {}

    async def reload_correction_hints(self) -> bool:
        """
        原子重载 correction_hints。
        加载到临时变量、校验通过后再原子替换 self.correction_hints，
        避免重载途中并发请求读到半截数据。
        """
        try:
            new_hints = self._load_correction_hints()
        except Exception:
            logger.exception("correction_hints 重载失败")
            return False
        async with self._hints_lock:
            self.correction_hints = new_hints
        logger.info("correction_hints 已原子重载 (%d accent, %d dialect, %d drug)",
                     len(new_hints.get("accent_errors") or []),
                     len(new_hints.get("dialect_phrases") or []),
                     len(new_hints.get("drug_confusables") or []))
        return True

    # ================================================================
    # Prompt 构造（三类区别对待）
    # ================================================================

    def _build_accent_prompt_section(self) -> str:
        """
        类型 A：口音错字。强约束——明确指示 LLM 遇到错写形式时应改正。
        这是确定性纠错，鼓励 LLM 改。
        """
        accent_errors = self.correction_hints.get("accent_errors") or []
        if not accent_errors:
            return ""
        lines = [
            "## 已知渝普口音易错对照（遇到下列错写形式时，必须改为对应正确术语）",
            "",
        ]
        for entry in accent_errors:
            wrongs = entry.get("wrong") or []
            right = entry.get("right") or ""
            note = entry.get("note") or ""
            if wrongs and right:
                wrong_str = "、".join(wrongs)
                line = f"  {wrong_str} → {right}"
                if note:
                    line += f"（{note}）"
                lines.append(line)
        lines.append("")
        lines.append("若识别文本中出现上述错写形式，且上下文符合医学语境，应自动替换为正确术语。")
        return "\n".join(lines)

    def _build_dialect_prompt_section(self) -> str:
        """
        类型 B：方言口语→规范术语。中等约束——替换为规范术语，但不得改变原意。
        """
        dialect_phrases = self.correction_hints.get("dialect_phrases") or []
        if not dialect_phrases:
            return ""
        lines = [
            "## 方言/口语表达规范化对照（将口语化表达替换为规范医学术语，不得改变原意）",
            "",
        ]
        for entry in dialect_phrases:
            wrongs = entry.get("wrong") or []
            right = entry.get("right") or ""
            if wrongs and right:
                wrong_str = "、".join(wrongs)
                lines.append(f"  {wrong_str} → {right}")
        return "\n".join(lines)

    def _build_drug_confusable_prompt_section(self) -> str:
        """
        类型 C：易混药名。只提示，绝不让 LLM 改。
        单独成段，与 A/B 的"请纠正"指令物理隔离。
        drug_confusables 已在加载时归一化为 list[dict{names, note}]。
        """
        drug_confusables = self.correction_hints.get("drug_confusables") or []
        if not drug_confusables:
            return ""
        lines = [
            "## 易混药名——严禁自动修改",
            "",
            "以下药名组互相易混。你不得自动修改其中任何一个。",
            "若识别文本命中其中某词，原样保留在 corrected_text 中，",
            "并在 suspect 数组中标注该药名，type 为 \"drug_confusable\"，提醒医生人工核对。",
            "",
        ]
        for entry in drug_confusables:
            names = entry.get("names") or []
            note = entry.get("note") or ""
            if names:
                names_str = " ↔ ".join(names)
                line = f"  {names_str}"
                if note:
                    line += f"（{note}）"
                lines.append(line)
        return "\n".join(lines)

    # ================================================================
    # 结构化 suspect + 药名混淆检测
    # ================================================================

    def _detect_drug_confusables(self, text: str) -> list[dict[str, str]]:
        """
        检测文本中是否出现易混药名对，返回结构化 suspect 列表。
        每条: {term, type: "drug_confusable", note}
        drug_confusables 已在加载时归一化为 list[dict{names, note}]。
        """
        drug_confusables = self.correction_hints.get("drug_confusables") or []
        suspects: list[dict[str, str]] = []
        for entry in drug_confusables:
            names = entry.get("names") or []
            note = entry.get("note") or ""
            found = [n for n in names if n in text]
            if len(found) >= 2:
                suspects.append({
                    "term": "、".join(found),
                    "type": SUSPECT_TYPE_DRUG,
                    "note": f"易混药名同时出现，请确认用药是否正确。{note}".strip(),
                })
            elif len(found) == 1:
                others = "、".join(n for n in names if n != found[0])
                suspects.append({
                    "term": found[0],
                    "type": SUSPECT_TYPE_DRUG,
                    "note": f"口音下可能与 {others} 混淆，请确认。{note}".strip(),
                })
        return suspects

    @staticmethod
    def _suspect_to_terms(suspects: list[dict[str, str]]) -> list[str]:
        """结构化 suspect → 扁平 list[str]（向前兼容字段）。"""
        return [s.get("term", "") for s in suspects if s.get("term")]

    # ================================================================
    # 级2：规则清洗
    # ================================================================

    def _strip_fillers(self, text: str) -> str:
        """
        去除填充词/语气词，走 config 词表。
        规则：填充词后跟 CJK 字符的保留（保护药名词组如"啊霉素"），
        其余情况移除（句首/句尾/后跟标点/后跟数字）。
        """
        fillers = self.cfg.get("filler_words") or [
            "嗯", "哦", "额", "呃", "那个", "就是说", "对吧", "啊",
        ]
        cleaned = text
        for w in fillers:
            cleaned = re.sub(rf"{re.escape(w)}(?={_CJK})", w, cleaned)
            cleaned = re.sub(re.escape(w), "", cleaned)
        cleaned = re.sub(r"[，,。\s]{2,}", "，", cleaned)
        return cleaned.strip("，。, ").strip()

    # ================================================================
    # 数值保护
    # ================================================================

    def _extract_numbers(self, text: str) -> list[str]:
        """从文本中抽取所有数字+单位（受保护字段）。"""
        return [m.group(0).replace(" ", "") for m in _NUM_PATTERN.finditer(text)]

    def _numbers_changed(self, before: str, after: str) -> bool:
        """LLM 纠错后若数字集合变了，判定为不安全改动。"""
        return sorted(self._extract_numbers(before)) != sorted(self._extract_numbers(after))

    # ================================================================
    # 级3：患者上下文 LLM 纠错
    # ================================================================

    async def _build_patient_context(self, patient_id: str) -> dict[str, Any]:
        """获取患者上下文（诊断、当前用药、最近检验）。"""
        patient = await self.db.col("patient").find_one({"_id": patient_id}) or {}
        his_pid = patient.get("hisPid") or patient.get("hisPID") or patient_id

        diagnosis = (
            patient.get("clinicalDiagnosis")
            or patient.get("admissionDiagnosis")
            or patient.get("hisDiagnose")
            or ""
        )

        drugs: list[str] = []
        try:
            drug_cursor = self.db.col("drug").find(
                {"$or": [{"pid": his_pid}, {"patient_id": patient_id}]}
            ).sort("start_time", -1).limit(20)
            async for doc in drug_cursor:
                name = str(doc.get("drugName") or doc.get("name") or "").strip()
                if name and name not in drugs:
                    drugs.append(name)
        except Exception:
            pass

        labs: dict[str, Any] = {}
        try:
            from datetime import timedelta
            since = datetime.now() - timedelta(hours=72)
            lab_cursor = self.db.col("lab").find(
                {
                    "$or": [{"pid": his_pid}, {"patient_id": patient_id}],
                    "report_time": {"$gte": since},
                }
            ).sort("report_time", -1).limit(30)
            async for doc in lab_cursor:
                key = str(doc.get("itemCode") or doc.get("testName") or "").strip()
                if not key:
                    continue
                labs[key] = {
                    "value": doc.get("result") or doc.get("value"),
                    "unit": doc.get("unit"),
                    "flag": doc.get("abnormalFlag"),
                }
        except Exception:
            pass

        return {
            "diagnosis": diagnosis,
            "current_drugs": drugs[:10],
            "recent_labs": labs,
        }

    async def _llm_correct(self, cleaned_text: str, patient_id: str) -> dict[str, Any]:
        """
        级3 LLM 纠错。
        - A 类 accent_errors：强约束，鼓励 LLM 改。
        - B 类 dialect_phrases：中等约束，替换为规范术语。
        - C 类 drug_confusables：禁止 LLM 改，只标 suspect。
        返回 suspect 为 list[dict{term, type, note}]，同时附 suspect_terms 兼容字段。
        """
        llm_cfg = self.cfg.get("llm_correction", {})
        if not bool(llm_cfg.get("enabled", True)):
            return {
                "text": cleaned_text,
                "corrected": False,
                "suspect": [],
                "suspect_terms": [],
                "needs_human_review": False,
            }

        context = await self._build_patient_context(patient_id)

        # ---- 构建 system_prompt：三段物理隔离 ----
        prompt_parts = [
            "你是 ICU 查房记录的语音转写纠错助手。输入是一段可能含方言口音、识别错字的查房口述。",
            "",
            "## 任务",
            "只纠正同音/近音错字、口音导致的识别错误、残余口语词；保持原意，不增删临床事实。",
            "",
            "## 受保护字段（严禁自动修改）",
            "1. 数字、剂量、单位——若你认为数字可能识别错误，不要改，在 suspect 字段里指出。",
            "",
        ]

        # 类型 A：口音错字纠正（强约束，鼓励改）
        accent_section = self._build_accent_prompt_section()
        if accent_section:
            prompt_parts.append(accent_section)
            prompt_parts.append("")

        # 类型 B：方言口语→规范术语（中等约束）
        dialect_section = self._build_dialect_prompt_section()
        if dialect_section:
            prompt_parts.append(dialect_section)
            prompt_parts.append("")

        # 类型 C：易混药名（禁止修改，单独成段，与 A/B 物理隔离）
        drug_section = self._build_drug_confusable_prompt_section()
        if drug_section:
            prompt_parts.append(drug_section)
            prompt_parts.append("")

        prompt_parts.append(
            "已知患者背景仅用于辅助判断术语，不得据此编造未说出的内容。"
        )

        system_prompt = "\n".join(prompt_parts)
        user_prompt = (
            f"患者背景：{json.dumps(context, ensure_ascii=False)}\n\n"
            f"待纠错文本：\n{cleaned_text}"
        )

        model = (
            getattr(self.config, "llm_model_medical", None)
            or getattr(self.config, "llm_fast_model", None)
        )

        try:
            result = await call_llm_chat(
                cfg=self.config,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                model=model,
                temperature=float(llm_cfg.get("temperature", 0.1)),
                max_tokens=int(llm_cfg.get("max_tokens", 2048)),
                timeout_seconds=float(llm_cfg.get("timeout", 30)),
            )
            raw = result.get("text") if isinstance(result, dict) else str(result)
            corrected, llm_suspects = self._parse_llm_json(raw, fallback=cleaned_text)
        except Exception:
            logger.exception("LLM 纠错失败，降级返回规则清洗文本")
            return {
                "text": cleaned_text,
                "corrected": False,
                "suspect": [],
                "suspect_terms": [],
                "needs_human_review": False,
                "degraded": True,
            }

        # ---- 收集结构化 suspect ----
        all_suspects: list[dict[str, str]] = []

        # LLM 返回的 suspect（字符串→归一化为结构化）
        for item in (llm_suspects or []):
            if isinstance(item, dict):
                all_suspects.append(item)
            elif isinstance(item, str) and item.strip():
                all_suspects.append({"term": item.strip(), "type": SUSPECT_TYPE_DIALECT, "note": ""})

        # 数值保护：若 LLM 动了数字，拒绝采纳，回退原文并标红
        needs_review = False
        if bool(llm_cfg.get("protect_numbers", True)) and self._numbers_changed(cleaned_text, corrected):
            logger.warning("LLM 纠错改动了数值，已拒绝采纳")
            corrected = cleaned_text
            needs_review = True
            all_suspects.append({
                "term": "数值被模型改动",
                "type": SUSPECT_TYPE_NUMBER,
                "note": "已保留原值，请人工核对剂量",
            })

        # C 类药名安全校验：检测易混药名，追加到 suspect
        all_suspects.extend(self._detect_drug_confusables(cleaned_text))

        return {
            "text": corrected,
            "corrected": corrected != cleaned_text,
            "suspect": all_suspects,
            "suspect_terms": self._suspect_to_terms(all_suspects),
            "needs_human_review": needs_review or bool(all_suspects),
            "degraded": False,
        }

    def _parse_llm_json(self, raw: str, fallback: str) -> tuple[str, list[Any]]:
        """解析 LLM 返回的 JSON，容错处理。suspect 保留原始结构。"""
        text = str(raw or "").strip()
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            text = m.group(0)
        try:
            data = json.loads(text)
            return str(data.get("corrected_text") or fallback), list(data.get("suspect") or [])
        except Exception:
            return fallback, []

    # ================================================================
    # 主流程
    # ================================================================

    async def transcribe(
        self, patient_id: str, audio_bytes: bytes, *, sample_rate: int = 16000
    ) -> dict[str, Any]:
        """
        四级流水线主入口。
        返回 draft 草稿，status="draft"，必须医生确认后才入库。
        draft 同时包含结构化 suspect 和兼容字段 suspect_terms。
        """
        max_sec = int(self.cfg.get("max_audio_seconds", 300))
        if len(audio_bytes) > max_sec * sample_rate * 2 * 1.5:
            raise ValueError("音频超过最大允许时长")

        # 级1: ASR
        raw_text = await self.asr.transcribe(audio_bytes, sample_rate=sample_rate)
        # 级2: 规则清洗
        cleaned = self._strip_fillers(raw_text)
        # 级3: LLM 纠错 + 数值保护 + 药名保护
        corrected = await self._llm_correct(cleaned, patient_id)
        # 级4: 结构化（第一版返回纯文本草稿）

        # hints_hit：收集本次命中的 A/B/C 规则（复用 _llm_correct 的检测结果）
        hints_hit = self._collect_hints_hit(cleaned, corrected.get("suspect", []))

        draft = {
            "patient_id": str(patient_id),
            "status": "draft",
            "raw_text": raw_text,
            "cleaned_text": cleaned,
            "corrected_text": corrected["text"],
            "suspect": corrected.get("suspect", []),
            "suspect_terms": corrected.get("suspect_terms", []),
            "hints_hit": hints_hit,
            "needs_human_review": corrected.get("needs_human_review", False),
            "degraded": corrected.get("degraded", False),
            "created_at": datetime.now(),
        }

        result = await self.db.col("voice_rounding_drafts").insert_one(draft)
        draft["_id"] = str(result.inserted_id)
        return draft

    def _collect_hints_hit(
        self, cleaned_text: str, suspects: list[dict[str, str]]
    ) -> dict[str, list[str]]:
        """
        收集本次转写命中的纠错规则，存入 draft 供后续日志分析。
        不重复扫描——A/B 类从 correction_hints 直接匹配，C 类复用 suspects。
        """
        hit: dict[str, list[str]] = {"accent": [], "dialect": [], "drug_confusable": []}

        # A 类：检查 cleaned_text 中是否含有 accent_errors 的 wrong 形式
        for entry in (self.correction_hints.get("accent_errors") or []):
            for w in (entry.get("wrong") or []):
                if w in cleaned_text:
                    hit["accent"].append(f"{w}→{entry.get('right', '')}")

        # B 类：检查 cleaned_text 中是否含有 dialect_phrases 的 wrong 形式
        for entry in (self.correction_hints.get("dialect_phrases") or []):
            for w in (entry.get("wrong") or []):
                if w in cleaned_text:
                    hit["dialect"].append(f"{w}→{entry.get('right', '')}")

        # C 类：复用 _detect_drug_confusables 的结果
        for s in suspects:
            if s.get("type") == SUSPECT_TYPE_DRUG:
                hit["drug_confusable"].append(s.get("term", ""))

        return {k: v for k, v in hit.items() if v}

    # ================================================================
    # 确认入库 + 编辑日志
    # ================================================================

    async def confirm(
        self, patient_id: str, *, final_text: str, draft_id: str = "", actor: str = ""
    ) -> dict[str, Any]:
        """
        医生在前端编辑确认后入库为正式查房记录。
        同时写一条编辑日志到 voice_rounding_logs（不阻断主流程）。
        """
        now = datetime.now()
        doc = {
            "patient_id": str(patient_id),
            "source": "voice_rounding",
            "status": "confirmed",
            "text": final_text,
            "draft_id": draft_id,
            "confirmed_by": actor,
            "confirmed_at": now,
            "created_at": now,
        }
        result = await self.db.col("voice_rounding_records").insert_one(doc)
        doc["_id"] = str(result.inserted_id)

        # 更新草稿状态
        if draft_id:
            try:
                from bson import ObjectId
                await self.db.col("voice_rounding_drafts").update_one(
                    {"_id": ObjectId(draft_id)},
                    {"$set": {"status": "confirmed", "confirmed_at": now}},
                )
            except Exception:
                logger.warning("更新草稿状态失败: %s", draft_id)

        # 编辑日志（防御式：失败不阻断主流程）
        await self._write_edit_log(
            patient_id=patient_id,
            draft_id=draft_id,
            final_text=final_text,
            actor=actor,
            now=now,
        )

        return doc

    async def _write_edit_log(
        self,
        *,
        patient_id: str,
        draft_id: str,
        final_text: str,
        actor: str,
        now: datetime,
    ) -> None:
        """
        写编辑日志到 voice_rounding_logs。
        从 draft 取历史文本，计算 edited_spans。
        失败不阻断 confirm 主流程。
        """
        # 反查 draft 取历史文本（防御：查不到时记 null）
        draft_doc: dict[str, Any] | None = None
        draft_missing = False
        if draft_id:
            try:
                from bson import ObjectId
                draft_doc = await self.db.col("voice_rounding_drafts").find_one(
                    {"_id": ObjectId(draft_id)}
                )
            except Exception:
                pass
        if not draft_doc:
            draft_missing = True

        raw_text = (draft_doc or {}).get("raw_text")
        cleaned_text = (draft_doc or {}).get("cleaned_text")
        corrected_text = (draft_doc or {}).get("corrected_text")
        suspects = (draft_doc or {}).get("suspect") or []
        hints_hit = (draft_doc or {}).get("hints_hit") or {}
        needs_human_review = (draft_doc or {}).get("needs_human_review", False)
        degraded = (draft_doc or {}).get("degraded", False)

        # diff：corrected_text（LLM 纠错后） vs final_text（医生确认）
        edited_spans = self._compute_edits(corrected_text or "", final_text)

        log_doc = {
            "patient_id": str(patient_id),
            "draft_id": draft_id,
            "raw_text": raw_text,
            "cleaned_text": cleaned_text,
            "corrected_text": corrected_text,
            "final_text": final_text,
            "edited_spans": edited_spans,
            "hints_hit": hints_hit,
            "suspects": suspects,
            "needs_human_review": needs_human_review,
            "degraded": degraded,
            "draft_missing": draft_missing,
            "confirmed_by": actor,
            "confirmed_at": now,
        }

        try:
            await self.db.col("voice_rounding_logs").insert_one(log_doc)
        except Exception:
            logger.exception("语音查房编辑日志写入失败（不阻断主流程）")

    @staticmethod
    def _compute_edits(before: str, after: str) -> list[dict[str, str]]:
        """
        对 corrected_text 和 final_text 做字符级 diff，记录 replace/delete/insert 片段对。
        这是积累错例的金矿——医生反复手改同一类错，说明 hints 表漏了。
        """
        if not before and not after:
            return []
        matcher = difflib.SequenceMatcher(None, before, after, autojunk=False)
        edits: list[dict[str, str]] = []
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            edit: dict[str, str] = {"op": tag}
            if tag in ("replace", "delete"):
                edit["before"] = before[i1:i2]
            if tag in ("replace", "insert"):
                edit["after"] = after[j1:j2]
            edits.append(edit)
        return edits
