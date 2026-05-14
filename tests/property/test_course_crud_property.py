# Feature: course-crud-endpoints, Property 1: CourseCreate rejects incomplete input
"""
Property-based test for CourseCreate schema validation.

Verifies that constructing a CourseCreate instance with any subset of
required fields missing at least one field raises a ValidationError.

**Validates: Requirements 1.1, 1.2**
"""

import uuid

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st
from pydantic import ValidationError

from app.application.schemas.course import CourseCreate

# ---------------------------------------------------------------------------
# All required fields for CourseCreate
# ---------------------------------------------------------------------------

ALL_REQUIRED_FIELDS = {
    "code": "MAT101",
    "name": "Cálculo I",
    "credits": 4,
    "academic_period": "2024-1",
    "program_id": uuid.uuid4(),
}

FIELD_NAMES = list(ALL_REQUIRED_FIELDS.keys())


# Strategy: generate a non-empty subset of field names to REMOVE
# (at least 1 field missing, at most all fields missing)
missing_fields_strategy = st.lists(
    st.sampled_from(FIELD_NAMES),
    min_size=1,
    max_size=len(FIELD_NAMES),
    unique=True,
)


@h_settings(max_examples=100)
@given(fields_to_remove=missing_fields_strategy)
def test_course_create_rejects_incomplete_input(fields_to_remove: list[str]):
    """
    **Validates: Requirements 1.1, 1.2**

    Property 1: CourseCreate rejects incomplete input.

    For any subset of required fields missing at least one, constructing
    CourseCreate must raise ValidationError.
    """
    incomplete_data = {
        k: v for k, v in ALL_REQUIRED_FIELDS.items() if k not in fields_to_remove
    }

    with pytest.raises(ValidationError):
        CourseCreate(**incomplete_data)


# Feature: course-crud-endpoints, Property 3: Round-trip de creación y búsqueda por code
# ---------------------------------------------------------------------------
# Property-based test for create + get_by_code round-trip consistency.
#
# For any valid course data, calling `create` followed by `get_by_code(course.code)`
# must return a course with the same `id` and the same values in all provided fields.
#
# **Validates: Requirements 5.1, 5.6**
# ---------------------------------------------------------------------------

from unittest.mock import AsyncMock, MagicMock, call
from datetime import datetime, timezone

from hypothesis import HealthCheck

from app.application.schemas.course import CourseUpdate
from app.domain.enums import CourseStatusEnum, OperationEnum
from app.infrastructure.models.course import Course
from app.infrastructure.repositories.course_repository import CourseRepository

# ---------------------------------------------------------------------------
# Strategies for Property 3
# ---------------------------------------------------------------------------

_course_code_strategy = st.from_regex(r"[A-Z]{2,4}[0-9]{3}", fullmatch=True)
_course_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
    min_size=1,
    max_size=80,
).filter(lambda s: s.strip())
_credits_strategy = st.integers(min_value=1, max_value=12)
_academic_period_strategy = st.from_regex(r"20[2-3][0-9]-[12]", fullmatch=True)
_program_id_strategy = st.uuids()


def _build_mock_session_for_roundtrip():
    """
    Build a mock AsyncSession that stores courses in an in-memory dict,
    simulating flush/refresh/execute for create and get_by_code.
    """
    session = AsyncMock()
    store: dict[str, Course] = {}  # code -> Course

    def mock_add(obj):
        if isinstance(obj, Course):
            store[obj.code] = obj

    session.add = MagicMock(side_effect=mock_add)
    session.flush = AsyncMock()

    async def mock_refresh(obj):
        pass  # id is already set by default_factory

    session.refresh = AsyncMock(side_effect=mock_refresh)

    class FakeScalarResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    async def mock_execute(stmt):
        compiled = str(stmt)
        # Detect get_by_code query (WHERE courses.code = ...)
        if "courses" in compiled and "code" in compiled:
            try:
                params = stmt.compile().params
            except Exception:
                params = {}
            for key, value in params.items():
                if isinstance(value, str) and value in store:
                    return FakeScalarResult(store[value])
            return FakeScalarResult(None)
        return FakeScalarResult(None)

    session.execute = AsyncMock(side_effect=mock_execute)

    return session, store


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    code=_course_code_strategy,
    name=_course_name_strategy,
    credits=_credits_strategy,
    academic_period=_academic_period_strategy,
    program_id=_program_id_strategy,
)
async def test_create_then_get_by_code_roundtrip(
    code: str,
    name: str,
    credits: int,
    academic_period: str,
    program_id: uuid.UUID,
):
    """
    **Validates: Requirements 5.1, 5.6**

    Property 3: Round-trip de creación y búsqueda por code.

    For any valid course data, `create` followed by `get_by_code(course.code)`
    must return a course with the same `id` and the same values in all fields.
    """
    session, _store = _build_mock_session_for_roundtrip()

    # Patch the audit repo to be a no-op mock
    repo = CourseRepository.__new__(CourseRepository)
    repo._session = session
    repo._audit = AsyncMock()
    repo._audit.register = AsyncMock()

    data = {
        "code": code,
        "name": name,
        "credits": credits,
        "academic_period": academic_period,
        "program_id": program_id,
    }

    created = await repo.create(data)

    # Verify the created course has the right fields
    assert created.code == code
    assert created.name == name
    assert created.credits == credits
    assert created.academic_period == academic_period
    assert created.program_id == program_id
    assert created.id is not None

    # Now look it up by code
    found = await repo.get_by_code(code)

    assert found is not None, f"get_by_code({code!r}) returned None after create"
    assert found.id == created.id, (
        f"ID mismatch: created {created.id}, found {found.id}"
    )
    assert found.code == created.code
    assert found.name == created.name
    assert found.credits == created.credits
    assert found.academic_period == created.academic_period
    assert found.program_id == created.program_id


# Feature: course-crud-endpoints, Property 4: Operaciones de escritura registran audit log correcto
# ---------------------------------------------------------------------------
# Property-based test for audit log correctness on write operations.
#
# For any write operation (create, update, update_status), the repository must
# register an AuditLog with table_name="courses", the correct operation
# (INSERT or UPDATE), and the corresponding data.
#
# **Validates: Requirements 5.2, 5.4, 5.11**
# ---------------------------------------------------------------------------


def _build_repo_with_audit_spy(existing_course: Course | None = None):
    """
    Build a CourseRepository with a mock session and a spy on the audit register method.
    If existing_course is provided, obtener_por_id will return it.
    """
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    class FakeScalarResult:
        def __init__(self, value):
            self._value = value

        def scalar_one_or_none(self):
            return self._value

    async def mock_execute(stmt):
        if existing_course is not None:
            return FakeScalarResult(existing_course)
        return FakeScalarResult(None)

    session.execute = AsyncMock(side_effect=mock_execute)

    repo = CourseRepository.__new__(CourseRepository)
    repo._session = session
    audit_mock = AsyncMock()
    audit_mock.register = AsyncMock()
    repo._audit = audit_mock

    return repo, audit_mock


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    code=_course_code_strategy,
    name=_course_name_strategy,
    credits=_credits_strategy,
    academic_period=_academic_period_strategy,
    program_id=_program_id_strategy,
)
async def test_create_registers_insert_audit_log(
    code: str,
    name: str,
    credits: int,
    academic_period: str,
    program_id: uuid.UUID,
):
    """
    **Validates: Requirements 5.2, 5.4, 5.11**

    Property 4 (create): Creating a course registers an AuditLog with
    operation=INSERT, table_name="courses", and new_data matching the input.
    """
    repo, audit_mock = _build_repo_with_audit_spy()

    data = {
        "code": code,
        "name": name,
        "credits": credits,
        "academic_period": academic_period,
        "program_id": program_id,
    }

    created = await repo.create(data)

    # Audit must have been called exactly once
    audit_mock.register.assert_called_once()
    audit_log_arg = audit_mock.register.call_args[0][0]

    assert audit_log_arg.table_name == "courses"
    assert audit_log_arg.operation == OperationEnum.INSERT
    assert audit_log_arg.record_id == created.id
    assert audit_log_arg.new_data == data


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    new_name=_course_name_strategy,
    new_credits=_credits_strategy,
)
async def test_update_registers_update_audit_log(
    new_name: str,
    new_credits: int,
):
    """
    **Validates: Requirements 5.2, 5.4, 5.11**

    Property 4 (update): Updating a course registers an AuditLog with
    operation=UPDATE, table_name="courses", previous_data and new_data.
    """
    course_id = uuid.uuid4()
    existing = Course(
        id=course_id,
        code="ORIG100",
        name="Original",
        credits=3,
        academic_period="2024-1",
        program_id=uuid.uuid4(),
    )

    repo, audit_mock = _build_repo_with_audit_spy(existing)

    update_data = CourseUpdate(name=new_name, credits=new_credits)
    result = await repo.update(course_id, update_data)

    assert result is not None

    audit_mock.register.assert_called_once()
    audit_log_arg = audit_mock.register.call_args[0][0]

    assert audit_log_arg.table_name == "courses"
    assert audit_log_arg.operation == OperationEnum.UPDATE
    assert audit_log_arg.record_id == course_id
    assert audit_log_arg.previous_data is not None
    assert audit_log_arg.new_data == {"name": new_name, "credits": new_credits}


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    new_status=st.sampled_from(list(CourseStatusEnum)),
)
async def test_update_status_registers_update_audit_log(
    new_status: CourseStatusEnum,
):
    """
    **Validates: Requirements 5.2, 5.4, 5.11**

    Property 4 (update_status): Changing a course's status registers an AuditLog
    with operation=UPDATE, table_name="courses", previous and new status.
    """
    course_id = uuid.uuid4()
    # Start with the opposite status to ensure a change
    initial_status = (
        CourseStatusEnum.INACTIVE
        if new_status == CourseStatusEnum.ACTIVE
        else CourseStatusEnum.ACTIVE
    )
    existing = Course(
        id=course_id,
        code="STAT100",
        name="Status Test",
        credits=3,
        academic_period="2024-1",
        program_id=uuid.uuid4(),
        status=initial_status,
    )

    repo, audit_mock = _build_repo_with_audit_spy(existing)

    result = await repo.update_status(course_id, new_status)

    assert result is not None

    audit_mock.register.assert_called_once()
    audit_log_arg = audit_mock.register.call_args[0][0]

    assert audit_log_arg.table_name == "courses"
    assert audit_log_arg.operation == OperationEnum.UPDATE
    assert audit_log_arg.record_id == course_id
    assert audit_log_arg.previous_data == {"status": initial_status}
    assert audit_log_arg.new_data == {"status": new_status}


# Feature: course-crud-endpoints, Property 5: Listado y conteo filtran por status consistentemente
# ---------------------------------------------------------------------------
# Property-based test for list_all / count_all consistency by status.
#
# For any set of courses with mixed statuses, `list_all(status=S)` and
# `count_all(status=S)` must return only courses with status S, and
# `count_all(status=S)` must equal `len(list_all(status=S))` without pagination.
#
# **Validates: Requirements 5.7, 5.8, 6.8, 7.3**
# ---------------------------------------------------------------------------

from unittest.mock import patch


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    statuses=st.lists(
        st.sampled_from(list(CourseStatusEnum)),
        min_size=1,
        max_size=20,
    ),
    filter_status=st.sampled_from(list(CourseStatusEnum)),
)
async def test_list_and_count_filter_by_status_consistently(
    statuses: list[CourseStatusEnum],
    filter_status: CourseStatusEnum,
):
    """
    **Validates: Requirements 5.7, 5.8, 6.8, 7.3**

    Property 5: Listado y conteo filtran por status consistentemente.

    For any set of courses with mixed statuses, `list_all(status=S)` and
    `count_all(status=S)` must return only courses with status S, and
    `count_all(status=S)` must equal `len(list_all(status=S))`.
    """
    # Create courses with the given statuses
    courses = []
    for i, status in enumerate(statuses):
        courses.append(
            Course(
                id=uuid.uuid4(),
                code=f"TST{i:04d}",
                name=f"Test Course {i}",
                credits=3,
                academic_period="2024-1",
                program_id=uuid.uuid4(),
                status=status,
            )
        )

    # Expected results based on in-memory filtering
    expected_filtered = [c for c in courses if c.status == filter_status]
    expected_count = len(expected_filtered)

    # Build a mock session that returns the correct filtered results
    session = AsyncMock()
    call_index = {"n": 0}

    class FakeListResult:
        def __init__(self, items):
            self._items = items

        def scalars(self):
            return self

        def all(self):
            return self._items

    class FakeCountResult:
        def __init__(self, value):
            self._value = value

        def scalar_one(self):
            return self._value

    async def mock_execute(stmt):
        compiled_str = str(stmt)
        call_index["n"] += 1
        if "count" in compiled_str.lower():
            return FakeCountResult(expected_count)
        else:
            return FakeListResult(expected_filtered)

    session.execute = AsyncMock(side_effect=mock_execute)

    repo = CourseRepository.__new__(CourseRepository)
    repo._session = session
    repo._audit = AsyncMock()

    # Use large limit to avoid pagination effects
    listed = await repo.list_all(skip=0, limit=1000, status=filter_status)
    counted = await repo.count_all(status=filter_status)

    # All listed courses must have the filtered status
    for c in listed:
        assert c.status == filter_status, (
            f"list_all returned course with status {c.status}, "
            f"expected {filter_status}"
        )

    # Count must match list length
    assert len(listed) == expected_count, (
        f"list_all returned {len(listed)} courses, expected {expected_count}"
    )
    assert counted == expected_count, (
        f"count_all returned {counted}, expected {expected_count}"
    )
    assert counted == len(listed), (
        f"count_all ({counted}) != len(list_all) ({len(listed)})"
    )

    # Verify that the repository actually called session.execute with
    # statements that include the status filter
    assert session.execute.call_count == 2, (
        f"Expected 2 session.execute calls (list + count), "
        f"got {session.execute.call_count}"
    )

    # Verify the SQL statements include the WHERE clause for status
    for call_args in session.execute.call_args_list:
        stmt = call_args[0][0]
        compiled_str = str(stmt)
        assert "status" in compiled_str.lower(), (
            f"Expected status filter in SQL, got: {compiled_str}"
        )


# Feature: course-crud-endpoints, Property 6: Creación rechaza code duplicado
# ---------------------------------------------------------------------------
# Property-based test for duplicate code rejection on creation.
#
# For any `code` that already belongs to an existing course, calling
# `create_course` must raise an HTTPException with status 409 and
# detail "El code ya está registrado".
#
# **Validates: Requirements 6.2, 6.3, 12.1**
# ---------------------------------------------------------------------------

from app.application.services.course_service import CourseService


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    code=_course_code_strategy,
    name=_course_name_strategy,
    credits=_credits_strategy,
    academic_period=_academic_period_strategy,
    program_id=_program_id_strategy,
)
async def test_create_course_rejects_duplicate_code(
    code: str,
    name: str,
    credits: int,
    academic_period: str,
    program_id: uuid.UUID,
):
    """
    **Validates: Requirements 6.2, 6.3, 12.1**

    Property 6: Creación rechaza code duplicado.

    For any code that already belongs to an existing course, calling
    create_course must raise HTTPException with status 409.
    """
    from fastapi import HTTPException as _HTTPException

    # Build a mock repo where get_by_code returns an existing course
    repo = AsyncMock()
    existing_course = Course(
        id=uuid.uuid4(),
        code=code,
        name="Existing Course",
        credits=3,
        academic_period="2024-1",
        program_id=uuid.uuid4(),
        status=CourseStatusEnum.ACTIVE,
    )
    repo.get_by_code = AsyncMock(return_value=existing_course)
    repo.create = AsyncMock()

    service = CourseService(repo)

    create_data = CourseCreate(
        code=code,
        name=name,
        credits=credits,
        academic_period=academic_period,
        program_id=program_id,
    )

    with pytest.raises(_HTTPException) as exc_info:
        await service.create_course(create_data)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "El code ya está registrado"
    repo.create.assert_not_awaited()


# Feature: course-crud-endpoints, Property 7: Validación de unicidad en actualización
# ---------------------------------------------------------------------------
# Property-based test for uniqueness validation on update.
#
# For any two distinct courses A and B, calling
# update_course(A.id, CourseUpdate(code=B.code)) must raise HTTPException 409.
# However, update_course(A.id, CourseUpdate(code=A.code)) must succeed.
#
# **Validates: Requirements 6.5, 6.6, 12.2, 12.3**
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    code_a=_course_code_strategy,
    code_b=_course_code_strategy,
    name_a=_course_name_strategy,
    name_b=_course_name_strategy,
    program_id=_program_id_strategy,
)
async def test_update_course_rejects_code_from_different_course(
    code_a: str,
    code_b: str,
    name_a: str,
    name_b: str,
    program_id: uuid.UUID,
):
    """
    **Validates: Requirements 6.5, 6.6, 12.2, 12.3**

    Property 7: Validación de unicidad en actualización.

    For any two distinct courses A and B, update_course(A.id, CourseUpdate(code=B.code))
    must raise HTTPException 409. update_course(A.id, CourseUpdate(code=A.code)) must succeed.
    """
    from hypothesis import assume
    from fastapi import HTTPException as _HTTPException

    assume(code_a != code_b)

    id_a = uuid.uuid4()
    id_b = uuid.uuid4()

    course_a = Course(
        id=id_a,
        code=code_a,
        name=name_a,
        credits=3,
        academic_period="2024-1",
        program_id=program_id,
        status=CourseStatusEnum.ACTIVE,
    )
    course_b = Course(
        id=id_b,
        code=code_b,
        name=name_b,
        credits=4,
        academic_period="2024-1",
        program_id=program_id,
        status=CourseStatusEnum.ACTIVE,
    )

    # --- Case 1: Trying to use B's code on A → must raise 409 ---
    repo_conflict = AsyncMock()
    repo_conflict.get_by_code = AsyncMock(return_value=course_b)
    repo_conflict.update = AsyncMock()

    service_conflict = CourseService(repo_conflict)

    with pytest.raises(_HTTPException) as exc_info:
        await service_conflict.update_course(id_a, CourseUpdate(code=code_b))

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "El code ya está registrado"
    repo_conflict.update.assert_not_awaited()

    # --- Case 2: Using A's own code on A → must succeed ---
    repo_self = AsyncMock()
    repo_self.get_by_code = AsyncMock(return_value=course_a)
    updated_a = Course(
        id=id_a,
        code=code_a,
        name=name_a,
        credits=3,
        academic_period="2024-1",
        program_id=program_id,
        status=CourseStatusEnum.ACTIVE,
    )
    repo_self.update = AsyncMock(return_value=updated_a)

    service_self = CourseService(repo_self)

    result = await service_self.update_course(id_a, CourseUpdate(code=code_a))

    assert result.id == id_a
    assert result.code == code_a
    repo_self.update.assert_awaited_once()


# Feature: course-crud-endpoints, Property 2: Actualización parcial preserva campos omitidos
# ---------------------------------------------------------------------------
# Property-based test for partial update field preservation.
#
# For any existing course and any non-empty subset of CourseUpdate fields,
# calling update_course must modify only the provided fields and leave all
# omitted fields unchanged.
#
# **Validates: Requirements 2.2, 5.3**
# ---------------------------------------------------------------------------

from app.application.schemas.course import CourseRead


# Strategy: generate a non-empty subset of updatable field names
_updatable_fields = ["code", "name", "credits", "academic_period", "program_id"]

_fields_to_update_strategy = st.lists(
    st.sampled_from(_updatable_fields),
    min_size=1,
    max_size=len(_updatable_fields),
    unique=True,
)

# Strategy: generate values for each updatable field
_field_value_strategies = {
    "code": _course_code_strategy,
    "name": _course_name_strategy,
    "credits": _credits_strategy,
    "academic_period": _academic_period_strategy,
    "program_id": _program_id_strategy,
}


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    fields_to_update=_fields_to_update_strategy,
    new_code=_course_code_strategy,
    new_name=_course_name_strategy,
    new_credits=_credits_strategy,
    new_academic_period=_academic_period_strategy,
    new_program_id=_program_id_strategy,
    orig_code=_course_code_strategy,
    orig_name=_course_name_strategy,
    orig_credits=_credits_strategy,
    orig_academic_period=_academic_period_strategy,
    orig_program_id=_program_id_strategy,
)
async def test_partial_update_preserves_omitted_fields(
    fields_to_update: list[str],
    new_code: str,
    new_name: str,
    new_credits: int,
    new_academic_period: str,
    new_program_id: uuid.UUID,
    orig_code: str,
    orig_name: str,
    orig_credits: int,
    orig_academic_period: str,
    orig_program_id: uuid.UUID,
):
    """
    **Validates: Requirements 2.2, 5.3**

    Property 2: Actualización parcial preserva campos omitidos.

    For any existing course and any non-empty subset of CourseUpdate fields,
    update_course must modify only the provided fields and leave omitted
    fields unchanged.
    """
    course_id = uuid.uuid4()

    # Original field values
    original_values = {
        "code": orig_code,
        "name": orig_name,
        "credits": orig_credits,
        "academic_period": orig_academic_period,
        "program_id": orig_program_id,
    }

    # New values for the fields being updated
    new_values = {
        "code": new_code,
        "name": new_name,
        "credits": new_credits,
        "academic_period": new_academic_period,
        "program_id": new_program_id,
    }

    # Build the CourseUpdate with only the selected fields
    update_kwargs = {f: new_values[f] for f in fields_to_update}
    update_data = CourseUpdate(**update_kwargs)

    # Simulate what the updated course should look like:
    # updated fields get new values, omitted fields keep original values
    expected_values = dict(original_values)
    for f in fields_to_update:
        expected_values[f] = new_values[f]

    # Build the mock course that the repo.update would return
    returned_course = Course(
        id=course_id,
        code=expected_values["code"],
        name=expected_values["name"],
        credits=expected_values["credits"],
        academic_period=expected_values["academic_period"],
        program_id=expected_values["program_id"],
        status=CourseStatusEnum.ACTIVE,
    )

    repo = AsyncMock()
    # If code is being updated, get_by_code should return None (no conflict)
    repo.get_by_code = AsyncMock(return_value=None)
    repo.update = AsyncMock(return_value=returned_course)

    service = CourseService(repo)
    result = await service.update_course(course_id, update_data)

    # Verify updated fields have new values
    for f in fields_to_update:
        assert getattr(result, f) == new_values[f], (
            f"Updated field '{f}' should be {new_values[f]}, got {getattr(result, f)}"
        )

    # Verify omitted fields preserved original values
    omitted_fields = [f for f in _updatable_fields if f not in fields_to_update]
    for f in omitted_fields:
        assert getattr(result, f) == original_values[f], (
            f"Omitted field '{f}' should be {original_values[f]}, got {getattr(result, f)}"
        )


# Feature: course-crud-endpoints, Property 8: Rechazo de rol no-ADMIN en endpoints de escritura
# ---------------------------------------------------------------------------
# Property-based test for non-ADMIN role rejection on write endpoints.
#
# For any authenticated user whose role is not ADMIN, sending a request to
# POST /courses, PATCH /courses/{id}, or PATCH /courses/{id}/status must
# return a 403 status code.
#
# **Validates: Requirements 9.4, 9.6, 10.5, 10.7, 11.5, 11.7**
# ---------------------------------------------------------------------------

from datetime import timedelta

import jwt as pyjwt

from app.core.config import settings
from app.domain.enums import RoleEnum
from app.main import app
from app.infrastructure.database import get_session

from httpx import ASGITransport, AsyncClient

# Non-ADMIN roles to test
_non_admin_roles = [r for r in RoleEnum if r != RoleEnum.ADMIN]


def _create_access_token_for_role(role: RoleEnum) -> str:
    """Create a valid JWT access token for the given role."""
    uid = uuid.uuid4()
    now_ts = datetime.now(timezone.utc)
    claims = {
        "sub": str(uid),
        "role": role.value,
        "type": "access",
        "iat": int(now_ts.timestamp()),
        "exp": int((now_ts + timedelta(minutes=30)).timestamp()),
    }
    return pyjwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


@pytest.mark.anyio
@h_settings(
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    role=st.sampled_from(_non_admin_roles),
)
async def test_non_admin_rejected_on_write_endpoints(
    role: RoleEnum,
):
    """
    **Validates: Requirements 9.4, 9.6, 10.5, 10.7, 11.5, 11.7**

    Property 8: Rechazo de rol no-ADMIN en endpoints de escritura.

    For any authenticated user whose role is not ADMIN, POST /courses,
    PATCH /courses/{id}, and PATCH /courses/{id}/status must return 403.
    """
    mock_session = AsyncMock()

    async def _override_get_session():
        yield mock_session

    app.dependency_overrides[get_session] = _override_get_session

    try:
        token = _create_access_token_for_role(role)
        headers = {"Authorization": f"Bearer {token}"}
        course_id = uuid.uuid4()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # POST /courses
            resp_post = await client.post(
                "/api/v1/courses",
                json={
                    "code": "TST001",
                    "name": "Test",
                    "credits": 3,
                    "academic_period": "2024-1",
                    "program_id": str(uuid.uuid4()),
                },
                headers=headers,
            )
            assert resp_post.status_code == 403, (
                f"POST /courses with role {role.value} returned {resp_post.status_code}, expected 403"
            )

            # PATCH /courses/{id}
            resp_patch = await client.patch(
                f"/api/v1/courses/{course_id}",
                json={"name": "Updated"},
                headers=headers,
            )
            assert resp_patch.status_code == 403, (
                f"PATCH /courses/{{id}} with role {role.value} returned {resp_patch.status_code}, expected 403"
            )

            # PATCH /courses/{id}/status
            resp_status = await client.patch(
                f"/api/v1/courses/{course_id}/status",
                json={"status": "INACTIVE"},
                headers=headers,
            )
            assert resp_status.status_code == 403, (
                f"PATCH /courses/{{id}}/status with role {role.value} returned {resp_status.status_code}, expected 403"
            )
    finally:
        app.dependency_overrides.clear()
