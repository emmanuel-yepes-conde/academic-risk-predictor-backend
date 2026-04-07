# Feature: postgresql-database-integration, Property 4: AuditLog insert-only
"""
Property-based tests for AuditLog insert-only immutability.

Verifies that calling update() or delete() on AuditLogRepository always raises
NotImplementedError, regardless of the arguments passed, and that no mutation
of the underlying session occurs.

**Validates: Requirements 4.7, 9.4**
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from app.domain.enums import OperationEnum
from app.infrastructure.repositories.audit_log_repository import AuditLogRepository


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

operation_strategy = st.sampled_from(list(OperationEnum))

audit_log_create_strategy = st.fixed_dictionaries(
    {
        "table_name": st.text(min_size=1, max_size=64),
        "operation": operation_strategy,
        "record_id": st.uuids(),
        "user_id": st.one_of(st.none(), st.uuids()),
        "previous_data": st.one_of(
            st.none(),
            st.dictionaries(
                st.text(min_size=1, max_size=20),
                st.one_of(st.text(max_size=50), st.integers(), st.none()),
                max_size=5,
            ),
        ),
        "new_data": st.one_of(
            st.none(),
            st.dictionaries(
                st.text(min_size=1, max_size=20),
                st.one_of(st.text(max_size=50), st.integers(), st.none()),
                max_size=5,
            ),
        ),
    }
)

# Strategy for arbitrary positional/keyword arguments passed to update/delete
args_strategy = st.lists(
    st.one_of(st.text(max_size=50), st.integers(), st.uuids(), st.none()),
    max_size=5,
)

kwargs_strategy = st.dictionaries(
    st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("Ll", "Lu", "Nd"), whitelist_characters="_")),
    st.one_of(st.text(max_size=50), st.integers(), st.none()),
    max_size=5,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_repo() -> AuditLogRepository:
    """Return an AuditLogRepository backed by a mock AsyncSession."""
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()
    return AuditLogRepository(session=mock_session)


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@h_settings(max_examples=100)
@given(record=audit_log_create_strategy, args=args_strategy, kwargs=kwargs_strategy)
async def test_update_always_raises_not_implemented(record, args, kwargs):
    """
    **Validates: Requirements 4.7, 9.4**

    Property 4: For ANY AuditLog record and ANY arguments, calling
    AuditLogRepository.update() must raise NotImplementedError.
    """
    repo = _make_repo()

    with pytest.raises(NotImplementedError):
        await repo.update(*args, **kwargs)


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(record=audit_log_create_strategy, args=args_strategy, kwargs=kwargs_strategy)
async def test_delete_always_raises_not_implemented(record, args, kwargs):
    """
    **Validates: Requirements 4.7, 9.4**

    Property 4: For ANY AuditLog record and ANY arguments, calling
    AuditLogRepository.delete() must raise NotImplementedError.
    """
    repo = _make_repo()

    with pytest.raises(NotImplementedError):
        await repo.delete(*args, **kwargs)


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(record=audit_log_create_strategy, args=args_strategy, kwargs=kwargs_strategy)
async def test_update_does_not_mutate_session(record, args, kwargs):
    """
    **Validates: Requirements 4.7, 9.4**

    Property 4 (state invariant): After a failed update() call, the underlying
    session must not have had any mutating methods (add, flush, commit) called.
    """
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    repo = AuditLogRepository(session=mock_session)

    with pytest.raises(NotImplementedError):
        await repo.update(*args, **kwargs)

    mock_session.add.assert_not_called()
    mock_session.flush.assert_not_awaited()
    mock_session.commit.assert_not_awaited()


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(record=audit_log_create_strategy, args=args_strategy, kwargs=kwargs_strategy)
async def test_delete_does_not_mutate_session(record, args, kwargs):
    """
    **Validates: Requirements 4.7, 9.4**

    Property 4 (state invariant): After a failed delete() call, the underlying
    session must not have had any mutating methods (add, flush, commit) called.
    """
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    repo = AuditLogRepository(session=mock_session)

    with pytest.raises(NotImplementedError):
        await repo.delete(*args, **kwargs)

    mock_session.add.assert_not_called()
    mock_session.flush.assert_not_awaited()
    mock_session.commit.assert_not_awaited()
