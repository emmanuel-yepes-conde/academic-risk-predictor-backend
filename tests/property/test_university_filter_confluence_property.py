# Feature: multi-university-support, Property 15: Confluencia del filtro por universidad
"""
Property-based test for university filter confluence.

Verifies that for any university U, the set of courses obtained via the
hierarchical endpoint GET /api/v1/universities/{U}/programs/{P}/courses
is identical to the set obtained by filtering all courses whose program
belongs to U via GET /api/v1/programs/{P}/courses.

In other words, the order in which hierarchy filters are applied must not
affect the result. Filtering by university first and then by program must
yield the same courses as filtering by program directly — provided the
program belongs to that university.

**Validates: Requirements 6.4**
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
    st.integers(min_value=0, max_value=100), min_size=1, max_size=15,
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
                snies_code=3000 + i,
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
                code=f"CRS-CF{i:04d}",
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
    Return a mock AsyncSession that simulates the queries used by both:

    1. GET /programs/{program_id}/courses
       → CourseRepository.listar_por_programa(program_id)
       → SELECT Course WHERE program_id = :pid

    2. GET /universities/{uid}/programs/{pid}/courses
       → First: SELECT Program WHERE id = :pid AND university_id = :uid
       → Then: CourseRepository.listar_por_universidad_y_programa(uid, pid)
       → SELECT Course JOIN Program WHERE Program.id = :pid AND Program.university_id = :uid

    We distinguish queries by inspecting the SQL text for table references.
    """
    mock_session = AsyncMock()

    async def _execute(stmt, *args, **kwargs):
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

        if "courses" in sql_text and "programs" in sql_text:
            # Query 2b: Course JOIN Program (listar_por_universidad_y_programa)
            # Filters by both program_id and university_id
            matching_courses: list[Course] = []
            for course in all_courses:
                course_program = next(
                    (p for p in all_programs if p.id == course.program_id), None
                )
                if course_program is None:
                    continue
                if (
                    course_program.id in target_uuids
                    and course_program.university_id in target_uuids
                ):
                    matching_courses.append(course)

            scalars_mock = MagicMock()
            scalars_mock.all = MagicMock(return_value=matching_courses)
            result.scalars = MagicMock(return_value=scalars_mock)

        elif "courses" in sql_text:
            # Query 1: Simple course filter by program_id (listar_por_programa)
            # Only one UUID param: the program_id
            target_pid = target_uuids[0] if target_uuids else None
            filtered = (
                [c for c in all_courses if c.program_id == target_pid]
                if target_pid
                else all_courses
            )
            scalars_mock = MagicMock()
            scalars_mock.all = MagicMock(return_value=filtered)
            result.scalars = MagicMock(return_value=scalars_mock)

        else:
            # Query 2a: Program validation (SELECT Program WHERE id AND university_id)
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
# Property test — confluence of university filter
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
async def test_university_filter_confluence(
    university_ids: list[uuid.UUID],
    program_ids: list[uuid.UUID],
    program_assignments: list[int],
    course_assignments: list[int],
):
    """
    Property 15: Confluencia del filtro por universidad.

    For any university U and any program P that belongs to U, the set of
    courses returned by:

        GET /api/v1/universities/{U}/programs/{P}/courses

    must be IDENTICAL to the set returned by:

        GET /api/v1/programs/{P}/courses

    This guarantees that the order of applying hierarchy filters does not
    affect the result — filtering by university first and then by program
    yields the same courses as filtering by program alone (when the program
    belongs to that university).

    **Validates: Requirements 6.4**
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

                # Path A: hierarchical route (university → program → courses)
                resp_hierarchical = await client.get(
                    f"/api/v1/universities/{uid}/programs/{pid}/courses"
                )
                assert resp_hierarchical.status_code == 200, (
                    f"Hierarchical route failed for university={uid}, "
                    f"program={pid}: {resp_hierarchical.status_code} "
                    f"{resp_hierarchical.text}"
                )
                courses_hierarchical = resp_hierarchical.json()

                # Path B: flat route (program → courses)
                resp_flat = await client.get(
                    f"/api/v1/programs/{pid}/courses"
                )
                assert resp_flat.status_code == 200, (
                    f"Flat route failed for program={pid}: "
                    f"{resp_flat.status_code} {resp_flat.text}"
                )
                courses_flat = resp_flat.json()

                # --- The two sets of course IDs must be identical ---
                ids_hierarchical = {c["id"] for c in courses_hierarchical}
                ids_flat = {c["id"] for c in courses_flat}

                assert ids_hierarchical == ids_flat, (
                    f"Confluence violation for university={uid}, program={pid}: "
                    f"hierarchical route returned {len(ids_hierarchical)} courses, "
                    f"flat route returned {len(ids_flat)} courses. "
                    f"Only in hierarchical={ids_hierarchical - ids_flat}, "
                    f"only in flat={ids_flat - ids_hierarchical}"
                )

                # --- Counts must match ---
                assert len(courses_hierarchical) == len(courses_flat), (
                    f"Confluence count mismatch for university={uid}, "
                    f"program={pid}: hierarchical={len(courses_hierarchical)}, "
                    f"flat={len(courses_flat)}"
                )

                # --- Each course's fields must match between both responses ---
                hierarchical_by_id = {c["id"]: c for c in courses_hierarchical}
                flat_by_id = {c["id"]: c for c in courses_flat}

                for course_id in ids_hierarchical:
                    h_course = hierarchical_by_id[course_id]
                    f_course = flat_by_id[course_id]
                    assert h_course == f_course, (
                        f"Confluence field mismatch for course {course_id} "
                        f"(university={uid}, program={pid}): "
                        f"hierarchical={h_course}, flat={f_course}"
                    )
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Property test — aggregate confluence across all programs of a university
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
async def test_university_filter_aggregate_confluence(
    university_ids: list[uuid.UUID],
    program_ids: list[uuid.UUID],
    program_assignments: list[int],
    course_assignments: list[int],
):
    """
    Property 15 (aggregate case): Confluencia del filtro por universidad.

    For any university U, the UNION of courses obtained by querying
    GET /api/v1/universities/{U}/programs/{P}/courses for every program P
    belonging to U must be identical to the UNION of courses obtained by
    querying GET /api/v1/programs/{P}/courses for those same programs.

    This verifies that the university filter is confluent at the aggregate
    level — no courses are gained or lost when the university filter is
    applied across the entire hierarchy.

    **Validates: Requirements 6.4**
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
            for uid in university_ids:
                # Programs belonging to this university
                uni_programs = [p for p in programs if p.university_id == uid]

                # Expected courses: all courses whose program belongs to U
                expected_course_ids = {
                    str(c.id)
                    for c in courses
                    if any(p.id == c.program_id for p in uni_programs)
                }

                # Collect courses via hierarchical route
                hierarchical_ids: set[str] = set()
                for program in uni_programs:
                    resp = await client.get(
                        f"/api/v1/universities/{uid}/programs/{program.id}/courses"
                    )
                    assert resp.status_code == 200
                    for c in resp.json():
                        hierarchical_ids.add(c["id"])

                # Collect courses via flat route
                flat_ids: set[str] = set()
                for program in uni_programs:
                    resp = await client.get(
                        f"/api/v1/programs/{program.id}/courses"
                    )
                    assert resp.status_code == 200
                    for c in resp.json():
                        flat_ids.add(c["id"])

                # All three sets must be identical
                assert hierarchical_ids == expected_course_ids, (
                    f"University {uid}: hierarchical aggregate mismatch. "
                    f"Only in hierarchical={hierarchical_ids - expected_course_ids}, "
                    f"missing={expected_course_ids - hierarchical_ids}"
                )

                assert flat_ids == expected_course_ids, (
                    f"University {uid}: flat aggregate mismatch. "
                    f"Only in flat={flat_ids - expected_course_ids}, "
                    f"missing={expected_course_ids - flat_ids}"
                )

                assert hierarchical_ids == flat_ids, (
                    f"University {uid}: confluence violation at aggregate level. "
                    f"Only in hierarchical={hierarchical_ids - flat_ids}, "
                    f"only in flat={flat_ids - hierarchical_ids}"
                )
    finally:
        app.dependency_overrides.clear()
