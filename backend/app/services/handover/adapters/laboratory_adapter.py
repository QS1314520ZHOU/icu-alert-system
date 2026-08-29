"""Laboratory data adapter — queries VI_ICU_EXAM_ITEM collection."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from .base import AdapterResult

logger = logging.getLogger("icu-alert")


def _safe_text(val: Any) -> str:
    return str(val or "").strip()


class LaboratoryAdapter:
    """Queries lab results from VI_ICU_EXAM_ITEM."""

    def __init__(self, db) -> None:
        self.db = db

    async def query(
        self,
        p_ids: list[str],
        start: datetime,
        end: datetime,
    ) -> AdapterResult:
        """Query lab results for the given patient IDs and time range."""
        try:
            rows = await self.db.dc_col("VI_ICU_EXAM_ITEM").find(
                {
                    "hisPid": {"$in": p_ids},
                    "$or": [
                        {"authTime": {"$gte": start, "$lte": end}},
                        {"reportTime": {"$gte": start, "$lte": end}},
                    ],
                }
            ).sort("authTime", -1).to_list(length=200)

            if not rows:
                return AdapterResult(
                    status="empty",
                    source="VI_ICU_EXAM_ITEM",
                    patient_match_field="hisPid",
                    time_field="authTime/reportTime",
                    time_range={"start": start.isoformat(), "end": end.isoformat()},
                    count=0,
                )

            # Deduplicate: keep latest per item name
            seen: set[str] = set()
            results: list[dict[str, Any]] = []
            last_time = ""
            for r in rows:
                name = _safe_text(r.get("itemCnName") or r.get("itemName"))
                if not name or name in seen:
                    continue
                seen.add(name)
                val = _safe_text(r.get("result") or r.get("fResult"))
                ref = _safe_text(r.get("refRange") or r.get("range"))
                unit = _safe_text(r.get("unit"))
                flag = ""
                if val and ref:
                    try:
                        f_val = float(val)
                        ref_parts = ref.replace(" ", "").split("-")
                        if len(ref_parts) == 2:
                            lo, hi = float(ref_parts[0]), float(ref_parts[1])
                            if f_val < lo:
                                flag = "↓"
                            elif f_val > hi:
                                flag = "↑"
                    except Exception:
                        pass
                results.append({"name": name, "value": val, "ref": ref, "unit": unit, "flag": flag})
                if not last_time:
                    last_time = str(r.get("authTime", "") or r.get("reportTime", ""))

            return AdapterResult(
                status="available",
                source="VI_ICU_EXAM_ITEM",
                patient_match_field="hisPid",
                time_field="authTime/reportTime",
                time_range={"start": start.isoformat(), "end": end.isoformat()},
                count=len(results),
                last_updated_at=last_time,
                data=results,
            )

        except Exception as exc:
            logger.warning("LaboratoryAdapter: query failed: %s", exc)
            return AdapterResult(
                status="failed",
                source="VI_ICU_EXAM_ITEM",
                error_code="QUERY_FAILED",
                error_message=str(exc),
            )
