"""
Integration tests for course CRUD endpoints.

Tests the full HTTP flow for:
- GET /api/v1/courses          (list, auth, default filter)
- GET /api/v1/courses/{id}     (get by id, auth, not found)
- POST /api/v1/courses         (create, auth, validation, uniqueness)
- PATCH /api/v1/courses/{id}   (update, auth, not found)
- PATCH /api/v1/courses/{id}/status  (status change, auth, not found)

Requirements: 7.1–7.6, 8.1–8.5, 9.1–9.7, 10.1–10.8, 11.1–11.8, 12.1–12.3
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.domain.enums import CourseStatusEnum, RoleEnum
from app.infrastructure.models.course import Course
from app.main import app
from app.infrastructure.database import get_session


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


def _make_course(**kwargs) -> Course:
    """Build a Course model instance with sensible defaults."""
    defaults = dict(
        id=uuid.uuid4(),
        code=f"CS{uuid.uuid4().hex[:4].upper()}",
        name="Test Course",
        credits=3,
        academic_period="2024-1",
        program_id=uuid.uuid4(),
        status=CourseStatusEnum.ACTIVE,
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    return Course(**defaults)


VALID_COURSE_BODY = {
    "code": "MAT101",
    "name": "Cálculo I",
    "credits": 4,
    "academic_period": "2024-1",
    "program_id": str(uuid.uuid4()),
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
# GET /api/v1/courses — 200 list with auth (Req 7.1, 7.4, 7.5)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_get_courses_returns_200(client: AsyncClient):
    """Valid GET with auth token returns 200 with paginated response."""
    token = _create_access_token(role=RoleEnum.ADMIN)
    course = _make_course()

    with patch(
        "app.api.v1.endpoints.courses.CourseService.list_courses",
        new_callable=AsyncMock,
    ) as mock_list:
        from app.application.schemas.user import PaginatedResponse
        from app.application.schemas.course import CourseRead

        mock_list.return_value = PaginatedResponse[CourseRead](
            data=[CourseRead.model_validate(course)],
            total=1,
            skip=0,
            limit=20,
        )
        response = await client.get(
            "/api/v1/courses",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert "data" in body
    assert body["total"] == 1
    assert len(body["data"]) == 1


# ---------------------------------------------------------------------------
# GET /api/v1/courses — default ACTIVE filter (Req 7.3)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_get_courses_default_active_filter(client: AsyncClient):
    """GET without status param passes None to service (service defaults to ACTIVE)."""
    token = _create_access_token(role=RoleEnum.ADMIN)

    with patch(
        "app.api.v1.endpoints.courses.CourseService.list_courses",
        new_callable=AsyncMock,
    ) as mock_list:
        from app.application.schemas.user import PaginatedResponse
        from app.application.schemas.course import CourseRead

        mock_list.return_value = PaginatedResponse[CourseRead](
            data=[], total=0, skip=0, limit=20,
        )
        await client.get(
            "/api/v1/courses",
            headers={"Authorization": f"Bearer {token}"},
        )

    # The endpoint passes status=None; the service applies ACTIVE default
    mock_list.assert_called_once()
    call_args = mock_list.call_args
    assert call_args[0][0] is None or call_args[1].get("status") is None


# ---------------------------------------------------------------------------
# GET /api/v1/courses/{id} — 200 (Req 8.1, 8.2)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_get_course_by_id_returns_200(client: AsyncClient):
    """Valid GET by ID with auth returns 200 with course data."""
    token = _create_access_token(role=RoleEnum.ADMIN)
    course = _make_course()

    with patch(
        "app.api.v1.endpoints.courses.CourseService.get_course",
        new_callable=AsyncMock,
    ) as mock_get:
        from app.application.schemas.course import CourseRead

        mock_get.return_value = CourseRead.model_validate(course)
        response = await client.get(
            f"/api/v1/courses/{course.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(course.id)
    assert body["code"] == course.code


# ---------------------------------------------------------------------------
# GET /api/v1/courses/{id} — 404 not found (Req 8.3)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_get_course_by_id_not_found_returns_404(client: AsyncClient):
    """GET for non-existent course returns 404."""
    from fastapi import HTTPException

    token = _create_access_token(role=RoleEnum.ADMIN)
    course_id = uuid.uuid4()

    with patch(
        "app.api.v1.endpoints.courses.CourseService.get_course",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=404, detail="Curso no encontrado"),
    ):
        response = await client.get(
            f"/api/v1/courses/{course_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Curso no encontrado"


# ---------------------------------------------------------------------------
# POST /api/v1/courses — 201 valid creation (Req 9.1, 9.2)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_post_courses_returns_201(client: AsyncClient):
    """Valid POST with ADMIN token returns 201 with created course data."""
    token = _create_access_token(role=RoleEnum.ADMIN)
    created_course = _make_course(code="MAT101", name="Cálculo I", credits=4)

    with patch(
        "app.api.v1.endpoints.courses.CourseService.create_course",
        new_callable=AsyncMock,
    ) as mock_create:
        from app.application.schemas.course import CourseRead

        mock_create.return_value = CourseRead.model_validate(created_course)
        response = await client.post(
            "/api/v1/courses",
            json=VALID_COURSE_BODY,
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["code"] == "MAT101"
    assert "id" in body


# ---------------------------------------------------------------------------
# POST /api/v1/courses — 409 duplicate code (Req 12.1)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_post_courses_duplicate_code_returns_409(client: AsyncClient):
    """POST with duplicate code returns 409."""
    from fastapi import HTTPException

    token = _create_access_token(role=RoleEnum.ADMIN)

    with patch(
        "app.api.v1.endpoints.courses.CourseService.create_course",
        new_callable=AsyncMock,
        side_effect=HTTPException(
            status_code=409, detail="El code ya está registrado"
        ),
    ):
        response = await client.post(
            "/api/v1/courses",
            json=VALID_COURSE_BODY,
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "El code ya está registrado"


# ---------------------------------------------------------------------------
# POST /api/v1/courses — 422 missing field (Req 1.2)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_post_courses_missing_field_returns_422(client: AsyncClient):
    """POST with missing required field returns 422."""
    token = _create_access_token(role=RoleEnum.ADMIN)
    incomplete_body = {
        "code": "MAT101",
        "name": "Cálculo I",
        # credits missing
        "academic_period": "2024-1",
        "program_id": str(uuid.uuid4()),
    }

    response = await client.post(
        "/api/v1/courses",
        json=incomplete_body,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/v1/courses — 401 no auth (Req 9.3, 9.5)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_post_courses_no_auth_returns_401(client: AsyncClient):
    """POST without Authorization header returns 401."""
    response = await client.post(
        "/api/v1/courses",
        json=VALID_COURSE_BODY,
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Token no proporcionado"


# ---------------------------------------------------------------------------
# POST /api/v1/courses — 403 non-ADMIN (Req 9.4, 9.6)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_post_courses_non_admin_returns_403(client: AsyncClient):
    """POST with STUDENT token returns 403."""
    token = _create_access_token(role=RoleEnum.STUDENT)

    response = await client.post(
        "/api/v1/courses",
        json=VALID_COURSE_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "No tiene permisos para esta acción"


# ---------------------------------------------------------------------------
# PATCH /api/v1/courses/{id} — 200 valid update (Req 10.1, 10.2)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_patch_course_returns_200(client: AsyncClient):
    """Valid PATCH with ADMIN token returns 200 with updated course data."""
    token = _create_access_token(role=RoleEnum.ADMIN)
    course_id = uuid.uuid4()
    updated_course = _make_course(id=course_id, name="Cálculo Diferencial")

    with patch(
        "app.api.v1.endpoints.courses.CourseService.update_course",
        new_callable=AsyncMock,
    ) as mock_update:
        from app.application.schemas.course import CourseRead

        mock_update.return_value = CourseRead.model_validate(updated_course)
        response = await client.patch(
            f"/api/v1/courses/{course_id}",
            json={"name": "Cálculo Diferencial"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Cálculo Diferencial"
    assert body["id"] == str(course_id)


# ---------------------------------------------------------------------------
# PATCH /api/v1/courses/{id} — 404 not found (Req 10.3)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_patch_course_not_found_returns_404(client: AsyncClient):
    """PATCH for non-existent course returns 404."""
    from fastapi import HTTPException

    token = _create_access_token(role=RoleEnum.ADMIN)
    course_id = uuid.uuid4()

    with patch(
        "app.api.v1.endpoints.courses.CourseService.update_course",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=404, detail="Curso no encontrado"),
    ):
        response = await client.patch(
            f"/api/v1/courses/{course_id}",
            json={"name": "Nuevo Nombre"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Curso no encontrado"


# ---------------------------------------------------------------------------
# PATCH /api/v1/courses/{id}/status — 200 (Req 11.1, 11.2)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_patch_course_status_returns_200(client: AsyncClient):
    """Valid PATCH status with ADMIN token returns 200."""
    token = _create_access_token(role=RoleEnum.ADMIN)
    course_id = uuid.uuid4()
    updated_course = _make_course(id=course_id, status=CourseStatusEnum.INACTIVE)

    with patch(
        "app.api.v1.endpoints.courses.CourseService.update_course_status",
        new_callable=AsyncMock,
    ) as mock_status:
        from app.application.schemas.course import CourseRead

        mock_status.return_value = CourseRead.model_validate(updated_course)
        response = await client.patch(
            f"/api/v1/courses/{course_id}/status",
            json={"status": "INACTIVE"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "INACTIVE"


# ---------------------------------------------------------------------------
# PATCH /api/v1/courses/{id}/status — 404 not found (Req 11.3)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_patch_course_status_not_found_returns_404(client: AsyncClient):
    """PATCH status for non-existent course returns 404."""
    from fastapi import HTTPException

    token = _create_access_token(role=RoleEnum.ADMIN)
    course_id = uuid.uuid4()

    with patch(
        "app.api.v1.endpoints.courses.CourseService.update_course_status",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=404, detail="Curso no encontrado"),
    ):
        response = await client.patch(
            f"/api/v1/courses/{course_id}/status",
            json={"status": "INACTIVE"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Curso no encontrado"


# ---------------------------------------------------------------------------
# PATCH /api/v1/courses/{id}/status — 401 no auth (Req 11.4, 11.6)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_patch_course_status_no_auth_returns_401(client: AsyncClient):
    """PATCH status without Authorization header returns 401."""
    course_id = uuid.uuid4()

    response = await client.patch(
        f"/api/v1/courses/{course_id}/status",
        json={"status": "INACTIVE"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Token no proporcionado"


# ---------------------------------------------------------------------------
# PATCH /api/v1/courses/{id}/status — 403 non-ADMIN (Req 11.5, 11.7)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_patch_course_status_non_admin_returns_403(client: AsyncClient):
    """PATCH status with PROFESSOR token returns 403."""
    token = _create_access_token(role=RoleEnum.PROFESSOR)
    course_id = uuid.uuid4()

    response = await client.patch(
        f"/api/v1/courses/{course_id}/status",
        json={"status": "INACTIVE"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "No tiene permisos para esta acción"
