"""
Integration tests for ConsentRepository (Req 6.4).

Covers: register_consent(), get_consent(), not-found case,
        and duplicate student_id IntegrityError.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.infrastructure.models.consent import Consent
from app.infrastructure.repositories.consent_repository import ConsentRepository

from tests.integration.conftest import make_mock_session, make_sqlite_engine, now


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_repo(stored_consent: Consent | None = None) -> ConsentRepository:
    """Return a ConsentRepository backed by a mock session."""
    session = make_mock_session()

    if stored_consent is not None:
        async def _execute(stmt, *args, **kwargs):
            result = MagicMock()
            result.scalar_one_or_none.return_value = stored_consent
            result.scalars.return_value.all.return_value = [stored_consent]
            return result

        session.execute = AsyncMock(side_effect=_execute)

    return ConsentRepository(session=session)


def _make_empty_repo() -> ConsentRepository:
    """Return a ConsentRepository whose session always returns None."""
    session = make_mock_session()

    async def _empty_execute(stmt, *args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.scalars.return_value.all.return_value = []
        return result

    session.execute = AsyncMock(side_effect=_empty_execute)
    return ConsentRepository(session=session)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_register_consent():
    """register_consent() creates a Consent record with correct fields."""
    repo = _make_repo()
    student_id = uuid.uuid4()

    consent = await repo.register_consent(student_id=student_id, version="v1.0")

    assert consent is not None
    assert consent.student_id == student_id
    assert consent.terms_version == "v1.0"
    assert consent.accepted is True


@pytest.mark.anyio
async def test_register_consent_accepted_false():
    """register_consent() with accepted=False stores revocation record."""
    repo = _make_repo()
    student_id = uuid.uuid4()

    consent = await repo.register_consent(
        student_id=student_id, version="v1.1", accepted=False
    )

    assert consent.accepted is False
    assert consent.terms_version == "v1.1"


@pytest.mark.anyio
async def test_get_consent_not_found():
    """get_consent() returns None when no consent exists for the student."""
    repo = _make_empty_repo()

    result = await repo.get_consent(uuid.uuid4())
    assert result is None


@pytest.mark.anyio
async def test_get_consent_after_register():
    """get_consent() returns the same record that was registered."""
    student_id = uuid.uuid4()

    # First, create via a repo that stores the object
    session = make_mock_session()
    repo = ConsentRepository(session=session)
    created = await repo.register_consent(student_id=student_id, version="v2.0")

    # Now wire execute to return the created consent
    async def _execute(stmt, *args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = created
        result.scalars.return_value.all.return_value = [created]
        return result

    session.execute = AsyncMock(side_effect=_execute)

    fetched = await repo.get_consent(student_id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.student_id == student_id
    assert fetched.terms_version == "v2.0"


# ---------------------------------------------------------------------------
# Consent immutability: multiple records per student are allowed (migration 0022
# intentionally dropped the UNIQUE constraint so revocation + re-acceptance
# can each create a new row without modifying existing ones).
# ---------------------------------------------------------------------------

def test_duplicate_consent_raises_integrity_error():
    """Two Consent rows for the same student_id are allowed (no unique constraint
    since migration 0022 — consent history is append-only)."""
    engine = make_sqlite_engine()
    student_id = uuid.uuid4()

    with Session(engine) as session:
        session.add(Consent(
            id=uuid.uuid4(),
            student_id=student_id,
            accepted=True,
            terms_version="v1.0",
            accepted_at=now(),
        ))
        session.commit()

    with Session(engine) as session:
        session.add(Consent(
            id=uuid.uuid4(),
            student_id=student_id,
            accepted=False,
            terms_version="v1.1",
            accepted_at=now(),
        ))
        session.commit()  # must NOT raise — multiple records allowed

    with Session(engine) as session:
        from sqlalchemy import select, func
        count = session.execute(
            select(func.count()).where(Consent.student_id == student_id)
        ).scalar_one()
        assert count == 2, f"Expected 2 consent rows, got {count}"

    engine.dispose()
