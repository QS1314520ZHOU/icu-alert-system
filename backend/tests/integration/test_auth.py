"""
Auth integration tests.

Tests the authentication and authorization flow:
- JWT validation → 401 if invalid/expired
- User loading from DB → fallback to JWT
- Patient access authorization by dept/ward/permission

These tests use a minimal FastAPI app with mocked MongoDB
to test the auth middleware without requiring a real database.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from jose import jwt

# Ensure backend root is importable
BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.auth import User, UserRole, get_current_user, require_patient_access
from app.auth.jwt_handler import SECRET_KEY, ALGORITHM
from bson import ObjectId

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    """Minimal FastAPI app with auth-protected endpoints."""
    _app = FastAPI()

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _lifespan(app):
        yield

    _app.router.lifespan_context = _lifespan

    @_app.get("/api/test/no-auth")
    async def no_auth():
        return {"ok": True}

    @_app.get("/api/test/current-user")
    async def get_user(current_user: User = Depends(get_current_user)):
        return {
            "username": current_user.username,
            "role": current_user.role,
            "dept": current_user.dept,
            "permissions": current_user.permissions,
        }

    @_app.get("/api/test/patient-access/{patient_id}")
    async def patient_access(
        patient_id: str,
        current_user: User = Depends(get_current_user),
    ):
        await require_patient_access(
            current_user=current_user,
            patient_id=patient_id,
            permission="patient:risk:view",
        )
        return {"access": True}

    return _app


@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_token(
    sub: str = "testuser",
    role: str = "doctor",
    dept: str = "ICU-1",
    allowed_depts: list[str] | None = None,
    allowed_wards: list[str] | None = None,
    permissions: list[str] | None = None,
    expired: bool = False,
    secret: str = SECRET_KEY,
) -> str:
    """Create a JWT token for testing."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "role": role,
        "type": "access",
        "exp": now - timedelta(hours=1) if expired else now + timedelta(hours=24),
        "dept": dept,
        "allowed_depts": allowed_depts or [],
        "allowed_wards": allowed_wards or [],
        "permissions": permissions or ["patient:risk:view", "patient:overview:view"],
    }
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def _mock_runtime(mock_user=None, mock_patient=None):
    """Create a mock runtime with find_one returning appropriate records.

    Returns a context manager that patches app.runtime.
    The "patient" collection is queried by ObjectId; mock_patient must have
    an ``_id`` that is a valid ObjectId string or ObjectId instance.
    """

    class _MockCol:
        def __init__(self, name):
            self._name = name

        async def find_one(self, query, *args, **kwargs):
            if self._name == "users":
                return mock_user
            if self._name == "patient":
                return mock_patient
            return None

    class _MockDB:
        def col(self, name):
            return _MockCol(name)

    class _MockRuntime:
        db = _MockDB()

    return patch("app.runtime", _MockRuntime())


# Valid ObjectId constants for patient IDs
PATIENT_ID_1 = "507f1f77bcf86cd799439011"
PATIENT_ID_2 = "507f1f77bcf86cd799439012"
PATIENT_ID_3 = "507f1f77bcf86cd799439013"
PATIENT_ID_4 = "507f1f77bcf86cd799439014"
PATIENT_ID_5 = "507f1f77bcf86cd799439015"
PATIENT_ID_6 = "507f1f77bcf86cd799439016"
PATIENT_ID_7 = "507f1f77bcf86cd799439017"
PATIENT_ID_8 = "507f1f77bcf86cd799439018"
PATIENT_ID_9 = "507f1f77bcf86cd799439019"
PATIENT_ID_10 = "507f1f77bcf86cd799439020"


# ---------------------------------------------------------------------------
# P0: Auth tests - 无 token → 401
# ---------------------------------------------------------------------------

class TestNoToken:
    """P0: No token → 401."""

    def test_no_auth_header_returns_401(self, client):
        """No Authorization header → 401."""
        resp = client.get("/api/test/current-user")
        assert resp.status_code == 401

    def test_empty_auth_header_returns_401(self, client):
        """Empty Authorization header → 401."""
        resp = client.get(
            "/api/test/current-user",
            headers={"Authorization": ""},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# P0: Token expired → 401
# ---------------------------------------------------------------------------

class TestExpiredToken:
    """P0: Expired token → 401."""

    def test_expired_token_returns_401(self, client):
        """Expired JWT → 401."""
        token = _make_token(expired=True)
        resp = client.get(
            "/api/test/current-user",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401
        # Error message should indicate auth failure (not "inactive")
        detail = resp.json().get("detail", "")
        assert len(detail) > 0

    def test_invalid_signature_returns_401(self, client):
        """Token signed with wrong key → 401."""
        token = _make_token(secret="wrong-secret-key-1234567890")
        resp = client.get(
            "/api/test/current-user",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    def test_malformed_token_returns_401(self, client):
        """Garbage token → 401."""
        resp = client.get(
            "/api/test/current-user",
            headers={"Authorization": "Bearer not-a-valid-jwt"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# P0: User inactive → 401
# ---------------------------------------------------------------------------

class TestInactiveUser:
    """P0: Inactive user → 401."""

    def test_inactive_user_returns_401(self, client):
        """User with is_active=False → 401.

        Note: get_current_user queries DB with is_active=True filter.
        An inactive user won't be found in DB, so it falls back to JWT.
        The fallback user always has is_active=True.
        To test inactive user properly, we need to test the code path where
        DB returns an inactive user (which shouldn't happen with the query).
        This test verifies the fallback behavior.
        """
        token = _make_token(sub="inactive_user")
        # Simulate DB returning inactive user (bypassing the is_active filter)
        # This requires a more sophisticated mock that checks the query.
        # For now, test that get_current_user fallback returns active user.
        # The inactive check is in require_patient_access which uses current_user.is_active.
        mock_user = {
            "_id": "u001",
            "username": "inactive_user",
            "role": "doctor",
            "dept": "ICU-1",
            "allowed_depts": ["ICU-1"],
            "allowed_wards": [],
            "permissions": ["patient:risk:view"],
            "is_active": False,  # inactive in DB
        }
        mock_patient = {
            "_id": ObjectId(PATIENT_ID_1),
            "dept": "ICU-1",
            "ward": "ward-A",
        }

        # Patch _mock_runtime to return inactive user from users collection
        # but still return patient from patient collection
        class _InactiveMockCol:
            def __init__(self, name):
                self._name = name

            async def find_one(self, query, *args, **kwargs):
                if self._name == "users":
                    # Return inactive user even though query filters is_active=True
                    # This tests the edge case where DB returns inconsistent data
                    return mock_user
                if self._name == "patient":
                    return mock_patient
                return None

        class _InactiveMockDB:
            def col(self, name):
                return _InactiveMockCol(name)

        class _InactiveMockRuntime:
            db = _InactiveMockDB()

        with patch("app.runtime", _InactiveMockRuntime()):
            resp = client.get(
                f"/api/test/patient-access/{PATIENT_ID_1}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 401


# ---------------------------------------------------------------------------
# P0: Dept mismatch → 403
# ---------------------------------------------------------------------------

class TestDeptMismatch:
    """P0: Patient dept not in user's allowed depts → 403."""

    def test_dept_mismatch_returns_403(self, client):
        """User from ICU-1 tries to access ICU-2 patient → 403."""
        token = _make_token(sub="icu1_doc", dept="ICU-1", allowed_depts=["ICU-1"])
        mock_user = {
            "_id": "u002",
            "username": "icu1_doc",
            "role": "doctor",
            "dept": "ICU-1",
            "allowed_depts": ["ICU-1"],
            "allowed_wards": [],
            "permissions": ["patient:risk:view"],
            "is_active": True,
        }
        mock_patient = {
            "_id": ObjectId(PATIENT_ID_2),
            "dept": "ICU-2",
            "ward": "ward-B",
        }

        with _mock_runtime(mock_user=mock_user, mock_patient=mock_patient):
            resp = client.get(
                f"/api/test/patient-access/{PATIENT_ID_2}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 403

    def test_403_does_not_leak_patient_dept(self, client):
        """403 message must not contain patient dept info."""
        token = _make_token(sub="icu1_doc", dept="ICU-1", allowed_depts=["ICU-1"])
        mock_user = {
            "_id": "u002",
            "username": "icu1_doc",
            "role": "doctor",
            "dept": "ICU-1",
            "allowed_depts": ["ICU-1"],
            "allowed_wards": [],
            "permissions": ["patient:risk:view"],
            "is_active": True,
        }
        mock_patient = {
            "_id": ObjectId(PATIENT_ID_3),
            "dept": "ICU-2",
            "ward": "ward-B",
        }

        with _mock_runtime(mock_user=mock_user, mock_patient=mock_patient):
            resp = client.get(
                f"/api/test/patient-access/{PATIENT_ID_3}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 403
            detail = resp.json().get("detail", "")
            assert "ICU-2" not in detail, f"403 message leaked patient dept: {detail}"


# ---------------------------------------------------------------------------
# P0: Permission check → 403
# ---------------------------------------------------------------------------

class TestPermissionCheck:
    """P0: User missing required permission → 403."""

    def test_missing_permission_returns_403(self, client):
        """User has permissions config but missing patient:risk:view → 403."""
        token = _make_token(sub="viewer", permissions=["patient:overview:view"])
        mock_user = {
            "_id": "u003",
            "username": "viewer",
            "role": "doctor",
            "dept": "ICU-1",
            "allowed_depts": ["ICU-1"],
            "allowed_wards": [],
            "permissions": ["patient:overview:view"],  # no patient:risk:view
            "is_active": True,
        }
        mock_patient = {
            "_id": ObjectId(PATIENT_ID_4),
            "dept": "ICU-1",
            "ward": "ward-A",
        }

        with _mock_runtime(mock_user=mock_user, mock_patient=mock_patient):
            resp = client.get(
                f"/api/test/patient-access/{PATIENT_ID_4}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 403
            assert "权限" in resp.json().get("detail", "")

    def test_no_permissions_config_skips_check(self, client):
        """User with empty permissions → permission check skipped (backward compat)."""
        token = _make_token(sub="legacy_user", permissions=[])
        mock_user = {
            "_id": "u004",
            "username": "legacy_user",
            "role": "doctor",
            "dept": "ICU-1",
            "allowed_depts": ["ICU-1"],
            "allowed_wards": [],
            "permissions": [],  # empty → skip check
            "is_active": True,
        }
        mock_patient = {
            "_id": ObjectId(PATIENT_ID_5),
            "dept": "ICU-1",
            "ward": "ward-A",
        }

        with _mock_runtime(mock_user=mock_user, mock_patient=mock_patient):
            resp = client.get(
                f"/api/test/patient-access/{PATIENT_ID_5}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200

    def test_has_required_permission_grants_access(self, client):
        """User has the required permission → 200."""
        token = _make_token(sub="risk_viewer", permissions=["patient:risk:view"])
        mock_user = {
            "_id": "u005",
            "username": "risk_viewer",
            "role": "doctor",
            "dept": "ICU-1",
            "allowed_depts": ["ICU-1"],
            "allowed_wards": [],
            "permissions": ["patient:risk:view"],
            "is_active": True,
        }
        mock_patient = {
            "_id": ObjectId(PATIENT_ID_6),
            "dept": "ICU-1",
            "ward": "ward-A",
        }

        with _mock_runtime(mock_user=mock_user, mock_patient=mock_patient):
            resp = client.get(
                f"/api/test/patient-access/{PATIENT_ID_6}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# P1: Ward access check
# ---------------------------------------------------------------------------

class TestWardAccess:
    """P1: Ward-based access control."""

    def test_ward_match_grants_access(self, client):
        """User's allowed_wards matches patient ward → 200."""
        token = _make_token(
            sub="ward_doc",
            dept="",
            allowed_depts=[],
            allowed_wards=["ward-A"],
        )
        mock_user = {
            "_id": "u006",
            "username": "ward_doc",
            "role": "doctor",
            "dept": "",
            "allowed_depts": [],
            "allowed_wards": ["ward-A"],
            "permissions": ["patient:risk:view"],
            "is_active": True,
        }
        mock_patient = {
            "_id": ObjectId(PATIENT_ID_7),
            "dept": "ICU-1",
            "ward": "ward-A",
        }

        with _mock_runtime(mock_user=mock_user, mock_patient=mock_patient):
            resp = client.get(
                f"/api/test/patient-access/{PATIENT_ID_7}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200

    def test_ward_mismatch_returns_403(self, client):
        """User's allowed_wards doesn't match patient ward → 403."""
        token = _make_token(
            sub="ward_doc",
            dept="",
            allowed_depts=[],
            allowed_wards=["ward-B"],
        )
        mock_user = {
            "_id": "u007",
            "username": "ward_doc",
            "role": "doctor",
            "dept": "",
            "allowed_depts": [],
            "allowed_wards": ["ward-B"],
            "permissions": ["patient:risk:view"],
            "is_active": True,
        }
        mock_patient = {
            "_id": ObjectId(PATIENT_ID_8),
            "dept": "ICU-1",
            "ward": "ward-A",
        }

        with _mock_runtime(mock_user=mock_user, mock_patient=mock_patient):
            resp = client.get(
                f"/api/test/patient-access/{PATIENT_ID_8}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 403


# ---------------------------------------------------------------------------
# P0: DB user loading
# ---------------------------------------------------------------------------

class TestDBUserLoading:
    """P0: User loaded from DB, not just JWT payload."""

    def test_db_user_dept_overrides_jwt(self, client):
        """DB user's dept takes precedence over JWT payload."""
        token = _make_token(sub="moved_user", dept="ICU-1")
        mock_user = {
            "_id": "u008",
            "username": "moved_user",
            "role": "doctor",
            "dept": "ICU-3",  # different from JWT
            "allowed_depts": ["ICU-3"],
            "allowed_wards": [],
            "permissions": ["patient:risk:view"],
            "is_active": True,
        }

        with _mock_runtime(mock_user=mock_user):
            resp = client.get(
                "/api/test/current-user",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            assert resp.json()["dept"] == "ICU-3"

    def test_fallback_to_jwt_when_db_unavailable(self, client):
        """When DB is unavailable, fall back to JWT payload."""
        token = _make_token(sub="jwt_user", dept="ICU-1")

        # Mock runtime that raises (simulating DB failure)
        class _FailingCol:
            async def find_one(self, *a, **kw):
                raise RuntimeError("DB connection failed")

        class _FailingDB:
            def col(self, name):
                return _FailingCol()

        class _FailingRuntime:
            db = _FailingDB()

        with patch("app.runtime", _FailingRuntime()):
            resp = client.get(
                "/api/test/current-user",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["username"] == "jwt_user"
            assert data["dept"] == "ICU-1"  # from JWT


# ---------------------------------------------------------------------------
# P0: Admin bypass
# ---------------------------------------------------------------------------

class TestAdminBypass:
    """P0: Admin users bypass all checks."""

    def test_admin_bypasses_dept_check(self, client):
        """Admin can access any patient regardless of dept."""
        token = _make_token(sub="admin", role="admin", dept="ICU-1")
        mock_user = {
            "_id": "u009",
            "username": "admin",
            "role": "admin",
            "dept": "ICU-1",
            "allowed_depts": ["ICU-1"],
            "allowed_wards": [],
            "permissions": [],
            "is_active": True,
        }

        with _mock_runtime(mock_user=mock_user):
            resp = client.get(
                f"/api/test/patient-access/{PATIENT_ID_9}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200


# ---------------------------------------------------------------------------
# P0: Ward granted via allowed_depts (patient in user's dept list)
# ---------------------------------------------------------------------------

class TestAllowedDepts:
    """P0: Patient dept in user's allowed_depts → access."""

    def test_allowed_depts_match(self, client):
        """User's allowed_depts contains patient dept → 200."""
        token = _make_token(sub="multi_dept", dept="", allowed_depts=["ICU-1", "ICU-3"])
        mock_user = {
            "_id": "u010",
            "username": "multi_dept",
            "role": "doctor",
            "dept": "",
            "allowed_depts": ["ICU-1", "ICU-3"],
            "allowed_wards": [],
            "permissions": ["patient:risk:view"],
            "is_active": True,
        }
        mock_patient = {
            "_id": ObjectId(PATIENT_ID_10),
            "dept": "ICU-3",
            "ward": "ward-C",
        }

        with _mock_runtime(mock_user=mock_user, mock_patient=mock_patient):
            resp = client.get(
                f"/api/test/patient-access/{PATIENT_ID_10}",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 200
