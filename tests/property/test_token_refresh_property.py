# Feature: jwt-role-authentication, Property 10: Valid Refresh Token Produces New Token Pair
"""
Property-based tests for the AuthService refresh flow.

**Property 10 — Valid Refresh Token Produces New Token Pair (Validates: Requirements 4.1):**
For any valid refresh token (with type "refresh", valid signature, and non-expired),
submitting it to the AuthService.refresh method SHALL produce a new access_token and
a new refresh_token, both with valid signatures and correct claims.
"""

from __future__ import annotations

import uuid

import pytest
from hypothesis import given
from hypothesis import settings as h_settings
from hypothesis import strategies as st

from app.application.services.auth_service import AuthService
from app.application.services.token_service import TokenService
from app.domain.enums import RoleEnum

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

role_strategy = st.sampled_from(list(RoleEnum))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_SECRET = "test-secret-key-for-property-tests"


def _make_token_service(
    access_expire_minutes: int = 30,
    refresh_expire_days: int = 7,
) -> TokenService:
    """Return a TokenService configured with deterministic test settings."""
    return TokenService(
        secret_key=_TEST_SECRET,
        algorithm="HS256",
        access_expire_minutes=access_expire_minutes,
        refresh_expire_days=refresh_expire_days,
    )


# ---------------------------------------------------------------------------
# Property 10: Valid Refresh Token Produces New Token Pair
# ---------------------------------------------------------------------------


@h_settings(max_examples=100)
@given(
    user_id=st.uuids(),
    role=role_strategy,
)
@pytest.mark.anyio
async def test_valid_refresh_token_produces_new_token_pair(
    user_id: uuid.UUID,
    role: RoleEnum,
):
    """
    **Validates: Requirements 4.1**

    Property 10: For any valid refresh token, submitting it to
    AuthService.refresh SHALL produce a new access_token and a new
    refresh_token, both with valid signatures and correct claims.
    """
    token_service = _make_token_service()

    # AuthService.refresh only uses token_service (no provider needed for
    # the refresh path), but the constructor requires a provider argument.
    # We pass None since it won't be called.
    auth_service = AuthService(provider=None, token_service=token_service)  # type: ignore[arg-type]

    # Create a valid refresh token for the generated user
    refresh_token = token_service.create_refresh_token(user_id, role)

    # Execute the refresh flow
    result = await auth_service.refresh(refresh_token)

    # Both tokens must be non-empty strings
    assert isinstance(result.access_token, str) and len(result.access_token) > 0
    assert isinstance(result.refresh_token, str) and len(result.refresh_token) > 0

    # token_type must be "bearer"
    assert result.token_type == "bearer"

    # expires_in must match the configured access token TTL in seconds
    assert result.expires_in == 30 * 60

    # Decoded access token must have correct claims
    decoded_access = token_service.decode_token(result.access_token)
    assert decoded_access.sub == str(user_id)
    assert decoded_access.role == role
    assert decoded_access.type == "access"

    # Decoded refresh token must have correct claims
    decoded_refresh = token_service.decode_token(result.refresh_token)
    assert decoded_refresh.sub == str(user_id)
    assert decoded_refresh.role == role
    assert decoded_refresh.type == "refresh"


@h_settings(max_examples=100)
@given(
    user_id=st.uuids(),
    role=role_strategy,
)
@pytest.mark.anyio
async def test_refresh_produces_distinct_tokens(
    user_id: uuid.UUID,
    role: RoleEnum,
):
    """
    **Validates: Requirements 4.1**

    Corollary: The new access_token and new refresh_token returned by
    refresh SHALL be distinct strings (different type claims produce
    different JWT encodings).
    """
    token_service = _make_token_service()
    auth_service = AuthService(provider=None, token_service=token_service)  # type: ignore[arg-type]

    refresh_token = token_service.create_refresh_token(user_id, role)
    result = await auth_service.refresh(refresh_token)

    # The new access and refresh tokens must differ from each other
    assert result.access_token != result.refresh_token


@h_settings(max_examples=100)
@given(
    user_id=st.uuids(),
    role=role_strategy,
)
@pytest.mark.anyio
async def test_refresh_preserves_user_identity(
    user_id: uuid.UUID,
    role: RoleEnum,
):
    """
    **Validates: Requirements 4.1**

    For any valid refresh token, the new token pair SHALL preserve the
    original user identity (sub) and role from the refresh token.
    """
    token_service = _make_token_service()
    auth_service = AuthService(provider=None, token_service=token_service)  # type: ignore[arg-type]

    original_refresh = token_service.create_refresh_token(user_id, role)
    original_payload = token_service.decode_token(original_refresh)

    result = await auth_service.refresh(original_refresh)

    # Verify identity is preserved in the new access token
    new_access_payload = token_service.decode_token(result.access_token)
    assert new_access_payload.sub == original_payload.sub
    assert new_access_payload.role == original_payload.role

    # Verify identity is preserved in the new refresh token
    new_refresh_payload = token_service.decode_token(result.refresh_token)
    assert new_refresh_payload.sub == original_payload.sub
    assert new_refresh_payload.role == original_payload.role
