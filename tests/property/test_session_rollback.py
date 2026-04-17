# Feature: postgresql-database-integration, Property 2: Session rollback
"""
Property-based tests for automatic rollback on session exception.

Validates: Requirement 3.3
"""

import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# SQLAlchemy stubs (same pattern as tests/unit/test_database.py)
# ---------------------------------------------------------------------------

def _install_sqlalchemy_stubs():
    """
    Patch sqlalchemy.ext.asyncio so that create_async_engine is a no-op mock.
    Works even when the real sqlalchemy is installed — prevents asyncpg import.
    """
    fake_async = types.ModuleType("sqlalchemy.ext.asyncio")
    fake_async.AsyncSession = MagicMock()
    fake_async.async_sessionmaker = MagicMock()
    fake_async.create_async_engine = MagicMock(return_value=MagicMock())
    sys.modules["sqlalchemy.ext.asyncio"] = fake_async


def _load_db_module():
    _install_sqlalchemy_stubs()
    # Save the conftest stub so we can restore it after the test
    _saved = sys.modules.get("app.infrastructure.database")
    for key in list(sys.modules.keys()):
        if key == "app.infrastructure.database":
            del sys.modules[key]
    import app.infrastructure.database as db_module
    # Restore the conftest stub so other tests are not affected
    if _saved is not None:
        sys.modules["app.infrastructure.database"] = _saved
    return db_module


def _make_mock_session_factory():
    mock_session = AsyncMock()
    mock_cm = MagicMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_cm)
    return mock_session, mock_factory


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Exception classes to sample from for property generation
EXCEPTION_TYPES = [
    RuntimeError,
    ValueError,
    TypeError,
    OSError,
    Exception,
]

exception_strategy = st.builds(
    lambda exc_cls, msg: exc_cls(msg),
    exc_cls=st.sampled_from(EXCEPTION_TYPES),
    msg=st.text(min_size=0, max_size=100),
)


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@h_settings(max_examples=100)
@given(exc=exception_strategy)
async def test_rollback_called_on_any_exception(exc: Exception):
    """
    Property 2: For ANY exception raised inside get_session, rollback() must
    be awaited exactly once and commit() must NOT be awaited.

    Validates: Requirement 3.3
    """
    db_module = _load_db_module()
    mock_session, mock_factory = _make_mock_session_factory()

    with patch.object(db_module, "AsyncSessionFactory", mock_factory):
        gen = db_module.get_session()
        await gen.__anext__()  # advance to yield

        with pytest.raises(type(exc)):
            await gen.athrow(exc)

    mock_session.rollback.assert_awaited_once()
    mock_session.commit.assert_not_awaited()


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(exc=exception_strategy)
async def test_exception_is_reraised_after_rollback(exc: Exception):
    """
    Property 2 (corollary): The original exception must be re-raised after
    rollback, preserving the exception type.

    Validates: Requirement 3.3
    """
    db_module = _load_db_module()
    mock_session, mock_factory = _make_mock_session_factory()

    with patch.object(db_module, "AsyncSessionFactory", mock_factory):
        gen = db_module.get_session()
        await gen.__anext__()

        raised_exc = None
        try:
            await gen.athrow(exc)
        except Exception as e:
            raised_exc = e

    assert raised_exc is not None, "Exception should have been re-raised"
    assert type(raised_exc) is type(exc), (
        f"Expected {type(exc).__name__} to be re-raised, got {type(raised_exc).__name__}"
    )


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(
    exc=exception_strategy,
    write_ops=st.lists(st.text(min_size=1, max_size=50), min_size=1, max_size=5),
)
async def test_db_state_unchanged_after_rollback(exc: Exception, write_ops: list):
    """
    Property 2 (state invariant): After a rollback, the mock session's
    execute call count reflects only the operations performed before the
    exception — no additional state-mutating calls occur after rollback.

    Simulates write operations as session.execute() calls, then injects
    an exception and verifies rollback is called and no commit occurs.

    Validates: Requirement 3.3
    """
    db_module = _load_db_module()
    mock_session, mock_factory = _make_mock_session_factory()

    with patch.object(db_module, "AsyncSessionFactory", mock_factory):
        gen = db_module.get_session()
        session = await gen.__anext__()

        # Simulate write operations
        for op in write_ops:
            await session.execute(op)

        execute_count_before = mock_session.execute.await_count

        with pytest.raises(type(exc)):
            await gen.athrow(exc)

    # No additional executes after the exception
    assert mock_session.execute.await_count == execute_count_before
    # Rollback was called, not commit
    mock_session.rollback.assert_awaited_once()
    mock_session.commit.assert_not_awaited()
