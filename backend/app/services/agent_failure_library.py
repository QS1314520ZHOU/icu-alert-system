from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any


def _clip(value: Any, limit: int = 180) -> str:
    text = " ".join(str(value or "").strip().split())
    return text[: max(0, limit - 1)].rstrip() + "…" if len(text) > limit else text


def _deidentify(text: str) -> str:
    cleaned = str(text or "")
    cleaned = re.sub(r"[A-Za-z0-9_.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", "P###", cleaned)
    cleaned = re.sub(r"1[3-9]\d{9}", "P###", cleaned)
    cleaned = re.sub(r"\b\d{8,}\b", "P###", cleaned)
    cleaned = re.sub(r"([\u4e00-\u9fa5]{1,4})(?:患者|先生|女士)", "P###患者", cleaned)
    cleaned = re.sub(r"\b\d{1,3}\s*床\b", "B##床", cleaned)
    return cleaned


class AgentFailureLibrary:
    """Retrieves deidentified few-shot failure cases for agent reflection."""

    def __init__(self, *, db, config=None) -> None:
        self.db = db
        self.config = config

    def _tokens(self, twin: dict[str, Any]) -> set[str]:
        text = " ".join(
            [
                str(twin.get("patient", {}).get("diagnosis") if isinstance(twin.get("patient"), dict) else ""),
                " ".join(
                    str(item.get("title") or item.get("problem") or item) if isinstance(item, dict) else str(item)
                    for item in (twin.get("problem_list") or [])[:8]
                ),
                " ".join(str(row.get("alert_type") or row.get("rule_id") or row.get("name") or "") for row in (twin.get("recent_alerts_24h") or [])[:12]),
            ]
        ).lower()
        return {token for token in re.split(r"[^a-zA-Z0-9\u4e00-\u9fa5]+", text) if len(token) >= 2}

    @staticmethod
    def _failure_reason(doc: dict[str, Any]) -> str | None:
        outcomes = doc.get("outcomes") if isinstance(doc.get("outcomes"), dict) else {}
        if outcomes.get("24h") in {"event_occurred", "worsened", "deteriorated"}:
            return "24h反向结局"
        if doc.get("adopted") is False and str(doc.get("harm") or doc.get("harm_level") or "").lower() in {"moderate", "severe", "critical"}:
            return "未采纳且伤害等级≥moderate"
        if str(doc.get("disposition") or "").lower() in {"overridden", "ignored"} and outcomes.get("24h") == "event_occurred":
            return "处置与结局不符"
        return None

    async def get_relevant_failures(self, twin: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
        query_since = datetime.now() - timedelta(days=180)
        docs: list[dict[str, Any]] = []
        try:
            cursor = self.db.col("alert_outcomes").find({"fired_at": {"$gte": query_since}}).sort("updated_at", -1).limit(300)
            docs.extend([doc async for doc in cursor])
        except Exception:
            docs = []
        try:
            cursor = self.db.col("ai_generation_logs").find({"created_at": {"$gte": query_since}}).sort("created_at", -1).limit(200)
            docs.extend([doc async for doc in cursor])
        except Exception:
            pass

        twin_tokens = self._tokens(twin)
        scored: list[tuple[int, dict[str, Any]]] = []
        for doc in docs:
            reason = self._failure_reason(doc)
            if not reason:
                detail = doc.get("detail") if isinstance(doc.get("detail"), dict) else {}
                if not (detail.get("adopted") is False and str(detail.get("harm") or "").lower() in {"moderate", "severe", "critical"}):
                    continue
                reason = "AI建议反馈显示未采纳且潜在伤害≥moderate"
            text = " ".join(str(doc.get(key) or "") for key in ("scanner_name", "rule_id", "alert_type", "summary", "recommendation", "answer", "module"))
            tokens = {token for token in re.split(r"[^a-zA-Z0-9\u4e00-\u9fa5]+", text.lower()) if len(token) >= 2}
            score = len(tokens & twin_tokens)
            payload = {
                "case_id": f"failure-{len(scored) + 1}",
                "reason": reason,
                "lesson": _clip(_deidentify(text or reason), 180),
            }
            scored.append((score, payload))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [item for _, item in scored[: max(1, min(int(limit or 3), 3))]]
