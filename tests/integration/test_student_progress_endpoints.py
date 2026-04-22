"""
Integration tests for student progress view endpoints.

Tests the full HTTP flow for:
- GET /api/v1/students/{student_id}/enrollments  (self-access, RBAC, status filter)
- PATCH /api/v1/enrollments/{id}/status          (COMPLETED, PENDING)
- GET /api/v1/programs/{program_id}              (get by id, 404, multi-role access)

Requirements: 1.1–1.6, 2.2, 2.3, 3.1–3.4, 4.1–4.3, 5.1–5.4
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.domain.enums import EnrollmentStatusEnum, RoleEnum
from app.infrastructure.models.enrollment import Enrollment
from app.infrastructure.models.program import Program
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


def _make_program(**kwargs) -> Program:
    """Build a Program model instance with sensible defaults."""
    defaults = dict(
        id=uuid.uuid4(),
        institution="USBCO",
        degree_type="PREG",
        program_code=f"P{uuid.uuid4().hex[:6].upper()}",
        program_name="Ingeniería de Sistemas",
        location="SAN BENITO",
        snies_code=abs(hash(uuid.uuid4())) % 100000,
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    return Program(**defaults)


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
# GET /api/v1/students/{student_id}/enrollments — STUDENT self-access (Req 1.1)
# ===========================================================================

@pytest.mark.anyio
async def test_get_student_enrollments_student_self_access_returns_200(client: AsyncClient):
    """STUDENT accessing their own enrollments returns 200."""
    student_id = uuid.uuid4()
    token = _create_access_token(user_id=student_id, role=RoleEnum.STUDENT)
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
    assert body[0]["student_id"] == str(student_id)


# ===========================================================================
# GET /api/v1/students/{student_id}/enrollments — STUDENT other student (Req 1.2)
# ===========================================================================

@pytest.mark.anyio
async def test_get_student_enrollments_student_other_returns_403(client: AsyncClient):
    """STUDENT accessing another student's enrollments returns 403."""
    my_id = uuid.uuid4()
    other_student_id = uuid.uuid4()
    token = _create_access_token(user_id=my_id, role=RoleEnum.STUDENT)

    response = await client.get(
        f"/api/v1/students/{other_student_id}/enrollments",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "No tiene permisos para esta acción"


# ===========================================================================
# GET /api/v1/students/{student_id}/enrollments — ADMIN access (Req 1.3)
# ===========================================================================

@pytest.mark.anyio
async def test_get_student_enrollments_admin_returns_200(client: AsyncClient):
    """ADMIN accessing any student's enrollments returns 200."""
    token = _create_access_token(role=RoleEnum.ADMIN)
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
# GET /api/v1/students/{student_id}/enrollments — PROFESSOR RB-04 (Req 1.4)
# ===========================================================================

@pytest.mark.anyio
async def test_get_student_enrollments_professor_rb04_returns_200(client: AsyncClient):
    """PROFESSOR with RB-04 visibility accessing student enrollments returns 200.

    The require_student_self_or_roles dependency does a DB query to check if
    the student is enrolled in one of the professor's courses. We mock the
    session.execute to return a non-None result for that check.
    """
    professor_id = uuid.uuid4()
    student_id = uuid.uuid4()
    token = _create_access_token(user_id=professor_id, role=RoleEnum.PROFESSOR)
    enrollment = _make_enrollment(student_id=student_id)

    # Mock the session.execute used by require_student_self_or_roles for RB-04 check
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = uuid.uuid4()  # non-None → access granted
    mock_session.execute.return_value = mock_result

    async def _override_get_session():
        yield mock_session

    app.dependency_overrides[get_session] = _override_get_session

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
# GET /api/v1/students/{student_id}/enrollments — status=COMPLETED filter (Req 3.1)
# ===========================================================================

@pytest.mark.anyio
async def test_get_student_enrollments_filter_completed(client: AsyncClient):
    """GET with status=COMPLETED returns only COMPLETED enrollments."""
    student_id = uuid.uuid4()
    token = _create_access_token(user_id=student_id, role=RoleEnum.STUDENT)
    enrollment = _make_enrollment(student_id=student_id, status=EnrollmentStatusEnum.COMPLETED)

    with patch(
        "app.api.v1.endpoints.enrollments.EnrollmentService.list_student_enrollments",
        new_callable=AsyncMock,
    ) as mock_list:
        from app.application.schemas.enrollment import EnrollmentRead

        mock_list.return_value = [EnrollmentRead.model_validate(enrollment)]
        response = await client.get(
            f"/api/v1/students/{student_id}/enrollments?status=COMPLETED",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["status"] == "COMPLETED"
    # Verify the service was called with the correct status filter
    mock_list.assert_called_once()
    call_args = mock_list.call_args
    assert call_args[0][2] == EnrollmentStatusEnum.COMPLETED


# ===========================================================================
# GET /api/v1/students/{student_id}/enrollments — status=PENDING filter (Req 3.1)
# ===========================================================================

@pytest.mark.anyio
async def test_get_student_enrollments_filter_pending(client: AsyncClient):
    """GET with status=PENDING returns only PENDING enrollments."""
    student_id = uuid.uuid4()
    token = _create_access_token(user_id=student_id, role=RoleEnum.STUDENT)
    enrollment = _make_enrollment(student_id=student_id, status=EnrollmentStatusEnum.PENDING)

    with patch(
        "app.api.v1.endpoints.enrollments.EnrollmentService.list_student_enrollments",
        new_callable=AsyncMock,
    ) as mock_list:
        from app.application.schemas.enrollment import EnrollmentRead

        mock_list.return_value = [EnrollmentRead.model_validate(enrollment)]
        response = await client.get(
            f"/api/v1/students/{student_id}/enrollments?status=PENDING",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["status"] == "PENDING"
    mock_list.assert_called_once()
    call_args = mock_list.call_args
    assert call_args[0][2] == EnrollmentStatusEnum.PENDING


# ===========================================================================
# GET /api/v1/students/{student_id}/enrollments — invalid status (Req 3.3, 5.1)
# ===========================================================================

@pytest.mark.anyio
async def test_get_student_enrollments_invalid_status_returns_422(client: AsyncClient):
    """GET with invalid status query param returns 422."""
    student_id = uuid.uuid4()
    token = _create_access_token(user_id=student_id, role=RoleEnum.STUDENT)

    response = await client.get(
        f"/api/v1/students/{student_id}/enrollments?status=INVALID_STATUS",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


# ===========================================================================
# PATCH /api/v1/enrollments/{id}/status — COMPLETED (Req 2.2)
# ===========================================================================

@pytest.mark.anyio
async def test_patch_enrollment_status_completed_returns_200(client: AsyncClient):
    """PATCH status with COMPLETED returns 200 with updated enrollment."""
    token = _create_access_token(role=RoleEnum.ADMIN)
    enrollment = _make_enrollment(status=EnrollmentStatusEnum.COMPLETED)

    with patch(
        "app.api.v1.endpoints.enrollments.EnrollmentService.update_enrollment_status",
        new_callable=AsyncMock,
    ) as mock_update:
        from app.application.schemas.enrollment import EnrollmentRead

        mock_update.return_value = EnrollmentRead.model_validate(enrollment)
        response = await client.patch(
            f"/api/v1/enrollments/{enrollment.id}/status",
            json={"status": "COMPLETED"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "COMPLETED"


# ===========================================================================
# PATCH /api/v1/enrollments/{id}/status — PENDING (Req 2.3)
# ===========================================================================

@pytest.mark.anyio
async def test_patch_enrollment_status_pending_returns_200(client: AsyncClient):
    """PATCH status with PENDING returns 200 with updated enrollment."""
    token = _create_access_token(role=RoleEnum.ADMIN)
    enrollment = _make_enrollment(status=EnrollmentStatusEnum.PENDING)

    with patch(
        "app.api.v1.endpoints.enrollments.EnrollmentService.update_enrollment_status",
        new_callable=AsyncMock,
    ) as mock_update:
        from app.application.schemas.enrollment import EnrollmentRead

        mock_update.return_value = EnrollmentRead.model_validate(enrollment)
        response = await client.patch(
            f"/api/v1/enrollments/{enrollment.id}/status",
            json={"status": "PENDING"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "PENDING"


# ===========================================================================
# GET /api/v1/programs/{program_id} — valid ID (Req 4.1)
# ===========================================================================

@pytest.mark.anyio
async def test_get_program_valid_id_returns_200(client: AsyncClient):
    """GET program by valid ID returns 200 with program data."""
    token = _create_access_token(role=RoleEnum.STUDENT)
    program = _make_program()

    with patch(
        "app.api.v1.endpoints.programs.ProgramService.get_program",
        new_callable=AsyncMock,
    ) as mock_get:
        from app.application.schemas.program import ProgramRead

        mock_get.return_value = ProgramRead.model_validate(program)
        response = await client.get(
            f"/api/v1/programs/{program.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(program.id)
    assert body["program_name"] == program.program_name
    assert body["program_code"] == program.program_code


# ===========================================================================
# GET /api/v1/programs/{program_id} — non-existent ID (Req 4.2)
# ===========================================================================

@pytest.mark.anyio
async def test_get_program_not_found_returns_404(client: AsyncClient):
    """GET program with non-existent ID returns 404."""
    from fastapi import HTTPException

    token = _create_access_token(role=RoleEnum.STUDENT)
    program_id = uuid.uuid4()

    with patch(
        "app.api.v1.endpoints.programs.ProgramService.get_program",
        new_callable=AsyncMock,
        side_effect=HTTPException(status_code=404, detail="Programa no encontrado"),
    ):
        response = await client.get(
            f"/api/v1/programs/{program_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Programa no encontrado"


# ===========================================================================
# GET /api/v1/programs/{program_id} — accessible by STUDENT, PROFESSOR, ADMIN (Req 4.3)
# ===========================================================================

@pytest.mark.anyio
@pytest.mark.parametrize("role", [RoleEnum.STUDENT, RoleEnum.PROFESSOR, RoleEnum.ADMIN])
async def test_get_program_accessible_by_all_roles(client: AsyncClient, role: RoleEnum):
    """GET program is accessible by STUDENT, PROFESSOR, and ADMIN."""
    token = _create_access_token(role=role)
    program = _make_program()

    with patch(
        "app.api.v1.endpoints.programs.ProgramService.get_program",
        new_callable=AsyncMock,
    ) as mock_get:
        from app.application.schemas.program import ProgramRead

        mock_get.return_value = ProgramRead.model_validate(program)
        response = await client.get(
            f"/api/v1/programs/{program.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(program.id)
