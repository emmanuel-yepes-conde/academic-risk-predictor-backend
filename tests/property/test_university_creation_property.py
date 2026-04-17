# Feature: multi-university-support, Property 1: Creación de universidad con datos válidos
"""
Property-based test for university creation via the service layer.

Verifies that for any valid UniversityCreate payload, calling
UniversityService.create() with ADMIN role always returns a UniversityRead
whose fields are equivalent to the input payload.

**Validates: Requirements 1.2**
"""

from unittest.mock import AsyncMock, MagicMock
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


def _make_mock_repo() -> AsyncMock:
    """
    Return a mock IUniversityRepository that:
    - get_by_code() returns None (no duplicate)
    - create() builds a University ORM object from the input and returns it
    """
    mock_repo = AsyncMock()

    # No existing university with the same code
    mock_repo.get_by_code = AsyncMock(return_value=None)

    async def _create(data: UniversityCreate) -> University:
        return University(
            id=uuid4(),
            **data.model_dump(),
        )

    mock_repo.create = AsyncMock(side_effect=_create)

    return mock_repo


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(uni_data=university_create_strategy)
async def test_university_creation_returns_matching_resource(
    uni_data: UniversityCreate,
):
    """
    Property 1: Creación de universidad con datos válidos siempre retorna
    el recurso creado.

    For any valid UniversityCreate payload (name, code, country, city, active),
    calling UniversityService.create() with ADMIN role SHALL return a
    UniversityRead whose content is equivalent to the payload sent.

    Specifically:
      - name, code, country, city, active must match the input exactly
      - id must be a non-None UUID
      - created_at must be a non-None datetime
      - The return type must be UniversityRead

    **Validates: Requirements 1.2**
    """
    mock_repo = _make_mock_repo()
    service = UniversityService(repo=mock_repo)

    result = await service.create(data=uni_data, actor_role=RoleEnum.ADMIN)

    # --- Return type must be UniversityRead ---
    assert isinstance(result, UniversityRead), (
        f"Expected UniversityRead, got {type(result).__name__}"
    )

    # --- All input fields must match ---
    assert result.name == uni_data.name, (
        f"name mismatch: expected {uni_data.name!r}, got {result.name!r}"
    )
    assert result.code == uni_data.code, (
        f"code mismatch: expected {uni_data.code!r}, got {result.code!r}"
    )
    assert result.country == uni_data.country, (
        f"country mismatch: expected {uni_data.country!r}, got {result.country!r}"
    )
    assert result.city == uni_data.city, (
        f"city mismatch: expected {uni_data.city!r}, got {result.city!r}"
    )
    assert result.active == uni_data.active, (
        f"active mismatch: expected {uni_data.active!r}, got {result.active!r}"
    )

    # --- Structural fields must be present ---
    assert result.id is not None, "id must not be None"
    assert result.created_at is not None, "created_at must not be None"

    # --- Repository was called correctly ---
    mock_repo.get_by_code.assert_awaited_once_with(uni_data.code)
    mock_repo.create.assert_awaited_once_with(uni_data)
