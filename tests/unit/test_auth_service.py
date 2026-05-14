"""
Unit tests for AuthService.

Tests cover specific examples and edge cases for the authentication,
refresh, and logout flows:
- Login with non-existent email (Req 1.2)
- Login with wrong password (Req 1.3)
- Login with inactive user (Req 1.4)
- Login with SSO-only user (Req 1.5)
- Successful login returns token pair (Req 1.1)
- Refresh with expired token (Req 4.2)
- Refresh with access token used as refresh (Req 4.3)
- Refresh with invalid signature (Req 4.4)
- Successful refresh returns new token pair (Req 4.1)
- Logout returns confirmation message

Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 4.1, 4.2, 4.3, 4.4
"""

from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import jwt as pyjwt
import pytest

from app.application.services.auth_service import AuthService
from app.application.services.token_service import TokenService
from app.domain.enums import RoleEnum, UserStatusEnum
from app.domain.exceptions import (
    AuthenticationError,
    InvalidTokenError,
    TokenExpiredError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_SECRET = "unit-test-secret-key"
_USER_ID = uuid.UUID("550e8400-e29b-41d4-a716-446655440000")


def _make_token_service(
    secret_key: str = _TEST_SECRET,
    access_expire_minutes: int = 30,
    refresh_expire_days: int = 7,
) -> TokenService:
    """Return a TokenService configured with deterministic test settings."""
    return TokenService(
        secret_key=secret_key,
        algorithm="HS256",
        access_expire_minutes=access_expire_minutes,
        refresh_expire_days=refresh_expire_days,
    )


def _make_user(
    *,
    user_id: uuid.UUID = _USER_ID,
    email: str = "user@university.edu",
    password_hash: str | None = "$2b$12$hashedpasswordvalue",
    role: RoleEnum = RoleEnum.STUDENT,
    status: UserStatusEnum = UserStatusEnum.ACTIVE,
) -> MagicMock:
    """Create a mock User with the given attributes."""
    user = MagicMock()
    user.id = user_id
    user.email = email
    user.password_hash = password_hash
    user.role = role
    user.status = status
    return user


def _make_auth_service(
    provider: AsyncMock | None = None,
    token_service: TokenService | None = None,
) -> AuthService:
    """Build an AuthService with the given or default dependencies."""
    return AuthService(
        provider=provider or AsyncMock(),
        token_service=token_service or _make_token_service(),
    )


# ===================================================================
# Login: successful authentication (Requirement 1.1)
# ===================================================================


class TestLoginSuccess:
    """Verify that valid credentials produce a token pair."""

    @pytest.mark.anyio
    async def test_login_returns_token_response(self):
        """A successful login must return access_token, refresh_token,
        token_type='bearer', and expires_in in seconds."""
        user = _make_user()
        provider = AsyncMock()
        provider.authenticate.return_value = user
        token_service = _make_token_service()
        svc = _make_auth_service(provider=provider, token_service=token_service)

        result = await svc.login("user@university.edu", "correct-password")

        assert result.access_token
        assert result.refresh_token
        assert result.token_type == "bearer"
        assert result.expires_in == 30 * 60

    @pytest.mark.anyio
    async def test_login_access_token_contains_correct_sub(self):
        """The decoded access token sub must match the user UUID."""
        user = _make_user()
        provider = AsyncMock()
        provider.authenticate.return_value = user
        token_service = _make_token_service()
        svc = _make_auth_service(provider=provider, token_service=token_service)

        result = await svc.login("user@university.edu", "correct-password")

        decoded = token_service.decode_token(result.access_token)
        assert decoded.sub == str(_USER_ID)
        assert decoded.role == RoleEnum.STUDENT
        assert decoded.type == "access"

    @pytest.mark.anyio
    async def test_login_refresh_token_contains_correct_sub(self):
        """The decoded refresh token sub must match the user UUID."""
        user = _make_user()
        provider = AsyncMock()
        provider.authenticate.return_value = user
        token_service = _make_token_service()
        svc = _make_auth_service(provider=provider, token_service=token_service)

        result = await svc.login("user@university.edu", "correct-password")

        decoded = token_service.decode_token(result.refresh_token)
        assert decoded.sub == str(_USER_ID)
        assert decoded.type == "refresh"

    @pytest.mark.anyio
    async def test_login_delegates_to_provider(self):
        """AuthService must delegate credential verification to the provider."""
        provider = AsyncMock()
        provider.authenticate.return_value = _make_user()
        svc = _make_auth_service(provider=provider)

        await svc.login("user@university.edu", "secret")

        provider.authenticate.assert_awaited_once_with(
            email="user@university.edu", password="secret"
        )


# ===================================================================
# Login: non-existent email (Requirement 1.2)
# ===================================================================


class TestLoginNonExistentEmail:
    """Verify that a non-existent email propagates AuthenticationError."""

    @pytest.mark.anyio
    async def test_nonexistent_email_raises_authentication_error(self):
        """When the provider raises AuthenticationError for unknown email,
        AuthService must let it propagate."""
        provider = AsyncMock()
        provider.authenticate.side_effect = AuthenticationError(
            "Credenciales inválidas", 401
        )
        svc = _make_auth_service(provider=provider)

        with pytest.raises(AuthenticationError) as exc_info:
            await svc.login("unknown@university.edu", "any-password")

        assert exc_info.value.message == "Credenciales inválidas"
        assert exc_info.value.status_code == 401


# ===================================================================
# Login: wrong password (Requirement 1.3)
# ===================================================================


class TestLoginWrongPassword:
    """Verify that a wrong password propagates AuthenticationError."""

    @pytest.mark.anyio
    async def test_wrong_password_raises_authentication_error(self):
        """When the provider raises AuthenticationError for wrong password,
        AuthService must let it propagate."""
        provider = AsyncMock()
        provider.authenticate.side_effect = AuthenticationError(
            "Credenciales inválidas", 401
        )
        svc = _make_auth_service(provider=provider)

        with pytest.raises(AuthenticationError) as exc_info:
            await svc.login("user@university.edu", "wrong-password")

        assert exc_info.value.message == "Credenciales inválidas"
        assert exc_info.value.status_code == 401


# ===================================================================
# Login: inactive user (Requirement 1.4)
# ===================================================================


class TestLoginInactiveUser:
    """Verify that inactive users are rejected with HTTP 403."""

    @pytest.mark.anyio
    async def test_inactive_user_raises_authentication_error_403(self):
        """An inactive user must be rejected with status_code 403 and
        the message 'Cuenta desactivada'."""
        user = _make_user(status=UserStatusEnum.INACTIVE)
        provider = AsyncMock()
        provider.authenticate.return_value = user
        svc = _make_auth_service(provider=provider)

        with pytest.raises(AuthenticationError) as exc_info:
            await svc.login("user@university.edu", "correct-password")

        assert exc_info.value.status_code == 403
        assert exc_info.value.message == "Cuenta desactivada"

    @pytest.mark.anyio
    async def test_inactive_admin_is_also_rejected(self):
        """Even an ADMIN with INACTIVE status must be rejected."""
        user = _make_user(role=RoleEnum.ADMIN, status=UserStatusEnum.INACTIVE)
        provider = AsyncMock()
        provider.authenticate.return_value = user
        svc = _make_auth_service(provider=provider)

        with pytest.raises(AuthenticationError) as exc_info:
            await svc.login("admin@university.edu", "correct-password")

        assert exc_info.value.status_code == 403
        assert exc_info.value.message == "Cuenta desactivada"


# ===================================================================
# Login: SSO-only user (Requirement 1.5)
# ===================================================================


class TestLoginSSOOnlyUser:
    """Verify that SSO-only users are rejected at the provider level."""

    @pytest.mark.anyio
    async def test_sso_only_user_raises_authentication_error(self):
        """When the provider raises AuthenticationError for an SSO-only user
        (no password_hash), AuthService must let it propagate."""
        provider = AsyncMock()
        provider.authenticate.side_effect = AuthenticationError(
            "Credenciales inválidas", 401
        )
        svc = _make_auth_service(provider=provider)

        with pytest.raises(AuthenticationError) as exc_info:
            await svc.login("sso@university.edu", "any-password")

        assert exc_info.value.message == "Credenciales inválidas"
        assert exc_info.value.status_code == 401


# ===================================================================
# Refresh: successful refresh (Requirement 4.1)
# ===================================================================


class TestRefreshSuccess:
    """Verify that a valid refresh token produces a new token pair."""

    @pytest.mark.anyio
    async def test_refresh_returns_new_token_pair(self):
        """A valid refresh token must produce new access and refresh tokens."""
        token_service = _make_token_service()
        svc = _make_auth_service(token_service=token_service)

        refresh_token = token_service.create_refresh_token(_USER_ID, RoleEnum.STUDENT)
        result = await svc.refresh(refresh_token)

        assert result.access_token
        assert result.refresh_token
        assert result.token_type == "bearer"
        assert result.expires_in == 30 * 60

    @pytest.mark.anyio
    async def test_refresh_preserves_user_identity(self):
        """The new tokens must carry the same sub and role as the original."""
        token_service = _make_token_service()
        svc = _make_auth_service(token_service=token_service)

        refresh_token = token_service.create_refresh_token(
            _USER_ID, RoleEnum.PROFESSOR
        )
        result = await svc.refresh(refresh_token)

        decoded_access = token_service.decode_token(result.access_token)
        assert decoded_access.sub == str(_USER_ID)
        assert decoded_access.role == RoleEnum.PROFESSOR
        assert decoded_access.type == "access"

        decoded_refresh = token_service.decode_token(result.refresh_token)
        assert decoded_refresh.sub == str(_USER_ID)
        assert decoded_refresh.role == RoleEnum.PROFESSOR
        assert decoded_refresh.type == "refresh"

    @pytest.mark.anyio
    async def test_refresh_returns_distinct_tokens(self):
        """The new access_token and refresh_token must be different strings."""
        token_service = _make_token_service()
        svc = _make_auth_service(token_service=token_service)

        refresh_token = token_service.create_refresh_token(_USER_ID, RoleEnum.ADMIN)
        result = await svc.refresh(refresh_token)

        assert result.access_token != result.refresh_token


# ===================================================================
# Refresh: expired token (Requirement 4.2)
# ===================================================================


class TestRefreshExpiredToken:
    """Verify that an expired refresh token raises TokenExpiredError."""

    @pytest.mark.anyio
    async def test_expired_refresh_token_raises_token_expired_error(self):
        """An expired refresh token must raise TokenExpiredError."""
        token_service = _make_token_service()
        svc = _make_auth_service(token_service=token_service)

        # Build an already-expired refresh token manually
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        claims = {
            "sub": str(_USER_ID),
            "role": RoleEnum.STUDENT.value,
            "type": "refresh",
            "iat": int((now - timedelta(days=8)).timestamp()),
            "exp": int((now - timedelta(seconds=1)).timestamp()),
        }
        expired_token = pyjwt.encode(claims, _TEST_SECRET, algorithm="HS256")

        with pytest.raises(TokenExpiredError):
            await svc.refresh(expired_token)


# ===================================================================
# Refresh: access token used as refresh (Requirement 4.3)
# ===================================================================


class TestRefreshWithAccessToken:
    """Verify that using an access token for refresh raises InvalidTokenError."""

    @pytest.mark.anyio
    async def test_access_token_as_refresh_raises_invalid_token_error(self):
        """An access token submitted to refresh must raise InvalidTokenError."""
        token_service = _make_token_service()
        svc = _make_auth_service(token_service=token_service)

        access_token = token_service.create_access_token(_USER_ID, RoleEnum.STUDENT)

        with pytest.raises(InvalidTokenError) as exc_info:
            await svc.refresh(access_token)

        assert exc_info.value.message == "Token inválido"


# ===================================================================
# Refresh: invalid signature (Requirement 4.4)
# ===================================================================


class TestRefreshInvalidSignature:
    """Verify that a refresh token with wrong signature raises InvalidTokenError."""

    @pytest.mark.anyio
    async def test_wrong_signature_raises_invalid_token_error(self):
        """A refresh token signed with a different key must be rejected."""
        token_service = _make_token_service()
        svc = _make_auth_service(token_service=token_service)

        # Create a refresh token with a different secret
        wrong_service = _make_token_service(secret_key="wrong-secret-key")
        bad_token = wrong_service.create_refresh_token(_USER_ID, RoleEnum.STUDENT)

        with pytest.raises(InvalidTokenError):
            await svc.refresh(bad_token)

    @pytest.mark.anyio
    async def test_malformed_token_raises_invalid_token_error(self):
        """A completely malformed string must be rejected."""
        token_service = _make_token_service()
        svc = _make_auth_service(token_service=token_service)

        with pytest.raises(InvalidTokenError):
            await svc.refresh("not-a-valid-jwt")

    @pytest.mark.anyio
    async def test_empty_string_raises_invalid_token_error(self):
        """An empty string must be rejected."""
        token_service = _make_token_service()
        svc = _make_auth_service(token_service=token_service)

        with pytest.raises(InvalidTokenError):
            await svc.refresh("")


# ===================================================================
# Logout (Requirement 9.1, 9.2)
# ===================================================================


class TestLogout:
    """Verify stateless logout returns confirmation message."""

    def test_logout_returns_confirmation_message(self):
        """logout() must return a dict with the expected message."""
        svc = _make_auth_service()

        result = svc.logout()

        assert result == {"message": "Sesión cerrada exitosamente"}

    def test_logout_is_synchronous(self):
        """logout() is a regular method, not async — it returns immediately."""
        svc = _make_auth_service()

        result = svc.logout()

        assert isinstance(result, dict)
        assert "message" in result


# ===================================================================
# Edge cases
# ===================================================================


class TestAuthServiceEdgeCases:
    """Additional edge cases for AuthService."""

    @pytest.mark.anyio
    async def test_login_with_different_roles_produces_correct_tokens(self):
        """Login must produce tokens with the correct role for each RoleEnum."""
        token_service = _make_token_service()

        for role in RoleEnum:
            user = _make_user(role=role)
            provider = AsyncMock()
            provider.authenticate.return_value = user
            svc = _make_auth_service(provider=provider, token_service=token_service)

            result = await svc.login("user@university.edu", "password")

            decoded = token_service.decode_token(result.access_token)
            assert decoded.role == role

    @pytest.mark.anyio
    async def test_login_expires_in_matches_configured_minutes(self):
        """expires_in must reflect the configured access_expire_minutes."""
        token_service = _make_token_service(access_expire_minutes=15)
        user = _make_user()
        provider = AsyncMock()
        provider.authenticate.return_value = user
        svc = _make_auth_service(provider=provider, token_service=token_service)

        result = await svc.login("user@university.edu", "password")

        assert result.expires_in == 15 * 60

    @pytest.mark.anyio
    async def test_refresh_with_token_missing_type_claim_raises_error(self):
        """A token missing the 'type' claim must be rejected by decode_token."""
        from datetime import datetime, timezone

        token_service = _make_token_service()
        svc = _make_auth_service(token_service=token_service)

        now = datetime.now(timezone.utc)
        claims = {
            "sub": str(_USER_ID),
            "role": RoleEnum.STUDENT.value,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(days=7)).timestamp()),
        }
        token = pyjwt.encode(claims, _TEST_SECRET, algorithm="HS256")

        with pytest.raises(InvalidTokenError):
            await svc.refresh(token)
