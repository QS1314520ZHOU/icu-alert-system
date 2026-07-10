from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

SAFE_PATIENT_FIELDS = {"age", "sex", "dept", "diagnosis", "summary", "reasoning", "recommendation", "outcome", "created_at"}
BLOCKED_FIELDS = {"name", "hisName", "idNo", "phone", "mobile", "address", "contact", "hisPid", "patient_id", "_id"}


def stable_hash(value: Any) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()[:16]


def deidentify_text(text: str) -> str:
    text = re.sub(r"1[3-9]\d{9}", "PHONE_REDACTED", str(text or ""))
    text = re.sub(r"\b\d{15,18}[\dXx]?\b", "ID_REDACTED", text)
    text = re.sub(r"(患者|姓名)[:：]?\s*[\u4e00-\u9fa5]{2,4}", r"\1: NAME_REDACTED", text)
    return text[:4000]


def whitelist_payload(doc: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for key, value in doc.items():
        if key in BLOCKED_FIELDS:
            continue
        if key not in SAFE_PATIENT_FIELDS:
            continue
        row[key] = deidentify_text(value) if isinstance(value, str) else value
    return row


def jsonl_write(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
