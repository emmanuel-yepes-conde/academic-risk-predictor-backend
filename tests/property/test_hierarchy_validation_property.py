# Feature: multi-university-support, Property 9: Validación jerárquica universidad→programa→cursos
"""
Property-based test for hierarchical validation university→program→courses.

Verifies that GET /api/v1/universities/{university_id}/programs/{program_id}/courses
returns courses ONLY when the program belongs to the specified university. When the
program does NOT belong to the university, the endpoint must return 404 Not Found.

**Validates: Requirements 3.5, 6.3**
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st
from httpx import ASGITransport, AsyncClient

from app.infrastructure.database import get_session
from app.infrastructure.models.course import Course
from app.infrastructure.models.program import Program
from app.main import app

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate 2–4 university IDs
university_ids_strategy = st.lists(
    st.uuids(), min_size=2, max_size=4, unique=True,
)

# Generate 2–6 program IDs
program_ids_strategy = st.lists(
    st.uuids(), min_size=2, max_size=6, unique=True,
)

# Assignments: each element is an index into the university_ids list
program_assignments_strategy = st.lists(
    st.integers(min_value=0, max_value=100), min_size=2, max_size=6,
)

# Course assignments: each element is an index into the program list
course_assignments_strategy = st.lists(
    st.integers(min_value=0, max_value=100), min_size=0, max_size=15,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_programs(
    program_ids: list[uuid.UUID],
    university_ids: list[uuid.UUID],
    assignments: list[int],
) -> list[Program]:
    """Build Program ORM objects, each assigned to a university."""
    now = datetime.now(timezone.utc)
    programs: list[Program] = []
    for i, pid in enumerate(program_ids):
        # Use the assignment index (mod len) to pick a university
        uni_idx = assignments[i % len(assignments)] % len(university_ids)
        programs.append(
            Program(
                id=pid,
                campus_id=uuid.uuid4(),
                university_id=university_ids[uni_idx],
                institution=f"INST-{i}",
                degree_type="PREG",
                program_code=f"P{i:04d}",
                program_name=f"Program {i}",
                pensum=f"PEN{i:04d}",
                academic_group=f"GRP{i}",
                location=f"LOC-{i}",
                snies_code=2000 + i,
                created_at=now,
            )
        )
    return programs


def _build_courses(
    programs: list[Program],
    assignments: list[int],
) -> list[Course]:
    """Build Course ORM objects, each assigned to a program."""
    now = datetime.now(timezone.utc)
    courses: list[Course] = []
    for i, prog_idx in enumerate(assignments):
        pid = programs[prog_idx % len(programs)].id
        courses.append(
            Course(
                id=uuid.uuid4(),
                code=f"CRS-H{i:04d}",
                name=f"Course {i}",
                credits=3,
                academic_period="2025-1",
                program_id=pid,
                created_at=now,
            )
        )
    return courses


# ---------------------------------------------------------------------------
# Mock session helper
# ---------------------------------------------------------------------------


def _make_mock_session(
    all_programs: list[Program],
    all_courses: list[Course],
) -> AsyncMock:
    """
    Return a mock AsyncSession that simulates the queries used by the
    list_courses_by_university_and_program endpoint.

    The endpoint executes two queries:
      1. SELECT Program WHERE id = :program_id AND university_id = :university_id
         → returns Program or None (for 404 check)
      2. SELECT Course JOIN Program WHERE Program.id = :pid AND Program.university_id = :uid
         → returns filtered courses (via CourseRepository.listar_por_universidad_y_programa)
    """
    mock_session = AsyncMock()
    call_count = 0

    async def _execute(stmt, *args, **kwargs):
        nonlocal call_count
        call_count += 1

        # Extract UUID parameters from the compiled statement
        target_uuids: list[uuid.UUID] = []
        try:
            compiled = stmt.compile(compile_kwargs={"literal_binds": False})
            for param_value in compiled.params.values():
                if isinstance(param_value, uuid.UUID):
                    target_uuids.append(param_value)
        except Exception:
            pass

        sql_text = str(stmt).lower()
        result = MagicMock()

        # Detect whether this is the Program validation query or the Course query
        if "courses" in sql_text:
            # This is the Course query (via CourseRepository.listar_por_universidad_y_programa)
            # It joins Course with Program and filters by program_id AND university_id
            # Find matching courses: program must belong to the university
            matching_courses: list[Course] = []
            for course in all_courses:
                # Find the program for this course
                course_program = next(
                    (p for p in all_programs if p.id == course.program_id), None
                )
                if course_program is None:
                    continue
                # Check if both UUIDs match (program_id and university_id)
                if (
                    course_program.id in target_uuids
                    and course_program.university_id in target_uuids
                ):
                    matching_courses.append(course)

            scalars_mock = MagicMock()
            scalars_mock.all = MagicMock(return_value=matching_courses)
            result.scalars = MagicMock(return_value=scalars_mock)
        else:
            # This is the Program validation query
            # Find a program matching both program_id and university_id
            matched_program = None
            for p in all_programs:
                if p.id in target_uuids and p.university_id in target_uuids:
                    matched_program = p
                    break
            result.scalar_one_or_none = MagicMock(return_value=matched_program)

        return result

    mock_session.execute = AsyncMock(side_effect=_execute)
    return mock_session


# ---------------------------------------------------------------------------
# Property test — valid hierarchy returns courses
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    university_ids=university_ids_strategy,
    program_ids=program_ids_strategy,
    program_assignments=program_assignments_strategy,
    course_assignments=course_assignments_strategy,
)
async def test_valid_hierarchy_returns_correct_courses(
    university_ids: list[uuid.UUID],
    program_ids: list[uuid.UUID],
    program_assignments: list[int],
    course_assignments: list[int],
):
    """
    Property 9 (positive case): Validación jerárquica universidad→programa→cursos.

    For any (university_id, program_id) pair where the program DOES belong to
    the university, the endpoint must return exactly the courses belonging to
    that program — no more, no fewer.

    **Validates: Requirements 3.5, 6.3**
    """
    programs = _build_programs(program_ids, university_ids, program_assignments)
    courses = _build_courses(programs, course_assignments)
    mock_session = _make_mock_session(programs, courses)

    async def _override_get_session():
        yield mock_session

    app.dependency_overrides[get_session] = _override_get_session

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            for program in programs:
                uid = program.university_id
                pid = program.id

                # Expected courses for this program
                expected_courses = [c for c in courses if c.program_id == pid]

                resp = await client.get(
                    f"/api/v1/universities/{uid}/programs/{pid}/courses"
                )

                assert resp.status_code == 200, (
                    f"Expected 200 for valid hierarchy "
                    f"university={uid}, program={pid}, "
                    f"got {resp.status_code}: {resp.text}"
                )

                returned_data = resp.json()

                # --- Count must match ---
                assert len(returned_data) == len(expected_courses), (
                    f"University {uid}, Program {pid}: count mismatch — "
                    f"expected {len(expected_courses)}, got {len(returned_data)}"
                )

                # --- Returned course IDs must match expected ---
                expected_ids = {str(c.id) for c in expected_courses}
                returned_ids = {c["id"] for c in returned_data}
                assert returned_ids == expected_ids, (
                    f"University {uid}, Program {pid}: course ID mismatch — "
                    f"missing={expected_ids - returned_ids}, "
                    f"extra={returned_ids - expected_ids}"
                )
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Property test — invalid hierarchy returns 404
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    university_ids=university_ids_strategy,
    program_ids=program_ids_strategy,
    program_assignments=program_assignments_strategy,
    course_assignments=course_assignments_strategy,
)
async def test_invalid_hierarchy_returns_404(
    university_ids: list[uuid.UUID],
    program_ids: list[uuid.UUID],
    program_assignments: list[int],
    course_assignments: list[int],
):
    """
    Property 9 (negative case): Validación jerárquica universidad→programa→cursos.

    For any (university_id, program_id) pair where the program does NOT belong
    to the university, the endpoint must return 404 Not Found. This guarantees
    that the hierarchical validation is enforced and cross-university access
    to courses is impossible.

    **Validates: Requirements 3.5, 6.3**
    """
    programs = _build_programs(program_ids, university_ids, program_assignments)
    courses = _build_courses(programs, course_assignments)
    mock_session = _make_mock_session(programs, courses)

    # Build a set of invalid (university_id, program_id) pairs:
    # pairs where the program does NOT belong to the university
    invalid_pairs: list[tuple[uuid.UUID, uuid.UUID]] = []
    for program in programs:
        for uid in university_ids:
            if uid != program.university_id:
                invalid_pairs.append((uid, program.id))

    if not invalid_pairs:
        # All programs belong to the same university — skip this iteration
        return

    async def _override_get_session():
        yield mock_session

    app.dependency_overrides[get_session] = _override_get_session

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            for uid, pid in invalid_pairs:
                resp = await client.get(
                    f"/api/v1/universities/{uid}/programs/{pid}/courses"
                )

                assert resp.status_code == 404, (
                    f"Expected 404 for invalid hierarchy "
                    f"university={uid}, program={pid} "
                    f"(program belongs to {next(p.university_id for p in programs if p.id == pid)}), "
                    f"got {resp.status_code}: {resp.text}"
                )

                body = resp.json()
                assert "detail" in body, (
                    f"404 response must include 'detail' field, got: {body}"
                )
    finally:
        app.dependency_overrides.clear()
