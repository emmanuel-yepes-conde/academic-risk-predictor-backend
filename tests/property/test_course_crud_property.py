"""Property tests for the current Course-as-section contract."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import jwt as pyjwt
import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from hypothesis import HealthCheck, given, settings as h_settings
from hypothesis import strategies as st
from pydantic import ValidationError

from app.application.schemas.course import CourseCreate, CourseRead, CourseUpdate
from app.application.services.course_service import CourseService
from app.core.config import settings
from app.domain.enums import CourseStatusEnum, OperationEnum, RoleEnum
from app.infrastructure.database import get_session
from app.infrastructure.models.course import Course
from app.infrastructure.models.subject import Subject
from app.infrastructure.repositories.course_repository import CourseRepository
from app.main import app


_academic_period_strategy = st.from_regex(r"20[2-3][0-9]-[12]", fullmatch=True)
_section_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=8,
).filter(lambda s: s.strip())
_subject_code_strategy = st.from_regex(r"[A-Z]{2,4}[0-9]{3}", fullmatch=True)
_subject_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N", "Zs")),
    min_size=1,
    max_size=80,
).filter(lambda s: s.strip())
_credits_strategy = st.integers(min_value=1, max_value=12)


def _subject(**kwargs) -> Subject:
    defaults = dict(
        id=uuid.uuid4(),
        code="MAT101",
        name="Calculo I",
        credits=4,
        program_id=uuid.uuid4(),
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    return Subject(**defaults)


def _course_read(**kwargs) -> CourseRead:
    defaults = dict(
        id=uuid.uuid4(),
        subject_id=uuid.uuid4(),
        section="A",
        academic_period="2024-1",
        professor_id=None,
        status=CourseStatusEnum.ACTIVE,
        created_at=datetime.now(timezone.utc),
        code="MAT101",
        name="Calculo I",
        credits=4,
        program_id=uuid.uuid4(),
        evaluation_config=None,
    )
    defaults.update(kwargs)
    return CourseRead(**defaults)


class _Result:
    def __init__(self, *, row=None, scalar=None, rows=None, count=None):
        self._row = row
        self._scalar = scalar
        self._rows = rows or []
        self._count = count

    def first(self):
        return self._row

    def scalar_one_or_none(self):
        return self._scalar

    def scalar_one(self):
        return self._count

    def all(self):
        return self._rows


REQUIRED_CREATE_FIELDS = {
    "subject_id": uuid.uuid4(),
    "academic_period": "2024-1",
}


@h_settings(max_examples=50)
@given(
    fields_to_remove=st.lists(
        st.sampled_from(list(REQUIRED_CREATE_FIELDS)),
        min_size=1,
        max_size=len(REQUIRED_CREATE_FIELDS),
        unique=True,
    )
)
def test_course_create_rejects_incomplete_input(fields_to_remove: list[str]):
    incomplete = {
        k: v for k, v in REQUIRED_CREATE_FIELDS.items() if k not in fields_to_remove
    }

    with pytest.raises(ValidationError):
        CourseCreate(**incomplete)


@pytest.mark.anyio
@h_settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(
    subject_id=st.uuids(),
    section=_section_strategy,
    academic_period=_academic_period_strategy,
    code=_subject_code_strategy,
    name=_subject_name_strategy,
    credits=_credits_strategy,
    program_id=st.uuids(),
)
async def test_create_then_get_by_code_roundtrip(
    subject_id: uuid.UUID,
    section: str,
    academic_period: str,
    code: str,
    name: str,
    credits: int,
    program_id: uuid.UUID,
):
    subject = _subject(id=subject_id, code=code, name=name, credits=credits, program_id=program_id)
    store: dict[str, Course] = {}
    session = AsyncMock()

    def add(obj):
        if isinstance(obj, Course):
            store["course"] = obj

    session.add = MagicMock(side_effect=add)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock(
        side_effect=lambda stmt: _Result(row=(store["course"], subject))
    )
    repo = CourseRepository.__new__(CourseRepository)
    repo._session = session
    repo._audit = AsyncMock()
    repo._audit.register = AsyncMock()

    created = await repo.create(
        {
            "subject_id": subject_id,
            "section": section,
            "academic_period": academic_period,
        }
    )
    found = await repo.get_by_code(code)

    assert found is not None
    assert found.id == created.id
    assert found.subject_id == subject_id
    assert found.section == section
    assert found.academic_period == academic_period
    assert found.code == code
    assert found.name == name
    assert found.credits == credits
    assert found.program_id == program_id


def _repo_with_existing(course: Course, subject: Subject):
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    async def execute(stmt):
        text = str(stmt)
        if "JOIN subjects" in text:
            return _Result(row=(course, subject))
        return _Result(scalar=course)

    session.execute = AsyncMock(side_effect=execute)
    repo = CourseRepository.__new__(CourseRepository)
    repo._session = session
    repo._audit = AsyncMock()
    repo._audit.register = AsyncMock()
    return repo


@pytest.mark.anyio
@h_settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(section=_section_strategy, academic_period=_academic_period_strategy)
async def test_create_registers_insert_audit_log(section: str, academic_period: str):
    subject = _subject()
    store: dict[str, Course] = {}
    session = AsyncMock()

    def add(obj):
        if isinstance(obj, Course):
            store["course"] = obj

    session.add = MagicMock(side_effect=add)
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock(
        side_effect=lambda stmt: _Result(row=(store["course"], subject))
    )
    repo = CourseRepository.__new__(CourseRepository)
    repo._session = session
    repo._audit = AsyncMock()
    repo._audit.register = AsyncMock()

    created = await repo.create(
        {"subject_id": subject.id, "section": section, "academic_period": academic_period}
    )

    repo._audit.register.assert_called_once()
    audit_log = repo._audit.register.call_args[0][0]
    assert audit_log.table_name == "courses"
    assert audit_log.operation == OperationEnum.INSERT
    assert audit_log.record_id == created.id


@pytest.mark.anyio
@h_settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(new_section=_section_strategy)
async def test_update_registers_update_audit_log(new_section: str):
    subject = _subject()
    course = Course(subject_id=subject.id, section="A", academic_period="2024-1")
    repo = _repo_with_existing(course, subject)

    result = await repo.update(course.id, CourseUpdate(section=new_section))

    assert result is not None
    repo._audit.register.assert_called_once()
    audit_log = repo._audit.register.call_args[0][0]
    assert audit_log.table_name == "courses"
    assert audit_log.operation == OperationEnum.UPDATE
    assert audit_log.record_id == course.id
    assert audit_log.new_data == {"section": new_section}


@pytest.mark.anyio
@h_settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
@given(new_status=st.sampled_from(list(CourseStatusEnum)))
async def test_update_status_registers_update_audit_log(new_status: CourseStatusEnum):
    subject = _subject()
    initial_status = (
        CourseStatusEnum.INACTIVE
        if new_status == CourseStatusEnum.ACTIVE
        else CourseStatusEnum.ACTIVE
    )
    course = Course(
        subject_id=subject.id,
        section="A",
        academic_period="2024-1",
        status=initial_status,
    )
    repo = _repo_with_existing(course, subject)

    result = await repo.update_status(course.id, new_status)

    assert result is not None
    repo._audit.register.assert_called_once()
    audit_log = repo._audit.register.call_args[0][0]
    assert audit_log.table_name == "courses"
    assert audit_log.operation == OperationEnum.UPDATE
    assert audit_log.previous_data == {"status": initial_status}
    assert audit_log.new_data == {"status": new_status}


@pytest.mark.anyio
@h_settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(
    statuses=st.lists(st.sampled_from(list(CourseStatusEnum)), min_size=1, max_size=20),
    filter_status=st.sampled_from(list(CourseStatusEnum)),
)
async def test_list_and_count_filter_by_status_consistently(
    statuses: list[CourseStatusEnum],
    filter_status: CourseStatusEnum,
):
    subject = _subject()
    rows = [
        (
            Course(subject_id=subject.id, section=f"S{i}", academic_period="2024-1", status=status),
            subject,
        )
        for i, status in enumerate(statuses)
        if status == filter_status
    ]
    session = AsyncMock()

    async def execute(stmt):
        if "count" in str(stmt).lower():
            return _Result(count=len(rows))
        return _Result(rows=rows)

    session.execute = AsyncMock(side_effect=execute)
    repo = CourseRepository.__new__(CourseRepository)
    repo._session = session
    repo._audit = AsyncMock()

    listed = await repo.list_all(skip=0, limit=1000, status=filter_status)
    counted = await repo.count_all(status=filter_status)

    assert len(listed) == counted == len(rows)
    assert all(course.status == filter_status for course in listed)


@pytest.mark.anyio
@h_settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(section=_section_strategy, academic_period=_academic_period_strategy)
async def test_create_course_delegates_to_repository(section: str, academic_period: str):
    subject_id = uuid.uuid4()
    repo = AsyncMock()
    repo.create = AsyncMock(
        return_value=_course_read(
            subject_id=subject_id,
            section=section,
            academic_period=academic_period,
        )
    )
    service = CourseService(repo)

    result = await service.create_course(
        CourseCreate(subject_id=subject_id, section=section, academic_period=academic_period)
    )

    assert result.subject_id == subject_id
    assert result.section == section
    repo.create.assert_awaited_once()


@pytest.mark.anyio
@h_settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
@given(
    section=_section_strategy,
    academic_period=_academic_period_strategy,
    professor_id=st.one_of(st.none(), st.uuids()),
)
async def test_partial_update_preserves_omitted_fields(
    section: str,
    academic_period: str,
    professor_id: uuid.UUID | None,
):
    original = _course_read(section="A", academic_period="2024-1", professor_id=None)
    updated = original.model_copy(
        update={
            "section": section,
            "academic_period": academic_period,
            "professor_id": professor_id,
        }
    )
    repo = AsyncMock()
    repo.update = AsyncMock(return_value=updated)
    service = CourseService(repo)

    result = await service.update_course(
        original.id,
        CourseUpdate(
            section=section,
            academic_period=academic_period,
            professor_id=professor_id,
        ),
    )

    assert result.id == original.id
    assert result.subject_id == original.subject_id
    assert result.section == section
    assert result.academic_period == academic_period
    assert result.professor_id == professor_id
    assert result.code == original.code


def _create_access_token_for_role(role: RoleEnum) -> str:
    uid = uuid.uuid4()
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(uid),
        "role": role.value,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=30)).timestamp()),
    }
    return pyjwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


@pytest.mark.anyio
@h_settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
@given(role=st.sampled_from([r for r in RoleEnum if r != RoleEnum.ADMIN]))
async def test_non_admin_rejected_on_write_endpoints(role: RoleEnum):
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
            resp_post = await client.post(
                "/api/v1/courses",
                json={
                    "subject_id": str(uuid.uuid4()),
                    "section": "A",
                    "academic_period": "2024-1",
                },
                headers=headers,
            )
            assert resp_post.status_code == 403

            resp_patch = await client.patch(
                f"/api/v1/courses/{course_id}",
                json={"section": "B"},
                headers=headers,
            )
            assert resp_patch.status_code == 403

            resp_status = await client.patch(
                f"/api/v1/courses/{course_id}/status",
                json={"status": "INACTIVE"},
                headers=headers,
            )
            assert resp_status.status_code == 403
    finally:
        app.dependency_overrides.clear()
