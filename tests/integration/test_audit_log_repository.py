"""
Integration tests for AuditLogRepository (Req 6.3).

Covers: register(), and that update()/delete() raise NotImplementedError.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.schemas.audit_log import AuditLogCreate
from app.domain.enums import OperationEnum
from app.infrastructure.models.audit_log import AuditLog
from app.infrastructure.repositories.audit_log_repository import AuditLogRepository

from tests.integration.conftest import make_mock_session


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _audit_create(**kwargs) -> AuditLogCreate:
    defaults = dict(
        table_name="users",
        operation=OperationEnum.INSERT,
        record_id=uuid.uuid4(),
        user_id=None,
        previous_data=None,
        new_data={"email": "test@example.com"},
    )
    defaults.update(kwargs)
    return AuditLogCreate(**defaults)


def _make_repo() -> AuditLogRepository:
    session = make_mock_session()
    return AuditLogRepository(session=session)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_register_audit_log():
    """register() persists an AuditLog entry and returns it with correct fields."""
    repo = _make_repo()
    log_data = _audit_create(
        table_name="users",
        operation=OperationEnum.INSERT,
        new_data={"email": "alice@example.com"},
    )

    entry = await repo.register(log_data)

    assert entry is not None
    assert entry.table_name == "users"
    assert entry.operation == OperationEnum.INSERT
    assert entry.record_id == log_data.record_id
    assert entry.new_data == {"email": "alice@example.com"}


@pytest.mark.anyio
async def test_register_audit_log_with_previous_data():
    """register() stores previous_data for UPDATE operations."""
    repo = _make_repo()
    log_data = _audit_create(
        table_name="users",
        operation=OperationEnum.UPDATE,
        previous_data={"full_name": "Old Name"},
        new_data={"full_name": "New Name"},
    )

    entry = await repo.register(log_data)

    assert entry.operation == OperationEnum.UPDATE
    assert entry.previous_data == {"full_name": "Old Name"}
    assert entry.new_data == {"full_name": "New Name"}


@pytest.mark.anyio
async def test_audit_log_no_update_method():
    """Calling update() on AuditLogRepository raises NotImplementedError."""
    repo = _make_repo()

    with pytest.raises(NotImplementedError):
        await repo.update(uuid.uuid4(), {"table_name": "hacked"})


@pytest.mark.anyio
async def test_audit_log_no_delete_method():
    """Calling delete() on AuditLogRepository raises NotImplementedError."""
    repo = _make_repo()

    with pytest.raises(NotImplementedError):
        await repo.delete(uuid.uuid4())


@pytest.mark.anyio
async def test_audit_log_update_no_args():
    """update() raises NotImplementedError even with no arguments."""
    repo = _make_repo()

    with pytest.raises(NotImplementedError):
        await repo.update()


@pytest.mark.anyio
async def test_audit_log_delete_no_args():
    """delete() raises NotImplementedError even with no arguments."""
    repo = _make_repo()

    with pytest.raises(NotImplementedError):
        await repo.delete()


@pytest.mark.anyio
async def test_register_does_not_raise():
    """register() completes without raising for any valid OperationEnum value."""
    for op in OperationEnum:
        repo = _make_repo()
        log_data = _audit_create(operation=op)
        entry = await repo.register(log_data)
        assert entry is not None
