# Feature: jwt-role-authentication, Property 8: Valid Credentials Produce Token Pair
# Feature: jwt-role-authentication, Property 9: Inactive Users Cannot Authenticate
"""
Property-based tests for the AuthService login flow.

**Property 8 — Valid Credentials Produce Token Pair (Validates: Requirements 1.1):**
For any active user with a valid password_hash, when the correct email and
password are submitted to the AuthService, the response SHALL contain both a
non-empty ``access_token`` and a non-empty ``refresh_token``, and the decoded
access token's ``sub`` SHALL match the user's UUID.

**Property 9 — Inactive Users Cannot Authenticate (Validates: Requirements 1.4):**
For any user with status INACTIVE, regardless of whether the email and password
are correct, the AuthService SHALL reject the authentication attempt by raising
``AuthenticationError`` with ``status_code`` 403.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest
from hypothesis import given
from hypothesis import settings as h_settings
from hypothesis import strategies as st

from app.application.services.auth_service import AuthService
from app.application.services.token_service import TokenService
from app.core.security import hash_password
from app.domain.enums import RoleEnum, UserStatusEnum
from app.domain.exceptions import AuthenticationError
from app.infrastructure.models.user import User

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

role_strategy = st.sampled_from(list(RoleEnum))

# Generate realistic email-like strings for the property test.
email_strategy = st.from_regex(
    r"[a-z]{3,10}@[a-z]{3,8}\.(com|edu|org)", fullmatch=True
)

full_name_strategy = st.from_regex(r"[A-Z][a-z]{2,10} [A-Z][a-z]{2,10}", fullmatch=True)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_SECRET = "test-secret-key-for-property-tests"

# Pre-compute a bcrypt hash once at module level to avoid the ~200ms cost
# of hashing inside each Hypothesis example.  The property under test is
# the AuthService login flow (token generation & claims), not bcrypt itself.
_FIXED_PASSWORD = "property-test-password"
_FIXED_PASSWORD_HASH = hash_password(_FIXED_PASSWORD)


def _make_token_service() -> TokenService:
    """Return a TokenService configured with deterministic test settings."""
    return TokenService(
        secret_key=_TEST_SECRET,
        algorithm="HS256",
        access_expire_minutes=30,
        refresh_expire_days=7,
    )


def _build_active_user(
    user_id: uuid.UUID,
    email: str,
    full_name: str,
    role: RoleEnum,
    password_hash: str,
) -> User:
    """Build a User model instance with ACTIVE status and a password hash."""
    return User(
        id=user_id,
        email=email,
        full_name=full_name,
        role=role,
        status=UserStatusEnum.ACTIVE,
        password_hash=password_hash,
    )


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


@h_settings(max_examples=100)
@given(
    user_id=st.uuids(),
    email=email_strategy,
    full_name=full_name_strategy,
    role=role_strategy,
)
@pytest.mark.anyio
async def test_valid_credentials_produce_token_pair(
    user_id: uuid.UUID,
    email: str,
    full_name: str,
    role: RoleEnum,
):
    """
    **Validates: Requirements 1.1**

    Property 8: For any active user with a valid password_hash, when the
    correct email and password are submitted to the AuthService, the response
    SHALL contain both a non-empty ``access_token`` and a non-empty
    ``refresh_token``, and the decoded access token's ``sub`` SHALL match
    the user's UUID.
    """
    user = _build_active_user(user_id, email, full_name, role, _FIXED_PASSWORD_HASH)

    # Mock the auth provider to return the pre-built user.
    # The provider is responsible for credential verification; here we test
    # that AuthService correctly orchestrates token generation for any user.
    mock_provider = AsyncMock()
    mock_provider.authenticate.return_value = user

    token_service = _make_token_service()
    auth_service = AuthService(provider=mock_provider, token_service=token_service)

    result = await auth_service.login(email, _FIXED_PASSWORD)

    # Both tokens must be non-empty strings
    assert isinstance(result.access_token, str) and len(result.access_token) > 0
    assert isinstance(result.refresh_token, str) and len(result.refresh_token) > 0

    # token_type must be "bearer"
    assert result.token_type == "bearer"

    # expires_in must match the configured access token TTL in seconds
    assert result.expires_in == 30 * 60

    # Decoded access token sub must match the user UUID
    decoded = token_service.decode_token(result.access_token)
    assert decoded.sub == str(user_id)
    assert decoded.role == role
    assert decoded.type == "access"

    # Decoded refresh token sub must also match the user UUID
    decoded_refresh = token_service.decode_token(result.refresh_token)
    assert decoded_refresh.sub == str(user_id)
    assert decoded_refresh.role == role
    assert decoded_refresh.type == "refresh"

    # The provider was called with the correct credentials
    mock_provider.authenticate.assert_called_once_with(
        email=email, password=_FIXED_PASSWORD
    )


@h_settings(max_examples=100)
@given(
    user_id=st.uuids(),
    role=role_strategy,
)
@pytest.mark.anyio
async def test_token_pair_contains_distinct_tokens(
    user_id: uuid.UUID,
    role: RoleEnum,
):
    """
    **Validates: Requirements 1.1, 2.5**

    Corollary: For any valid login, the access_token and refresh_token
    SHALL be distinct strings (different type claims produce different
    JWT encodings).
    """
    user = _build_active_user(
        user_id, "test@example.com", "Test User", role, _FIXED_PASSWORD_HASH
    )

    mock_provider = AsyncMock()
    mock_provider.authenticate.return_value = user

    token_service = _make_token_service()
    auth_service = AuthService(provider=mock_provider, token_service=token_service)

    result = await auth_service.login("test@example.com", _FIXED_PASSWORD)

    # Access and refresh tokens must be different
    assert result.access_token != result.refresh_token


# ---------------------------------------------------------------------------
# Property 9: Inactive Users Cannot Authenticate
# ---------------------------------------------------------------------------


def _build_inactive_user(
    user_id: uuid.UUID,
    email: str,
    full_name: str,
    role: RoleEnum,
    password_hash: str,
) -> User:
    """Build a User model instance with INACTIVE status and a password hash."""
    return User(
        id=user_id,
        email=email,
        full_name=full_name,
        role=role,
        status=UserStatusEnum.INACTIVE,
        password_hash=password_hash,
    )


@h_settings(max_examples=100)
@given(
    user_id=st.uuids(),
    email=email_strategy,
    full_name=full_name_strategy,
    role=role_strategy,
)
@pytest.mark.anyio
async def test_inactive_users_cannot_authenticate(
    user_id: uuid.UUID,
    email: str,
    full_name: str,
    role: RoleEnum,
):
    """
    **Validates: Requirements 1.4**

    Property 9: For any user with status INACTIVE, regardless of whether
    the email and password are correct, the AuthService SHALL reject the
    authentication attempt by raising ``AuthenticationError`` with
    ``status_code`` 403.
    """
    user = _build_inactive_user(
        user_id, email, full_name, role, _FIXED_PASSWORD_HASH
    )

    # The provider returns the user (credentials are valid), but the user
    # is inactive — AuthService must reject before issuing tokens.
    mock_provider = AsyncMock()
    mock_provider.authenticate.return_value = user

    token_service = _make_token_service()
    auth_service = AuthService(provider=mock_provider, token_service=token_service)

    with pytest.raises(AuthenticationError) as exc_info:
        await auth_service.login(email, _FIXED_PASSWORD)

    # Must be a 403 (Forbidden), not 401 (Unauthorized)
    assert exc_info.value.status_code == 403
    assert exc_info.value.message == "Cuenta desactivada"

    # The provider was still called — the rejection happens after credential
    # verification, at the status check stage.
    mock_provider.authenticate.assert_called_once_with(
        email=email, password=_FIXED_PASSWORD
    )
