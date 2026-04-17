"""
Integration tests for role-based endpoint protection.

Verifies the endpoint protection matrix:
- ADMIN can access all user endpoints.
- PROFESSOR can list users and view students in their courses (RB-04)
  but cannot create users or change status.
- STUDENT can only view own profile.

Requirements: 6.2, 6.3, 6.4, 6.5
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.domain.enums import RoleEnum, UserStatusEnum
from app.infrastructure.models.user import User

# Import app after conftest stubs are applied
from app.main import app  # noqa: E402
from app.infrastructure.database import get_session  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_access_token(
    user_id: uuid.UUID,
    role: RoleEnum,
) -> str:
    """Create a valid JWT access token for the given user."""
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(user_id),
        "role": role.value,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=30)).timestamp()),
    }
    return jwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def _make_user(
    *,
    user_id: uuid.UUID | None = None,
    email: str = "user@uni.edu",
    role: RoleEnum = RoleEnum.STUDENT,
    status: UserStatusEnum = UserStatusEnum.ACTIVE,
) -> User:
    """Build a User model instance for mock returns."""
    uid = user_id or uuid.uuid4()
    now = datetime.now(timezone.utc)
    return User(
        id=uid,
        email=email,
        full_name="Test User",
        role=role,
        status=status,
        ml_consent=False,
        created_at=now,
        updated_at=now,
    )


def _auth_header(token: str) -> dict[str, str]:
    """Build an Authorization header dict."""
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def anyio_backend():
    return "asyncio"


# Fixed UUIDs for consistent test data
ADMIN_ID = uuid.uuid4()
PROFESSOR_ID = uuid.uuid4()
STUDENT_ID = uuid.uuid4()
OTHER_STUDENT_ID = uuid.uuid4()


@pytest.fixture
def admin_token() -> str:
    return _create_access_token(ADMIN_ID, RoleEnum.ADMIN)


@pytest.fixture
def professor_token() -> str:
    return _create_access_token(PROFESSOR_ID, RoleEnum.PROFESSOR)


@pytest.fixture
def student_token() -> str:
    return _create_access_token(STUDENT_ID, RoleEnum.STUDENT)


def _make_mock_session(*, professor_can_see_student: bool = False):
    """Build a mock AsyncSession.

    When ``professor_can_see_student`` is True, the mock will simulate a DB
    result indicating that the professor has the student enrolled in one of
    their courses (RB-04).  Otherwise it returns ``None`` (no relationship).
    """
    mock_session = AsyncMock()

    async def _execute(stmt, *args, **kwargs):
        result = MagicMock()
        if professor_can_see_student:
            # Simulate finding an enrollment row
            result.scalar_one_or_none.return_value = uuid.uuid4()
        else:
            result.scalar_one_or_none.return_value = None
        # For list/count queries (UserRepository)
        result.scalars.return_value.all.return_value = []
        result.scalar_one.return_value = 0
        return result

    mock_session.execute = AsyncMock(side_effect=_execute)
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_session.refresh = AsyncMock()
    return mock_session


@pytest.fixture
async def admin_client(admin_token):
    """Client with mock session; caller adds auth header per-request."""
    mock_session = _make_mock_session()

    async def _override():
        yield mock_session

    app.dependency_overrides[get_session] = _override
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def professor_client():
    """Client whose mock session says professor CAN see the student (RB-04)."""
    mock_session = _make_mock_session(professor_can_see_student=True)

    async def _override():
        yield mock_session

    app.dependency_overrides[get_session] = _override
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def professor_client_no_rb04():
    """Client whose mock session says professor CANNOT see the student."""
    mock_session = _make_mock_session(professor_can_see_student=False)

    async def _override():
        yield mock_session

    app.dependency_overrides[get_session] = _override
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
async def student_client():
    """Client with mock session for student tests."""
    mock_session = _make_mock_session(professor_can_see_student=False)

    async def _override():
        yield mock_session

    app.dependency_overrides[get_session] = _override
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()


# ===========================================================================
# ADMIN — full access to all user endpoints (Req 6.2, 6.3, 6.4)
# ===========================================================================


@pytest.mark.anyio
async def test_admin_can_list_users(admin_client: AsyncClient, admin_token: str):
    """ADMIN can GET /api/v1/users (Req 6.3)."""
    response = await admin_client.get(
        "/api/v1/users",
        headers=_auth_header(admin_token),
    )
    # 200 if service returns data; should NOT be 401 or 403.
    assert response.status_code == 200


@pytest.mark.anyio
async def test_admin_can_create_user(admin_client: AsyncClient, admin_token: str):
    """ADMIN can POST /api/v1/users (Req 6.2)."""
    new_user = _make_user(email="nuevo@uni.edu", role=RoleEnum.STUDENT)

    with patch(
        "app.application.services.user_service.UserService.create_user",
        new_callable=AsyncMock,
        return_value=new_user,
    ):
        response = await admin_client.post(
            "/api/v1/users",
            json={
                "email": "nuevo@uni.edu",
                "full_name": "Nuevo User",
                "role": "STUDENT",
            },
            headers=_auth_header(admin_token),
        )

    assert response.status_code == 201
    assert response.json()["email"] == "nuevo@uni.edu"


@pytest.mark.anyio
async def test_admin_can_get_any_user(admin_client: AsyncClient, admin_token: str):
    """ADMIN can GET /api/v1/users/{user_id} for any user (Req 6.5)."""
    target_user = _make_user(
        user_id=STUDENT_ID, email="student@uni.edu", role=RoleEnum.STUDENT
    )

    with patch(
        "app.application.services.user_service.UserService.get_user",
        new_callable=AsyncMock,
        return_value=target_user,
    ):
        response = await admin_client.get(
            f"/api/v1/users/{STUDENT_ID}",
            headers=_auth_header(admin_token),
        )

    assert response.status_code == 200
    assert response.json()["id"] == str(STUDENT_ID)


@pytest.mark.anyio
async def test_admin_can_update_user(admin_client: AsyncClient, admin_token: str):
    """ADMIN can PATCH /api/v1/users/{user_id} (Req 6.4)."""
    updated_user = _make_user(user_id=STUDENT_ID, email="student@uni.edu")

    with patch(
        "app.application.services.user_service.UserService.update_user",
        new_callable=AsyncMock,
        return_value=updated_user,
    ):
        response = await admin_client.patch(
            f"/api/v1/users/{STUDENT_ID}",
            json={"full_name": "Updated Name"},
            headers=_auth_header(admin_token),
        )

    assert response.status_code == 200


@pytest.mark.anyio
async def test_admin_can_change_user_status(admin_client: AsyncClient, admin_token: str):
    """ADMIN can PATCH /api/v1/users/{user_id}/status (Req 6.4)."""
    updated_user = _make_user(
        user_id=STUDENT_ID, email="student@uni.edu",
        status=UserStatusEnum.INACTIVE,
    )

    with patch(
        "app.application.services.user_service.UserService.update_user_status",
        new_callable=AsyncMock,
        return_value=updated_user,
    ):
        response = await admin_client.patch(
            f"/api/v1/users/{STUDENT_ID}/status",
            json={"status": "INACTIVE"},
            headers=_auth_header(admin_token),
        )

    assert response.status_code == 200


# ===========================================================================
# PROFESSOR — can list users and view students in courses (Req 6.3, 6.5)
# ===========================================================================


@pytest.mark.anyio
async def test_professor_can_list_users(
    professor_client: AsyncClient, professor_token: str
):
    """PROFESSOR can GET /api/v1/users (Req 6.3)."""
    response = await professor_client.get(
        "/api/v1/users",
        headers=_auth_header(professor_token),
    )
    assert response.status_code == 200


@pytest.mark.anyio
async def test_professor_can_view_student_in_course(
    professor_client: AsyncClient, professor_token: str
):
    """PROFESSOR can view a student enrolled in their course — RB-04 (Req 6.5)."""
    target_user = _make_user(
        user_id=STUDENT_ID, email="student@uni.edu", role=RoleEnum.STUDENT
    )

    with patch(
        "app.application.services.user_service.UserService.get_user",
        new_callable=AsyncMock,
        return_value=target_user,
    ):
        response = await professor_client.get(
            f"/api/v1/users/{STUDENT_ID}",
            headers=_auth_header(professor_token),
        )

    assert response.status_code == 200
    assert response.json()["id"] == str(STUDENT_ID)


@pytest.mark.anyio
async def test_professor_cannot_view_student_not_in_course(
    professor_client_no_rb04: AsyncClient, professor_token: str
):
    """PROFESSOR cannot view a student NOT in their courses (Req 6.5 / RB-04)."""
    response = await professor_client_no_rb04.get(
        f"/api/v1/users/{OTHER_STUDENT_ID}",
        headers=_auth_header(professor_token),
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "No tiene permisos para esta acción"


@pytest.mark.anyio
async def test_professor_cannot_create_user(
    professor_client: AsyncClient, professor_token: str
):
    """PROFESSOR cannot POST /api/v1/users (Req 6.2)."""
    response = await professor_client.post(
        "/api/v1/users",
        json={
            "email": "nuevo@uni.edu",
            "full_name": "Nuevo User",
            "role": "STUDENT",
        },
        headers=_auth_header(professor_token),
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "No tiene permisos para esta acción"


@pytest.mark.anyio
async def test_professor_cannot_update_user(
    professor_client: AsyncClient, professor_token: str
):
    """PROFESSOR cannot PATCH /api/v1/users/{user_id} (Req 6.4)."""
    response = await professor_client.patch(
        f"/api/v1/users/{STUDENT_ID}",
        json={"full_name": "Hacked Name"},
        headers=_auth_header(professor_token),
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "No tiene permisos para esta acción"


@pytest.mark.anyio
async def test_professor_cannot_change_user_status(
    professor_client: AsyncClient, professor_token: str
):
    """PROFESSOR cannot PATCH /api/v1/users/{user_id}/status (Req 6.4)."""
    response = await professor_client.patch(
        f"/api/v1/users/{STUDENT_ID}/status",
        json={"status": "INACTIVE"},
        headers=_auth_header(professor_token),
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "No tiene permisos para esta acción"


@pytest.mark.anyio
async def test_professor_can_view_own_profile(
    professor_client: AsyncClient, professor_token: str
):
    """PROFESSOR can view their own profile via self-access (Req 6.5)."""
    prof_user = _make_user(
        user_id=PROFESSOR_ID, email="prof@uni.edu", role=RoleEnum.PROFESSOR
    )

    with patch(
        "app.application.services.user_service.UserService.get_user",
        new_callable=AsyncMock,
        return_value=prof_user,
    ):
        response = await professor_client.get(
            f"/api/v1/users/{PROFESSOR_ID}",
            headers=_auth_header(professor_token),
        )

    assert response.status_code == 200
    assert response.json()["id"] == str(PROFESSOR_ID)


# ===========================================================================
# STUDENT — can only view own profile (Req 6.5)
# ===========================================================================


@pytest.mark.anyio
async def test_student_can_view_own_profile(
    student_client: AsyncClient, student_token: str
):
    """STUDENT can GET /api/v1/users/{own_id} (Req 6.5)."""
    own_user = _make_user(
        user_id=STUDENT_ID, email="student@uni.edu", role=RoleEnum.STUDENT
    )

    with patch(
        "app.application.services.user_service.UserService.get_user",
        new_callable=AsyncMock,
        return_value=own_user,
    ):
        response = await student_client.get(
            f"/api/v1/users/{STUDENT_ID}",
            headers=_auth_header(student_token),
        )

    assert response.status_code == 200
    assert response.json()["id"] == str(STUDENT_ID)


@pytest.mark.anyio
async def test_student_cannot_view_other_user(
    student_client: AsyncClient, student_token: str
):
    """STUDENT cannot view another user's profile (Req 6.5)."""
    response = await student_client.get(
        f"/api/v1/users/{OTHER_STUDENT_ID}",
        headers=_auth_header(student_token),
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "No tiene permisos para esta acción"


@pytest.mark.anyio
async def test_student_cannot_list_users(
    student_client: AsyncClient, student_token: str
):
    """STUDENT cannot GET /api/v1/users (Req 6.3)."""
    response = await student_client.get(
        "/api/v1/users",
        headers=_auth_header(student_token),
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "No tiene permisos para esta acción"


@pytest.mark.anyio
async def test_student_cannot_create_user(
    student_client: AsyncClient, student_token: str
):
    """STUDENT cannot POST /api/v1/users (Req 6.2)."""
    response = await student_client.post(
        "/api/v1/users",
        json={
            "email": "nuevo@uni.edu",
            "full_name": "Nuevo User",
            "role": "STUDENT",
        },
        headers=_auth_header(student_token),
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "No tiene permisos para esta acción"


@pytest.mark.anyio
async def test_student_cannot_update_user(
    student_client: AsyncClient, student_token: str
):
    """STUDENT cannot PATCH /api/v1/users/{user_id} (Req 6.4)."""
    response = await student_client.patch(
        f"/api/v1/users/{STUDENT_ID}",
        json={"full_name": "Hacked Name"},
        headers=_auth_header(student_token),
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "No tiene permisos para esta acción"


@pytest.mark.anyio
async def test_student_cannot_change_user_status(
    student_client: AsyncClient, student_token: str
):
    """STUDENT cannot PATCH /api/v1/users/{user_id}/status (Req 6.4)."""
    response = await student_client.patch(
        f"/api/v1/users/{STUDENT_ID}/status",
        json={"status": "INACTIVE"},
        headers=_auth_header(student_token),
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "No tiene permisos para esta acción"
