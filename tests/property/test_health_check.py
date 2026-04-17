# Feature: postgresql-database-integration, Property 11: Health check DB state
"""
Property-based tests for the /health endpoint DB state reporting.

Verifies that for any simulated DB state ("connected", "unreachable", "timeout"),
the endpoint's `database` field and HTTP status code faithfully reflect that state.

**Validates: Requirements 10.1, 10.2, 10.3, 10.4**
"""

import asyncio
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Module-level stubs (run once before any app import)
# ---------------------------------------------------------------------------

def _build_stubs():
    # Idempotent: if conftest.py already installed the stub, reuse it.
    if "app.infrastructure.database" in sys.modules:
        return sys.modules["app.infrastructure.database"]

    mock_engine = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.execute = AsyncMock()
    mock_engine.connect = MagicMock(return_value=mock_conn)

    fake_db = types.ModuleType("app.infrastructure.database")
    fake_db.engine = mock_engine
    fake_db.get_session = AsyncMock()
    sys.modules["app.infrastructure.database"] = fake_db

    mock_risk_svc = MagicMock()
    mock_risk_svc.model = MagicMock()
    mock_risk_svc.scaler = MagicMock()
    mock_risk_svc.promedio_estudiantes_aprobados = 3.5

    fake_ml = types.ModuleType("app.services.ml_service")
    fake_ml.risk_service = mock_risk_svc
    sys.modules["app.services.ml_service"] = fake_ml

    return fake_db


_DB_STUB = _build_stubs()

# Expected outcomes per simulated state
_EXPECTED = {
    "connected":   {"database": "connected",   "http_status": 200, "status": "healthy"},
    "unreachable": {"database": "unreachable", "http_status": 503, "status": "unhealthy"},
    "timeout":     {"database": "timeout",     "http_status": 503, "status": "unhealthy"},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reload_health():
    sys.modules.pop("app.api.v1.endpoints.health", None)
    import app.api.v1.endpoints.health as m  # noqa: PLC0415
    return m


def _configure_engine(db_state: str):
    """Point the engine stub to behave according to db_state."""
    mock_conn = AsyncMock()
    mock_conn.__aexit__ = AsyncMock(return_value=False)

    if db_state == "connected":
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.execute = AsyncMock()
        _DB_STUB.engine.connect = MagicMock(return_value=mock_conn)

    elif db_state == "unreachable":
        mock_conn.__aenter__ = AsyncMock(side_effect=Exception("connection refused"))
        _DB_STUB.engine.connect = MagicMock(return_value=mock_conn)

    # "timeout" is handled by patching asyncio.wait_for below


def _make_client(health_mod) -> TestClient:
    health_mod.engine = _DB_STUB.engine
    app = FastAPI()
    app.include_router(health_mod.router)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

@h_settings(max_examples=100)
@given(db_state=st.sampled_from(["connected", "unreachable", "timeout"]))
def test_health_database_field_matches_state(db_state: str):
    """
    **Validates: Requirements 10.1, 10.2, 10.3, 10.4**

    Property 11: For any simulated DB state, the `database` field in the
    response body must exactly match the expected value for that state.
    """
    expected = _EXPECTED[db_state]
    _configure_engine(db_state)
    health_mod = _reload_health()

    if db_state == "timeout":
        import unittest.mock as mock  # noqa: PLC0415
        with mock.patch.object(asyncio, "wait_for", side_effect=asyncio.TimeoutError()):
            client = _make_client(health_mod)
            response = client.get("/health")
    else:
        client = _make_client(health_mod)
        response = client.get("/health")

    body = response.json()
    assert body["database"] == expected["database"], (
        f"db_state={db_state!r}: expected database={expected['database']!r}, "
        f"got {body['database']!r}"
    )


@h_settings(max_examples=100)
@given(db_state=st.sampled_from(["connected", "unreachable", "timeout"]))
def test_health_http_status_matches_state(db_state: str):
    """
    **Validates: Requirements 10.1, 10.2, 10.3, 10.4**

    Property 11: For any simulated DB state, the HTTP status code must be
    200 when connected and 503 when unreachable or timed out.
    """
    expected = _EXPECTED[db_state]
    _configure_engine(db_state)
    health_mod = _reload_health()

    if db_state == "timeout":
        import unittest.mock as mock  # noqa: PLC0415
        with mock.patch.object(asyncio, "wait_for", side_effect=asyncio.TimeoutError()):
            client = _make_client(health_mod)
            response = client.get("/health")
    else:
        client = _make_client(health_mod)
        response = client.get("/health")

    assert response.status_code == expected["http_status"], (
        f"db_state={db_state!r}: expected HTTP {expected['http_status']}, "
        f"got {response.status_code}"
    )


@h_settings(max_examples=100)
@given(db_state=st.sampled_from(["connected", "unreachable", "timeout"]))
def test_health_overall_status_matches_state(db_state: str):
    """
    **Validates: Requirements 10.1, 10.2, 10.3, 10.4**

    Property 11: For any simulated DB state, the `status` field must be
    "healthy" when connected and "unhealthy" otherwise.
    """
    expected = _EXPECTED[db_state]
    _configure_engine(db_state)
    health_mod = _reload_health()

    if db_state == "timeout":
        import unittest.mock as mock  # noqa: PLC0415
        with mock.patch.object(asyncio, "wait_for", side_effect=asyncio.TimeoutError()):
            client = _make_client(health_mod)
            response = client.get("/health")
    else:
        client = _make_client(health_mod)
        response = client.get("/health")

    body = response.json()
    assert body["status"] == expected["status"], (
        f"db_state={db_state!r}: expected status={expected['status']!r}, "
        f"got {body['status']!r}"
    )


@h_settings(max_examples=100)
@given(db_state=st.sampled_from(["connected", "unreachable", "timeout"]))
def test_health_response_always_has_required_fields(db_state: str):
    """
    **Validates: Requirements 10.1, 10.2, 10.3, 10.4**

    Property 11 (shape invariant): Regardless of DB state, the response body
    must always contain both `status` and `database` fields.
    """
    _configure_engine(db_state)
    health_mod = _reload_health()

    if db_state == "timeout":
        import unittest.mock as mock  # noqa: PLC0415
        with mock.patch.object(asyncio, "wait_for", side_effect=asyncio.TimeoutError()):
            client = _make_client(health_mod)
            response = client.get("/health")
    else:
        client = _make_client(health_mod)
        response = client.get("/health")

    body = response.json()
    assert "status" in body, "Response missing 'status' field"
    assert "database" in body, "Response missing 'database' field"
