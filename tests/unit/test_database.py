"""
Unit tests for app/infrastructure/database.py

Validates: Requirement 3.3 — rollback automático ante excepción en sesión.

Since sqlalchemy/asyncpg may not be installed in all environments, we mock
the sqlalchemy imports so the module can be loaded and the get_session logic
can be tested in isolation.
"""

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers to stub out sqlalchemy before importing the database module
# ---------------------------------------------------------------------------

def _install_sqlalchemy_stubs():
    """
    Patch sqlalchemy.ext.asyncio so that create_async_engine is a no-op mock.
    This works even when the real sqlalchemy is installed (which it is), because
    we only need to prevent the asyncpg driver import that happens at engine
    creation time.
    """
    fake_async = types.ModuleType("sqlalchemy.ext.asyncio")
    fake_async.AsyncSession = MagicMock()
    fake_async.async_sessionmaker = MagicMock()
    fake_async.create_async_engine = MagicMock(return_value=MagicMock())

    sys.modules["sqlalchemy.ext.asyncio"] = fake_async


def _load_db_module():
    """Import (or reload) database module with stubs in place."""
    _install_sqlalchemy_stubs()

    # Save the current stub (installed by conftest) so we can restore it after the test
    _saved = sys.modules.get("app.infrastructure.database")

    # Remove cached module so it re-executes with our stubs
    for key in list(sys.modules.keys()):
        if key == "app.infrastructure.database":
            del sys.modules[key]

    import app.infrastructure.database as db_module  # noqa: PLC0415

    # Restore the conftest stub so other tests are not affected
    if _saved is not None:
        sys.modules["app.infrastructure.database"] = _saved

    return db_module


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def anyio_backend():
    return "asyncio"


def _make_mock_session_factory():
    """Return (mock_session, mock_factory_callable)."""
    mock_session = AsyncMock()
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_cm)
    return mock_session, mock_factory


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_get_session_commits_on_success():
    """get_session debe hacer commit cuando no ocurre ninguna excepción."""
    db_module = _load_db_module()
    mock_session, mock_factory = _make_mock_session_factory()

    with patch.object(db_module, "AsyncSessionFactory", mock_factory):
        gen = db_module.get_session()
        session = await gen.__anext__()

        assert session is mock_session

        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()

    mock_session.commit.assert_awaited_once()
    mock_session.rollback.assert_not_awaited()


@pytest.mark.anyio
async def test_get_session_rollback_on_exception():
    """
    Requirement 3.3: cuando ocurre una excepción dentro de la sesión,
    get_session debe invocar rollback() y re-lanzar la excepción.
    """
    db_module = _load_db_module()
    mock_session, mock_factory = _make_mock_session_factory()

    with patch.object(db_module, "AsyncSessionFactory", mock_factory):
        gen = db_module.get_session()
        await gen.__anext__()  # advance to yield

        with pytest.raises(RuntimeError, match="simulated error"):
            await gen.athrow(RuntimeError("simulated error"))

    mock_session.rollback.assert_awaited_once()
    mock_session.commit.assert_not_awaited()


@pytest.mark.anyio
async def test_get_session_rollback_reraises_exception():
    """La excepción original debe propagarse después del rollback."""
    db_module = _load_db_module()
    mock_session, mock_factory = _make_mock_session_factory()

    class CustomError(Exception):
        pass

    with patch.object(db_module, "AsyncSessionFactory", mock_factory):
        gen = db_module.get_session()
        await gen.__anext__()

        with pytest.raises(CustomError):
            await gen.athrow(CustomError("db write failed"))

    mock_session.rollback.assert_awaited_once()
    mock_session.commit.assert_not_awaited()
