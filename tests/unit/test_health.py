"""
Unit tests for app/api/v1/endpoints/health.py

Validates: Requirements 10.1, 10.2, 10.3, 10.4
- DB available   → HTTP 200, database="connected"
- DB unavailable → HTTP 503, database="unreachable"
- DB timeout     → HTTP 503, database="timeout"
"""

import asyncio
import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Module-level stubs — must run before any app import
# ---------------------------------------------------------------------------

def _stub_modules():
    """
    Stub out heavy dependencies (asyncpg engine + ML service) so the health
    module can be imported without a real DB driver or ML model on disk.
    Idempotent: if conftest.py already installed the stub, reuse it.
    """
    if "app.infrastructure.database" in sys.modules:
        return sys.modules["app.infrastructure.database"], sys.modules.get("app.services.ml_service")

    # --- database stub ---
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

    # --- ml_service stub ---
    mock_risk_svc = MagicMock()
    mock_risk_svc.model = MagicMock()
    mock_risk_svc.scaler = MagicMock()
    mock_risk_svc.promedio_estudiantes_aprobados = 3.5

    fake_ml = types.ModuleType("app.services.ml_service")
    fake_ml.risk_service = mock_risk_svc
    sys.modules["app.services.ml_service"] = fake_ml

    return fake_db, fake_ml


# Stub once at import time so all tests share the same clean state
_DB_STUB, _ML_STUB = _stub_modules()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reload_health():
    """Force-reload the health module so it picks up current stubs."""
    for key in list(sys.modules.keys()):
        if key == "app.api.v1.endpoints.health":
            del sys.modules[key]
    import app.api.v1.endpoints.health as health_mod  # noqa: PLC0415
    return health_mod


def _make_app(health_mod):
    app = FastAPI()
    app.include_router(health_mod.router)
    return app


def _set_db_connected():
    """Configure the engine stub to succeed on connect."""
    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_conn.execute = AsyncMock()
    _DB_STUB.engine.connect = MagicMock(return_value=mock_conn)


def _set_db_unreachable():
    """Configure the engine stub to raise on connect."""
    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(side_effect=Exception("connection refused"))
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    _DB_STUB.engine.connect = MagicMock(return_value=mock_conn)


# ---------------------------------------------------------------------------
# Tests — DB available
# ---------------------------------------------------------------------------

def test_health_db_connected():
    """Requirement 10.1 / 10.3: DB responds → HTTP 200, database='connected'."""
    _set_db_connected()
    health_mod = _reload_health()
    health_mod.engine = _DB_STUB.engine
    app = _make_app(health_mod)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["database"] == "connected"


# ---------------------------------------------------------------------------
# Tests — DB unavailable
# ---------------------------------------------------------------------------

def test_health_db_unreachable():
    """Requirement 10.2: DB raises exception → HTTP 503, database='unreachable'."""
    _set_db_unreachable()
    health_mod = _reload_health()
    health_mod.engine = _DB_STUB.engine
    app = _make_app(health_mod)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy"
    assert body["database"] == "unreachable"


# ---------------------------------------------------------------------------
# Tests — DB timeout
# ---------------------------------------------------------------------------

def test_health_db_timeout():
    """Requirement 10.4: asyncio.wait_for times out → HTTP 503, database='timeout'."""
    _set_db_connected()
    health_mod = _reload_health()
    health_mod.engine = _DB_STUB.engine

    # Patch wait_for on the health module's asyncio reference
    import unittest.mock as mock  # noqa: PLC0415
    with mock.patch.object(
        sys.modules["asyncio"], "wait_for", side_effect=asyncio.TimeoutError()
    ):
        app = _make_app(health_mod)
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unhealthy"
    assert body["database"] == "timeout"


# ---------------------------------------------------------------------------
# Tests — response shape
# ---------------------------------------------------------------------------

def test_health_200_response_has_required_fields():
    """HTTP 200 response always contains 'status' and 'database' fields."""
    _set_db_connected()
    health_mod = _reload_health()
    health_mod.engine = _DB_STUB.engine
    app = _make_app(health_mod)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/health")

    body = response.json()
    assert "status" in body
    assert "database" in body


def test_health_503_response_has_required_fields():
    """HTTP 503 response also contains 'status' and 'database' fields."""
    _set_db_unreachable()
    health_mod = _reload_health()
    health_mod.engine = _DB_STUB.engine
    app = _make_app(health_mod)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/health")

    body = response.json()
    assert "status" in body
    assert "database" in body
