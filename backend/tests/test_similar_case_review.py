from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.alert_engine.similar_case_review import SimilarCaseReviewMixin


class _Cursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = list(docs)
        self._idx = 0

    def sort(self, key: str, direction: int) -> "_Cursor":
        self._docs.sort(key=lambda row: row.get(key), reverse=direction == -1)
        return self

    def limit(self, count: int) -> "_Cursor":
        self._docs = self._docs[:count]
        return self

    def __aiter__(self) -> "_Cursor":
        self._idx = 0
        return self

    async def __anext__(self) -> dict[str, Any]:
        if self._idx >= len(self._docs):
            raise StopAsyncIteration
        row = self._docs[self._idx]
        self._idx += 1
        return dict(row)


class _Collection:
    def __init__(self, docs: list[dict[str, Any]] | None = None) -> None:
        self.docs = [dict(doc) for doc in (docs or [])]

    def find(self, query: dict[str, Any] | None = None, projection: dict[str, int] | None = None) -> _Cursor:
        query = query or {}
        rows = [doc for doc in self.docs if self._match(doc, query)]
        if projection:
            projected = []
            for doc in rows:
                item = {}
                for key, enabled in projection.items():
                    if enabled and key in doc:
                        item[key] = doc[key]
                if "_id" in doc:
                    item["_id"] = doc["_id"]
                projected.append(item)
            rows = projected
        return _Cursor(rows)

    async def find_one(self, query: dict[str, Any], sort: list[tuple[str, int]] | None = None) -> dict[str, Any] | None:
        rows = [doc for doc in self.docs if self._match(doc, query)]
        if sort:
            key, direction = sort[0]
            rows.sort(key=lambda row: row.get(key), reverse=direction == -1)
        return dict(rows[0]) if rows else None

    async def insert_one(self, doc: dict[str, Any]):
        row = dict(doc)
        row.setdefault("_id", len(self.docs) + 1)
        self.docs.append(row)

        class _Result:
            inserted_id = row["_id"]

        return _Result()

    async def update_one(self, selector: dict[str, Any], update: dict[str, Any]) -> None:
        for doc in self.docs:
            if self._match(doc, selector):
                for key, value in update.get("$set", {}).items():
                    doc[key] = value
                return

    @classmethod
    def _match(cls, doc: dict[str, Any], query: dict[str, Any]) -> bool:
        for key, value in query.items():
            if key == "$and":
                if not all(cls._match(doc, item) for item in value):
                    return False
                continue
            if key == "$or":
                if not any(cls._match(doc, item) for item in value):
                    return False
                continue
            current = doc.get(key)
            if isinstance(value, dict):
                if "$ne" in value and current == value["$ne"]:
                    return False
                if "$exists" in value:
                    exists = key in doc and doc.get(key) is not None
                    if bool(value["$exists"]) != exists:
                        return False
                if "$in" in value and current not in value["$in"]:
                    return False
                if "$regex" in value:
                    if value["$regex"].lower() not in str(current or "").lower():
                        return False
            elif current != value:
                return False
        return True


class _FakeDb:
    def __init__(self, collections: dict[str, list[dict[str, Any]]]) -> None:
        self._collections = {name: _Collection(rows) for name, rows in collections.items()}

    def col(self, name: str) -> _Collection:
        return self._collections.setdefault(name, _Collection())


class _ReviewEngine(SimilarCaseReviewMixin):
    def __init__(self, db: _FakeDb) -> None:
        self.db = db
        self.config = SimpleNamespace(
            yaml_cfg={
                "alert_engine": {
                    "similar_case_review": {
                        "max_candidates": 20,
                        "age_band_years": 15,
                        "sofa_band": 3,
                        "min_diagnosis_similarity": 0.05,
                        "embedding_weight": 0.0,
                        "token_weight": 0.45,
                        "age_weight": 0.2,
                        "sofa_weight": 0.25,
                        "support_weight": 0.1,
                    },
                    "drug_mapping": {"vasopressors": ["去甲肾上腺素"]},
                }
            },
            llm_fast_model=None,
        )

    def _get_cfg_list(self, path: tuple[str, ...], default: list[str]) -> list[str]:
        cursor: Any = self.config.yaml_cfg
        for key in path:
            if not isinstance(cursor, dict) or key not in cursor:
                return default
            cursor = cursor[key]
        return cursor if isinstance(cursor, list) else default

    def _patient_icu_start_time(self, patient_doc: dict) -> datetime | None:
        return patient_doc.get("icuAdmissionTime") or patient_doc.get("admissionTime")


@pytest.mark.asyncio
async def test_similar_case_review_returns_ranked_cases_and_summary() -> None:
    now = datetime.now()
    db = _FakeDb(
        {
            "patient": [
                {"_id": "p1", "name": "当前患者", "hisPid": "H1", "age": 62, "clinicalDiagnosis": "脓毒症 肺炎", "icuAdmissionTime": now - timedelta(days=2)},
                {"_id": "p2", "name": "病例A", "hisPid": "H2", "age": 65, "clinicalDiagnosis": "脓毒症 肺炎", "status": "discharged", "icuAdmissionTime": now - timedelta(days=9), "dischargeTime": now - timedelta(days=2)},
                {"_id": "p3", "name": "病例B", "hisPid": "H3", "age": 59, "clinicalDiagnosis": "感染性休克 肺炎", "status": "dead", "icuAdmissionTime": now - timedelta(days=11), "deathTime": now - timedelta(days=1)},
            ],
            "deviceBind": [
                {"pid": "p1", "type": "vent", "bindTime": now - timedelta(days=2), "unBindTime": None, "deviceName": "呼吸机"},
                {"pid": "p2", "type": "vent", "bindTime": now - timedelta(days=9), "unBindTime": now - timedelta(days=4), "deviceName": "呼吸机"},
                {"pid": "p3", "type": "vent", "bindTime": now - timedelta(days=11), "unBindTime": now - timedelta(days=8), "deviceName": "呼吸机"},
            ],
            "score": [
                {"patient_id": "p1", "score_type": "sofa", "calc_time": now - timedelta(days=2), "score": 8},
                {"patient_id": "p2", "score_type": "sofa", "calc_time": now - timedelta(days=9), "score": 7},
                {"patient_id": "p3", "score_type": "sofa", "calc_time": now - timedelta(days=11), "score": 9},
            ],
            "alert_records": [],
            "drugExe": [{"pid": "p2", "drugName": "去甲肾上腺素"}],
        }
    )
    engine = _ReviewEngine(db)

    result = await engine.get_similar_case_outcomes(db.col("patient").docs[0], limit=5)

    assert result["summary"]["matched_cases"] >= 2
    assert len(result["cases"]) >= 2
    assert result["cases"][0]["similarity_score"] >= result["cases"][1]["similarity_score"]
    assert result["historical_case_insight"]["summary"]
    assert "diagnosis_tokens" in result["current_profile"]

