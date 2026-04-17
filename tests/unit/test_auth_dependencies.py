"""Unit tests for auth dependencies (get_current_user, require_roles, require_self_or_roles).

Tests cover:
- Missing Authorization header → 401 "Token no proporcionado" (Req 3.2)
- Malformed bearer format → 401 "Token no proporcionado" (Req 3.2)
- Refresh token used as access token → 401 "Token inválido" (Req 3.5)
- Expired token → 401 "Token expirado" (Req 3.3)
- Tampered/invalid token → 401 "Token inválido" (Req 3.4)
- Valid token extraction → CurrentUser with correct id and role (Req 3.1)

Requirements: 3.1, 3.2, 3.4, 3.5
"""

import uuid

import pytest
from fastapi import HTTPException

from app.api.v1.dependencies.auth import CurrentUser, get_current_user, require_roles
from app.application.services.token_service import TokenService
from app.domain.enums import RoleEnum

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_SECRET = "test-auth-deps-secret"
_USER_ID = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")


def _make_token_service(
    secret_key: str = _TEST_SECRET,
    access_expire_minutes: int = 30,
    refresh_expire_days: int = 7,
) -> TokenService:
    return TokenService(
        secret_key=secret_key,
        algorithm="HS256",
        access_expire_minutes=access_expire_minutes,
        refresh_expire_days=refresh_expire_days,
    )


# ===================================================================
# Missing Authorization header (Requirement 3.2)
# ===================================================================


class TestMissingAuthorizationHeader:
    """Verify that requests without an Authorization header are rejected."""

    @pytest.mark.anyio
    async def test_none_authorization_raises_401(self):
        """When Authorization header is None, return 401 with 'Token no proporcionado'."""
        ts = _make_token_service()

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(authorization=None, token_service=ts)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Token no proporcionado"


# ===================================================================
# Malformed bearer format (Requirement 3.2)
# ===================================================================


class TestMalformedBearerFormat:
    """Verify that malformed Authorization header values are rejected."""

    @pytest.mark.anyio
    async def test_empty_string_raises_401(self):
        """An empty Authorization header must be rejected."""
        ts = _make_token_service()

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(authorization="", token_service=ts)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Token no proporcionado"

    @pytest.mark.anyio
    async def test_token_without_bearer_prefix_raises_401(self):
        """A raw token without the 'Bearer' prefix must be rejected."""
        ts = _make_token_service()
        token = ts.create_access_token(_USER_ID, RoleEnum.STUDENT)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(authorization=token, token_service=ts)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Token no proporcionado"

    @pytest.mark.anyio
    async def test_wrong_prefix_raises_401(self):
        """A header with a prefix other than 'Bearer' must be rejected."""
        ts = _make_token_service()
        token = ts.create_access_token(_USER_ID, RoleEnum.STUDENT)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(authorization=f"Token {token}", token_service=ts)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Token no proporcionado"

    @pytest.mark.anyio
    async def test_bearer_with_extra_segments_raises_401(self):
        """A header with more than two space-separated parts must be rejected."""
        ts = _make_token_service()
        token = ts.create_access_token(_USER_ID, RoleEnum.STUDENT)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                authorization=f"Bearer {token} extra", token_service=ts
            )

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Token no proporcionado"

    @pytest.mark.anyio
    async def test_bearer_only_no_token_raises_401(self):
        """'Bearer' keyword alone without a token value must be rejected."""
        ts = _make_token_service()

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(authorization="Bearer", token_service=ts)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Token no proporcionado"


# ===================================================================
# Refresh token used as access token (Requirement 3.5)
# ===================================================================


class TestRefreshTokenUsedAsAccess:
    """Verify that refresh tokens are rejected when used as access tokens."""

    @pytest.mark.anyio
    async def test_refresh_token_rejected_with_invalid_message(self):
        """A valid refresh token must not be accepted as an access token."""
        ts = _make_token_service()
        refresh = ts.create_refresh_token(_USER_ID, RoleEnum.STUDENT)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                authorization=f"Bearer {refresh}", token_service=ts
            )

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Token inválido"

    @pytest.mark.anyio
    async def test_refresh_token_for_admin_also_rejected(self):
        """Even an ADMIN refresh token must not be accepted as access."""
        ts = _make_token_service()
        refresh = ts.create_refresh_token(_USER_ID, RoleEnum.ADMIN)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                authorization=f"Bearer {refresh}", token_service=ts
            )

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Token inválido"


# ===================================================================
# Expired token (Requirement 3.3)
# ===================================================================


class TestExpiredToken:
    """Verify that expired tokens produce the correct error message."""

    @pytest.mark.anyio
    async def test_expired_access_token_raises_401_with_expired_message(self):
        """An expired access token must return 'Token expirado'."""
        # Create a service with 0-minute expiration to produce an already-expired token
        ts = _make_token_service(access_expire_minutes=0)
        token = ts.create_access_token(_USER_ID, RoleEnum.STUDENT)

        # Decode with a normal service (the token is already expired)
        normal_ts = _make_token_service()

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                authorization=f"Bearer {token}", token_service=normal_ts
            )

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Token expirado"


# ===================================================================
# Tampered / invalid token (Requirement 3.4)
# ===================================================================


class TestTamperedToken:
    """Verify that tampered or invalid tokens are rejected."""

    @pytest.mark.anyio
    async def test_random_string_raises_401_invalid(self):
        """A random string that is not a JWT must be rejected."""
        ts = _make_token_service()

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                authorization="Bearer not.a.real.jwt", token_service=ts
            )

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Token inválido"

    @pytest.mark.anyio
    async def test_token_signed_with_different_secret_raises_401(self):
        """A token signed with a different secret must be rejected."""
        wrong_ts = _make_token_service(secret_key="wrong-secret")
        token = wrong_ts.create_access_token(_USER_ID, RoleEnum.STUDENT)

        correct_ts = _make_token_service()

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                authorization=f"Bearer {token}", token_service=correct_ts
            )

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Token inválido"


# ===================================================================
# Valid token extraction (Requirement 3.1)
# ===================================================================


class TestValidTokenExtraction:
    """Verify that a valid access token produces the correct CurrentUser."""

    @pytest.mark.anyio
    async def test_valid_access_token_returns_current_user(self):
        """A valid access token must produce a CurrentUser with correct id and role."""
        ts = _make_token_service()
        token = ts.create_access_token(_USER_ID, RoleEnum.STUDENT)

        user = await get_current_user(
            authorization=f"Bearer {token}", token_service=ts
        )

        assert isinstance(user, CurrentUser)
        assert user.id == _USER_ID
        assert user.role == RoleEnum.STUDENT

    @pytest.mark.anyio
    async def test_valid_token_for_each_role(self):
        """Valid tokens for each RoleEnum value must produce matching CurrentUser."""
        ts = _make_token_service()

        for role in RoleEnum:
            token = ts.create_access_token(_USER_ID, role)
            user = await get_current_user(
                authorization=f"Bearer {token}", token_service=ts
            )

            assert user.id == _USER_ID
            assert user.role == role

    @pytest.mark.anyio
    async def test_bearer_prefix_is_case_insensitive(self):
        """The 'Bearer' prefix should be matched case-insensitively."""
        ts = _make_token_service()
        token = ts.create_access_token(_USER_ID, RoleEnum.ADMIN)

        user = await get_current_user(
            authorization=f"bearer {token}", token_service=ts
        )

        assert user.id == _USER_ID
        assert user.role == RoleEnum.ADMIN

    @pytest.mark.anyio
    async def test_valid_token_user_id_is_uuid(self):
        """The returned CurrentUser.id must be a UUID instance."""
        ts = _make_token_service()
        token = ts.create_access_token(_USER_ID, RoleEnum.PROFESSOR)

        user = await get_current_user(
            authorization=f"Bearer {token}", token_service=ts
        )

        assert isinstance(user.id, uuid.UUID)


# ===================================================================
# require_roles dependency (Requirements 5.1, 5.2, 5.4)
# ===================================================================


class TestRequireRoles:
    """Verify the require_roles factory produces correct guard behavior."""

    @pytest.mark.anyio
    async def test_admin_always_passes_regardless_of_allowed_roles(self):
        """ADMIN must always pass the role guard, even if not in the allowed list."""
        guard = require_roles(RoleEnum.PROFESSOR)
        admin_user = CurrentUser(id=_USER_ID, role=RoleEnum.ADMIN)

        result = await guard(current_user=admin_user)

        assert result is admin_user

    @pytest.mark.anyio
    async def test_allowed_role_passes(self):
        """A user whose role is in the allowed list must pass."""
        guard = require_roles(RoleEnum.PROFESSOR, RoleEnum.STUDENT)
        prof_user = CurrentUser(id=_USER_ID, role=RoleEnum.PROFESSOR)

        result = await guard(current_user=prof_user)

        assert result is prof_user

    @pytest.mark.anyio
    async def test_unauthorized_role_raises_403(self):
        """A user whose role is not in the allowed list and is not ADMIN must get 403."""
        guard = require_roles(RoleEnum.ADMIN)
        student_user = CurrentUser(id=_USER_ID, role=RoleEnum.STUDENT)

        with pytest.raises(HTTPException) as exc_info:
            await guard(current_user=student_user)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "No tiene permisos para esta acción"

    @pytest.mark.anyio
    async def test_student_denied_when_only_professor_allowed(self):
        """STUDENT must be denied when only PROFESSOR is allowed."""
        guard = require_roles(RoleEnum.PROFESSOR)
        student_user = CurrentUser(id=_USER_ID, role=RoleEnum.STUDENT)

        with pytest.raises(HTTPException) as exc_info:
            await guard(current_user=student_user)

        assert exc_info.value.status_code == 403

    @pytest.mark.anyio
    async def test_professor_denied_when_only_student_allowed(self):
        """PROFESSOR must be denied when only STUDENT is allowed."""
        guard = require_roles(RoleEnum.STUDENT)
        prof_user = CurrentUser(id=_USER_ID, role=RoleEnum.PROFESSOR)

        with pytest.raises(HTTPException) as exc_info:
            await guard(current_user=prof_user)

        assert exc_info.value.status_code == 403
