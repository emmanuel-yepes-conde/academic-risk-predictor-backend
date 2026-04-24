"""
Integration tests for enrollment CRUD endpoints.

Tests the full HTTP flow for:
- POST /api/v1/enrollments          (create, auth, validation, uniqueness, reactivation)
- PATCH /api/v1/enrollments/{id}    (update course, auth, not found, duplicate)
- PATCH /api/v1/enrollments/{id}/status  (cancel, auth, not found)
- GET /api/v1/enrollments/{id}      (get by id, auth, not found)
- GET /api/v1/students/{id}/enrollments  (list, auth, RBAC)

Requirements: 1.1–1.9, 2.1–2.7, 3.1–3.5, 4.1–4.4, 5.1–5.3
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.domain.enums import CourseStatusEnum, EnrollmentStatusEnum, RoleEnum
from app.infrastructure.models.enrollment import Enrollment
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


def _make_enrollment(**kwargs) -> Enrollment:
    """Build an Enrollment model instance with sensible defaults."""
    defaults = dict(
        id=uuid.uuid4(),
        student_id=uuid.uuid4(),
        course_id=uuid.uuid4(),
        status=EnrollmentStatusEnum.ACTIVE,
        enrollment_date=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    return Enrollment(**defaults)


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


# ===========================================================================
# POST /api/v1/enrollments — 201 valid creation (Req 1.1)
# ===========================================================================

@pytest.mark.anyio
async def test_post_enrollments_returns_201(client: AsyncClient):
    """Valid POST with ADMIN token returns 201 with created enrollment data."""
    token = _create_access_token(role=RoleEnum.ADMIN)
    enrollment = _make_enrollment()

    with patch(
        "app.api.v1.endpoints.enrollments.EnrollmentService.create_enrollment",
        new_callable=AsyncMock,
    ) as mock_create:
        from app.application.schemas.enrollment import EnrollmentRead

        mock_create.return_value = EnrollmentRead.model_validate(enrollment)
        response = await client.post(
            "/api/v1/enrollments",
            json={
                "student_id": str(enrollment.student_id),
                "course_id": str(enrollment.course_id),
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == str(enrollment.id)
    assert body["student_id"] == str(enrollment.student_id)
    assert body["course_id"] == str(enrollment.course_id)
    assert body["status"] == "ACTIVE"


# ===========================================================================
# POST /api/v1/enrollments — 409 duplicate active enrollment (Req 1.6)
# ===========================================================================

@pytest.mark.anyio
async def test_post_enrollments_duplicate_active_returns_409(client: AsyncClient):
    """POST with duplicate active enrollment returns 409."""
    from fastapi import HTTPException

    token = _create_access_token(role=RoleEnum.ADMIN)

    with patch(
        "app.api.v1.endpoints.enrollments.EnrollmentService.create_enrollment",
        new_callable=AsyncMock,
        side_effect=HTTPException(
            status_code=409,
            detail="El estudiante ya está inscrito en este curso",
        ),
    ):
        response = await client.post(
            "/api/v1/enrollments",
            json={
                "student_id": str(uuid.uuid4()),
                "course_id": str(uuid.uuid4()),
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "El estudiante ya está inscrito en este curso"


# ===========================================================================
# POST /api/v1/enrollments — 422 invalid student (Req 1.4)
# ===========================================================================

@pytest.mark.anyio
async def test_post_enrollments_invalid_student_returns_422(client: AsyncClient):
    """POST with invalid student_id returns 422."""
    from fastapi import HTTPException

    token = _create_access_token(role=RoleEnum.ADMIN)

    with patch(
        "app.api.v1.endpoints.enrollments.EnrollmentService.create_enrollment",
        new_callable=AsyncMock,
        side_effect=HTTPException(
            status_code=422,
            detail="El usuario indicado no existe o no tiene rol de estudiante",
        ),
    ):
        response = await client.post(
            "/api/v1/enrollments",
            json={
                "student_id": str(uuid.uuid4()),
                "course_id": str(uuid.uuid4()),
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 422
    assert (
        response.json()["detail"]
        == "El usuario indicado no existe o no tiene rol de estudiante"
    )


# ===========================================================================
# POST /api/v1/enrollments — 404 invalid course (Req 1.5)
# ===========================================================================

@pytest.mark.anyio
async def test_post_enrollments_invalid_course_returns_404(client: AsyncClient):
    """POST with invalid course_id returns 404."""
    from fastapi import HTTPException

    token = _create_access_token(role=RoleEnum.ADMIN)

    with patch(
        "app.api.v1.endpoints.enrollments.EnrollmentService.create_enrollment",
        new_callable=AsyncMock,
        side_effect=HTTPException(
            status_code=404,
            detail="Curso no encontrado",
        ),
    ):
        response = await client.post(
            "/api/v1/enrollments",
            json={
                "student_id": str(uuid.uuid4()),
                "course_id": str(uuid.uuid4()),
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Curso no encontrado"


# ===========================================================================
# POST /api/v1/enrollments — reactivates cancelled enrollment (Req 1.7)
# ===========================================================================

@pytest.mark.anyio
async def test_post_enrollments_reactivates_cancelled(client: AsyncClient):
    """POST for a cancelled enrollment reactivates it (returns 201 with ACTIVE status)."""
    token = _create_access_token(role=RoleEnum.ADMIN)
    enrollment = _make_enrollment(status=EnrollmentStatusEnum.ACTIVE)

    with patch(
        "app.api.v1.endpoints.enrollments.EnrollmentService.create_enrollment",
        new_callable=AsyncMock,
    ) as mock_create:
        from app.application.schemas.enrollment import EnrollmentRead

        mock_create.return_value = EnrollmentRead.model_validate(enrollment)
        response = await client.post(
            "/api/v1/enrollments",
            json={
                "student_id": str(enrollment.student_id),
                "course_id": str(enrollment.course_id),
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ACTIVE"
    assert body["id"] == str(enrollment.id)


# ===========================================================================
# POST /api/v1/enrollments — 401 no auth (Req 1.9)
# ===========================================================================

@pytest.mark.anyio
async def test_post_enrollments_no_auth_returns_401(client: AsyncClient):
    """POST without Authorization header returns 401."""
    response = await client.post(
        "/api/v1/enrollments",
        json={
            "student_id": str(uuid.uuid4()),
            "course_id": str(uuid.uuid4()),
        },
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Token no proporcionado"


# ===========================================================================
# POST /api/v1/enrollments — 403 non-ADMIN (Req 1.9)
# ===========================================================================

@pytest.mark.anyio
async def test_post_enrollments_non_admin_returns_403(client: AsyncClient):
    """POST with STUDENT token returns 403."""
    token = _create_access_token(role=RoleEnum.STUDENT)

    response = await client.post(
        "/api/v1/enrollments",
        json={
            "student_id": str(uuid.uuid4()),
            "course_id": str(uuid.uuid4()),
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "No tiene permisos para esta acción"


# ===========================================================================
# PATCH /api/v1/enrollments/{id} — 200 valid update (Req 2.1)
# ===========================================================================

@pytest.mark.anyio
async def test_patch_enrollment_returns_200(client: AsyncClient):
    """Valid PATCH with ADMIN token returns 200 with updated enrollment data."""
    token = _create_access_token(role=RoleEnum.ADMIN)
    new_course_id = uuid.uuid4()
    enrollment = _make_enrollment(course_id=new_course_id)

    with patch(
        "app.api.v1.endpoints.enrollments.EnrollmentService.update_enrollment",
        new_callable=AsyncMock,
    ) as mock_update:
        from app.application.schemas.enrollment import EnrollmentRead

        mock_update.return_value = EnrollmentRead.model_validate(enrollment)
        response = await client.patch(
            f"/api/v1/enrollments/{enrollment.id}",
            json={"course_id": str(new_course_id)},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["course_id"] == str(new_course_id)
    assert body["id"] == str(enrollment.id)


# ===========================================================================
# PATCH /api/v1/enrollments/{id} — 404 not found (Req 2.2)
# ===========================================================================

@pytest.mark.anyio
async def test_patch_enrollment_not_found_returns_404(client: AsyncClient):
    """PATCH for non-existent enrollment returns 404."""
    from fastapi import HTTPException

    token = _create_access_token(role=RoleEnum.ADMIN)
    enrollment_id = uuid.uuid4()

    with patch(
        "app.api.v1.endpoints.enrollments.EnrollmentService.update_enrollment",
        new_callable=AsyncMock,
        side_effect=HTTPException(
            status_code=404, detail="Inscripción no encontrada"
        ),
    ):
        response = await client.patch(
            f"/api/v1/enrollments/{enrollment_id}",
            json={"course_id": str(uuid.uuid4())},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Inscripción no encontrada"


# ===========================================================================
# PATCH /api/v1/enrollments/{id} — 409 duplicate in destination (Req 2.5)
# ===========================================================================

@pytest.mark.anyio
async def test_patch_enrollment_duplicate_destination_returns_409(client: AsyncClient):
    """PATCH to a course where student is already enrolled returns 409."""
    from fastapi import HTTPException

    token = _create_access_token(role=RoleEnum.ADMIN)
    enrollment_id = uuid.uuid4()

    with patch(
        "app.api.v1.endpoints.enrollments.EnrollmentService.update_enrollment",
        new_callable=AsyncMock,
        side_effect=HTTPException(
            status_code=409,
            detail="El estudiante ya está inscrito en el curso destino",
        ),
    ):
        response = await client.patch(
            f"/api/v1/enrollments/{enrollment_id}",
            json={"course_id": str(uuid.uuid4())},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 409
    assert (
        response.json()["detail"]
        == "El estudiante ya está inscrito en el curso destino"
    )


# ===========================================================================
# PATCH /api/v1/enrollments/{id} — 403 non-ADMIN (Req 2.7)
# ===========================================================================

@pytest.mark.anyio
async def test_patch_enrollment_non_admin_returns_403(client: AsyncClient):
    """PATCH with STUDENT token returns 403."""
    token = _create_access_token(role=RoleEnum.STUDENT)
    enrollment_id = uuid.uuid4()

    response = await client.patch(
        f"/api/v1/enrollments/{enrollment_id}",
        json={"course_id": str(uuid.uuid4())},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "No tiene permisos para esta acción"


# ===========================================================================
# PATCH /api/v1/enrollments/{id}/status — 200 cancel (Req 3.1)
# ===========================================================================

@pytest.mark.anyio
async def test_patch_enrollment_status_returns_200(client: AsyncClient):
    """Valid PATCH status with ADMIN token returns 200 with CANCELLED status."""
    token = _create_access_token(role=RoleEnum.ADMIN)
    enrollment = _make_enrollment(status=EnrollmentStatusEnum.CANCELLED)

    with patch(
        "app.api.v1.endpoints.enrollments.EnrollmentService.update_enrollment_status",
        new_callable=AsyncMock,
    ) as mock_cancel:
        from app.application.schemas.enrollment import EnrollmentRead

        mock_cancel.return_value = EnrollmentRead.model_validate(enrollment)
        response = await client.patch(
            f"/api/v1/enrollments/{enrollment.id}/status",
            json={"status": "CANCELLED"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "CANCELLED"


# ===========================================================================
# PATCH /api/v1/enrollments/{id}/status — 404 not found (Req 3.2)
# ===========================================================================

@pytest.mark.anyio
async def test_patch_enrollment_status_not_found_returns_404(client: AsyncClient):
    """PATCH status for non-existent enrollment returns 404."""
    from fastapi import HTTPException

    token = _create_access_token(role=RoleEnum.ADMIN)
    enrollment_id = uuid.uuid4()

    with patch(
        "app.api.v1.endpoints.enrollments.EnrollmentService.update_enrollment_status",
        new_callable=AsyncMock,
        side_effect=HTTPException(
            status_code=404, detail="Inscripción no encontrada"
        ),
    ):
        response = await client.patch(
            f"/api/v1/enrollments/{enrollment_id}/status",
            json={"status": "CANCELLED"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Inscripción no encontrada"


# ===========================================================================
# PATCH /api/v1/enrollments/{id}/status — 401 no auth (Req 3.4)
# ===========================================================================

@pytest.mark.anyio
async def test_patch_enrollment_status_no_auth_returns_401(client: AsyncClient):
    """PATCH status without Authorization header returns 401."""
    enrollment_id = uuid.uuid4()

    response = await client.patch(
        f"/api/v1/enrollments/{enrollment_id}/status",
        json={"status": "CANCELLED"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Token no proporcionado"


# ===========================================================================
# PATCH /api/v1/enrollments/{id}/status — 403 non-ADMIN (Req 3.4)
# ===========================================================================

@pytest.mark.anyio
async def test_patch_enrollment_status_non_admin_returns_403(client: AsyncClient):
    """PATCH status with PROFESSOR token returns 403."""
    token = _create_access_token(role=RoleEnum.PROFESSOR)
    enrollment_id = uuid.uuid4()

    response = await client.patch(
        f"/api/v1/enrollments/{enrollment_id}/status",
        json={"status": "CANCELLED"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "No tiene permisos para esta acción"


# ===========================================================================
# GET /api/v1/enrollments/{id} — 200 detail (Req 5.1)
# ===========================================================================

@pytest.mark.anyio
async def test_get_enrollment_returns_200(client: AsyncClient):
    """Valid GET by ID with ADMIN auth returns 200 with enrollment data."""
    token = _create_access_token(role=RoleEnum.ADMIN)
    enrollment = _make_enrollment()

    with patch(
        "app.api.v1.endpoints.enrollments.EnrollmentService.get_enrollment",
        new_callable=AsyncMock,
    ) as mock_get:
        from app.application.schemas.enrollment import EnrollmentRead

        mock_get.return_value = EnrollmentRead.model_validate(enrollment)
        response = await client.get(
            f"/api/v1/enrollments/{enrollment.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(enrollment.id)
    assert body["student_id"] == str(enrollment.student_id)
    assert body["course_id"] == str(enrollment.course_id)


# ===========================================================================
# GET /api/v1/enrollments/{id} — 404 not found (Req 5.2)
# ===========================================================================

@pytest.mark.anyio
async def test_get_enrollment_not_found_returns_404(client: AsyncClient):
    """GET for non-existent enrollment returns 404."""
    from fastapi import HTTPException

    token = _create_access_token(role=RoleEnum.ADMIN)
    enrollment_id = uuid.uuid4()

    with patch(
        "app.api.v1.endpoints.enrollments.EnrollmentService.get_enrollment",
        new_callable=AsyncMock,
        side_effect=HTTPException(
            status_code=404, detail="Inscripción no encontrada"
        ),
    ):
        response = await client.get(
            f"/api/v1/enrollments/{enrollment_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Inscripción no encontrada"


# ===========================================================================
# GET /api/v1/enrollments/{id} — 403 non-ADMIN (Req 5.3)
# ===========================================================================

@pytest.mark.anyio
async def test_get_enrollment_non_admin_returns_403(client: AsyncClient):
    """GET enrollment detail with STUDENT token returns 403."""
    token = _create_access_token(role=RoleEnum.STUDENT)
    enrollment_id = uuid.uuid4()

    response = await client.get(
        f"/api/v1/enrollments/{enrollment_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "No tiene permisos para esta acción"


# ===========================================================================
# GET /api/v1/students/{id}/enrollments — 200 list (Req 4.1)
# ===========================================================================

@pytest.mark.anyio
async def test_get_student_enrollments_returns_200(client: AsyncClient):
    """Valid GET student enrollments with ADMIN auth returns 200 with list."""
    token = _create_access_token(role=RoleEnum.ADMIN)
    student_id = uuid.uuid4()
    enrollment1 = _make_enrollment(student_id=student_id)
    enrollment2 = _make_enrollment(student_id=student_id)

    with patch(
        "app.api.v1.endpoints.enrollments.EnrollmentService.list_student_enrollments",
        new_callable=AsyncMock,
    ) as mock_list:
        from app.application.schemas.enrollment import EnrollmentRead

        mock_list.return_value = [
            EnrollmentRead.model_validate(enrollment1),
            EnrollmentRead.model_validate(enrollment2),
        ]
        response = await client.get(
            f"/api/v1/students/{student_id}/enrollments",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["student_id"] == str(student_id)
    assert body[1]["student_id"] == str(student_id)


# ===========================================================================
# GET /api/v1/students/{id}/enrollments — 200 empty list (Req 4.2)
# ===========================================================================

@pytest.mark.anyio
async def test_get_student_enrollments_empty_returns_200(client: AsyncClient):
    """GET student enrollments with no enrollments returns 200 with empty list."""
    token = _create_access_token(role=RoleEnum.ADMIN)
    student_id = uuid.uuid4()

    with patch(
        "app.api.v1.endpoints.enrollments.EnrollmentService.list_student_enrollments",
        new_callable=AsyncMock,
    ) as mock_list:
        mock_list.return_value = []
        response = await client.get(
            f"/api/v1/students/{student_id}/enrollments",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body == []


# ===========================================================================
# GET /api/v1/students/{id}/enrollments — 200 with PROFESSOR (Req 4.3, 4.4)
# ===========================================================================

@pytest.mark.anyio
async def test_get_student_enrollments_professor_returns_200(client: AsyncClient):
    """GET student enrollments with PROFESSOR token returns 200 (RBAC allows PROFESSOR)."""
    token = _create_access_token(role=RoleEnum.PROFESSOR)
    student_id = uuid.uuid4()
    enrollment = _make_enrollment(student_id=student_id)

    with patch(
        "app.api.v1.endpoints.enrollments.EnrollmentService.list_student_enrollments",
        new_callable=AsyncMock,
    ) as mock_list:
        from app.application.schemas.enrollment import EnrollmentRead

        mock_list.return_value = [EnrollmentRead.model_validate(enrollment)]
        response = await client.get(
            f"/api/v1/students/{student_id}/enrollments",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1


# ===========================================================================
# GET /api/v1/students/{id}/enrollments — 403 STUDENT (Req 4.3)
# ===========================================================================

@pytest.mark.anyio
async def test_get_student_enrollments_student_returns_403(client: AsyncClient):
    """GET student enrollments with STUDENT token returns 403."""
    token = _create_access_token(role=RoleEnum.STUDENT)
    student_id = uuid.uuid4()

    response = await client.get(
        f"/api/v1/students/{student_id}/enrollments",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "No tiene permisos para esta acción"
