from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any


def normalize_actor(*values: Any) -> str:
    for item in values:
        text = str(item or "").strip()
        if text:
            return text
    return "anonymous"


def source_hash(value: Any) -> str:
    text = str(value or "")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def write_audit_log(
    db,
    *,
    action: str,
    module: str,
    actor: str = "anonymous",
    target_type: str | None = None,
    target_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    now = datetime.now()
    payload = {
        "action": str(action or "").strip(),
        "module": str(module or "").strip(),
        "actor": normalize_actor(actor),
        "target_type": str(target_type or "").strip() or None,
        "target_id": str(target_id or "").strip() or None,
        "detail": detail or {},
        "created_at": now,
        "updated_at": now,
    }
    await db.col("audit_logs").insert_one(payload)


async def write_ai_generation_log(
    db,
    *,
    module: str,
    action: str,
    model: str,
    prompt_version: str,
    source_data_summary: Any,
    result: Any,
    actor: str = "anonymous",
    patient_id: str | None = None,
    success: bool = True,
    metadata: dict[str, Any] | None = None,
) -> None:
    now = datetime.now()
    summary_text = str(source_data_summary or "")
    result_text = str(result or "")
    payload = {
        "module": str(module or "").strip(),
        "action": str(action or "").strip(),
        "model": str(model or "").strip(),
        "prompt_version": str(prompt_version or "").strip(),
        "actor": normalize_actor(actor),
        "patient_id": str(patient_id or "").strip() or None,
        "generated_at": now,
        "created_at": now,
        "updated_at": now,
        "success": bool(success),
        "source_data_summary": source_data_summary,
        "source_data_hash": source_hash(summary_text),
        "result": result,
        "result_hash": source_hash(result_text),
        "metadata": metadata or {},
    }
    await db.col("ai_generated_content_logs").insert_one(payload)
