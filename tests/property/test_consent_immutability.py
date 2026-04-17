# Feature: postgresql-database-integration, Property 10: Consent immutability
"""
Property-based tests for Consent record immutability.

Verifies that ConsentRepository exposes no methods that directly modify
existing consent records, and that revocation works by creating a new
record with accepted=False rather than mutating the original.

**Validates: Requirements 8.4**
"""

import inspect
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given
from hypothesis import settings as h_settings
from hypothesis import strategies as st

from app.infrastructure.models.consent import Consent
from app.infrastructure.repositories.consent_repository import ConsentRepository

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

student_id_strategy = st.uuids()
version_strategy = st.text(min_size=1, max_size=20)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_session() -> AsyncMock:
    """Return a mock AsyncSession that captures added Consent objects."""
    added: list = []

    def _add(obj):
        if isinstance(obj, Consent):
            added.append(obj)

    mock_session = AsyncMock()
    mock_session.add = MagicMock(side_effect=_add)
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()

    call_count = [0]

    async def _execute(stmt, *args, **kwargs):
        result = MagicMock()
        idx = call_count[0]
        result.scalar_one_or_none.return_value = added[idx] if idx < len(added) else None
        call_count[0] += 1
        return result

    mock_session.execute = AsyncMock(side_effect=_execute)
    mock_session._added = added
    return mock_session


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@h_settings(max_examples=100)
@given(student_id=student_id_strategy, version=version_strategy)
async def test_consent_repository_has_no_direct_mutation_methods(
    student_id: uuid.UUID, version: str
):
    """
    **Validates: Requirements 8.4**

    Property 10 (structural): ConsentRepository must not expose any method
    whose name suggests direct in-place mutation (update, patch, modify,
    delete, set_*). Revocation is achieved by creating a new record, not
    by modifying an existing one.
    """
    forbidden_prefixes = ("update", "patch", "modify", "delete", "set_")
    forbidden_exact = {"update", "patch", "modify", "delete"}

    public_methods = [
        name
        for name, _ in inspect.getmembers(ConsentRepository, predicate=inspect.isfunction)
        if not name.startswith("_")
    ]

    for method_name in public_methods:
        assert method_name not in forbidden_exact, (
            f"ConsentRepository must not expose '{method_name}' — "
            "consent records are immutable; revocation creates a new record."
        )
        for prefix in forbidden_prefixes:
            assert not method_name.startswith(prefix), (
                f"ConsentRepository must not expose '{method_name}' — "
                "consent records are immutable; revocation creates a new record."
            )


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(student_id=student_id_strategy, version=version_strategy)
async def test_revocation_creates_new_record_not_mutation(
    student_id: uuid.UUID, version: str
):
    """
    **Validates: Requirements 8.4**

    Property 10 (behavioural): Revoking consent must produce a second,
    distinct Consent record with accepted=False. The original record must
    remain untouched (accepted=True), proving that revocation never mutates
    an existing row.
    """
    mock_session = _make_mock_session()
    repo = ConsentRepository(session=mock_session)

    # Register initial consent (accepted=True by default)
    original = await repo.register_consent(student_id=student_id, version=version)

    # Revoke by registering a new record with accepted=False
    revocation = await repo.register_consent(
        student_id=student_id, version=version, accepted=False
    )

    # Two distinct objects must have been created
    assert original is not revocation, (
        "Revocation must create a new Consent object, not return the same instance."
    )

    # Original record must still reflect accepted=True
    assert original.accepted is True, (
        "The original consent record must remain accepted=True after revocation."
    )

    # Revocation record must have accepted=False
    assert revocation.accepted is False, (
        "The revocation record must have accepted=False."
    )

    # Both records share the same student_id and version
    assert original.student_id == student_id
    assert revocation.student_id == student_id
    assert original.terms_version == version
    assert revocation.terms_version == version


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(student_id=student_id_strategy, version=version_strategy)
async def test_revocation_does_not_call_session_execute_update(
    student_id: uuid.UUID, version: str
):
    """
    **Validates: Requirements 8.4**

    Property 10 (session invariant): Revoking consent must only use
    session.add() to insert a new row. The session must never receive an
    UPDATE statement, confirming that no in-place mutation occurs at the
    ORM level.
    """
    mock_session = _make_mock_session()
    repo = ConsentRepository(session=mock_session)

    await repo.register_consent(student_id=student_id, version=version)
    await repo.register_consent(student_id=student_id, version=version, accepted=False)

    # session.add must have been called at least twice for the two Consent rows
    consent_adds = [
        call.args[0]
        for call in mock_session.add.call_args_list
        if isinstance(call.args[0], Consent)
    ]
    assert len(consent_adds) >= 2, (
        "Two separate Consent objects must be added to the session — "
        "one for the original consent and one for the revocation."
    )

    # Verify no execute call contained an UPDATE statement
    for call in mock_session.execute.call_args_list:
        stmt = call.args[0] if call.args else None
        if stmt is not None:
            stmt_str = str(stmt).upper()
            assert "UPDATE" not in stmt_str, (
                "session.execute must not be called with an UPDATE statement — "
                "consent records are immutable."
            )
