"""
Integration tests for protected endpoint enforcement.

Verifies that:
- All ``/api/v1/users`` endpoints return HTTP 401 without a valid token.
- Public endpoints (``/health``, ``/``, ``/api/v1/auth/login``,
  ``/api/v1/auth/refresh``) remain accessible without authentication.

Requirements: 6.1, 6.6, 6.7
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.domain.enums import RoleEnum

# Import app after conftest stubs are applied
from app.main import app  # noqa: E402
from app.infrastructure.database import get_session  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DUMMY_USER_ID = uuid.uuid4()


def _create_access_token(
    user_id: uuid.UUID = _DUMMY_USER_ID,
    role: RoleEnum = RoleEnum.ADMIN,
) -> str:
    """Create a valid access token for test setup."""
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user_id),
        "role": role.value,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=30)).timestamp()),
    }
    return jwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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


# ===========================================================================
# Protected endpoints — must return 401 without a token (Req 6.1)
# ===========================================================================


@pytest.mark.anyio
async def test_get_users_without_token_returns_401(client: AsyncClient):
    """GET /api/v1/users without Authorization header returns 401."""
    response = await client.get("/api/v1/users")

    assert response.status_code == 401
    assert response.json()["detail"] == "Token no proporcionado"


@pytest.mark.anyio
async def test_post_users_without_token_returns_401(client: AsyncClient):
    """POST /api/v1/users without Authorization header returns 401."""
    response = await client.post(
        "/api/v1/users",
        json={
            "email": "nuevo@uni.edu",
            "password": "segura123",
            "full_name": "Test User",
            "role": "STUDENT",
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Token no proporcionado"


@pytest.mark.anyio
async def test_get_user_by_id_without_token_returns_401(client: AsyncClient):
    """GET /api/v1/users/{user_id} without Authorization header returns 401."""
    user_id = uuid.uuid4()
    response = await client.get(f"/api/v1/users/{user_id}")

    assert response.status_code == 401
    assert response.json()["detail"] == "Token no proporcionado"


@pytest.mark.anyio
async def test_patch_user_without_token_returns_401(client: AsyncClient):
    """PATCH /api/v1/users/{user_id} without Authorization header returns 401."""
    user_id = uuid.uuid4()
    response = await client.patch(
        f"/api/v1/users/{user_id}",
        json={"full_name": "Updated Name"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Token no proporcionado"


@pytest.mark.anyio
async def test_patch_user_status_without_token_returns_401(client: AsyncClient):
    """PATCH /api/v1/users/{user_id}/status without Authorization header returns 401."""
    user_id = uuid.uuid4()
    response = await client.patch(
        f"/api/v1/users/{user_id}/status",
        json={"status": "INACTIVE"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Token no proporcionado"


# ===========================================================================
# Protected endpoints — invalid tokens also rejected (Req 6.1)
# ===========================================================================


@pytest.mark.anyio
async def test_get_users_with_invalid_token_returns_401(client: AsyncClient):
    """GET /api/v1/users with a garbage token returns 401."""
    response = await client.get(
        "/api/v1/users",
        headers={"Authorization": "Bearer not-a-real-token"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Token inválido"


@pytest.mark.anyio
async def test_get_users_with_malformed_auth_header_returns_401(client: AsyncClient):
    """GET /api/v1/users with a malformed Authorization header returns 401."""
    response = await client.get(
        "/api/v1/users",
        headers={"Authorization": "Token abc123"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Token no proporcionado"


# ===========================================================================
# Public endpoints — accessible without authentication (Req 6.6, 6.7)
# ===========================================================================


@pytest.mark.anyio
async def test_root_endpoint_is_public(client: AsyncClient):
    """GET / is accessible without authentication."""
    response = await client.get("/")

    assert response.status_code == 200
    body = response.json()
    assert "mensaje" in body
    assert "version" in body


@pytest.mark.anyio
async def test_health_endpoint_is_public(client: AsyncClient):
    """GET /health is accessible without authentication."""
    response = await client.get("/health")

    # Health check may return 200 or 503 depending on DB mock state,
    # but it should NOT return 401 (authentication not required).
    assert response.status_code != 401
    body = response.json()
    assert "status" in body


@pytest.mark.anyio
async def test_login_endpoint_is_public(client: AsyncClient):
    """POST /api/v1/auth/login is accessible without authentication."""
    # Even though credentials are wrong, we should get a 401 from AuthService
    # (credential failure), NOT from the auth middleware.
    from app.domain.exceptions import AuthenticationError

    with patch(
        "app.infrastructure.auth.credential_provider.CredentialAuthProvider.authenticate",
        new_callable=AsyncMock,
        side_effect=AuthenticationError("Credenciales inválidas", 401),
    ):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "test@uni.edu", "password": "whatever"},
        )

    # 401 from credential failure is fine — the point is that the endpoint
    # didn't reject us for a missing Bearer token.
    assert response.status_code == 401
    assert response.json()["detail"] == "Credenciales inválidas"


@pytest.mark.anyio
async def test_refresh_endpoint_is_public(client: AsyncClient):
    """POST /api/v1/auth/refresh is accessible without authentication."""
    # Submit a garbage refresh token — we should get a token validation error,
    # NOT a "Token no proporcionado" middleware rejection.
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "not-a-valid-token"},
    )

    assert response.status_code == 401
    # The error comes from TokenService (invalid token), not auth middleware
    assert response.json()["detail"] == "Token inválido"
