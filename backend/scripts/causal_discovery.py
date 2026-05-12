from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import AppConfig
from app.database import DatabaseManager
from app.utils.serialization import serialize_doc


def _fallback_candidates(limit: int) -> list[dict[str, Any]]:
    now = datetime.now()
    return [
        {
            "candidate_id": f"dryrun-lactate-hypotension-{idx}",
            "status": "pending",
            "source": {"algorithm": "dry_run_template", "confidence": 0.42},
            "finding_key": "lactate_rise",
            "cause_node": {
                "key": "dynamic_hypoperfusion_lactate",
                "label": "动态低灌注相关乳酸升高",
                "mechanism": "历史轨迹模板提示 MAP 下降与乳酸升高存在候选因果关联。",
                "clinical_domain": "hemodynamic",
                "base_rate": 0.12,
                "required_evidence": ["map_low"],
                "supportive_evidence": ["lactate_high", "shock_signal"],
                "contraindicating_evidence": [],
                "recommended_checks": ["复核 MAP、乳酸清除率与尿量趋势"],
                "initial_actions": ["由专家审核后再纳入知识图谱"],
                "rag_terms": ["hypoperfusion", "lactate"],
            },
            "evidence": [
                {
                    "key": "dynamic_hypoperfusion_pattern",
                    "label": "动态低灌注模式",
                    "category": "causal_discovery",
                    "positive_hint": "候选模型提示低灌注模式与异常相关",
                    "negative_hint": "候选模型未提示低灌注模式",
                }
            ],
            "created_at": now,
            "updated_at": now,
        }
        for idx in range(1, max(1, limit) + 1)
    ][:limit]


async def _sample_counts(db: DatabaseManager) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name in ("patient", "alert_records", "score"):
        try:
            counts[name] = await db.col(name).estimated_document_count()
        except Exception:
            counts[name] = 0
    return counts


async def main_async() -> int:
    parser = argparse.ArgumentParser(description="Discover candidate clinical KG causal nodes from Mongo history.")
    parser.add_argument("--output", default="causal_candidates.json")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--write-db", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        import dowhy  # type: ignore  # noqa: F401
    except Exception:
        print("Optional dependency missing: install DoWhy/NOTEARS in the training environment only, e.g. pip install dowhy notears.")
        print("Continuing with deterministic dry-run candidate generation.")

    cfg = AppConfig()
    db = DatabaseManager(cfg)
    await db.connect()
    try:
        counts = await _sample_counts(db)
        candidates = _fallback_candidates(max(1, min(int(args.limit or 3), 100)))
        for row in candidates:
            row["source"]["sample_counts"] = counts
        out = Path(args.output)
        out.write_text(json.dumps(serialize_doc(candidates), ensure_ascii=False, indent=2), encoding="utf-8")
        if args.write_db:
            for row in candidates:
                await db.col("kg_causal_candidates").update_one(
                    {"candidate_id": row["candidate_id"]},
                    {"$set": row, "$setOnInsert": {"created_at": datetime.now()}},
                    upsert=True,
                )
        print(f"wrote {len(candidates)} candidate(s) to {out}")
        return 0
    finally:
        await db.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
