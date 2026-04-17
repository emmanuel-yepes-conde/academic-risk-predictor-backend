# Feature: multi-university-support, Property 5: Usuarios no-ADMIN no pueden escribir universidades
"""
Property-based test verifying that users with roles other than ADMIN are
forbidden from creating or updating universities.

For any valid UniversityCreate or UniversityUpdate payload and any non-ADMIN
role (STUDENT, PROFESSOR), calling UniversityService.create() or
UniversityService.update() SHALL raise HTTPException with status_code 403.

**Validates: Requirements 1.7**
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st

from app.application.schemas.university import UniversityCreate, UniversityUpdate
from app.application.services.university_service import UniversityService
from app.domain.enums import RoleEnum

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

non_admin_role_strategy = st.sampled_from([RoleEnum.STUDENT, RoleEnum.PROFESSOR])

university_create_strategy = st.builds(
    UniversityCreate,
    name=st.text(min_size=1, max_size=200),
    code=st.from_regex(r"[A-Z0-9]{3,20}", fullmatch=True),
    country=st.text(min_size=1, max_size=100),
    city=st.text(min_size=1, max_size=100),
    active=st.booleans(),
)

university_update_strategy = st.builds(
    UniversityUpdate,
    name=st.one_of(st.none(), st.text(min_size=1, max_size=200)),
    country=st.one_of(st.none(), st.text(min_size=1, max_size=100)),
    city=st.one_of(st.none(), st.text(min_size=1, max_size=100)),
    active=st.one_of(st.none(), st.booleans()),
)

# ---------------------------------------------------------------------------
# Mock repository helper
# ---------------------------------------------------------------------------


def _make_mock_repo() -> AsyncMock:
    """
    Return a mock IUniversityRepository.

    The repository methods should never be called because the service must
    reject the request before reaching the repository layer.
    """
    mock_repo = AsyncMock()
    mock_repo.get_by_code = AsyncMock()
    mock_repo.create = AsyncMock()
    mock_repo.update = AsyncMock()
    return mock_repo


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    uni_data=university_create_strategy,
    role=non_admin_role_strategy,
)
async def test_non_admin_cannot_create_university(
    uni_data: UniversityCreate,
    role: RoleEnum,
):
    """
    Property 5 (create): Usuarios no-ADMIN no pueden crear universidades.

    For any valid UniversityCreate payload and any non-ADMIN role (STUDENT
    or PROFESSOR), calling UniversityService.create() SHALL raise
    HTTPException with status_code 403.

    The repository must never be called — the service rejects the request
    at the authorization check before any persistence logic.

    **Validates: Requirements 1.7**
    """
    mock_repo = _make_mock_repo()
    service = UniversityService(repo=mock_repo)

    with pytest.raises(HTTPException) as exc_info:
        await service.create(data=uni_data, actor_role=role)

    assert exc_info.value.status_code == 403, (
        f"Expected 403 Forbidden for role {role.value}, "
        f"got {exc_info.value.status_code}"
    )

    # Repository must not have been touched
    mock_repo.get_by_code.assert_not_awaited()
    mock_repo.create.assert_not_awaited()


@pytest.mark.anyio
@h_settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(
    update_data=university_update_strategy,
    role=non_admin_role_strategy,
)
async def test_non_admin_cannot_update_university(
    update_data: UniversityUpdate,
    role: RoleEnum,
):
    """
    Property 5 (update): Usuarios no-ADMIN no pueden actualizar universidades.

    For any valid UniversityUpdate payload, any existing university ID, and
    any non-ADMIN role (STUDENT or PROFESSOR), calling
    UniversityService.update() SHALL raise HTTPException with status_code 403.

    The repository must never be called — the service rejects the request
    at the authorization check before any persistence logic.

    **Validates: Requirements 1.7**
    """
    mock_repo = _make_mock_repo()
    service = UniversityService(repo=mock_repo)
    target_id = uuid4()

    with pytest.raises(HTTPException) as exc_info:
        await service.update(id=target_id, data=update_data, actor_role=role)

    assert exc_info.value.status_code == 403, (
        f"Expected 403 Forbidden for role {role.value}, "
        f"got {exc_info.value.status_code}"
    )

    # Repository must not have been touched
    mock_repo.update.assert_not_awaited()
