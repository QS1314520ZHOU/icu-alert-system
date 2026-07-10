"""
语音查房错例 review 服务。
候选生成（从 voice_rounding_logs 聚类）+ admin 采纳/驳回 + 安全写回 correction_hints.yaml。

安全硬约束：
- 药名相关候选拒绝走快速采纳（医疗安全红线）。
- 写 yaml 前备份，写后校验，坏则回滚。
- 每次配置变更写 audit_log。
- reload 必须原子。
- 定期任务只生成候选，绝不自动采纳。
"""
from __future__ import annotations

import logging
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from app.services.audit_service import write_audit_log
from app.utils.runtime_paths import package_root

logger = logging.getLogger("icu-alert")


# ================================================================
# 候选生成（从 logs 聚类，复用脚本的纯函数）
# ================================================================

async def generate_candidates(db, config, *, since: str | None = None) -> dict[str, Any]:
    """
    从 voice_rounding_logs 聚类生成 review 候选，写入 voice_rounding_review_candidates。
    已采纳/已驳回的候选不重复生成。
    返回生成统计。
    """
    # 延迟导入避免循环
    from scripts.review_voice_corrections import (
        _DRUG_NAMES_FLAT,
        _load_drug_names_from_hints,
        _load_existing_wrong_terms,
        classify_and_dedup,
        cluster_pairs,
        extract_edit_pairs,
        filter_clusters,
    )

    # 加载 hints（去重用）
    hints_path = _resolve_hints_path(config)
    existing_hints: dict[str, Any] = {}
    try:
        p = Path(hints_path)
        if p.exists():
            with p.open("r", encoding="utf-8") as f:
                existing_hints = yaml.safe_load(f) or {}
    except Exception:
        pass

    import scripts.review_voice_corrections as mod
    mod._DRUG_NAMES_FLAT = _load_drug_names_from_hints(existing_hints)

    # 查询 logs
    query: dict[str, Any] = {}
    if since:
        try:
            query["confirmed_at"] = {"$gte": datetime.fromisoformat(since)}
        except ValueError:
            pass

    cursor = db.col("voice_rounding_logs").find(query).sort("confirmed_at", -1)
    logs: list[dict[str, Any]] = []
    async for doc in cursor:
        logs.append(doc)

    if not logs:
        return {"logs_analyzed": 0, "candidates_generated": 0}

    # 聚类流水线
    pairs = extract_edit_pairs(logs)
    clusters = cluster_pairs(pairs)
    passed, rejected = filter_clusters(
        clusters, min_count=3, min_distinct_actors=2, min_score=0.4,
    )
    classified = classify_and_dedup(passed, existing_hints)

    # 查已有候选（去重）
    existing_keys: set[tuple[str, str]] = set()
    async for doc in db.col("voice_rounding_review_candidates").find(
        {}, {"before_key": 1, "after_key": 1}
    ):
        bk = str(doc.get("before_key") or "")
        ak = str(doc.get("after_key") or "")
        if bk and ak:
            existing_keys.add((bk, ak))

    # 写入候选
    now = datetime.now()
    generated = 0
    for category, candidates in classified.items():
        for c in candidates:
            before_key = "|".join(sorted(c.get("before_variants", [])))
            after_key = c.get("after", "")
            if (before_key, after_key) in existing_keys:
                continue

            is_drug = category == "drug_review"
            doc = {
                "before_key": before_key,
                "after_key": after_key,
                "before_variants": c.get("before_variants", []),
                "after": after_key,
                "suggested_category": category if not is_drug else "drug_review",
                "count": c.get("count", 0),
                "distinct_actors": c.get("distinct_actors", 0),
                "distinct_patients": c.get("distinct_patients", 0),
                "systematic_score": c.get("systematic_score", 0),
                "direction_consistency": c.get("direction_consistency", 0),
                "sample_log_ids": c.get("sample_log_ids", []),
                "status": "pending",
                "is_drug_confusable": is_drug,
                "created_at": now,
            }
            try:
                await db.col("voice_rounding_review_candidates").insert_one(doc)
                generated += 1
            except Exception:
                logger.warning("写入候选失败: %s → %s", before_key, after_key)

    return {
        "logs_analyzed": len(logs),
        "edit_pairs": len(pairs),
        "clusters_passed": len(passed),
        "clusters_rejected": len(rejected),
        "candidates_generated": generated,
    }


# ================================================================
# Admin CRUD
# ================================================================

async def list_candidates(db, *, status: str = "pending", limit: int = 200) -> list[dict[str, Any]]:
    """列出候选，药名严审区置顶，按系统性分降序。"""
    query: dict[str, Any] = {}
    if status:
        query["status"] = status

    cursor = db.col("voice_rounding_review_candidates").find(query).sort(
        [("is_drug_confusable", -1), ("systematic_score", -1)]
    ).limit(limit)

    results: list[dict[str, Any]] = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        results.append(doc)
    return results


async def decide_candidate(
    db,
    config,
    candidate_id: str,
    *,
    action: str,
    reviewer: str,
    target_category: str = "",
    voice_rounding_service=None,
) -> dict[str, Any]:
    """
    采纳或驳回候选。
    accept：写回 yaml + 热重载 + 审计。
    reject：标记状态 + 审计。
    """
    from bson import ObjectId

    try:
        doc = await db.col("voice_rounding_review_candidates").find_one(
            {"_id": ObjectId(candidate_id)}
        )
    except Exception:
        return {"code": 404, "message": "候选不存在"}

    if not doc:
        return {"code": 404, "message": "候选不存在"}
    if doc.get("status") != "pending":
        return {"code": 409, "message": f"候选状态为 {doc.get('status')}，不可重复操作"}

    now = datetime.now()

    if action == "reject":
        await db.col("voice_rounding_review_candidates").update_one(
            {"_id": ObjectId(candidate_id)},
            {"$set": {"status": "rejected", "reviewed_by": reviewer, "reviewed_at": now}},
        )
        await write_audit_log(
            db,
            action="voice_correction_reject",
            module="voice_rounding",
            actor=reviewer,
            target_type="voice_correction_candidate",
            target_id=candidate_id,
            detail={"before": doc.get("before_variants"), "after": doc.get("after")},
        )
        return {"code": 0, "message": "已驳回"}

    if action != "accept":
        return {"code": 400, "message": f"未知 action: {action}"}

    # ---- accept 流程 ----

    # 红线：药名相关禁止走快速采纳
    if doc.get("is_drug_confusable"):
        return {
            "code": 403,
            "message": "药名相关纠错必须由临床负责人在 yaml 中手动审定，不走快速采纳",
        }

    # 确定目标 category
    category = target_category or doc.get("suggested_category") or ""
    if category not in ("accent_errors", "dialect_phrases"):
        return {"code": 400, "message": f"无效的 target_category: {category}"}

    # 构建新条目
    wrong_variants = doc.get("before_variants") or []
    right = doc.get("after") or ""
    if not wrong_variants or not right:
        return {"code": 400, "message": "候选数据不完整"}

    new_entry = {"wrong": wrong_variants, "right": right}

    # 写回 yaml（带备份 + 校验 + 回滚）
    hints_path = _resolve_hints_path(config)
    write_result = await _safe_write_hints_yaml(
        hints_path=hints_path,
        category=category,
        new_entry=new_entry,
        db=db,
        reviewer=reviewer,
        candidate_id=candidate_id,
    )
    if not write_result["success"]:
        return {"code": 500, "message": write_result["message"]}

    # 如果是去重（已存在），直接返回，不重复写入
    if "已存在" in str(write_result.get("message", "")):
        await db.col("voice_rounding_review_candidates").update_one(
            {"_id": ObjectId(candidate_id)},
            {"$set": {"status": "accepted", "reviewed_by": reviewer, "reviewed_at": datetime.now(), "target_category": category}},
        )
        return {"code": 0, "message": write_result["message"]}

    # 更新候选状态
    await db.col("voice_rounding_review_candidates").update_one(
        {"_id": ObjectId(candidate_id)},
        {"$set": {
            "status": "accepted",
            "reviewed_by": reviewer,
            "reviewed_at": now,
            "target_category": category,
        }},
    )

    # 热重载
    if voice_rounding_service:
        await voice_rounding_service.reload_correction_hints()

    # 审计
    await write_audit_log(
        db,
        action="voice_correction_accept",
        module="voice_rounding",
        actor=reviewer,
        target_type="voice_correction_candidate",
        target_id=candidate_id,
        detail={
            "before_variants": wrong_variants,
            "after": right,
            "target_category": category,
            "hints_path": hints_path,
        },
    )

    return {"code": 0, "message": f"已采纳到 {category}"}


# ================================================================
# 安全写回 hints yaml
# ================================================================

def _resolve_hints_path(config) -> str:
    vr_cfg: dict[str, Any] = {}
    try:
        vr_cfg = config.yaml_cfg.get("voice_rounding", {}) or {}
    except Exception:
        pass
    custom = vr_cfg.get("correction_hints_path") or ""
    if custom:
        return custom
    return str(package_root() / "config" / "voice_rounding" / "correction_hints.yaml")


async def _safe_write_hints_yaml(
    *,
    hints_path: str,
    category: str,
    new_entry: dict[str, Any],
    db,
    reviewer: str,
    candidate_id: str,
) -> dict[str, Any]:
    """
    安全写回 correction_hints.yaml：
    1. 写前备份
    2. 去重检查
    3. 写入
    4. 写后校验（重新解析）
    5. 失败回滚
    """
    path = Path(hints_path)

    # 读取当前内容
    try:
        with path.open("r", encoding="utf-8") as f:
            current = yaml.safe_load(f) or {}
    except Exception as exc:
        return {"success": False, "message": f"读取 yaml 失败: {exc}"}

    if not isinstance(current, dict):
        current = {}

    # 去重：检查是否已存在
    existing = current.get(category) or []
    wrong_set = {tuple(sorted(e.get("wrong") or [])) for e in existing if isinstance(e, dict)}
    new_key = tuple(sorted(new_entry.get("wrong") or []))
    if new_key in wrong_set:
        # 已存在，标记 accepted 但不重复写入
        return {"success": True, "message": "对照已存在，不重复写入"}

    # 写前备份
    timestamp = int(time.time())
    bak_path = path.parent / f"{path.name}.bak.{timestamp}"
    try:
        shutil.copy2(str(path), str(bak_path))
    except Exception as exc:
        return {"success": False, "message": f"备份失败: {exc}"}

    # 追加新条目
    if category not in current:
        current[category] = []
    current[category].append(new_entry)

    # 写入
    try:
        with path.open("w", encoding="utf-8") as f:
            yaml.dump(current, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    except Exception as exc:
        # 写入失败，回滚
        _rollback_yaml(path, bak_path)
        return {"success": False, "message": f"写入 yaml 失败: {exc}"}

    # 写后校验：重新解析
    try:
        with path.open("r", encoding="utf-8") as f:
            reparsed = yaml.safe_load(f)
        if not isinstance(reparsed, dict):
            raise ValueError("解析结果不是 dict")
    except Exception as exc:
        # 解析失败，回滚
        _rollback_yaml(path, bak_path)
        return {"success": False, "message": f"写后校验失败，已回滚: {exc}"}

    return {"success": True, "message": f"已写入 {category}"}


def _rollback_yaml(path: Path, bak_path: Path) -> None:
    """回滚到备份文件。"""
    try:
        if bak_path.exists():
            shutil.copy2(str(bak_path), str(path))
            logger.warning("已回滚 %s 到 %s", path, bak_path)
    except Exception:
        logger.exception("回滚失败！%s 可能已损坏，请手动恢复自 %s", path, bak_path)
