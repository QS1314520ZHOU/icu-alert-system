from __future__ import annotations

from datetime import datetime, timezone
import math
from zoneinfo import ZoneInfo

from bson import ObjectId

API_TZ = ZoneInfo("Asia/Shanghai")


def serialize_doc(doc):
    """将 MongoDB 文档转换为 JSON 可序列化结构（支持顶层 dict / list / 标量）"""
    if doc is None:
        return None
    if isinstance(doc, ObjectId):
        return str(doc)
    if isinstance(doc, datetime):
        if doc.tzinfo is None:
            doc = doc.replace(tzinfo=timezone.utc)
        return doc.astimezone(API_TZ).isoformat()
    if isinstance(doc, list):
        return [serialize_doc(item) for item in doc]
    if isinstance(doc, tuple):
        return [serialize_doc(item) for item in doc]
    if not isinstance(doc, dict):
        if isinstance(doc, float):
            return doc if math.isfinite(doc) else None
        if hasattr(doc, "item") and callable(getattr(doc, "item")):
            try:
                return serialize_doc(doc.item())
            except Exception:
                return str(doc)
        return doc

    return {key: serialize_doc(value) for key, value in doc.items()}


def safe_oid(value):
    try:
        return ObjectId(str(value))
    except Exception:
        return None
