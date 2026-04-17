# Feature: multi-university-support, Property 3: Round-trip de universidad por ID
"""
Property-based test for university repository round trip: create → get_by_id.

Verifies that after creating a university via the repository, retrieving it
by id returns exactly the same field values that were passed to create.

**Validates: Requirements 1.5**
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

from app.application.schemas.university import UniversityCreate
from app.infrastructure.models.audit_log import AuditLog
from app.infrastructure.models.university import University
from app.infrastructure.repositories.university_repository import UniversityRepository

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
# Mock session helper
# ---------------------------------------------------------------------------


def _make_mock_session() -> AsyncMock:
    """
    Return a mock AsyncSession that simulates DB behaviour for the
    UniversityRepository.

    The repository calls session.add() for both the University entity and
    the AuditLog entry. We store only the University so that get_by_id
    returns the correct object.
    """
    stored: list[University] = []

    def _add(obj):
        if isinstance(obj, University) and not stored:
            stored.append(obj)

    mock_session = AsyncMock()
    mock_session.add = MagicMock(side_effect=_add)
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()

    async def _execute(stmt, *args, **kwargs):
        result = MagicMock()
        result.scalar_one_or_none.return_value = stored[0] if stored else None
        return result

    mock_session.execute = AsyncMock(side_effect=_execute)
    return mock_session


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@h_settings(max_examples=100)
@given(uni_data=university_create_strategy)
async def test_university_roundtrip_get_by_id(uni_data: UniversityCreate):
    """
    Property 3: Round-trip de universidad por ID.

    For any valid UniversityCreate input, the University returned by
    get_by_id(created.id) must have the same name, code, country, city,
    and active flag as the original UniversityCreate payload.

    **Validates: Requirements 1.5**
    """
    mock_session = _make_mock_session()
    repo = UniversityRepository(session=mock_session)

    created = await repo.create(uni_data)

    retrieved = await repo.get_by_id(created.id)

    assert retrieved is not None, "get_by_id must return the created university"
    assert retrieved.name == uni_data.name
    assert retrieved.code == uni_data.code
    assert retrieved.country == uni_data.country
    assert retrieved.city == uni_data.city
    assert retrieved.active == uni_data.active
    # Structural fields must be present
    assert retrieved.id is not None
    assert retrieved.created_at is not None
