"""
Integration tests for program CRUD endpoints.

Tests the full HTTP flow for:
- POST /api/v1/programs   (create, auth, validation, uniqueness)
- PATCH /api/v1/programs/{program_id}  (update, auth, not found)

Requirements: 6.1–6.7, 7.1–7.8, 8.1–8.5
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.domain.enums import RoleEnum
from app.infrastructure.models.program import Program

# Import app after conftest stubs are applied
from app.main import app  # noqa: E402
from app.infrastructure.database import get_session  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_access_token(
    user_id: uuid.UUID | None = None,
    role: RoleEnum = RoleEnum.ADMIN,
) -> str:
    """Create a valid JWT access token for test setup."""
    uid = user_id or uuid.uuid4()
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(uid),
        "role": role.value,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=30)).timestamp()),
    }
    return jwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _make_program(**kwargs) -> Program:
    """Build a Program model instance with sensible defaults."""
    defaults = dict(
        id=uuid.uuid4(),
        institution="USBCO",
        degree_type="PREG",
        program_code=f"P{uuid.uuid4().hex[:6].upper()}",
        program_name="Psicología",
        academic_group="MFPSI",
        location="SAN BENITO",
        snies_code=int(uuid.uuid4().int % 100000),
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    return Program(**defaults)


VALID_PROGRAM_BODY = {
    "institution": "USBCO",
    "degree_type": "PREG",
    "program_code": "M0200",
    "program_name": "Psicología",
    "academic_group": "MFPSI",
    "location": "SAN BENITO",
    "snies_code": 12345,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    """AsyncClient with mocked DB session (no auth override — tests control auth)."""
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
# POST /api/v1/programs — 201 valid creation (Req 6.1, 6.2)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_post_programs_returns_201(client: AsyncClient):
    """Valid POST with ADMIN token returns 201 with created program data."""
    token = _create_access_token(role=RoleEnum.ADMIN)
    created_program = _make_program(
        program_code="M0200", snies_code=12345, program_name="Psicología"
    )

    with patch(
        "app.api.v1.endpoints.programs.ProgramService.create_program",
        new_callable=AsyncMock,
        return_value=created_program,
    ):
        response = await client.post(
            "/api/v1/programs",
            json=VALID_PROGRAM_BODY,
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["program_code"] == "M0200"
    assert body["snies_code"] == 12345
    assert "id" in body
    assert "created_at" in body


# ---------------------------------------------------------------------------
# PATCH /api/v1/programs/{id} — 200 valid update (Req 7.1, 7.2)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_patch_programs_returns_200(client: AsyncClient):
    """Valid PATCH with ADMIN token returns 200 with updated program data."""
    token = _create_access_token(role=RoleEnum.ADMIN)
    prog_id = uuid.uuid4()
    updated_program = _make_program(
        id=prog_id, program_name="Psicología Clínica"
    )

    with patch(
        "app.api.v1.endpoints.programs.ProgramService.update_program",
        new_callable=AsyncMock,
        return_value=updated_program,
    ):
        response = await client.patch(
            f"/api/v1/programs/{prog_id}",
            json={"program_name": "Psicología Clínica"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["program_name"] == "Psicología Clínica"
    assert body["id"] == str(prog_id)


# ---------------------------------------------------------------------------
# POST /api/v1/programs — 401 no auth (Req 6.3, 6.5)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_post_programs_no_auth_returns_401(client: AsyncClient):
    """POST without Authorization header returns 401."""
    response = await client.post(
        "/api/v1/programs",
        json=VALID_PROGRAM_BODY,
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Token no proporcionado"


# ---------------------------------------------------------------------------
# POST /api/v1/programs — 403 non-ADMIN (Req 6.4, 6.6)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_post_programs_non_admin_returns_403(client: AsyncClient):
    """POST with STUDENT token returns 403."""
    token = _create_access_token(role=RoleEnum.STUDENT)

    response = await client.post(
        "/api/v1/programs",
        json=VALID_PROGRAM_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "No tiene permisos para esta acción"


# ---------------------------------------------------------------------------
# PATCH /api/v1/programs/{id} — 404 not found (Req 7.3)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_patch_programs_not_found_returns_404(client: AsyncClient):
    """PATCH for non-existent program returns 404."""
    from fastapi import HTTPException

    token = _create_access_token(role=RoleEnum.ADMIN)
    prog_id = uuid.uuid4()

    with patch(
        "app.api.v1.endpoints.programs.ProgramService.update_program",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=404, detail="Programa no encontrado"),
    ):
        response = await client.patch(
            f"/api/v1/programs/{prog_id}",
            json={"program_name": "Nuevo Nombre"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Programa no encontrado"


# ---------------------------------------------------------------------------
# POST /api/v1/programs — 409 duplicate program_code (Req 8.1)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_post_programs_duplicate_program_code_returns_409(client: AsyncClient):
    """POST with duplicate program_code returns 409."""
    from fastapi import HTTPException

    token = _create_access_token(role=RoleEnum.ADMIN)

    with patch(
        "app.api.v1.endpoints.programs.ProgramService.create_program",
        new_callable=AsyncMock,
        side_effect=HTTPException(
            status_code=409, detail="El program_code ya está registrado"
        ),
    ):
        response = await client.post(
            "/api/v1/programs",
            json=VALID_PROGRAM_BODY,
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "El program_code ya está registrado"


# ---------------------------------------------------------------------------
# POST /api/v1/programs — 422 missing field (Req 1.2)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_post_programs_missing_field_returns_422(client: AsyncClient):
    """POST with missing required field returns 422."""
    token = _create_access_token(role=RoleEnum.ADMIN)
    incomplete_body = {
        "institution": "USBCO",
        "degree_type": "PREG",
        # program_code missing
        "program_name": "Psicología",
        "academic_group": "MFPSI",
        "location": "SAN BENITO",
        "snies_code": 12345,
    }

    response = await client.post(
        "/api/v1/programs",
        json=incomplete_body,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422
