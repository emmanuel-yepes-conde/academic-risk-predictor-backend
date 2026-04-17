# Feature: multi-university-support, Property 2: Listado paginado consistente con total
"""
Property-based test for university paginated listing consistency.

Verifies that for any set of universities in the database and any valid
combination of skip and limit, the sum of page sizes across all pages equals
the total field, and no university appears in more than one page.

**Validates: Requirements 1.4**
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st

from app.application.schemas.university import UniversityCreate, UniversityRead
from app.application.services.university_service import UniversityService
from app.domain.enums import RoleEnum
from app.infrastructure.models.university import University

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

university_create_strategy = st.builds(
    UniversityCreate,
    name=st.text(min_size=1, max_size=200),
    code=st.from_regex(r"[A-Z0-9]{3,20}", fullmatch=True),
    country=st.text(min_size=1, max_size=100),
    city=st.text(min_size=1, max_size=100),
    active=st.booleans(),
)


# ---------------------------------------------------------------------------
# Mock repository helper
# ---------------------------------------------------------------------------


def _make_mock_repo(universities: list[University]) -> AsyncMock:
    """
    Return a mock IUniversityRepository backed by an in-memory list.

    - list(skip, limit) returns the correct slice of the stored universities.
    - count() returns the total number of stored universities.
    """
    mock_repo = AsyncMock()

    async def _list(skip: int, limit: int) -> list[University]:
        return universities[skip : skip + limit]

    async def _count() -> int:
        return len(universities)

    mock_repo.list = AsyncMock(side_effect=_list)
    mock_repo.count = AsyncMock(side_effect=_count)

    return mock_repo


def _build_universities(create_payloads: list[UniversityCreate]) -> list[University]:
    """Convert a list of UniversityCreate payloads into University ORM objects."""
    return [
        University(id=uuid4(), **payload.model_dump())
        for payload in create_payloads
    ]


# ---------------------------------------------------------------------------
# Property test — single page consistency
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    payloads=st.lists(university_create_strategy, min_size=0, max_size=30),
    skip=st.integers(min_value=0, max_value=50),
    limit=st.integers(min_value=1, max_value=100),
)
async def test_paginated_list_page_size_consistent_with_total(
    payloads: list[UniversityCreate],
    skip: int,
    limit: int,
):
    """
    Property 2 (single page): Listado paginado es consistente con el total.

    For any set of universities and any valid (skip, limit):
      - total must equal the actual number of universities
      - len(data) must equal min(limit, max(0, total - skip))
      - skip and limit in the response must match the request

    **Validates: Requirements 1.4**
    """
    universities = _build_universities(payloads)
    mock_repo = _make_mock_repo(universities)
    service = UniversityService(repo=mock_repo)

    result = await service.list(skip=skip, limit=limit)

    total = len(universities)
    expected_page_size = min(limit, max(0, total - skip))

    # --- total must reflect the actual count ---
    assert result.total == total, (
        f"total mismatch: expected {total}, got {result.total}"
    )

    # --- page size must be correct ---
    assert len(result.data) == expected_page_size, (
        f"page size mismatch: expected {expected_page_size}, "
        f"got {len(result.data)} (skip={skip}, limit={limit}, total={total})"
    )

    # --- skip and limit echoed back correctly ---
    assert result.skip == skip, f"skip mismatch: expected {skip}, got {result.skip}"
    assert result.limit == limit, f"limit mismatch: expected {limit}, got {result.limit}"

    # --- all returned items must be UniversityRead ---
    for item in result.data:
        assert isinstance(item, UniversityRead), (
            f"Expected UniversityRead, got {type(item).__name__}"
        )


# ---------------------------------------------------------------------------
# Property test — full pagination sweep (no duplicates, no missing items)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    payloads=st.lists(university_create_strategy, min_size=0, max_size=30),
    limit=st.integers(min_value=1, max_value=10),
)
async def test_paginated_sweep_covers_all_universities_without_duplicates(
    payloads: list[UniversityCreate],
    limit: int,
):
    """
    Property 2 (full sweep): Listado paginado es consistente con el total.

    For any set of universities and any page size (limit), iterating through
    all pages (skip=0, limit, 2*limit, ...) must:
      - Collect exactly `total` universities in aggregate
      - Never return the same university on more than one page
      - total must be consistent across all pages

    **Validates: Requirements 1.4**
    """
    universities = _build_universities(payloads)
    mock_repo = _make_mock_repo(universities)
    service = UniversityService(repo=mock_repo)

    total = len(universities)
    all_ids: list = []
    observed_total: int | None = None
    skip = 0

    while skip <= total:
        result = await service.list(skip=skip, limit=limit)

        # --- total must be consistent across all pages ---
        if observed_total is None:
            observed_total = result.total
        else:
            assert result.total == observed_total, (
                f"total changed between pages: first saw {observed_total}, "
                f"now got {result.total} at skip={skip}"
            )

        for item in result.data:
            all_ids.append(item.id)

        # If this page returned fewer items than limit, we've reached the end
        if len(result.data) < limit:
            break

        skip += limit

    # --- total items collected must equal total ---
    assert len(all_ids) == total, (
        f"Collected {len(all_ids)} items across all pages, expected {total}"
    )

    # --- no duplicates ---
    assert len(set(all_ids)) == len(all_ids), (
        f"Duplicate universities found across pages: "
        f"{len(all_ids)} items but only {len(set(all_ids))} unique"
    )
