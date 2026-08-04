"""
Tests for GET /api/patients/resolve — precise patient resolution by HIS identifiers.

Covers:
  1. mrn hit
  2. hisMrn alias hit
  3. his_pid hit
  4. mrn + his_pid priority (mrn wins)
  5. name+bed unique hit
  6. name+bed ambiguous (2 candidates)
  7. bed normalization ("5床" vs "05")
  8. name only (no bed) → 404
  9. all params empty → 404
  10. dept_code scoping → 404
  11. route order regression (resolve not caught by {patient_id})
  12. response body excludes sensitive fields
"""
from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId


# ---------------------------------------------------------------------------
# Fake collection / cursor for mocking runtime.db.col("patient")
# ---------------------------------------------------------------------------

class _AsyncIter:
    def __init__(self, docs):
        self._docs = list(docs)
        self._idx = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._docs):
            raise StopAsyncIteration
        item = self._docs[self._idx]
        self._idx += 1
        return item


class _FakeCursor:
    def __init__(self, docs):
        self._docs = list(docs)
        self._limit = None

    def limit(self, n):
        self._limit = n
        return self

    def __aiter__(self):
        docs = self._docs[: self._limit] if self._limit else self._docs
        return _AsyncIter(docs)


class _FakeCollection:
    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]

    def _match(self, doc, cond):
        """Minimal recursive matcher for $and / $or / field equality."""
        if not cond:
            return True
        if "$and" in cond:
            return all(self._match(doc, sub) for sub in cond["$and"])
        if "$or" in cond:
            return any(self._match(doc, sub) for sub in cond["$or"])
        for key, val in cond.items():
            if key.startswith("$"):
                return True
            if isinstance(val, dict):
                if "$in" in val:
                    if doc.get(key) not in val["$in"]:
                        return False
                elif "$nin" in val:
                    if doc.get(key) in val["$nin"]:
                        return False
                elif "$exists" in val:
                    if val["$exists"] != (key in doc):
                        return False
            elif doc.get(key) != val:
                return False
        return True

    def find(self, query=None, projection=None):
        query = query or {}
        matched = [doc for doc in self.docs if self._match(doc, query)]
        if projection:
            reduced = []
            for doc in matched:
                row = {}
                for k, enabled in projection.items():
                    if enabled and k in doc:
                        row[k] = doc[k]
                if "_id" in doc:
                    row["_id"] = doc["_id"]
                reduced.append(row)
            matched = reduced
        return _FakeCursor(matched)

    async def find_one(self, query, projection=None):
        query = query or {}
        for doc in self.docs:
            if self._match(doc, query):
                if projection:
                    row = {}
                    for k, enabled in projection.items():
                        if enabled and k in doc:
                            row[k] = doc[k]
                    if "_id" in doc:
                        row["_id"] = doc["_id"]
                    return row
                return dict(doc)
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_patient(**overrides) -> dict:
    doc = {
        "_id": ObjectId(),
        "name": "张三",
        "hisName": "张三",
        "mrn": "MRN001",
        "hisMrn": "HMRN001",
        "admissionNo": "ADM001",
        "hisPid": "HP001",
        "hisPID": "HP001",
        "hisBed": "05",
        "bed": "05",
        "showBed": "05床",
        "deptCode": "ICU01",
        "status": "admitted",
    }
    doc.update(overrides)
    return doc


def _patch_runtime(collection: _FakeCollection):
    """Patch runtime.db.col("patient") to return our fake collection."""
    mock_db = MagicMock()
    mock_db.col = MagicMock(return_value=collection)
    rt_mock = MagicMock()
    rt_mock.db = mock_db
    return patch("app.routers.patients.runtime", rt_mock)


def _patch_scope(query_result=None):
    """Patch research_patient_scope_query to return a permissive query."""
    return patch("app.routers.patients.research_patient_scope_query", return_value=query_result or {})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestResolvePatient:
    """GET /api/patients/resolve — exact HIS identifier resolution."""

    # 1. mrn hit
    @pytest.mark.asyncio
    async def test_mrn_hit(self):
        from app.routers.patients import resolve_patient

        pid = ObjectId()
        doc = _make_patient(_id=pid)
        col = _FakeCollection([doc])

        with _patch_runtime(col).start(), _patch_scope().start():
            resp = await resolve_patient(mrn="MRN001")

        assert resp["code"] == 0
        assert resp["patient_id"] == str(pid)
        assert resp["match_type"] == "mrn"

    # 2. hisMrn alias hit
    @pytest.mark.asyncio
    async def test_his_mrn_alias_hit(self):
        from app.routers.patients import resolve_patient

        pid = ObjectId()
        doc = _make_patient(_id=pid)
        col = _FakeCollection([doc])

        with _patch_runtime(col).start(), _patch_scope().start():
            resp = await resolve_patient(mrn="HMRN001")

        assert resp["code"] == 0
        assert resp["patient_id"] == str(pid)
        assert resp["match_type"] == "mrn"

    # 3. his_pid hit
    @pytest.mark.asyncio
    async def test_his_pid_hit(self):
        from app.routers.patients import resolve_patient

        pid = ObjectId()
        doc = _make_patient(_id=pid)
        col = _FakeCollection([doc])

        with _patch_runtime(col).start(), _patch_scope().start():
            resp = await resolve_patient(his_pid="HP001")

        assert resp["code"] == 0
        assert resp["patient_id"] == str(pid)
        assert resp["match_type"] == "his_pid"

    # 4. mrn + his_pid both present → mrn takes priority
    @pytest.mark.asyncio
    async def test_mrn_priority_over_his_pid(self):
        from app.routers.patients import resolve_patient

        pid = ObjectId()
        doc = _make_patient(_id=pid)
        col = _FakeCollection([doc])

        with _patch_runtime(col).start(), _patch_scope().start():
            resp = await resolve_patient(mrn="MRN001", his_pid="HP001")

        assert resp["code"] == 0
        assert resp["match_type"] == "mrn"

    # 5. name+bed unique hit
    @pytest.mark.asyncio
    async def test_name_bed_unique_hit(self):
        from app.routers.patients import resolve_patient

        pid = ObjectId()
        doc = _make_patient(_id=pid)
        col = _FakeCollection([doc])

        with _patch_runtime(col).start(), _patch_scope().start():
            resp = await resolve_patient(name="张三", bed="5")

        assert resp["code"] == 0
        assert resp["patient_id"] == str(pid)
        assert resp["match_type"] == "name_bed"

    # 6. name+bed ambiguous (2 same-name same-bed)
    @pytest.mark.asyncio
    async def test_name_bed_ambiguous(self):
        from app.routers.patients import resolve_patient

        doc1 = _make_patient(_id=ObjectId(), name="李四", hisName="李四", hisBed="03", bed="03", showBed="03床")
        doc2 = _make_patient(_id=ObjectId(), name="李四", hisName="李四", hisBed="03", bed="03", showBed="03床")
        col = _FakeCollection([doc1, doc2])

        with _patch_runtime(col).start(), _patch_scope().start():
            resp = await resolve_patient(name="李四", bed="03")

        assert resp["code"] == 409
        assert resp["match_type"] == "ambiguous"
        assert resp["candidates"] == 2

    # 7. bed normalization: "5床" matches "05"
    @pytest.mark.asyncio
    async def test_bed_normalization(self):
        from app.routers.patients import resolve_patient

        pid = ObjectId()
        doc = _make_patient(_id=pid, hisBed="05", bed="05", showBed="05床")
        col = _FakeCollection([doc])

        with _patch_runtime(col).start(), _patch_scope().start():
            resp = await resolve_patient(name="张三", bed="5床")

        assert resp["code"] == 0
        assert resp["patient_id"] == str(pid)
        assert resp["match_type"] == "name_bed"

    # 8. name only (no bed) → 404
    @pytest.mark.asyncio
    async def test_name_only_no_bed_returns_404(self):
        from app.routers.patients import resolve_patient

        doc = _make_patient()
        col = _FakeCollection([doc])

        with _patch_runtime(col).start(), _patch_scope().start():
            resp = await resolve_patient(name="张三")

        assert resp["code"] == 404

    # 9. all params empty → 404
    @pytest.mark.asyncio
    async def test_empty_params_returns_404(self):
        from app.routers.patients import resolve_patient

        doc = _make_patient()
        col = _FakeCollection([doc])

        with _patch_runtime(col).start(), _patch_scope().start():
            resp = await resolve_patient()

        assert resp["code"] == 404

    # 10. dept_code scoping — patient not in that dept → 404
    @pytest.mark.asyncio
    async def test_dept_code_scoping(self):
        from app.routers.patients import resolve_patient

        doc = _make_patient(deptCode="ICU01")
        col = _FakeCollection([doc])

        with _patch_runtime(col).start(), _patch_scope().start():
            resp = await resolve_patient(mrn="MRN001", dept_code="WARD99")

        assert resp["code"] == 404

    # 11. route order regression: /api/patients/resolve is not caught by /{patient_id}
    @pytest.mark.asyncio
    async def test_resolve_route_not_caught_by_patient_id(self):
        """If the route order is wrong, requesting /api/patients/resolve would
        match the {patient_id} endpoint and return code 400 '无效患者ID'.
        This test verifies that doesn't happen."""
        from app.routers.patients import resolve_patient

        col = _FakeCollection([])

        with _patch_runtime(col).start(), _patch_scope().start():
            resp = await resolve_patient()

        # Must NOT be the 400 from get_patient's ObjectId("resolve") failure
        assert resp.get("message") != "无效患者ID"
        assert resp["code"] == 404

    # 12. response body excludes sensitive fields
    @pytest.mark.asyncio
    async def test_response_excludes_sensitive_fields(self):
        from app.routers.patients import resolve_patient

        pid = ObjectId()
        doc = _make_patient(_id=pid)
        col = _FakeCollection([doc])

        with _patch_runtime(col).start(), _patch_scope().start():
            resp = await resolve_patient(mrn="MRN001")

        assert resp["code"] == 0
        # Only expected keys
        assert set(resp.keys()) == {"code", "patient_id", "match_type"}
        # No patient identity leakage
        assert "name" not in resp
        assert "mrn" not in resp
        assert "hisPid" not in resp

    # extra: admissionNo alias
    @pytest.mark.asyncio
    async def test_admission_no_alias_hit(self):
        from app.routers.patients import resolve_patient

        pid = ObjectId()
        doc = _make_patient(_id=pid)
        col = _FakeCollection([doc])

        with _patch_runtime(col).start(), _patch_scope().start():
            resp = await resolve_patient(mrn="ADM001")

        assert resp["code"] == 0
        assert resp["patient_id"] == str(pid)
        assert resp["match_type"] == "mrn"

    # extra: name+bed name match but bed mismatch → 404
    @pytest.mark.asyncio
    async def test_name_bed_wrong_bed(self):
        from app.routers.patients import resolve_patient

        doc = _make_patient(hisBed="05", bed="05")
        col = _FakeCollection([doc])

        with _patch_runtime(col).start(), _patch_scope().start():
            resp = await resolve_patient(name="张三", bed="99")

        assert resp["code"] == 404

    # extra: hisPID alias
    @pytest.mark.asyncio
    async def test_his_pid_uppercase_alias(self):
        from app.routers.patients import resolve_patient

        pid = ObjectId()
        doc = _make_patient(_id=pid)
        col = _FakeCollection([doc])

        with _patch_runtime(col).start(), _patch_scope().start():
            resp = await resolve_patient(his_pid="HP001")

        assert resp["code"] == 0
        assert resp["match_type"] == "his_pid"

    # extra: name match via hisName field
    @pytest.mark.asyncio
    async def test_name_bed_via_his_name(self):
        from app.routers.patients import resolve_patient

        pid = ObjectId()
        doc = _make_patient(_id=pid, name="", hisName="王五", hisBed="02", bed="02")
        col = _FakeCollection([doc])

        with _patch_runtime(col).start(), _patch_scope().start():
            resp = await resolve_patient(name="王五", bed="2")

        assert resp["code"] == 0
        assert resp["patient_id"] == str(pid)
        assert resp["match_type"] == "name_bed"
