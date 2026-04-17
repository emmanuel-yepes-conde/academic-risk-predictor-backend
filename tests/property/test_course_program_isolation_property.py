# Feature: multi-university-support, Property 8: Aislamiento de cursos por programa
"""
Property-based test for course isolation by program.

Verifies that GET /api/v1/programs/{program_id}/courses returns ONLY courses
whose program_id matches the requested program. Courses belonging to other
programs must never appear in the response, regardless of how many programs
and courses exist in the system.

**Validates: Requirements 3.4, 6.3**
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
from app.main import app

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate 2–5 program IDs to distribute courses across
program_ids_strategy = st.lists(
    st.uuids(), min_size=2, max_size=5, unique=True,
)

# Assignments: each element is an index into the program_ids list
assignments_strategy = st.lists(
    st.integers(min_value=0, max_value=100), min_size=0, max_size=20,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_courses(
    program_ids: list[uuid.UUID],
    assignments: list[int],
) -> list[Course]:
    """
    Build Course ORM objects, each assigned to the program at the given
    index in program_ids.
    """
    now = datetime.now(timezone.utc)
    courses: list[Course] = []
    for i, prog_idx in enumerate(assignments):
        pid = program_ids[prog_idx % len(program_ids)]
        courses.append(
            Course(
                id=uuid.uuid4(),
                code=f"CRS-{i:04d}",
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


def _make_mock_session(all_courses: list[Course]) -> AsyncMock:
    """
    Return a mock AsyncSession that simulates the query used by
    CourseRepository.listar_por_programa.

    The repository executes:
        SELECT * FROM courses WHERE program_id = :pid

    We intercept execute() and filter the in-memory course list by the
    program_id extracted from the compiled statement parameters.
    """
    mock_session = AsyncMock()

    async def _execute(stmt, *args, **kwargs):
        # Extract the program_id from the statement's bound parameters
        target_pid = None
        try:
            compiled = stmt.compile(compile_kwargs={"literal_binds": False})
            for param_value in compiled.params.values():
                if isinstance(param_value, uuid.UUID):
                    target_pid = param_value
                    break
        except Exception:
            pass

        # Filter courses by program_id
        if target_pid is not None:
            filtered = [c for c in all_courses if c.program_id == target_pid]
        else:
            filtered = all_courses

        result = MagicMock()
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=filtered)
        result.scalars = MagicMock(return_value=scalars_mock)
        return result

    mock_session.execute = AsyncMock(side_effect=_execute)
    return mock_session


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    program_ids=program_ids_strategy,
    assignments=assignments_strategy,
)
async def test_courses_isolated_by_program(
    program_ids: list[uuid.UUID],
    assignments: list[int],
):
    """
    Property 8: Aislamiento de cursos por programa.

    For any set of programs and any distribution of courses across them,
    GET /api/v1/programs/{P.id}/courses must return ONLY courses whose
    program_id equals P.id. It must never return courses belonging to a
    different program.

    We verify this for every program in the generated set:
      - Every returned course has the correct program_id
      - The count of returned courses matches the expected count
      - No course from another program leaks into the response

    **Validates: Requirements 3.4, 6.3**
    """
    all_courses = _build_courses(program_ids, assignments)
    mock_session = _make_mock_session(all_courses)

    async def _override_get_session():
        yield mock_session

    app.dependency_overrides[get_session] = _override_get_session

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            for pid in program_ids:
                # Expected courses for this program
                expected = [c for c in all_courses if c.program_id == pid]

                resp = await client.get(f"/api/v1/programs/{pid}/courses")

                assert resp.status_code == 200, (
                    f"Expected 200 for program {pid}, got {resp.status_code}: "
                    f"{resp.text}"
                )

                returned_data = resp.json()

                # --- Count must match expected ---
                assert len(returned_data) == len(expected), (
                    f"Program {pid}: count mismatch — "
                    f"expected {len(expected)}, got {len(returned_data)}"
                )

                # --- Every returned course must belong to this program ---
                expected_ids = {str(c.id) for c in expected}
                returned_ids = {c["id"] for c in returned_data}
                assert returned_ids == expected_ids, (
                    f"Program {pid}: course ID mismatch — "
                    f"missing={expected_ids - returned_ids}, "
                    f"extra={returned_ids - expected_ids}"
                )
    finally:
        app.dependency_overrides.clear()
