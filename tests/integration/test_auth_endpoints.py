"""
Integration tests for authentication endpoints.

Tests the full HTTP flow for:
- POST /api/v1/auth/login   (login success, invalid credentials, inactive user)
- POST /api/v1/auth/refresh (refresh success, expired token, access token misuse)
- POST /api/v1/auth/logout  (with valid token, without token)

Requirements: 1.1, 1.2, 1.3, 1.4, 4.1, 4.2, 4.3, 9.1
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.security import hash_password
from app.domain.enums import RoleEnum, UserStatusEnum
from app.infrastructure.models.user import User


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(
    *,
    user_id: uuid.UUID | None = None,
    email: str = "profesor@uni.edu",
    password: str = "segura123",
    role: RoleEnum = RoleEnum.PROFESSOR,
    status: UserStatusEnum = UserStatusEnum.ACTIVE,
    password_hash: str | None = None,
) -> User:
    """Build a User model instance with a bcrypt password hash."""
    uid = user_id or uuid.uuid4()
    return User(
        id=uid,
        email=email,
        full_name="Test User",
        role=role,
        status=status,
        password_hash=password_hash or hash_password(password),
        ml_consent=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _create_token(
    user_id: uuid.UUID,
    role: RoleEnum,
    token_type: str = "access",
    expire_delta: timedelta | None = None,
) -> str:
    """Create a JWT token directly for test setup."""
    now = datetime.now(timezone.utc)
    if expire_delta is None:
        expire_delta = timedelta(minutes=30) if token_type == "access" else timedelta(days=7)
    claims = {
        "sub": str(user_id),
        "role": role.value,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expire_delta).timestamp()),
    }
    return jwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _create_expired_token(
    user_id: uuid.UUID,
    role: RoleEnum,
    token_type: str = "refresh",
) -> str:
    """Create an already-expired JWT token."""
    return _create_token(
        user_id, role, token_type, expire_delta=timedelta(seconds=-10)
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

# Import app after conftest stubs are applied (conftest.py stubs heavy deps)
from app.main import app  # noqa: E402
from app.infrastructure.database import get_session  # noqa: E402


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    """AsyncClient with mocked DB session."""
    mock_session = AsyncMock()

    async def _override_get_session():
        yield mock_session

    app.dependency_overrides[get_session] = _override_get_session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# POST /api/v1/auth/login — Success (Req 1.1)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_login_success(client: AsyncClient):
    """Valid email + password returns 200 with access and refresh tokens."""
    user = _make_user(email="admin@uni.edu", password="pass123", role=RoleEnum.ADMIN)

    with patch(
        "app.infrastructure.auth.credential_provider.CredentialAuthProvider.authenticate",
        new_callable=AsyncMock,
        return_value=user,
    ):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@uni.edu", "password": "pass123"},
        )

    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    # Decode access token and verify claims match the user
    decoded = jwt.decode(
        body["access_token"],
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
    assert decoded["sub"] == str(user.id)
    assert decoded["role"] == RoleEnum.ADMIN.value
    assert decoded["type"] == "access"


# ---------------------------------------------------------------------------
# POST /api/v1/auth/login — Non-existent email (Req 1.2)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_login_nonexistent_email(client: AsyncClient):
    """Non-existent email returns 401 with generic error message."""
    from app.domain.exceptions import AuthenticationError

    with patch(
        "app.infrastructure.auth.credential_provider.CredentialAuthProvider.authenticate",
        new_callable=AsyncMock,
        side_effect=AuthenticationError("Credenciales inválidas", 401),
    ):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "noexiste@uni.edu", "password": "whatever"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Credenciales inválidas"


# ---------------------------------------------------------------------------
# POST /api/v1/auth/login — Wrong password (Req 1.3)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_login_wrong_password(client: AsyncClient):
    """Valid email with wrong password returns 401 with generic error."""
    from app.domain.exceptions import AuthenticationError

    with patch(
        "app.infrastructure.auth.credential_provider.CredentialAuthProvider.authenticate",
        new_callable=AsyncMock,
        side_effect=AuthenticationError("Credenciales inválidas", 401),
    ):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "admin@uni.edu", "password": "wrongpass"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Credenciales inválidas"


# ---------------------------------------------------------------------------
# POST /api/v1/auth/login — Inactive user (Req 1.4)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_login_inactive_user(client: AsyncClient):
    """Inactive user returns 403 with 'Cuenta desactivada'."""
    user = _make_user(
        email="inactivo@uni.edu",
        password="pass123",
        status=UserStatusEnum.INACTIVE,
    )

    with patch(
        "app.infrastructure.auth.credential_provider.CredentialAuthProvider.authenticate",
        new_callable=AsyncMock,
        return_value=user,
    ):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "inactivo@uni.edu", "password": "pass123"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Cuenta desactivada"


# ---------------------------------------------------------------------------
# POST /api/v1/auth/login — SSO-only user (no password_hash) (Req 1.5)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_login_sso_only_user(client: AsyncClient):
    """SSO-only user (no password_hash) returns 401."""
    from app.domain.exceptions import AuthenticationError

    with patch(
        "app.infrastructure.auth.credential_provider.CredentialAuthProvider.authenticate",
        new_callable=AsyncMock,
        side_effect=AuthenticationError("Credenciales inválidas", 401),
    ):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "sso@uni.edu", "password": "anypass"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Credenciales inválidas"


# ---------------------------------------------------------------------------
# POST /api/v1/auth/refresh — Success (Req 4.1)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_refresh_success(client: AsyncClient):
    """Valid refresh token returns 200 with a new token pair."""
    user_id = uuid.uuid4()
    refresh_token = _create_token(user_id, RoleEnum.STUDENT, token_type="refresh")

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    # Verify the new access token has the correct sub
    decoded = jwt.decode(
        body["access_token"],
        settings.JWT_SECRET_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )
    assert decoded["sub"] == str(user_id)
    assert decoded["type"] == "access"


# ---------------------------------------------------------------------------
# POST /api/v1/auth/refresh — Expired refresh token (Req 4.2)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_refresh_expired_token(client: AsyncClient):
    """Expired refresh token returns 401."""
    user_id = uuid.uuid4()
    expired_token = _create_expired_token(user_id, RoleEnum.STUDENT, "refresh")

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": expired_token},
    )

    assert response.status_code == 401
    # TokenExpiredError message
    assert response.json()["detail"] == "Token expirado"


# ---------------------------------------------------------------------------
# POST /api/v1/auth/refresh — Access token used as refresh (Req 4.3)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_refresh_with_access_token(client: AsyncClient):
    """Access token submitted as refresh token returns 401."""
    user_id = uuid.uuid4()
    access_token = _create_token(user_id, RoleEnum.ADMIN, token_type="access")

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": access_token},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Token inválido"


# ---------------------------------------------------------------------------
# POST /api/v1/auth/refresh — Invalid signature (Req 4.4)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_refresh_invalid_signature(client: AsyncClient):
    """Refresh token signed with wrong key returns 401."""
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(uuid.uuid4()),
        "role": RoleEnum.STUDENT.value,
        "type": "refresh",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=7)).timestamp()),
    }
    bad_token = jwt.encode(claims, "wrong-secret-key", algorithm="HS256")

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": bad_token},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Token inválido"


# ---------------------------------------------------------------------------
# POST /api/v1/auth/logout — With valid token (Req 9.1)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_logout_with_valid_token(client: AsyncClient):
    """Logout with valid access token returns 200 with confirmation message."""
    user_id = uuid.uuid4()
    access_token = _create_token(user_id, RoleEnum.PROFESSOR, token_type="access")

    response = await client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Sesión cerrada exitosamente"


# ---------------------------------------------------------------------------
# POST /api/v1/auth/logout — Without token (Req 3.2)
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_logout_without_token(client: AsyncClient):
    """Logout without Authorization header returns 401."""
    response = await client.post("/api/v1/auth/logout")

    assert response.status_code == 401
    assert response.json()["detail"] == "Token no proporcionado"
