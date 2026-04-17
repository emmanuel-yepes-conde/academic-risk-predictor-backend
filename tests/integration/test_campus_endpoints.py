"""
Integration tests for campus endpoints.

Tests the full HTTP flow for:
- POST   /api/v1/universities/{uid}/campuses                              (create)
- GET    /api/v1/universities/{uid}/campuses                              (list)
- GET    /api/v1/universities/{uid}/campuses/{cid}                        (get by id)
- PATCH  /api/v1/universities/{uid}/campuses/{cid}                        (update)
- GET    /api/v1/universities/{uid}/campuses/{cid}/programs               (programs by campus)
- GET    /api/v1/universities/{uid}/campuses/{cid}/programs/{pid}/courses  (hierarchical courses)
- GET    /api/v1/universities/{uid}/programs                              (legacy endpoint)

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 4.1, 4.2, 4.3, 4.4, 4.5
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient

from app.application.schemas.campus import CampusRead
from app.application.schemas.course import CourseRead
from app.application.schemas.program import ProgramRead
from app.application.schemas.user import PaginatedResponse
from app.core.config import settings
from app.domain.enums import RoleEnum

# Import app after conftest stubs are applied
from app.main import app  # noqa: E402
from app.infrastructure.database import get_session  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ADMIN_ID = uuid.uuid4()
STUDENT_ID = uuid.uuid4()
UNIVERSITY_ID = uuid.uuid4()
CAMPUS_ID = uuid.uuid4()
PROGRAM_ID = uuid.uuid4()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _create_access_token(user_id: uuid.UUID, role: RoleEnum) -> str:
    """Create a valid JWT access token."""
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user_id),
        "role": role.value,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=30)).timestamp()),
    }
    return jwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _sample_campus_read(**overrides) -> CampusRead:
    defaults = dict(
        id=CAMPUS_ID,
        university_id=UNIVERSITY_ID,
        campus_code="MED",
        name="Sede Medellín",
        city="Medellín",
        active=True,
        created_at=_now(),
    )
    defaults.update(overrides)
    return CampusRead(**defaults)


def _sample_program_read(**overrides) -> ProgramRead:
    defaults = dict(
        id=PROGRAM_ID,
        university_id=UNIVERSITY_ID,
        campus_id=CAMPUS_ID,
        institution="USBCO",
        degree_type="PREG",
        program_code="PSI01",
        program_name="Psicología",
        pensum="PEN2024",
        academic_group="MFPSI",
        location="SAN BENITO",
        snies_code=12345,
        created_at=_now(),
    )
    defaults.update(overrides)
    return ProgramRead(**defaults)


def _sample_course_read(**overrides) -> CourseRead:
    defaults = dict(
        id=uuid.uuid4(),
        code="CS101",
        name="Intro to CS",
        credits=3,
        academic_period="2024-1",
        created_at=_now(),
    )
    defaults.update(overrides)
    return CourseRead(**defaults)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def admin_token() -> str:
    return _create_access_token(ADMIN_ID, RoleEnum.ADMIN)


@pytest.fixture
def student_token() -> str:
    return _create_access_token(STUDENT_ID, RoleEnum.STUDENT)


@pytest.fixture
async def client():
    """AsyncClient with mocked DB session (no real DB)."""
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
# POST /api/v1/universities/{uid}/campuses — 201 with valid data (Req 2.1)
# ===========================================================================


@pytest.mark.anyio
async def test_create_campus_returns_201(client: AsyncClient, admin_token: str):
    """POST campus with valid data and ADMIN role returns 201."""
    campus = _sample_campus_read()

    with patch(
        "app.application.services.campus_service.CampusService.create",
        new_callable=AsyncMock,
        return_value=campus,
    ):
        response = await client.post(
            f"/api/v1/universities/{UNIVERSITY_ID}/campuses",
            json={
                "campus_code": "MED",
                "name": "Sede Medellín",
                "city": "Medellín",
                "active": True,
            },
            headers=_auth_header(admin_token),
        )

    assert response.status_code == 201
    body = response.json()
    assert body["campus_code"] == "MED"
    assert body["name"] == "Sede Medellín"
    assert body["university_id"] == str(UNIVERSITY_ID)


# ===========================================================================
# POST campus — 404 if university doesn't exist (Req 2.2)
# ===========================================================================


@pytest.mark.anyio
async def test_create_campus_university_not_found_returns_404(
    client: AsyncClient, admin_token: str
):
    """POST campus returns 404 when university_id doesn't exist."""
    with patch(
        "app.application.services.campus_service.CampusService.create",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=404, detail="Universidad no encontrada"),
    ):
        response = await client.post(
            f"/api/v1/universities/{uuid.uuid4()}/campuses",
            json={
                "campus_code": "BOG",
                "name": "Sede Bogotá",
                "city": "Bogotá",
            },
            headers=_auth_header(admin_token),
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Universidad no encontrada"


# ===========================================================================
# POST campus — 409 if duplicate combination (Req 2.3)
# ===========================================================================


@pytest.mark.anyio
async def test_create_campus_duplicate_returns_409(
    client: AsyncClient, admin_token: str
):
    """POST campus returns 409 when university_id + campus_code already exists."""
    with patch(
        "app.application.services.campus_service.CampusService.create",
        new_callable=AsyncMock,
        side_effect=HTTPException(
            status_code=409,
            detail="La combinación university_id + campus_code ya existe",
        ),
    ):
        response = await client.post(
            f"/api/v1/universities/{UNIVERSITY_ID}/campuses",
            json={
                "campus_code": "MED",
                "name": "Sede Medellín",
                "city": "Medellín",
            },
            headers=_auth_header(admin_token),
        )

    assert response.status_code == 409
    assert "ya existe" in response.json()["detail"]


# ===========================================================================
# POST campus — 403 if not ADMIN (Req 2.7)
# ===========================================================================


@pytest.mark.anyio
async def test_create_campus_non_admin_returns_403(
    client: AsyncClient, student_token: str
):
    """POST campus returns 403 when the caller is not ADMIN."""
    with patch(
        "app.application.services.campus_service.CampusService.create",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=403, detail="Se requiere rol ADMIN"),
    ):
        response = await client.post(
            f"/api/v1/universities/{UNIVERSITY_ID}/campuses",
            json={
                "campus_code": "CAL",
                "name": "Sede Cali",
                "city": "Cali",
            },
            headers=_auth_header(student_token),
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Se requiere rol ADMIN"


# ===========================================================================
# GET /api/v1/universities/{uid}/campuses — paginated list (Req 2.4)
# ===========================================================================


@pytest.mark.anyio
async def test_list_campuses_returns_paginated(client: AsyncClient):
    """GET campuses returns a paginated list."""
    campus1 = _sample_campus_read(campus_code="MED", name="Sede Medellín")
    campus2 = _sample_campus_read(
        id=uuid.uuid4(), campus_code="BOG", name="Sede Bogotá"
    )
    paginated = PaginatedResponse[CampusRead](
        data=[campus1, campus2], total=2, skip=0, limit=20
    )

    with patch(
        "app.application.services.campus_service.CampusService.list_by_university",
        new_callable=AsyncMock,
        return_value=paginated,
    ):
        response = await client.get(
            f"/api/v1/universities/{UNIVERSITY_ID}/campuses?skip=0&limit=20"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 2
    assert len(body["data"]) == 2
    assert body["skip"] == 0
    assert body["limit"] == 20


# ===========================================================================
# GET /api/v1/universities/{uid}/campuses/{cid} — 200 or 404 (Req 2.5)
# ===========================================================================


@pytest.mark.anyio
async def test_get_campus_by_id_returns_200(client: AsyncClient):
    """GET campus by ID returns 200 with campus data."""
    campus = _sample_campus_read()

    with patch(
        "app.application.services.campus_service.CampusService.get",
        new_callable=AsyncMock,
        return_value=campus,
    ):
        response = await client.get(
            f"/api/v1/universities/{UNIVERSITY_ID}/campuses/{CAMPUS_ID}"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(CAMPUS_ID)
    assert body["campus_code"] == "MED"


@pytest.mark.anyio
async def test_get_campus_by_id_not_found_returns_404(client: AsyncClient):
    """GET campus by ID returns 404 when campus doesn't exist."""
    with patch(
        "app.application.services.campus_service.CampusService.get",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=404, detail="Campus no encontrado"),
    ):
        response = await client.get(
            f"/api/v1/universities/{UNIVERSITY_ID}/campuses/{uuid.uuid4()}"
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Campus no encontrado"


# ===========================================================================
# PATCH /api/v1/universities/{uid}/campuses/{cid} — 200 (Req 2.6)
# ===========================================================================


@pytest.mark.anyio
async def test_update_campus_returns_200(client: AsyncClient, admin_token: str):
    """PATCH campus returns 200 with updated fields."""
    updated = _sample_campus_read(name="Sede Medellín Actualizada", active=False)

    with patch(
        "app.application.services.campus_service.CampusService.update",
        new_callable=AsyncMock,
        return_value=updated,
    ):
        response = await client.patch(
            f"/api/v1/universities/{UNIVERSITY_ID}/campuses/{CAMPUS_ID}",
            json={"name": "Sede Medellín Actualizada", "active": False},
            headers=_auth_header(admin_token),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Sede Medellín Actualizada"
    assert body["active"] is False


# ===========================================================================
# GET .../campuses/{cid}/programs — filtered list (Req 4.1)
# ===========================================================================


@pytest.mark.anyio
async def test_list_programs_by_campus_returns_paginated(client: AsyncClient):
    """GET programs by campus returns a paginated list."""
    program = _sample_program_read()
    paginated = PaginatedResponse[ProgramRead](
        data=[program], total=1, skip=0, limit=20
    )

    with patch(
        "app.application.services.campus_service.CampusService.list_programs_by_campus",
        new_callable=AsyncMock,
        return_value=paginated,
    ):
        response = await client.get(
            f"/api/v1/universities/{UNIVERSITY_ID}/campuses/{CAMPUS_ID}/programs"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["data"]) == 1
    assert body["data"][0]["program_code"] == "PSI01"
    assert body["data"][0]["campus_id"] == str(CAMPUS_ID)


# ===========================================================================
# GET .../campuses/{cid}/programs/{pid}/courses — 404 if invalid chain (Req 4.2, 4.3, 4.4)
# ===========================================================================


@pytest.mark.anyio
async def test_hierarchical_courses_returns_200(client: AsyncClient):
    """GET courses by campus and program returns list when chain is valid."""
    course = _sample_course_read()

    with patch(
        "app.application.services.campus_service.CampusService.list_courses_by_campus_and_program",
        new_callable=AsyncMock,
        return_value=[course],
    ):
        response = await client.get(
            f"/api/v1/universities/{UNIVERSITY_ID}/campuses/{CAMPUS_ID}"
            f"/programs/{PROGRAM_ID}/courses"
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["code"] == "CS101"


@pytest.mark.anyio
async def test_hierarchical_courses_invalid_chain_returns_404(client: AsyncClient):
    """GET courses returns 404 when campus doesn't belong to university."""
    with patch(
        "app.application.services.campus_service.CampusService.list_courses_by_campus_and_program",
        new_callable=AsyncMock,
        side_effect=HTTPException(
            status_code=404,
            detail="El campus no pertenece a la universidad indicada",
        ),
    ):
        response = await client.get(
            f"/api/v1/universities/{UNIVERSITY_ID}/campuses/{uuid.uuid4()}"
            f"/programs/{PROGRAM_ID}/courses"
        )

    assert response.status_code == 404
    assert "no pertenece" in response.json()["detail"]


@pytest.mark.anyio
async def test_hierarchical_courses_program_not_in_campus_returns_404(
    client: AsyncClient,
):
    """GET courses returns 404 when program doesn't belong to campus."""
    with patch(
        "app.application.services.campus_service.CampusService.list_courses_by_campus_and_program",
        new_callable=AsyncMock,
        side_effect=HTTPException(
            status_code=404,
            detail="El programa no pertenece al campus indicado",
        ),
    ):
        response = await client.get(
            f"/api/v1/universities/{UNIVERSITY_ID}/campuses/{CAMPUS_ID}"
            f"/programs/{uuid.uuid4()}/courses"
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "El programa no pertenece al campus indicado"


# ===========================================================================
# GET /api/v1/universities/{uid}/programs — legacy endpoint (Req 4.5)
# ===========================================================================


@pytest.mark.anyio
async def test_legacy_programs_by_university_returns_200(client: AsyncClient):
    """GET /universities/{id}/programs legacy endpoint still works."""
    program = _sample_program_read()

    mock_session = AsyncMock()

    # Mock execute to return count and program list
    call_count = 0

    async def _mock_execute(stmt, *args, **kwargs):
        nonlocal call_count
        from unittest.mock import MagicMock

        result = MagicMock()
        call_count += 1
        if call_count <= 2:
            # First two calls are count queries
            result.scalar_one.return_value = 1
        else:
            # Third call is the data query
            mock_program = MagicMock()
            for field in [
                "id", "university_id", "campus_id", "institution",
                "degree_type", "program_code", "program_name", "pensum",
                "academic_group", "location", "snies_code", "created_at",
            ]:
                setattr(mock_program, field, getattr(program, field))
            result.scalars.return_value.all.return_value = [mock_program]
        return result

    mock_session.execute = AsyncMock(side_effect=_mock_execute)

    async def _override_get_session():
        yield mock_session

    app.dependency_overrides[get_session] = _override_get_session

    response = await client.get(
        f"/api/v1/universities/{UNIVERSITY_ID}/programs?skip=0&limit=20"
    )

    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert "total" in body
