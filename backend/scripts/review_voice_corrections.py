"""
语音查房错例离线聚类 + 人工 review 脚本。

从 voice_rounding_logs 集合抽取医生手改 (edited_spans)，
聚类为"系统性错例"候选清单，输出 YAML 供人工 review 后直接粘贴到 correction_hints.yaml。

只读 voice_rounding_logs，绝不写 correction_hints.yaml、绝不写任何在线集合。

用法：
  python backend/scripts/review_voice_corrections.py
  python backend/scripts/review_voice_corrections.py --since 2025-06-01 --min-count 5 --min-actors 2
"""
from __future__ import annotations

import argparse
import asyncio
import difflib
import hashlib
import logging
import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from app.config import get_config
from app.database import DatabaseManager
from app.utils.runtime_paths import package_root

logger = logging.getLogger("icu-alert")


# ================================================================
# 归一化
# ================================================================

def _normalize(text: str) -> str:
    """去首尾空白、统一全角→半角、统一 Unicode NFKC。"""
    text = unicodedata.normalize("NFKC", text or "").strip()
    # 全角数字/字母→半角
    text = text.translate(
        str.maketrans(
            "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ",
            "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
        )
    )
    return text


def _is_replace(span: dict[str, Any]) -> bool:
    return str(span.get("op") or "") == "replace"


# ================================================================
# 提取编辑对
# ================================================================

def extract_edit_pairs(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    从 logs 的 edited_spans 中提取 replace 类型的 (before, after) 对。
    每条对携带溯源字段。
    """
    pairs: list[dict[str, Any]] = []
    for log in logs:
        log_id = str(log.get("_id") or "")
        actor = str(log.get("confirmed_by") or "")
        patient_id = str(log.get("patient_id") or "")
        confirmed_at = log.get("confirmed_at")

        for span in (log.get("edited_spans") or []):
            if not _is_replace(span):
                continue
            raw_before = str(span.get("before") or "")
            raw_after = str(span.get("after") or "")
            if not raw_before.strip() or not raw_after.strip():
                continue
            pairs.append({
                "before_raw": raw_before,
                "after_raw": raw_after,
                "before_norm": _normalize(raw_before),
                "after_norm": _normalize(raw_after),
                "log_id": log_id,
                "actor": actor,
                "patient_id": patient_id,
                "confirmed_at": confirmed_at,
            })
    return pairs


# ================================================================
# 聚类
# ================================================================

def _similarity(a: str, b: str) -> float:
    """编辑距离相似度（SequenceMatcher ratio）。"""
    return difflib.SequenceMatcher(None, a, b).ratio()


def cluster_pairs(
    pairs: list[dict[str, Any]],
    merge_threshold: float = 0.75,
) -> list[dict[str, Any]]:
    """
    按 (before_norm, after_norm) 精确分组，再用编辑距离合并相似的 before。
    返回簇列表，每簇含代表性 before 列表、统一 after、元数据。
    """
    # 第一步：精确分组
    exact_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for p in pairs:
        key = (p["before_norm"], p["after_norm"])
        exact_groups[key].append(p)

    # 第二步：按 after 分桶，再对 before 做近似合并
    after_buckets: dict[str, list[tuple[str, list[dict[str, Any]]]]] = defaultdict(list)
    for (b_norm, a_norm), items in exact_groups.items():
        after_buckets[a_norm].append((b_norm, items))

    clusters: list[dict[str, Any]] = []
    for after_norm, bucket in after_buckets.items():
        # 对 bucket 内的 before 做贪心合并
        merged: list[list[tuple[str, list[dict[str, Any]]]]] = []
        used = set()
        for i, (b1, items1) in enumerate(bucket):
            if i in used:
                continue
            group = [(b1, items1)]
            used.add(i)
            for j, (b2, items2) in enumerate(bucket):
                if j in used:
                    continue
                if _similarity(b1, b2) >= merge_threshold:
                    group.append((b2, items2))
                    used.add(j)
            merged.append(group)

        for group in merged:
            all_items: list[dict[str, Any]] = []
            before_variants: list[str] = []
            for b_norm, items in group:
                before_variants.append(b_norm)
                all_items.extend(items)

            actors = {item["actor"] for item in all_items if item["actor"]}
            patients = {item["patient_id"] for item in all_items if item["patient_id"]}
            sample_log_ids = list({item["log_id"] for item in all_items if item["log_id"]})[:5]

            clusters.append({
                "before_variants": sorted(set(before_variants)),
                "after": after_norm,
                "count": len(all_items),
                "distinct_actors": len(actors),
                "distinct_patients": len(patients),
                "actors": sorted(actors),
                "sample_log_ids": sample_log_ids,
                "direction_consistency": _direction_consistency(all_items),
            })

    return clusters


def _direction_consistency(items: list[dict[str, Any]]) -> float:
    """
    方向一致性：同一个 before 是否总是改成同一个 after。
    返回 0.0~1.0，1.0 表示完全一致。
    """
    before_to_afters: dict[str, set[str]] = defaultdict(set)
    for item in items:
        before_to_afters[item["before_norm"]].add(item["after_norm"])
    if not before_to_afters:
        return 0.0
    consistent = sum(1 for afters in before_to_afters.values() if len(afters) == 1)
    return consistent / len(before_to_afters)


# ================================================================
# 噪声过滤
# ================================================================

def compute_systematic_score(
    cluster: dict[str, Any],
    *,
    min_count: int,
    min_distinct_actors: int,
) -> float:
    """
    系统性分：综合频次、跨医生数、方向一致性。
    满分 1.0，低于阈值的不进 review 清单。
    """
    count = cluster["count"]
    actors = cluster["distinct_actors"]
    consistency = cluster["direction_consistency"]

    # 频次分（归一化到 0~1，min_count 对应 ~0.5）
    count_score = min(1.0, count / max(min_count * 2, 1))

    # 跨医生分（权重最高，min_distinct_actors 对应 ~0.7）
    actor_score = min(1.0, actors / max(min_distinct_actors * 1.5, 1))

    # 加权：跨医生权重最高
    score = count_score * 0.3 + actor_score * 0.5 + consistency * 0.2
    return round(score, 3)


def filter_clusters(
    clusters: list[dict[str, Any]],
    *,
    min_count: int,
    min_distinct_actors: int,
    min_score: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    过滤并返回 (passed, rejected)。
    """
    passed: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for c in clusters:
        score = compute_systematic_score(
            c, min_count=min_count, min_distinct_actors=min_distinct_actors,
        )
        c["systematic_score"] = score

        # 方向不一致直接降级
        if c["direction_consistency"] < 0.8:
            c["reject_reason"] = "direction_inconsistent"
            rejected.append(c)
            continue

        # 频次不足
        if c["count"] < min_count:
            c["reject_reason"] = "low_count"
            rejected.append(c)
            continue

        # 跨医生不足
        if c["distinct_actors"] < min_distinct_actors:
            c["reject_reason"] = "low_actor_diversity"
            rejected.append(c)
            continue

        # 综合分不足
        if score < min_score:
            c["reject_reason"] = "low_systematic_score"
            rejected.append(c)
            continue

        passed.append(c)

    return passed, rejected


# ================================================================
# 分类 + 去重
# ================================================================

_DRUG_NAMES_FLAT: set[str] = set()


def _load_drug_names_from_hints(hints: dict[str, Any]) -> set[str]:
    """从 correction_hints 加载所有药名。"""
    names: set[str] = set()
    for entry in (hints.get("drug_confusables") or []):
        for n in (entry.get("names") or []):
            names.add(str(n))
    return names


def _load_existing_wrong_terms(hints: dict[str, Any]) -> set[str]:
    """加载现有 accent_errors + dialect_phrases 的 wrong 词，用于去重。"""
    terms: set[str] = set()
    for entry in (hints.get("accent_errors") or []):
        for w in (entry.get("wrong") or []):
            terms.add(_normalize(w))
    for entry in (hints.get("dialect_phrases") or []):
        for w in (entry.get("wrong") or []):
            terms.add(_normalize(w))
    return terms


def _hits_drug(before: str, after: str) -> bool:
    """编辑对是否涉及药名。"""
    for name in _DRUG_NAMES_FLAT:
        if name in before or name in after:
            return True
    return False


def _classify_candidate(cluster: dict[str, Any]) -> str:
    """
    启发式分类：accent_errors / dialect_phrases / drug_review。
    药名相关单独标记，不走快速采纳。
    """
    before = cluster["before_variants"][0] if cluster["before_variants"] else ""
    after = cluster["after"]

    # 药名严审
    if _hits_drug(before, after):
        return "drug_review"

    # 字面相近（编辑距离小、同音/形近）→ accent_errors
    sim = _similarity(before, after)
    if sim >= 0.5 and len(before) <= len(after) * 2:
        return "accent_errors"

    # 其他 → dialect_phrases
    return "dialect_phrases"


def classify_and_dedup(
    clusters: list[dict[str, Any]],
    existing_hints: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    """
    分类候选，与现有 hints 去重。
    返回 {"accent_errors": [...], "dialect_phrases": [...], "drug_review": [...]}。
    """
    existing_wrong = _load_existing_wrong_terms(existing_hints)
    result: dict[str, list[dict[str, Any]]] = {
        "accent_errors": [],
        "dialect_phrases": [],
        "drug_review": [],
    }

    for c in clusters:
        # 去重：所有 before_variants 都已在 hints 里 → 跳过
        all_in_hints = all(_normalize(v) in existing_wrong for v in c["before_variants"])
        if all_in_hints:
            continue

        category = _classify_candidate(c)
        result[category].append(c)

    # 按系统性分降序
    for key in result:
        result[key].sort(key=lambda x: -x.get("systematic_score", 0))

    return result


# ================================================================
# 输出
# ================================================================

def _build_output_yaml(
    classified: dict[str, list[dict[str, Any]]],
    run_meta: dict[str, Any],
) -> dict[str, Any]:
    """构建与 correction_hints.yaml 对齐的输出结构。"""
    output: dict[str, Any] = {"_meta": run_meta}

    # 药名严审区（置顶警示）
    drug_review = classified.get("drug_review") or []
    if drug_review:
        output["drug_review_warning"] = (
            "以下编辑对涉及易混药名，绝不走快速采纳，必须人工逐条严审。"
        )
        output["drug_review"] = [
            {
                "suggested_action": "人工严审，不自动采纳",
                "before_variants": c["before_variants"],
                "after": c["after"],
                "count": c["count"],
                "distinct_actors": c["distinct_actors"],
                "distinct_patients": c["distinct_patients"],
                "systematic_score": c["systematic_score"],
                "direction_consistency": c["direction_consistency"],
                "sample_log_ids": c["sample_log_ids"],
            }
            for c in drug_review
        ]

    # accent_errors 候选
    accent = classified.get("accent_errors") or []
    if accent:
        output["accent_errors_candidates"] = [
            {
                "suggested_category": "accent_errors",
                "wrong": c["before_variants"],
                "right": c["after"],
                "count": c["count"],
                "distinct_actors": c["distinct_actors"],
                "distinct_patients": c["distinct_patients"],
                "systematic_score": c["systematic_score"],
                "direction_consistency": c["direction_consistency"],
                "sample_log_ids": c["sample_log_ids"],
            }
            for c in accent
        ]

    # dialect_phrases 候选
    dialect = classified.get("dialect_phrases") or []
    if dialect:
        output["dialect_phrases_candidates"] = [
            {
                "suggested_category": "dialect_phrases",
                "wrong": c["before_variants"],
                "right": c["after"],
                "count": c["count"],
                "distinct_actors": c["distinct_actors"],
                "distinct_patients": c["distinct_patients"],
                "systematic_score": c["systematic_score"],
                "direction_consistency": c["direction_consistency"],
                "sample_log_ids": c["sample_log_ids"],
            }
            for c in dialect
        ]

    return output


def _print_summary(
    total_pairs: int,
    passed: int,
    rejected: int,
    classified: dict[str, list[dict[str, Any]]],
) -> None:
    """打印控制台摘要。"""
    drug = len(classified.get("drug_review") or [])
    accent = len(classified.get("accent_errors") or [])
    dialect = len(classified.get("dialect_phrases") or [])

    print("\n" + "=" * 60)
    print("语音查房错例聚类分析摘要")
    print("=" * 60)
    print(f"  总编辑对（replace 类型）：{total_pairs}")
    print(f"  通过过滤的候选簇：      {passed}")
    print(f"  被噪声过滤掉：          {rejected}")
    print(f"  ─────────────────────────")
    print(f"  ⚠️ 药名严审区：          {drug}")
    print(f"  口音错字候选：          {accent}")
    print(f"  方言口语候选：          {dialect}")
    print("=" * 60 + "\n")


# ================================================================
# 主流程
# ================================================================

async def main(
    *,
    since: str | None = None,
    min_count: int = 3,
    min_distinct_actors: int = 2,
    min_score: float = 0.4,
    out: str = "",
    merge_threshold: float = 0.75,
) -> None:
    cfg = get_config()
    db = DatabaseManager(cfg)
    await db.connect()

    try:
        # 加载现有 hints（用于去重 + 药名识别）
        global _DRUG_NAMES_FLAT
        hints_path = str(package_root() / "config" / "voice_rounding" / "correction_hints.yaml")
        hints_cfg = (cfg.yaml_cfg.get("voice_rounding") or {}).get("correction_hints_path") or ""
        if hints_cfg:
            hints_path = hints_cfg
        existing_hints: dict[str, Any] = {}
        try:
            p = Path(hints_path)
            if p.exists():
                with p.open("r", encoding="utf-8") as f:
                    existing_hints = yaml.safe_load(f) or {}
        except Exception:
            logger.warning("加载 correction_hints.yaml 失败，去重功能不可用")
        _DRUG_NAMES_FLAT = _load_drug_names_from_hints(existing_hints)

        # 查询 logs
        query: dict[str, Any] = {}
        if since:
            try:
                since_dt = datetime.fromisoformat(since)
                query["confirmed_at"] = {"$gte": since_dt}
            except ValueError:
                logger.warning("无效的 --since 格式: %s，忽略", since)

        cursor = db.col("voice_rounding_logs").find(query).sort("confirmed_at", -1)
        logs: list[dict[str, Any]] = []
        async for doc in cursor:
            logs.append(doc)

        if not logs:
            print("voice_rounding_logs 无数据，退出。")
            return

        # 流水线
        pairs = extract_edit_pairs(logs)
        clusters = cluster_pairs(pairs, merge_threshold=merge_threshold)
        passed, rejected = filter_clusters(
            clusters,
            min_count=min_count,
            min_distinct_actors=min_distinct_actors,
            min_score=min_score,
        )
        classified = classify_and_dedup(passed, existing_hints)

        # 输出
        total_pairs = len(pairs)
        total_passed = len(passed)
        total_rejected = len(rejected)

        _print_summary(total_pairs, total_passed, total_rejected, classified)

        if not out:
            date_str = datetime.now().strftime("%Y%m%d")
            out = str(package_root() / "scripts" / f"review_candidates_{date_str}.yaml")

        run_meta = {
            "generated_at": datetime.now().isoformat(),
            "logs_analyzed": len(logs),
            "edit_pairs_extracted": total_pairs,
            "clusters_passed": total_passed,
            "clusters_rejected": total_rejected,
            "min_count": min_count,
            "min_distinct_actors": min_distinct_actors,
            "min_score": min_score,
            "merge_threshold": merge_threshold,
        }
        output = _build_output_yaml(classified, run_meta)

        Path(out).parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            yaml.dump(output, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        print(f"✅ 候选清单已写入: {out}")

    finally:
        await db.disconnect()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

    ap = argparse.ArgumentParser(description="语音查房错例离线聚类 + 人工 review")
    ap.add_argument("--since", default=None, help="只分析此日期后的 log（ISO 格式，如 2025-06-01）")
    ap.add_argument("--min-count", type=int, default=3, help="最低出现次数（默认 3）")
    ap.add_argument("--min-actors", type=int, default=2, help="最低跨医生数（默认 2）")
    ap.add_argument("--min-score", type=float, default=0.4, help="最低系统性分（默认 0.4）")
    ap.add_argument("--merge-threshold", type=float, default=0.75, help="before 近似合并阈值（默认 0.75）")
    ap.add_argument("--out", default="", help="输出文件路径（默认 scripts/review_candidates_{date}.yaml）")
    args = ap.parse_args()

    asyncio.run(main(
        since=args.since,
        min_count=args.min_count,
        min_distinct_actors=args.min_actors,
        min_score=args.min_score,
        out=args.out,
        merge_threshold=args.merge_threshold,
    ))
