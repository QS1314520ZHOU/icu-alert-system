from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

from common import deidentify_text, jsonl_write, stable_hash, whitelist_payload

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.config import AppConfig
from app.database import DatabaseManager


async def main_async() -> int:
    parser = argparse.ArgumentParser(description="Prepare deidentified local ICU SFT JSONL for LoRA fine-tuning.")
    parser.add_argument("--output", default="backend/scripts/lora_finetune/out/sft.jsonl")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--review-sample", type=int, default=100)
    parser.add_argument("--write-audit", action="store_true")
    args = parser.parse_args()

    cfg = AppConfig()
    db = DatabaseManager(cfg)
    await db.connect()
    rows = []
    audit_rows = []
    try:
        cursor = db.col("ai_consult_logs").find({}).sort("created_at", -1).limit(max(1, int(args.limit or 100)))
        async for doc in cursor:
            answer = deidentify_text(doc.get("answer") or doc.get("result") or "")
            question = deidentify_text(doc.get("message") or doc.get("question") or "请给出ICU临床推理。")
            if len(answer) < 20:
                continue
            source_hash = stable_hash(doc.get("_id"))
            rows.append(
                {
                    "messages": [
                        {"role": "system", "content": "你是ICU临床推理助手，必须基于证据、避免正式医嘱。"},
                        {"role": "user", "content": question},
                        {"role": "assistant", "content": answer},
                    ],
                    "metadata": {"source_hash": source_hash, "deidentified": True, "fields": whitelist_payload(doc)},
                }
            )
            audit_rows.append({"source_hash": source_hash, "collection": "ai_consult_logs", "created_at": datetime.now(), "output": str(args.output)})
    finally:
        await db.disconnect()

    jsonl_write(Path(args.output), rows)
    review_path = Path(args.output).with_suffix(".review.jsonl")
    jsonl_write(review_path, rows[: max(1, min(int(args.review_sample or 100), 100))])
    if args.write_audit and audit_rows:
        db = DatabaseManager(cfg)
        await db.connect()
        try:
            await db.col("lora_training_corpus_audit").insert_many(audit_rows)
        finally:
            await db.disconnect()
    print(f"wrote {len(rows)} deidentified SFT sample(s); review file: {review_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
