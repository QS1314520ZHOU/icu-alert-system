from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import AppConfig
from app.database import DatabaseManager
from app.utils.serialization import serialize_doc


async def main_async() -> int:
    parser = argparse.ArgumentParser(description="Generate scanner-based pseudo labels for knowledge-guided pretraining.")
    parser.add_argument("--output", default="backend/scripts/knowledge_guided_pretrain/out/pseudo_labels.jsonl")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()
    cfg = AppConfig()
    db = DatabaseManager(cfg)
    await db.connect()
    rows = []
    try:
        cursor = db.col("alert_records").find({}).sort("created_at", -1).limit(max(1, int(args.limit or 500)))
        async for doc in cursor:
            rows.append(
                {
                    "patient_hash": str(doc.get("patient_id") or "")[-8:],
                    "label": doc.get("rule_id") or doc.get("alert_type"),
                    "severity": doc.get("severity"),
                    "time": doc.get("created_at"),
                    "source": "scanner",
                }
            )
    finally:
        await db.disconnect()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(serialize_doc(row), ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} pseudo label(s) to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
