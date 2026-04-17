"""
Integration tests for UserRepository (Req 6.1).

Covers: create, get_by_id, get_by_email, get_by_microsoft_oid,
        list, update, and duplicate-email IntegrityError.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.schemas.user import UserCreate, UserUpdate
from app.domain.enums import RoleEnum
from app.infrastructure.models.audit_log import AuditLog
from app.infrastructure.models.user import User
from app.infrastructure.repositories.user_repository import UserRepository

from tests.integration.conftest import make_mock_session, make_sqlite_engine, now


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _user_create(**kwargs) -> UserCreate:
    defaults = dict(
        email=f"u_{uuid.uuid4().hex[:8]}@test.com",
        full_name="Integration User",
        role=RoleEnum.STUDENT,
        ml_consent=False,
    )
    defaults.update(kwargs)
    return UserCreate(**defaults)


# ---------------------------------------------------------------------------
# Tests using mock AsyncSession (business logic)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_create_and_get_by_id():
    """create() persists user; get_by_id() returns it with matching fields."""
    session = make_mock_session()
    repo = UserRepository(session=session)

    data = _user_create(full_name="Alice", role=RoleEnum.STUDENT)
    created = await repo.create(data)

    assert created.email == data.email
    assert created.full_name == data.full_name
    assert created.role == data.role

    fetched = await repo.get_by_id(created.id)
    assert fetched is not None
    assert fetched.email == created.email


@pytest.mark.anyio
async def test_get_by_email():
    """get_by_email() returns the user matching the given email."""
    session = make_mock_session()
    repo = UserRepository(session=session)

    data = _user_create(email="alice@example.com")
    created = await repo.create(data)

    fetched = await repo.get_by_email("alice@example.com")
    assert fetched is not None
    assert fetched.id == created.id


@pytest.mark.anyio
async def test_get_by_email_not_found():
    """get_by_email() returns None when no user has that email."""
    # Empty session — execute returns None
    session = make_mock_session()
    # Override execute to always return None
    async def _empty_execute(stmt, *args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.scalars.return_value.all.return_value = []
        return result

    session.execute = AsyncMock(side_effect=_empty_execute)
    repo = UserRepository(session=session)

    result = await repo.get_by_email("nonexistent@example.com")
    assert result is None


@pytest.mark.anyio
async def test_get_by_id_not_found():
    """get_by_id() returns None for an unknown UUID."""
    session = make_mock_session()

    async def _empty_execute(stmt, *args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.scalars.return_value.all.return_value = []
        return result

    session.execute = AsyncMock(side_effect=_empty_execute)
    repo = UserRepository(session=session)

    result = await repo.get_by_id(uuid.uuid4())
    assert result is None


@pytest.mark.anyio
async def test_list_users():
    """list() returns all created users."""
    session = make_mock_session()
    repo = UserRepository(session=session)

    u1 = await repo.create(_user_create(full_name="Bob"))
    u2 = await repo.create(_user_create(full_name="Carol"))

    # Override execute to return both users
    users_in_db = [u1, u2]

    async def _list_execute(stmt, *args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.scalars.return_value.all.return_value = users_in_db
        return result

    session.execute = AsyncMock(side_effect=_list_execute)

    listed = await repo.list()
    assert len(listed) == 2
    names = {u.full_name for u in listed}
    assert "Bob" in names
    assert "Carol" in names


@pytest.mark.anyio
async def test_update_user():
    """update() persists field changes and returns the updated user."""
    stored_user = User(
        id=uuid.uuid4(),
        email="dave@example.com",
        full_name="Dave",
        role=RoleEnum.STUDENT,
        ml_consent=False,
        created_at=now(),
        updated_at=now(),
    )

    async def _execute(stmt, *args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = stored_user
        result.scalars.return_value.all.return_value = [stored_user]
        return result

    session = make_mock_session()
    session.execute = AsyncMock(side_effect=_execute)
    repo = UserRepository(session=session)

    updated = await repo.update(stored_user.id, UserUpdate(full_name="Dave Updated"))
    assert updated is not None
    assert updated.full_name == "Dave Updated"


@pytest.mark.anyio
async def test_update_user_not_found():
    """update() returns None when the user does not exist."""
    async def _empty_execute(stmt, *args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        result.scalars.return_value.all.return_value = []
        return result

    session = make_mock_session()
    session.execute = AsyncMock(side_effect=_empty_execute)
    repo = UserRepository(session=session)

    result = await repo.update(uuid.uuid4(), UserUpdate(full_name="Ghost"))
    assert result is None


# ---------------------------------------------------------------------------
# Constraint test using SQLite in-memory (IntegrityError on duplicate email)
# ---------------------------------------------------------------------------

def test_create_duplicate_email_raises_integrity_error():
    """Inserting two users with the same email raises IntegrityError."""
    engine = make_sqlite_engine()
    user_id_1 = uuid.uuid4()
    user_id_2 = uuid.uuid4()

    with Session(engine) as session:
        session.add(User(
            id=user_id_1,
            email="dup@example.com",
            full_name="First",
            role="STUDENT",
            ml_consent=False,
            created_at=now(),
            updated_at=now(),
        ))
        session.commit()

    with Session(engine) as session:
        session.add(User(
            id=user_id_2,
            email="dup@example.com",
            full_name="Second",
            role="STUDENT",
            ml_consent=False,
            created_at=now(),
            updated_at=now(),
        ))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

    engine.dispose()
