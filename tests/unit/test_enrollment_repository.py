"""
Unit tests for EnrollmentRepository.

Tests cover:
- create persists enrollment and registers audit log
- get_by_id returns enrollment or None
- update_course changes course_id and registers audit log
- update_status changes status and registers audit log
- list_by_student returns filtered results
- list_by_student_filtered_by_professor with status filter and RB-04

Requirements: 1.1, 1.8, 2.1, 2.6, 3.1, 3.3, 3.4
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from app.domain.enums import EnrollmentStatusEnum, OperationEnum
from app.infrastructure.models.audit_log import AuditLog
from app.infrastructure.models.enrollment import Enrollment
from app.infrastructure.repositories.enrollment_repository import EnrollmentRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ENROLLMENT_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_STUDENT_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")
_COURSE_ID = uuid.UUID("22222222-3333-4444-5555-666666666666")
_NEW_COURSE_ID = uuid.UUID("33333333-4444-5555-6666-777777777777")
_USER_ID = uuid.UUID("44444444-5555-6666-7777-888888888888")


def _make_enrollment(
    *,
    enrollment_id: uuid.UUID = _ENROLLMENT_ID,
    student_id: uuid.UUID = _STUDENT_ID,
    course_id: uuid.UUID = _COURSE_ID,
    status: EnrollmentStatusEnum = EnrollmentStatusEnum.ACTIVE,
) -> Enrollment:
    """Create an Enrollment instance with sensible defaults."""
    return Enrollment(
        id=enrollment_id,
        student_id=student_id,
        course_id=course_id,
        status=status,
        enrollment_date=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _make_mock_session(stored_objects: dict | None = None):
    """
    Build a mock AsyncSession that stores added objects by type and
    returns them on execute().
    """
    if stored_objects is None:
        stored_objects = {}

    added: list = []

    def _add(obj):
        added.append(obj)
        t = type(obj)
        stored_objects.setdefault(t, []).append(obj)

    async def _execute(stmt, *args, **kwargs):
        result = MagicMock()
        non_audit = [o for o in added if not isinstance(o, AuditLog)]
        result.scalar_one_or_none.return_value = non_audit[-1] if non_audit else None
        result.scalars.return_value.all.return_value = non_audit
        return result

    mock_session = AsyncMock()
    mock_session.add = MagicMock(side_effect=_add)
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=_execute)
    mock_session._added = added
    return mock_session


# ===================================================================
# Create: persists enrollment and registers audit log (Req 1.1, 1.8)
# ===================================================================


class TestCreateEnrollment:
    @pytest.mark.anyio
    async def test_create_persists_enrollment_and_audit_log(self):
        """create() must add an Enrollment + AuditLog and call flush/refresh."""
        session = _make_mock_session()
        repo = EnrollmentRepository(session)

        data = {
            "student_id": _STUDENT_ID,
            "course_id": _COURSE_ID,
        }
        result = await repo.create(data, _USER_ID)

        # Enrollment was persisted
        assert isinstance(result, Enrollment)
        assert result.student_id == _STUDENT_ID
        assert result.course_id == _COURSE_ID

        # session.add called twice: once for Enrollment, once for AuditLog
        assert session.add.call_count == 2
        added_types = [type(c.args[0]) for c in session.add.call_args_list]
        assert Enrollment in added_types
        assert AuditLog in added_types

        # flush called twice (enrollment + audit)
        assert session.flush.await_count == 2
        # refresh called twice (enrollment + audit)
        assert session.refresh.await_count == 2

    @pytest.mark.anyio
    async def test_create_audit_log_has_correct_operation(self):
        """The AuditLog entry must have operation INSERT and table 'enrollments'."""
        session = _make_mock_session()
        repo = EnrollmentRepository(session)

        data = {"student_id": _STUDENT_ID, "course_id": _COURSE_ID}
        await repo.create(data, _USER_ID)

        # Find the AuditLog among added objects
        audit_entries = [
            c.args[0] for c in session.add.call_args_list
            if isinstance(c.args[0], AuditLog)
        ]
        assert len(audit_entries) == 1
        audit = audit_entries[0]
        assert audit.operation == OperationEnum.INSERT
        assert audit.table_name == "enrollments"


# ===================================================================
# get_by_id: returns enrollment or None (Req 2.1)
# ===================================================================


class TestGetById:
    @pytest.mark.anyio
    async def test_get_by_id_returns_enrollment(self):
        """get_by_id() returns the enrollment when it exists."""
        enrollment = _make_enrollment()

        async def _execute(stmt, *args, **kwargs):
            result = MagicMock()
            result.scalar_one_or_none.return_value = enrollment
            return result

        session = _make_mock_session()
        session.execute = AsyncMock(side_effect=_execute)
        repo = EnrollmentRepository(session)

        fetched = await repo.get_by_id(_ENROLLMENT_ID)
        assert fetched is not None
        assert fetched.id == _ENROLLMENT_ID
        assert fetched.student_id == _STUDENT_ID
        assert fetched.course_id == _COURSE_ID

    @pytest.mark.anyio
    async def test_get_by_id_returns_none_when_not_found(self):
        """get_by_id() returns None for a non-existent ID."""
        async def _execute(stmt, *args, **kwargs):
            result = MagicMock()
            result.scalar_one_or_none.return_value = None
            return result

        session = _make_mock_session()
        session.execute = AsyncMock(side_effect=_execute)
        repo = EnrollmentRepository(session)

        fetched = await repo.get_by_id(uuid.uuid4())
        assert fetched is None


# ===================================================================
# update_course: changes course_id and registers audit log (Req 2.1, 2.6)
# ===================================================================


class TestUpdateCourse:
    @pytest.mark.anyio
    async def test_update_course_changes_course_id(self):
        """update_course() must change course_id and return updated enrollment."""
        enrollment = _make_enrollment()

        call_count = 0

        async def _execute(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                # get_by_id lookup
                result.scalar_one_or_none.return_value = enrollment
            else:
                result.scalar_one_or_none.return_value = None
            return result

        session = _make_mock_session()
        session.execute = AsyncMock(side_effect=_execute)
        repo = EnrollmentRepository(session)

        updated = await repo.update_course(_ENROLLMENT_ID, _NEW_COURSE_ID, _USER_ID)

        assert updated is not None
        assert updated.course_id == _NEW_COURSE_ID

    @pytest.mark.anyio
    async def test_update_course_registers_audit_log(self):
        """update_course() must register an UPDATE audit log with previous and new data."""
        enrollment = _make_enrollment()

        call_count = 0

        async def _execute(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = enrollment
            else:
                result.scalar_one_or_none.return_value = None
            return result

        session = _make_mock_session()
        session.execute = AsyncMock(side_effect=_execute)
        repo = EnrollmentRepository(session)

        await repo.update_course(_ENROLLMENT_ID, _NEW_COURSE_ID, _USER_ID)

        audit_entries = [
            c.args[0] for c in session.add.call_args_list
            if isinstance(c.args[0], AuditLog)
        ]
        assert len(audit_entries) == 1
        audit = audit_entries[0]
        assert audit.operation == OperationEnum.UPDATE
        assert audit.table_name == "enrollments"

    @pytest.mark.anyio
    async def test_update_course_returns_none_when_not_found(self):
        """update_course() returns None when enrollment doesn't exist."""
        async def _execute(stmt, *args, **kwargs):
            result = MagicMock()
            result.scalar_one_or_none.return_value = None
            return result

        session = _make_mock_session()
        session.execute = AsyncMock(side_effect=_execute)
        repo = EnrollmentRepository(session)

        updated = await repo.update_course(uuid.uuid4(), _NEW_COURSE_ID, _USER_ID)
        assert updated is None


# ===================================================================
# update_status: changes status and registers audit log (Req 3.1, 3.3)
# ===================================================================


class TestUpdateStatus:
    @pytest.mark.anyio
    async def test_update_status_changes_status(self):
        """update_status() must change status and return updated enrollment."""
        enrollment = _make_enrollment(status=EnrollmentStatusEnum.ACTIVE)

        call_count = 0

        async def _execute(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = enrollment
            else:
                result.scalar_one_or_none.return_value = None
            return result

        session = _make_mock_session()
        session.execute = AsyncMock(side_effect=_execute)
        repo = EnrollmentRepository(session)

        updated = await repo.update_status(
            _ENROLLMENT_ID, EnrollmentStatusEnum.CANCELLED, _USER_ID
        )

        assert updated is not None
        assert updated.status == EnrollmentStatusEnum.CANCELLED

    @pytest.mark.anyio
    async def test_update_status_registers_audit_log(self):
        """update_status() must register an UPDATE audit log with previous and new status."""
        enrollment = _make_enrollment(status=EnrollmentStatusEnum.ACTIVE)

        call_count = 0

        async def _execute(stmt, *args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            if call_count == 1:
                result.scalar_one_or_none.return_value = enrollment
            else:
                result.scalar_one_or_none.return_value = None
            return result

        session = _make_mock_session()
        session.execute = AsyncMock(side_effect=_execute)
        repo = EnrollmentRepository(session)

        await repo.update_status(
            _ENROLLMENT_ID, EnrollmentStatusEnum.CANCELLED, _USER_ID
        )

        audit_entries = [
            c.args[0] for c in session.add.call_args_list
            if isinstance(c.args[0], AuditLog)
        ]
        assert len(audit_entries) == 1
        audit = audit_entries[0]
        assert audit.operation == OperationEnum.UPDATE
        assert audit.table_name == "enrollments"

    @pytest.mark.anyio
    async def test_update_status_returns_none_when_not_found(self):
        """update_status() returns None when enrollment doesn't exist."""
        async def _execute(stmt, *args, **kwargs):
            result = MagicMock()
            result.scalar_one_or_none.return_value = None
            return result

        session = _make_mock_session()
        session.execute = AsyncMock(side_effect=_execute)
        repo = EnrollmentRepository(session)

        updated = await repo.update_status(
            uuid.uuid4(), EnrollmentStatusEnum.CANCELLED, _USER_ID
        )
        assert updated is None


# ===================================================================
# list_by_student: returns filtered results (Req 1.1, 3.1)
# ===================================================================


class TestListByStudent:
    @pytest.mark.anyio
    async def test_list_by_student_returns_all_when_no_status_filter(self):
        """list_by_student() without status returns all enrollments for the student."""
        e1 = _make_enrollment(status=EnrollmentStatusEnum.ACTIVE)
        e2 = _make_enrollment(
            enrollment_id=uuid.uuid4(), status=EnrollmentStatusEnum.CANCELLED
        )

        async def _execute(stmt, *args, **kwargs):
            result = MagicMock()
            result.scalars.return_value.all.return_value = [e1, e2]
            return result

        session = _make_mock_session()
        session.execute = AsyncMock(side_effect=_execute)
        repo = EnrollmentRepository(session)

        enrollments = await repo.list_by_student(_STUDENT_ID)
        assert len(enrollments) == 2

    @pytest.mark.anyio
    async def test_list_by_student_with_status_filter(self):
        """list_by_student() with status=ACTIVE returns only active enrollments."""
        e_active = _make_enrollment(status=EnrollmentStatusEnum.ACTIVE)

        async def _execute(stmt, *args, **kwargs):
            result = MagicMock()
            result.scalars.return_value.all.return_value = [e_active]
            return result

        session = _make_mock_session()
        session.execute = AsyncMock(side_effect=_execute)
        repo = EnrollmentRepository(session)

        enrollments = await repo.list_by_student(
            _STUDENT_ID, status=EnrollmentStatusEnum.ACTIVE
        )
        assert len(enrollments) == 1
        assert enrollments[0].status == EnrollmentStatusEnum.ACTIVE

    @pytest.mark.anyio
    async def test_list_by_student_returns_empty_list(self):
        """list_by_student() returns empty list when no enrollments exist."""
        async def _execute(stmt, *args, **kwargs):
            result = MagicMock()
            result.scalars.return_value.all.return_value = []
            return result

        session = _make_mock_session()
        session.execute = AsyncMock(side_effect=_execute)
        repo = EnrollmentRepository(session)

        enrollments = await repo.list_by_student(uuid.uuid4())
        assert enrollments == []

    @pytest.mark.anyio
    async def test_list_by_student_calls_execute(self):
        """list_by_student() must call session.execute with a SELECT statement."""
        async def _execute(stmt, *args, **kwargs):
            result = MagicMock()
            result.scalars.return_value.all.return_value = []
            return result

        session = _make_mock_session()
        session.execute = AsyncMock(side_effect=_execute)
        repo = EnrollmentRepository(session)

        await repo.list_by_student(_STUDENT_ID, status=EnrollmentStatusEnum.ACTIVE)
        session.execute.assert_awaited_once()


# ===================================================================
# list_by_student_filtered_by_professor: status filter + RB-04 (Req 3.1, 3.4)
# ===================================================================

_PROFESSOR_ID = uuid.UUID("55555555-6666-7777-8888-999999999999")


class TestListByStudentFilteredByProfessor:
    @pytest.mark.anyio
    async def test_with_explicit_status_filter(self):
        """list_by_student_filtered_by_professor() with status returns only that status."""
        e_completed = _make_enrollment(status=EnrollmentStatusEnum.COMPLETED)

        async def _execute(stmt, *args, **kwargs):
            result = MagicMock()
            result.scalars.return_value.all.return_value = [e_completed]
            return result

        session = _make_mock_session()
        session.execute = AsyncMock(side_effect=_execute)
        repo = EnrollmentRepository(session)

        enrollments = await repo.list_by_student_filtered_by_professor(
            _STUDENT_ID, _PROFESSOR_ID, status=EnrollmentStatusEnum.COMPLETED
        )

        assert len(enrollments) == 1
        assert enrollments[0].status == EnrollmentStatusEnum.COMPLETED
        session.execute.assert_awaited_once()

    @pytest.mark.anyio
    async def test_without_status_filter_returns_all_statuses(self):
        """list_by_student_filtered_by_professor() without status returns all statuses."""
        e_active = _make_enrollment(status=EnrollmentStatusEnum.ACTIVE)
        e_completed = _make_enrollment(
            enrollment_id=uuid.uuid4(), status=EnrollmentStatusEnum.COMPLETED
        )
        e_cancelled = _make_enrollment(
            enrollment_id=uuid.uuid4(), status=EnrollmentStatusEnum.CANCELLED
        )

        async def _execute(stmt, *args, **kwargs):
            result = MagicMock()
            result.scalars.return_value.all.return_value = [
                e_active, e_completed, e_cancelled
            ]
            return result

        session = _make_mock_session()
        session.execute = AsyncMock(side_effect=_execute)
        repo = EnrollmentRepository(session)

        enrollments = await repo.list_by_student_filtered_by_professor(
            _STUDENT_ID, _PROFESSOR_ID
        )

        assert len(enrollments) == 3
        statuses = {e.status for e in enrollments}
        assert EnrollmentStatusEnum.ACTIVE in statuses
        assert EnrollmentStatusEnum.COMPLETED in statuses
        assert EnrollmentStatusEnum.CANCELLED in statuses
        session.execute.assert_awaited_once()

    @pytest.mark.anyio
    async def test_applies_professor_course_filter(self):
        """list_by_student_filtered_by_professor() calls execute (RB-04 join is in the query)."""
        async def _execute(stmt, *args, **kwargs):
            result = MagicMock()
            result.scalars.return_value.all.return_value = []
            return result

        session = _make_mock_session()
        session.execute = AsyncMock(side_effect=_execute)
        repo = EnrollmentRepository(session)

        enrollments = await repo.list_by_student_filtered_by_professor(
            _STUDENT_ID, _PROFESSOR_ID, status=EnrollmentStatusEnum.ACTIVE
        )

        assert enrollments == []
        session.execute.assert_awaited_once()
        # Verify the SQL statement was built with the correct structure
        # by inspecting the compiled query contains the expected clauses
        executed_stmt = session.execute.call_args[0][0]
        compiled = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
        # Must JOIN courses table (RB-04 professor filter)
        assert "courses" in compiled.lower()
        # Must filter by student_id and professor_id
        assert "student_id" in compiled.lower()
        assert "professor_id" in compiled.lower()
