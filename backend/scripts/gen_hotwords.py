"""
从现有数据源自动生成 FunASR 热词表。
输出格式：每行 "词 权重"，如 "去甲肾上腺素 20"

权重经验值：
  药名/关键术语  20
  一般术语       15
  缩写/英文      25（缩写更易错，权重更高）

用法：
  python backend/scripts/gen_hotwords.py --out /opt/icu-models/hotwords.txt
  建议挂 cron/定时任务，知识库/药品字典更新后自动刷新。
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import re
from pathlib import Path

from app.config import get_config
from app.database import DatabaseManager

logger = logging.getLogger("icu-alert")

# ============================================================
# 种子术语（兜底，DB 无数据时仍能提供基础热词）
# ============================================================

# 药名/关键术语 → 权重 20
SEED_TERMS_HIGH: list[str] = [
    # 血管活性药 / 镇静镇痛
    "去甲肾上腺素", "肾上腺素", "多巴胺", "多巴酚丁胺", "间羟胺", "血管加压素", "去氧肾上腺素",
    "右美托咪定", "丙泊酚", "咪达唑仑", "瑞芬太尼", "芬太尼", "舒芬太尼", "吗啡", "氯胺酮",
    # 抗感染
    "美罗培南", "亚胺培南", "哌拉西林他唑巴坦", "万古霉素", "替考拉宁", "利奈唑胺",
    "头孢哌酮舒巴坦", "比阿培南", "替加环素", "多黏菌素", "卡泊芬净", "阿米卡星", "庆大霉素",
    # 设备/治疗
    "呼吸机", "俯卧位通气", "机械通气", "无创通气", "高流量氧疗", "气管插管", "气管切开",
    "连续性肾脏替代治疗", "血液净化", "体外膜肺氧合", "主动脉内球囊反搏",
    # 评估工具
    "镇静评分", "疼痛评分", "谵妄评估", "营养评估",
]

# 缩写/英文 → 权重 25（更易识别错误）
SEED_TERMS_ABBR: list[str] = [
    "CRRT", "ECMO", "IABP", "VAP", "CRBSI", "CAUTI", "ARDS", "AKI", "DIC", "SOFA",
    "APACHE", "qSOFA", "GCS", "RASS", "CAM-ICU", "CPOT", "BPS", "SBT", "PEEP", "FiO2",
    "P/F", "CVP", "MAP", "PCT", "BNP", "NTproBNP", "TDM", "PICS", "SpO2", "PaO2",
    "PaCO2", "Lac", "Hb", "WBC", "PLT", "INR", "PT", "APTT", "D-dimer",
    "BMI", "GRV", "NAS", "RSBI", "P0.1", "Pdi", "Edi",
]


def _is_valid_term(t: str) -> bool:
    """过滤无效术语。"""
    t = t.strip()
    if len(t) < 2:
        return False
    # 过滤纯标点、纯数字
    if re.fullmatch(r"[\d\s\W]+", t):
        return False
    return True


# ============================================================
# 从 DB 收集术语
# ============================================================

async def collect_drug_names(db: DatabaseManager) -> dict[str, int]:
    """从 configDrug 药品字典收集药名。"""
    terms: dict[str, int] = {}
    fields = ["name", "drugName", "genericName", "tradeName", "fullName"]
    try:
        cursor = db.col("configDrug").find({}, {f: 1 for f in fields})
        async for doc in cursor:
            for f in fields:
                name = doc.get(f)
                if name and _is_valid_term(str(name)):
                    terms[str(name).strip()] = 20
                # 处理列表字段（如 alias）
                if isinstance(doc.get(f), list):
                    for item in doc[f]:
                        if item and _is_valid_term(str(item)):
                            terms[str(item).strip()] = 20
    except Exception as exc:
        logger.warning("读取 configDrug 失败: %s", exc)
    return terms


async def collect_drug_names_from_orders(db: DatabaseManager, limit: int = 5000) -> dict[str, int]:
    """从 drugExe 实际用药记录收集药名（补充 configDrug 可能遗漏的）。"""
    terms: dict[str, int] = {}
    try:
        cursor = db.col("drugExe").find(
            {}, {"drugName": 1, "name": 1}
        ).sort("time", -1).limit(limit)
        async for doc in cursor:
            for key in ("drugName", "name"):
                name = doc.get(key)
                if name and _is_valid_term(str(name)):
                    terms.setdefault(str(name).strip(), 20)
    except Exception as exc:
        logger.warning("读取 drugExe 失败: %s", exc)
    return terms


async def collect_param_names(db: DatabaseManager) -> dict[str, int]:
    """从 configParam 收集监护参数中文名。"""
    terms: dict[str, int] = {}
    try:
        cursor = db.col("configParam").find({}, {"name": 1, "cnName": 1, "label": 1})
        async for doc in cursor:
            for key in ("name", "cnName", "label"):
                name = doc.get(key)
                if name and _is_valid_term(str(name)):
                    terms.setdefault(str(name).strip(), 15)
    except Exception as exc:
        logger.warning("读取 configParam 失败: %s", exc)
    return terms


async def collect_field_mapping_terms(db: DatabaseManager) -> dict[str, int]:
    """从 field_mapping 收集标准化概念名。"""
    terms: dict[str, int] = {}
    try:
        cursor = db.col("field_mapping").find(
            {"enabled": {"$ne": False}},
            {"standard_concept": 1, "standard_name": 1, "display_name": 1},
        ).limit(2000)
        async for doc in cursor:
            for key in ("standard_concept", "standard_name", "display_name"):
                name = doc.get(key)
                if name and _is_valid_term(str(name)):
                    terms.setdefault(str(name).strip(), 15)
    except Exception as exc:
        logger.warning("读取 field_mapping 失败: %s", exc)
    return terms


async def collect_lab_names(db: DatabaseManager, limit: int = 10000) -> dict[str, int]:
    """从 VI_ICU_EXAM_ITEM 收集检验项目名。"""
    terms: dict[str, int] = {}
    try:
        cursor = db.dc_col("VI_ICU_EXAM_ITEM").find(
            {}, {"itemName": 1, "testName": 1}
        ).sort("authTime", -1).limit(limit)
        async for doc in cursor:
            for key in ("itemName", "testName"):
                name = doc.get(key)
                if name and _is_valid_term(str(name)):
                    terms.setdefault(str(name).strip(), 15)
    except Exception as exc:
        logger.warning("读取 VI_ICU_EXAM_ITEM 失败: %s", exc)
    return terms


# ============================================================
# 合并 + 输出
# ============================================================

def merge_seeds(terms: dict[str, int]) -> dict[str, int]:
    """合并种子术语（DB 无数据时兜底）。"""
    for t in SEED_TERMS_HIGH:
        terms.setdefault(t, 20)
    for t in SEED_TERMS_ABBR:
        terms.setdefault(t, 25)  # 缩写最易错，权重最高
    return terms


def write_hotwords(terms: dict[str, int], out_path: str) -> int:
    """写入热词文件，按权重降序排列。"""
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for term, weight in sorted(terms.items(), key=lambda x: -x[1]):
            f.write(f"{term} {weight}\n")
    return len(terms)


async def main(out_path: str) -> None:
    cfg = get_config()
    db = DatabaseManager(cfg)
    await db.connect()
    try:
        terms: dict[str, int] = {}

        # 并发收集所有数据源
        results = await asyncio.gather(
            collect_drug_names(db),
            collect_drug_names_from_orders(db),
            collect_param_names(db),
            collect_field_mapping_terms(db),
            collect_lab_names(db),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, dict):
                # 合并，高权重不被低权重覆盖
                for k, v in result.items():
                    if k not in terms or v > terms[k]:
                        terms[k] = v

        terms = merge_seeds(terms)
        n = write_hotwords(terms, out_path)
        print(f"✅ 生成热词 {n} 条 → {out_path}")
    finally:
        await db.disconnect()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="生成 FunASR 热词表")
    ap.add_argument("--out", default="/opt/icu-models/hotwords.txt", help="输出文件路径")
    args = ap.parse_args()
    asyncio.run(main(args.out))
