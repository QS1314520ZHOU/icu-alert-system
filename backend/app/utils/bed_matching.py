from __future__ import annotations

import re
from typing import Any


def _normalize_bed(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    s = s.upper().replace("床", "")
    if s.startswith("BED"):
        s = s[3:]
    s = s.strip()
    match = re.search(r"\d+", s)
    if match:
        try:
            return str(int(match.group(0)))
        except Exception:
            return match.group(0)
    return s


def _bed_match(a: Any, b: Any) -> bool:
    na = _normalize_bed(a)
    nb = _normalize_bed(b)
    if not na or not nb:
        return False
    return na == nb
