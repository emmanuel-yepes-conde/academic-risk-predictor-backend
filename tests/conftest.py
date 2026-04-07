"""
Shared test configuration and fixtures.

Module-level stubs are applied here (conftest is loaded before any test module)
so that both test_users.py and test_users_properties.py share the same
sys.modules stubs and the same get_session reference.
"""

import sys
import types
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Apply heavy-dependency stubs ONCE before any test module is imported.
# This prevents the double-stub problem that arises when both test files
# each call _stub_heavy_deps() at module level, causing the second stub to
# overwrite sys.modules and break dependency_overrides key matching.
# ---------------------------------------------------------------------------

def _stub_heavy_deps():
    """Stub ML service and DB engine so app.main can be imported without I/O."""
    if "app.infrastructure.database" in sys.modules:
        return sys.modules["app.infrastructure.database"]

    mock_engine = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
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
    fake_ml.AcademicRiskService = MagicMock(return_value=mock_risk_svc)
    sys.modules["app.services.ml_service"] = fake_ml

    return fake_db


_DB_STUB = _stub_heavy_deps()

# Import app after stubs are in place
from app.main import app  # noqa: E402
from app.infrastructure.database import get_session  # noqa: E402


# ---------------------------------------------------------------------------
# Shared async client fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    """
    AsyncClient with mocked DB session injected via dependency_overrides.
    Shared by test_users.py and test_users_properties.py.
    """
    mock_session = AsyncMock()

    async def _override_get_session():
        yield mock_session

    app.dependency_overrides[get_session] = _override_get_session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()
