# Feature: jwt-role-authentication, Property 5: Role Guard Access
"""
Property-based tests for the ``require_roles`` dependency factory.

**Property 5 — Role Guard Grants Access If and Only If Authorized
(Validates: Requirements 5.1, 5.2, 5.4):**

For any RoleEnum value and any set of allowed roles for an endpoint, the
Role_Guard SHALL allow the request if and only if the user's role is in the
allowed set OR the user's role is ADMIN.  Conversely, if the user's role is
not in the allowed set and is not ADMIN, the Role_Guard SHALL raise
HTTPException 403.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from hypothesis import given
from hypothesis import settings as h_settings
from hypothesis import strategies as st

from app.api.v1.dependencies.auth import CurrentUser, require_roles
from app.domain.enums import RoleEnum

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

role_strategy = st.sampled_from(list(RoleEnum))
# Generate non-empty subsets of roles to use as the "allowed" set
allowed_roles_strategy = st.frozensets(role_strategy, min_size=1)
# Also test with empty allowed set (only ADMIN should pass)
allowed_roles_with_empty_strategy = st.frozensets(role_strategy, min_size=0)
user_id_strategy = st.uuids()


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@h_settings(max_examples=100)
@given(
    user_role=role_strategy,
    allowed_roles=allowed_roles_with_empty_strategy,
    user_id=user_id_strategy,
)
@pytest.mark.anyio
async def test_role_guard_grants_access_iff_authorized(
    user_role: RoleEnum,
    allowed_roles: frozenset[RoleEnum],
    user_id: uuid.UUID,
):
    """
    **Validates: Requirements 5.1, 5.2, 5.4**

    Property 5: For any RoleEnum value and any set of allowed roles, the
    guard SHALL allow the request if and only if the user's role is in the
    allowed set OR the user's role is ADMIN.
    """
    current_user = CurrentUser(id=user_id, role=user_role)
    guard = require_roles(*allowed_roles)

    should_allow = user_role in allowed_roles or user_role == RoleEnum.ADMIN

    if should_allow:
        # Patch get_current_user so the dependency receives our CurrentUser
        with patch(
            "app.api.v1.dependencies.auth.get_current_user",
            new_callable=AsyncMock,
            return_value=current_user,
        ):
            result = await guard(current_user=current_user)
        assert result.id == user_id
        assert result.role == user_role
    else:
        with pytest.raises(HTTPException) as exc_info:
            with patch(
                "app.api.v1.dependencies.auth.get_current_user",
                new_callable=AsyncMock,
                return_value=current_user,
            ):
                await guard(current_user=current_user)
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "No tiene permisos para esta acción"


@h_settings(max_examples=100)
@given(user_id=user_id_strategy, allowed_roles=allowed_roles_with_empty_strategy)
@pytest.mark.anyio
async def test_admin_always_has_access(
    user_id: uuid.UUID,
    allowed_roles: frozenset[RoleEnum],
):
    """
    **Validates: Requirements 5.4**

    Property 5 (ADMIN corollary): For any set of allowed roles — including
    the empty set — a user with role ADMIN SHALL always be granted access.
    """
    current_user = CurrentUser(id=user_id, role=RoleEnum.ADMIN)
    guard = require_roles(*allowed_roles)

    with patch(
        "app.api.v1.dependencies.auth.get_current_user",
        new_callable=AsyncMock,
        return_value=current_user,
    ):
        result = await guard(current_user=current_user)

    assert result.id == user_id
    assert result.role == RoleEnum.ADMIN


@h_settings(max_examples=100)
@given(
    user_role=st.sampled_from([RoleEnum.STUDENT, RoleEnum.PROFESSOR]),
    user_id=user_id_strategy,
)
@pytest.mark.anyio
async def test_non_admin_denied_when_not_in_allowed_set(
    user_role: RoleEnum,
    user_id: uuid.UUID,
):
    """
    **Validates: Requirements 5.2**

    Property 5 (denial): For any non-ADMIN role, when the role is NOT in the
    allowed set, the guard SHALL return HTTP 403 with the message
    "No tiene permisos para esta acción".
    """
    # Build an allowed set that explicitly excludes the user's role
    all_roles = set(RoleEnum)
    excluded_roles = all_roles - {user_role, RoleEnum.ADMIN}
    # Use only the roles that are neither the user's role nor ADMIN
    # (could be empty, which is fine — ADMIN bypass is tested separately)
    guard = require_roles(*excluded_roles)

    current_user = CurrentUser(id=user_id, role=user_role)

    with pytest.raises(HTTPException) as exc_info:
        with patch(
            "app.api.v1.dependencies.auth.get_current_user",
            new_callable=AsyncMock,
            return_value=current_user,
        ):
            await guard(current_user=current_user)

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "No tiene permisos para esta acción"


@h_settings(max_examples=100)
@given(
    user_role=role_strategy,
    user_id=user_id_strategy,
)
@pytest.mark.anyio
async def test_role_in_allowed_set_is_granted_access(
    user_role: RoleEnum,
    user_id: uuid.UUID,
):
    """
    **Validates: Requirements 5.1**

    Property 5 (grant): For any role, when that role IS in the allowed set,
    the guard SHALL allow the request to proceed and return the CurrentUser.
    """
    guard = require_roles(user_role)
    current_user = CurrentUser(id=user_id, role=user_role)

    with patch(
        "app.api.v1.dependencies.auth.get_current_user",
        new_callable=AsyncMock,
        return_value=current_user,
    ):
        result = await guard(current_user=current_user)

    assert result.id == user_id
    assert result.role == user_role
