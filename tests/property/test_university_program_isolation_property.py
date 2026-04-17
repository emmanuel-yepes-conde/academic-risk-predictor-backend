# Feature: multi-university-support, Property 6: Aislamiento de programas por universidad
"""
Property-based test for program isolation by university.

Verifies that GET /api/v1/universities/{university_id}/programs returns
ONLY programs whose university_id matches the requested university. Programs
belonging to other universities must never appear in the response, regardless
of how many universities and programs exist in the system.

**Validates: Requirements 2.4, 6.1, 6.3**
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st
from httpx import ASGITransport, AsyncClient

from app.infrastructure.database import get_session
from app.infrastructure.models.program import Program
from app.main import app

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Generate 2–5 university IDs to distribute programs across
university_ids_strategy = st.lists(
    st.uuids(), min_size=2, max_size=5, unique=True,
)

# Generate a list of programs, each assigned to a random university
# We use integers as indices into the university_ids list
program_count_strategy = st.integers(min_value=0, max_value=20)


def _build_programs(
    university_ids: list[uuid.UUID],
    assignments: list[int],
) -> list[Program]:
    """
    Build Program ORM objects, each assigned to the university at the
    given index in university_ids.
    """
    now = datetime.now(timezone.utc)
    programs = []
    for i, uni_idx in enumerate(assignments):
        uid = university_ids[uni_idx % len(university_ids)]
        programs.append(
            Program(
                id=uuid.uuid4(),
                campus_id=uuid.uuid4(),
                university_id=uid,
                institution=f"INST-{i}",
                degree_type="PREG",
                program_code=f"P{i:04d}",
                program_name=f"Program {i}",
                pensum=f"PEN{i:04d}",
                academic_group=f"GRP{i}",
                location=f"LOC-{i}",
                snies_code=1000 + i,
                created_at=now,
            )
        )
    return programs


# ---------------------------------------------------------------------------
# Mock session helper
# ---------------------------------------------------------------------------


def _make_mock_session(all_programs: list[Program]):
    """
    Return a mock AsyncSession that simulates the queries used by the
    list_programs_by_university endpoint.

    The endpoint executes two queries:
      1. SELECT count(*) FROM programs WHERE university_id = :uid
      2. SELECT * FROM programs WHERE university_id = :uid OFFSET :skip LIMIT :limit

    We intercept both by inspecting the compiled SQL for the WHERE clause
    and returning the correct filtered subset.
    """
    mock_session = AsyncMock()

    # Track call order to distinguish count vs select queries
    call_count = 0

    async def _execute(stmt, *args, **kwargs):
        nonlocal call_count
        call_count += 1

        # Extract the university_id from the statement's WHERE clause.
        # The endpoint always filters by Program.university_id == <uuid>.
        # We compile the statement to extract bound parameters.
        target_uid = None
        try:
            compiled = stmt.compile(compile_kwargs={"literal_binds": False})
            for param_value in compiled.params.values():
                if isinstance(param_value, uuid.UUID):
                    target_uid = param_value
                    break
        except Exception:
            pass

        # Filter programs by university_id
        if target_uid is not None:
            filtered = [p for p in all_programs if p.university_id == target_uid]
        else:
            filtered = all_programs

        result = MagicMock()

        # The count query uses scalar_one(), the select query uses scalars().all()
        # We detect count queries by checking if the SQL contains "count"
        sql_text = str(stmt)
        if "count" in sql_text.lower():
            result.scalar_one = MagicMock(return_value=len(filtered))
            return result

        # For the SELECT query, apply offset/limit from the statement
        # Extract offset and limit from the compiled statement
        offset = 0
        limit = len(filtered)
        try:
            # Try to get offset/limit from the statement object
            if hasattr(stmt, '_offset_clause') and stmt._offset_clause is not None:
                offset = stmt._offset_clause.value
            if hasattr(stmt, '_limit_clause') and stmt._limit_clause is not None:
                limit = stmt._limit_clause.value
        except Exception:
            pass

        page = filtered[offset:offset + limit]
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=page)
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
    university_ids=university_ids_strategy,
    assignments=st.lists(st.integers(min_value=0, max_value=100), min_size=0, max_size=20),
)
async def test_programs_isolated_by_university(
    university_ids: list[uuid.UUID],
    assignments: list[int],
):
    """
    Property 6: Aislamiento de programas por universidad.

    For any set of universities and any distribution of programs across them,
    GET /api/v1/universities/{U.id}/programs must return ONLY programs whose
    university_id equals U.id. It must never return programs belonging to a
    different university.

    We verify this for every university in the generated set:
      - Every returned program has university_id == queried university
      - The count of returned programs matches the expected count
      - No program from another university leaks into the response

    **Validates: Requirements 2.4, 6.1, 6.3**
    """
    all_programs = _build_programs(university_ids, assignments)
    mock_session = _make_mock_session(all_programs)

    async def _override_get_session():
        yield mock_session

    app.dependency_overrides[get_session] = _override_get_session

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            for uid in university_ids:
                # Expected programs for this university
                expected = [p for p in all_programs if p.university_id == uid]

                # Request with a large limit to get all programs in one page
                resp = await client.get(
                    f"/api/v1/universities/{uid}/programs",
                    params={"skip": 0, "limit": 100},
                )

                assert resp.status_code == 200, (
                    f"Expected 200 for university {uid}, got {resp.status_code}: "
                    f"{resp.text}"
                )

                body = resp.json()
                returned_data = body["data"]
                returned_total = body["total"]

                # --- Total must match expected count ---
                assert returned_total == len(expected), (
                    f"University {uid}: total mismatch — "
                    f"expected {len(expected)}, got {returned_total}"
                )

                # --- Page size must match expected count ---
                assert len(returned_data) == len(expected), (
                    f"University {uid}: data length mismatch — "
                    f"expected {len(expected)}, got {len(returned_data)}"
                )

                # --- Every returned program must belong to this university ---
                for prog in returned_data:
                    assert prog["university_id"] == str(uid), (
                        f"Isolation violation: university {uid} returned program "
                        f"with university_id={prog['university_id']}"
                    )

                # --- Returned program IDs must match expected IDs exactly ---
                expected_ids = {str(p.id) for p in expected}
                returned_ids = {p["id"] for p in returned_data}
                assert returned_ids == expected_ids, (
                    f"University {uid}: program ID mismatch — "
                    f"missing={expected_ids - returned_ids}, "
                    f"extra={returned_ids - expected_ids}"
                )
    finally:
        app.dependency_overrides.clear()
