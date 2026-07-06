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

    def _build_full_system_prompt(self) -> str:
        # Build correction system_prompt.
        # Two jobs: (A) format/unit normalization, (B) medical term correction + filler cleanup.
        # Never change numeric VALUES. A/B/C hint sections injected at end.
        accent_section = self._build_accent_prompt_section()
        dialect_section = self._build_dialect_prompt_section()
        drug_section = self._build_drug_confusable_prompt_section()

        known_refs = ""
        if accent_section or dialect_section:
            known_refs = "\n".join(filter(None, [
                "## 已知口音/方言对照（参考，非强制）",
                accent_section,
                dialect_section,
                "",
            ]))

        drug_warning = ""
        if drug_section:
            drug_warning = "\n".join([
                drug_section,
                "",
            ])

        prompt = (
            '你是 ICU（重症监护）语音查房记录的文本校对助手。'
            '医生口述的查房内容经过语音识别（ASR）转写成中文文本，'
            '其中常含口语填充词、汉字数字、汉字单位，并因谐音/口音造成术语识别错误。'
            '你的任务是把它校对成规范的书面医疗文本。\n'
            '\n'
            '你只做两类工作：(A) 格式与单位规范化；(B) 医学术语纠错与口语清理。'
            '你绝不改变任何临床数值本身，绝不增删临床信息。\n'
            '\n'
            '========== 最高铁律：数值的"大小"绝对不动 ==========\n'
            '\n'
            '- 你可以把"三八点五"写成"38.5"，但绝不能把 38.5 改成 38 或 39。\n'
            '- 你可以把汉字单位"毫米汞柱"写成"mmHg"，但绝不能换算数值口径（如 g/dL 与 g/L 之间不擅自换算）。\n'
            '- 一位数、负数、小数一律逐字保留其值（如 RASS -2、GCS 3、乳酸 1.7、去甲肾上腺素 0.1）。\n'
            '- 即使某数值临床上明显不合理，也不许改——那是医生复核的职责。保留原值并置 needs_human_review=true。\n'
            '- 数字缺失或没转出来时，保持原样，绝不凭经验补一个数字。\n'
            '\n'
            '========== A. 格式与单位规范化（这是允许且应做的）==========\n'
            '\n'
            '1. 汉字数字转阿拉伯数字（不改变数值大小）：三八点五→38.5；一百二十→120；零点二→0.2；二分之一→1/2；四百万→400万。\n'
            '2. 数值与单位之间不加空格；符号用半角。\n'
            '3. 汉字单位转标准符号（数量级前缀：毫=m、微=μ、纳=n、皮=p、千=k；"万""亿"保留中文）：\n'
            '【生命体征/血流动力学】摄氏度→℃ | 次每分→次/分 | 毫米汞柱→mmHg | 厘米水柱→cmH₂O | 毫升→mL | 升每分→L/min\n'
            '【呼吸/机械通气】百分之→% | 厘米水柱→cmH₂O | 升每分→L/min | 毫米汞柱→mmHg\n'
            '【血气/电解质】毫摩尔每升→mmol/L | 微摩尔每升→μmol/L | 毫当量每升→mEq/L | pH/INR→无单位\n'
            '【实验室/血液】克每升→g/L | 克每分升→g/dL | 乘以十的九次方每升→×10⁹/L | 乘以十的十二次方每升→×10¹²/L | 毫克每升→mg/L | 纳克每毫升→ng/mL | 皮克每毫升→pg/mL | 国际单位每升→U/L\n'
            '【药物剂量/泵速】微克每公斤每分钟→μg/kg/min | 微克每公斤每小时→μg/kg/h | 毫克每公斤每小时→mg/kg/h | 毫克每小时→mg/h | 微克每小时→μg/h | 单位每小时→U/h | 毫升每小时→mL/h | 滴每分→滴/分 | 毫摩尔→mmol | 国际单位→IU | 毫克每千克→mg/kg\n'
            '【出入量/肾脏/CRRT】毫升→mL | 毫升每小时→mL/h | 毫升每公斤每小时→mL/kg/h | 升→L | 毫升每分钟→mL/min\n'
            '【时间/体格/评分】小时/分钟/天/秒→h/min/d/s | 公斤→kg | 厘米→cm | 平方米→m² | GCS/APACHE/SOFA/RASS/CPOT/NRS 分→保留"分"(无量纲)\n'
            '4. 歧义单位靠上下文绑定："次/分"按上文判断心率或呼吸；"mL/h"按上文判断尿量或泵速。无法明确绑定的，原样保留并写入 suspect。\n'
            '\n'
            '========== B. 医学术语纠错与口语清理（允许）==========\n'
            '\n'
            '1. 纠正谐音/识别错误的医学术语，恢复规范写法（如"去甲肾上腺"→"去甲肾上腺素"；药名、检查名、诊断名、操作名的明显识别错误）。\n'
            '2. 补齐标点，使其成为通顺的书面医疗记录。\n'
            '3. 去除口语填充词、重复、口误自纠（嗯、啊、那个、就是说、不对是…）。\n'
            '4. 规范口语表达为书面语，不改变原意。\n'
            '\n'
            '========== 绝对禁止 ==========\n'
            '\n'
            '1. 不改任何数值的大小（见最高铁律）。\n'
            '2. 不修改、合并、替换药品名；易混药只规范格式，存疑写入 suspect。\n'
            '3. 不添加转写文本里没有的临床信息、诊断、判断、建议。\n'
            '4. 不删除任何有临床意义的内容。\n'
            '5. 不做医学推断、不下结论、不补全"应有但没说"的内容。\n'
            '6. 不做总结、归纳、重新组织结构——只做校对。\n'
            '7. 拿不准的术语，保持原样，写入 suspect，绝不猜。\n'
            '\n'
            '========== 输出格式（仅输出 JSON，不要任何解释、前言、markdown）==========\n'
            '\n'
            '{"corrected_text":"<校对后的文本>","suspect":[{"term":"<存疑片段>","reason":"<原因>"}],"needs_human_review":<true|false>}\n'
            '原文已准确无误时，corrected_text 原样返回，suspect 为空数组。\n'
            '\n'
            f'{known_refs}'
            f'{drug_warning}'
            '已知患者背景仅用于辅助判断术语，不得据此编造未说出的内容。'
        )
        return prompt

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

    # 汉字数字→float 映射
    _CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
                  "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "百": 100, "千": 1000, "万": 10000}

    def _parse_cn_number(self, text: str) -> float | None:
        """
        解析汉字数字为 float。
        支持：整数（三八→38、一百二十→120、一万二→12000）、
              小数（三八点五→38.5、零点零五→0.05）、
              分数（二分之一→0.5）、负数（负二→-2）。
        """
        text = text.strip()
        if not text:
            return None

        # 先试阿拉伯数字
        try:
            return float(text)
        except ValueError:
            pass

        # 负数
        if text.startswith("负"):
            inner = self._parse_cn_number(text[1:])
            return -inner if inner is not None else None

        # 分数：X分之Y → Y/X
        if "分之" in text:
            parts = text.split("分之")
            if len(parts) == 2:
                denom = self._parse_cn_number(parts[0])
                numer = self._parse_cn_number(parts[1])
                if denom is not None and numer is not None and denom != 0:
                    return numer / denom
            return None

        # 小数：X点Y
        if "点" in text:
            parts = text.split("点", 1)
            int_part = self._parse_cn_int(parts[0]) if parts[0] else 0.0
            if int_part is None:
                return None
            dec_str = parts[1] if len(parts) > 1 else ""
            dec_val = 0.0
            for i, ch in enumerate(dec_str):
                d = self._CN_DIGITS.get(ch)
                if d is None or d >= 10:
                    return None
                dec_val += d / (10 ** (i + 1))
            return int_part + dec_val

        # 纯整数
        return self._parse_cn_int(text)

    def _parse_cn_int(self, text: str) -> float | None:
        """
        解析汉字整数。
        乘法位：一百二十→120；一万二千三百→12300。
        连续数字：三八→38；二十一→21。
        省略式：一万二→12000（仅当下一位不是乘法位时）。
        """
        text = text.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            pass
        chars = list(text)
        total = 0
        digit = 0
        last_multiplier = 0
        for i, ch in enumerate(chars):
            d = self._CN_DIGITS.get(ch)
            if d is None:
                return None
            if d >= 10:
                if digit > 0:
                    # 有前置数字：四百 → 4*100
                    total += digit * d
                    digit = 0
                elif last_multiplier > 0:
                    # 连续乘法位：百万 → 100*10000
                    total *= d
                else:
                    # 开头乘法位：百 → 1*100
                    total += d
                last_multiplier = d
            else:
                # 前瞻判断省略式 vs 连续数字
                next_d = self._CN_DIGITS.get(chars[i + 1]) if i + 1 < len(chars) else None
                if last_multiplier > 0 and digit == 0 and (next_d is None or next_d < 10):
                    # 省略式：一万二 → 2 * (万/10)
                    digit = d * (last_multiplier // 10 or 1)
                    last_multiplier = 0
                elif digit > 0:
                    # 连续数字：三八 → 38
                    digit = digit * 10 + d
                else:
                    digit = d
        total += digit
        # "零" → 0 也是合法结果
        if total == 0 and digit == 0 and "零" not in text:
            return None
        return float(total)

    def _extract_numeric_values(self, text: str) -> list[float]:
        """
        从文本中抽取所有数值（阿拉伯数字 + 汉字数字），返回排序后的 float 列表。
        用于比较原文与纠错后的数值大小是否一致。
        """
        values: list[float] = []

        # 阿拉伯数字
        for m in re.finditer(r'-?\d+(?:\.\d+)?', text):
            try:
                values.append(float(m.group()))
            except ValueError:
                pass

        # 汉字数字（逐字符扫描）
        cn_buf = ""
        for ch in text:
            if ch in self._CN_DIGITS or ch in ("点", "分"):
                cn_buf += ch
            else:
                if cn_buf:
                    v = self._parse_cn_number(cn_buf)
                    if v is not None:
                        values.append(v)
                    cn_buf = ""
        if cn_buf:
            v = self._parse_cn_number(cn_buf)
            if v is not None:
                values.append(v)

        return sorted(values)

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

    def _resolve_asr_llm_cfg(self, llm_cfg: dict[str, Any]) -> tuple[Any, str | None]:
        """
        解析语音纠错 LLM 配置。
        ASR_LLM_BASE_URL 非空 → 用语音专用三件套（构造 cfg 替身覆盖 settings）。
        ASR_LLM_BASE_URL 为空 → 沿用全局 LLM 配置。
        返回 (cfg_to_use, model)。
        """
        settings = getattr(self.config, "settings", None)
        asr_llm_base = str(getattr(settings, "ASR_LLM_BASE_URL", "") or "").strip() if settings else ""
        asr_llm_key = str(getattr(settings, "ASR_LLM_API_KEY", "") or "").strip() if settings else ""
        asr_llm_model = str(getattr(settings, "ASR_LLM_MODEL", "") or "").strip() if settings else ""

        if asr_llm_base:
            # 语音专用配置：构造 cfg 替身，只覆盖 LLM_BASE_URL / LLM_API_KEY
            # 用 SimpleNamespace 浅拷贝 settings，只改 LLM 相关字段
            import copy
            overridden_settings = copy.copy(self.config.settings)
            overridden_settings.LLM_BASE_URL = asr_llm_base
            if asr_llm_key:
                overridden_settings.LLM_API_KEY = asr_llm_key

            cfg_override = copy.copy(self.config)
            cfg_override.settings = overridden_settings

            model = asr_llm_model or (
                getattr(self.config, "llm_model_medical", None)
                or getattr(self.config, "llm_fast_model", None)
            )
            logger.info("语音纠错使用专用 LLM: %s / %s", asr_llm_base, model or "(默认)")
            return cfg_override, model

        # 回退：全局 LLM 配置
        model = (
            getattr(self.config, "llm_model_medical", None)
            or getattr(self.config, "llm_fast_model", None)
        )
        return self.config, model

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

        # ---- 构建 system_prompt ----
        system_prompt = self._build_full_system_prompt()
        user_prompt = (
            f"患者背景：{json.dumps(context, ensure_ascii=False)}\n\n"
            f"待规范化文本：\n{cleaned_text}"
        )

        # ---- 解析 LLM 配置：语音专用优先，留空回退全局 ----
        llm_cfg_for_call, model = self._resolve_asr_llm_cfg(llm_cfg)

        try:
            result = await call_llm_chat(
                cfg=llm_cfg_for_call,
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

        # LLM 返回的 suspect：归一化 {term, reason} → {term, type, note}
        for item in (llm_suspects or []):
            if isinstance(item, dict):
                term = str(item.get("term") or "").strip()
                reason = str(item.get("reason") or item.get("note") or "").strip()
                if term:
                    # 根据 reason 推断 type
                    if "药名" in reason:
                        stype = SUSPECT_TYPE_DRUG
                    elif "数值" in reason or "剂量" in reason:
                        stype = SUSPECT_TYPE_NUMBER
                    else:
                        stype = SUSPECT_TYPE_DIALECT
                    all_suspects.append({"term": term, "type": stype, "note": reason})
            elif isinstance(item, str) and item.strip():
                all_suspects.append({"term": item.strip(), "type": SUSPECT_TYPE_DIALECT, "note": ""})

        # 数值保护：比较原文与纠错后文本中的数值大小。
        # 允许格式转换（三八点五→38.5），但禁止改变数值大小（38.5→39）。
        needs_review = False
        if bool(llm_cfg.get("protect_numbers", True)):
            original_nums = self._extract_numeric_values(cleaned_text)
            corrected_nums = self._extract_numeric_values(corrected)
            if original_nums and corrected_nums and original_nums != corrected_nums:
                logger.warning("LLM 纠错改动了数值大小，已拒绝采纳: %s -> %s", original_nums, corrected_nums)
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
