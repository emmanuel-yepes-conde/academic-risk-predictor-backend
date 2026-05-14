# Feature: postgresql-database-integration, Property 7: Atomic audit
"""
Property-based tests for atomic audit logging with correct content.

Verifies that for any write operation (INSERT / UPDATE) on audited tables
(users, courses, consents), exactly one AuditLog entry is registered within
the same session, and that entry carries the correct table_name, operation,
record_id, and new_data / previous_data values.

**Validates: Requirements 6.5, 9.1, 9.2**
"""

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from app.application.schemas.audit_log import AuditLogCreate
from app.application.schemas.course import CourseCreate
from app.application.schemas.user import UserCreate, UserUpdate
from app.domain.enums import OperationEnum, RoleEnum
from app.infrastructure.models.audit_log import AuditLog
from app.infrastructure.models.course import Course
from app.infrastructure.models.user import User
from app.infrastructure.repositories.course_repository import CourseRepository
from app.infrastructure.repositories.consent_repository import ConsentRepository
from app.infrastructure.repositories.user_repository import UserRepository

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

role_strategy = st.sampled_from(list(RoleEnum))

user_create_strategy = st.builds(
    UserCreate,
    email=st.emails(),
    full_name=st.text(min_size=1, max_size=100),
    role=role_strategy,
    microsoft_oid=st.none(),
    google_oid=st.none(),
    password_hash=st.none(),
    ml_consent=st.booleans(),
)

user_update_strategy = st.builds(
    UserUpdate,
    full_name=st.one_of(st.none(), st.text(min_size=1, max_size=100)),
    role=st.one_of(st.none(), role_strategy),
    microsoft_oid=st.none(),
    google_oid=st.none(),
    password_hash=st.none(),
    ml_consent=st.one_of(st.none(), st.booleans()),
)

course_create_strategy = st.builds(
    CourseCreate,
    code=st.text(
        min_size=1,
        max_size=20,
        alphabet=st.characters(
            whitelist_categories=("Lu", "Ll", "Nd"),
            whitelist_characters="-_",
        ),
    ),
    name=st.text(min_size=1, max_size=100),
    credits=st.integers(min_value=1, max_value=10),
    academic_period=st.text(min_size=1, max_size=20),
)

version_strategy = st.text(min_size=1, max_size=20)

# ---------------------------------------------------------------------------
# Mock session factory
# ---------------------------------------------------------------------------

def _make_session(entity_type: type) -> tuple[AsyncMock, list[AuditLogCreate]]:
    """
    Build a mock AsyncSession that:
    - Stores the first entity of `entity_type` added via session.add()
    - Captures every AuditLogCreate passed to AuditLogRepository.register()
      by intercepting the second session.add() call (which adds the AuditLog ORM object)
    - Returns the stored entity from session.execute() so get_by_* lookups work

    Returns (mock_session, captured_audit_logs).
    """
    stored_entity: list = []
    captured_audit_logs: list[AuditLog] = []

    def _add(obj):
        if isinstance(obj, entity_type) and not stored_entity:
            stored_entity.append(obj)
        elif isinstance(obj, AuditLog):
            captured_audit_logs.append(obj)

    mock_session = AsyncMock()
    mock_session.add = MagicMock(side_effect=_add)
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()

    async def _execute(stmt, *args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = stored_entity[0] if stored_entity else None
        return result

    mock_session.execute = AsyncMock(side_effect=_execute)
    return mock_session, captured_audit_logs


# ---------------------------------------------------------------------------
# Property tests — UserRepository.create (INSERT)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@h_settings(max_examples=100)
@given(user_data=user_create_strategy)
async def test_user_create_registers_exactly_one_audit_log(user_data: UserCreate):
    """
    **Validates: Requirements 6.5, 9.1, 9.2**

    Property 7 (User INSERT): For any UserCreate input, UserRepository.create()
    must register exactly one AuditLog entry in the same session.
    """
    mock_session, audit_logs = _make_session(User)
    repo = UserRepository(session=mock_session)

    await repo.create(user_data)

    assert len(audit_logs) == 1, (
        f"Expected exactly 1 AuditLog entry after User INSERT, got {len(audit_logs)}"
    )


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(user_data=user_create_strategy)
async def test_user_create_audit_log_has_correct_content(user_data: UserCreate):
    """
    **Validates: Requirements 6.5, 9.1, 9.2**

    Property 7 (User INSERT content): The AuditLog entry produced by
    UserRepository.create() must have table_name='users', operation=INSERT,
    record_id matching the created user's id, and new_data containing the
    input fields. previous_data must be None for an INSERT.
    """
    mock_session, audit_logs = _make_session(User)
    repo = UserRepository(session=mock_session)

    created = await repo.create(user_data)
    log = audit_logs[0]

    assert log.table_name == "users"
    assert log.operation == OperationEnum.INSERT
    assert log.record_id == created.id
    assert log.previous_data is None
    assert log.new_data is not None
    assert log.new_data.get("email") == user_data.email
    assert log.new_data.get("full_name") == user_data.full_name


# ---------------------------------------------------------------------------
# Property tests — UserRepository.update (UPDATE)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@h_settings(max_examples=100)
@given(user_data=user_create_strategy, update_data=user_update_strategy)
async def test_user_update_registers_exactly_one_audit_log(
    user_data: UserCreate, update_data: UserUpdate
):
    """
    **Validates: Requirements 6.5, 9.1, 9.2**

    Property 7 (User UPDATE): For any UserUpdate input on an existing user,
    UserRepository.update() must register exactly one AuditLog entry.
    """
    mock_session, audit_logs = _make_session(User)
    repo = UserRepository(session=mock_session)

    created = await repo.create(user_data)
    # Reset captured logs — we only care about the UPDATE audit entry
    audit_logs.clear()

    await repo.update(created.id, update_data)

    assert len(audit_logs) == 1, (
        f"Expected exactly 1 AuditLog entry after User UPDATE, got {len(audit_logs)}"
    )


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(user_data=user_create_strategy, update_data=user_update_strategy)
async def test_user_update_audit_log_has_correct_operation_and_table(
    user_data: UserCreate, update_data: UserUpdate
):
    """
    **Validates: Requirements 6.5, 9.1, 9.2**

    Property 7 (User UPDATE content): The AuditLog entry produced by
    UserRepository.update() must have table_name='users', operation=UPDATE,
    record_id matching the user's id, and both previous_data and new_data set.
    """
    mock_session, audit_logs = _make_session(User)
    repo = UserRepository(session=mock_session)

    created = await repo.create(user_data)
    audit_logs.clear()

    await repo.update(created.id, update_data)
    log = audit_logs[0]

    assert log.table_name == "users"
    assert log.operation == OperationEnum.UPDATE
    assert log.record_id == created.id
    assert log.previous_data is not None
    assert log.new_data is not None


# ---------------------------------------------------------------------------
# Property tests — CourseRepository.crear (INSERT)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@h_settings(max_examples=100)
@given(course_data=course_create_strategy)
async def test_course_create_registers_exactly_one_audit_log(course_data: CourseCreate):
    """
    **Validates: Requirements 6.5, 9.1, 9.2**

    Property 7 (Course INSERT): For any CourseCreate input,
    CourseRepository.crear() must register exactly one AuditLog entry.
    """
    mock_session, audit_logs = _make_session(Course)
    repo = CourseRepository(session=mock_session)

    await repo.crear(course_data)

    assert len(audit_logs) == 1, (
        f"Expected exactly 1 AuditLog entry after Course INSERT, got {len(audit_logs)}"
    )


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(course_data=course_create_strategy)
async def test_course_create_audit_log_has_correct_content(course_data: CourseCreate):
    """
    **Validates: Requirements 6.5, 9.1, 9.2**

    Property 7 (Course INSERT content): The AuditLog entry produced by
    CourseRepository.crear() must have table_name='courses', operation=INSERT,
    record_id matching the created course's id, new_data with the input fields,
    and previous_data=None.
    """
    mock_session, audit_logs = _make_session(Course)
    repo = CourseRepository(session=mock_session)

    created = await repo.crear(course_data)
    log = audit_logs[0]

    assert log.table_name == "courses"
    assert log.operation == OperationEnum.INSERT
    assert log.record_id == created.id
    assert log.previous_data is None
    assert log.new_data is not None
    assert log.new_data.get("code") == course_data.code
    assert log.new_data.get("name") == course_data.name


# ---------------------------------------------------------------------------
# Property tests — ConsentRepository.register_consent (INSERT)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@h_settings(max_examples=100)
@given(student_id=st.uuids(), version=version_strategy, accepted=st.booleans())
async def test_consent_register_registers_exactly_one_audit_log(
    student_id: uuid.UUID, version: str, accepted: bool
):
    """
    **Validates: Requirements 6.5, 9.1, 9.2**

    Property 7 (Consent INSERT): For any student_id, version, and accepted
    value, ConsentRepository.register_consent() must register exactly one
    AuditLog entry in the same session.
    """
    from app.infrastructure.models.consent import Consent

    mock_session, audit_logs = _make_session(Consent)
    repo = ConsentRepository(session=mock_session)

    await repo.register_consent(student_id=student_id, version=version, accepted=accepted)

    assert len(audit_logs) == 1, (
        f"Expected exactly 1 AuditLog entry after Consent INSERT, got {len(audit_logs)}"
    )


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(student_id=st.uuids(), version=version_strategy, accepted=st.booleans())
async def test_consent_register_audit_log_has_correct_content(
    student_id: uuid.UUID, version: str, accepted: bool
):
    """
    **Validates: Requirements 6.5, 9.1, 9.2**

    Property 7 (Consent INSERT content): The AuditLog entry produced by
    ConsentRepository.register_consent() must have table_name='consents',
    operation=INSERT, record_id matching the consent's id, new_data containing
    student_id, accepted, and terms_version, and previous_data=None.
    """
    from app.infrastructure.models.consent import Consent

    mock_session, audit_logs = _make_session(Consent)
    repo = ConsentRepository(session=mock_session)

    created = await repo.register_consent(
        student_id=student_id, version=version, accepted=accepted
    )
    log = audit_logs[0]

    assert log.table_name == "consents"
    assert log.operation == OperationEnum.INSERT
    assert log.record_id == created.id
    assert log.previous_data is None
    assert log.new_data is not None
    assert log.new_data.get("accepted") == accepted
    assert log.new_data.get("terms_version") == version
    assert log.new_data.get("student_id") == str(student_id)


# ---------------------------------------------------------------------------
# Property test — audit log uses the same session (atomicity guarantee)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
@h_settings(max_examples=100)
@given(user_data=user_create_strategy)
async def test_audit_log_registered_in_same_session_as_entity(user_data: UserCreate):
    """
    **Validates: Requirements 6.5, 9.2**

    Property 7 (atomicity): Both the entity and its AuditLog entry must be
    added to the same session object. This guarantees they are committed (or
    rolled back) together as a single transaction.
    """
    added_objects: list = []

    mock_session = AsyncMock()
    mock_session.add = MagicMock(side_effect=lambda obj: added_objects.append(obj))
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()

    async def _execute(stmt, *args, **kwargs):
        result = MagicMock()
        users = [o for o in added_objects if isinstance(o, User)]
        result.scalar_one_or_none.return_value = users[0] if users else None
        return result

    mock_session.execute = AsyncMock(side_effect=_execute)

    repo = UserRepository(session=mock_session)
    await repo.create(user_data)

    user_adds = [o for o in added_objects if isinstance(o, User)]
    audit_adds = [o for o in added_objects if isinstance(o, AuditLog)]

    assert len(user_adds) == 1, "Exactly one User must be added to the session"
    assert len(audit_adds) == 1, "Exactly one AuditLog must be added to the same session"

    # Both objects were added via the same mock_session.add — confirming atomicity
    assert mock_session.add.call_count == 2
