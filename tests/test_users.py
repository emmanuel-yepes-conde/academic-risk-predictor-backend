"""
Tests unitarios para los endpoints CRUD de User.
Requisitos: 1.x, 2.x, 3.x, 4.x, 5.x, 8.9
"""

import sys
import types
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Module-level stubs — must run before any app import
# Mirrors the pattern used in tests/unit/test_health.py
# ---------------------------------------------------------------------------

def _stub_heavy_deps():
    """Stub ML service and DB engine so app.main can be imported without disk I/O."""
    # Idempotent: if conftest.py already installed the stub, reuse it.
    if "app.infrastructure.database" in sys.modules:
        return sys.modules["app.infrastructure.database"]

    mock_engine = MagicMock()
    mock_conn = AsyncMock()
    mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_conn.__aexit__ = AsyncMock(return_value=False)
    mock_engine.connect = MagicMock(return_value=mock_conn)

    fake_db = types.ModuleType("app.infrastructure.database")
    fake_db.engine = mock_engine
    fake_db.get_session = AsyncMock()
    sys.modules["app.infrastructure.database"] = fake_db

    mock_risk_svc = MagicMock()
    mock_risk_svc.model = MagicMock()
    mock_risk_svc.scaler = MagicMock()
    mock_risk_svc.promedio_estudiantes_aprobados = 3.5

    fake_ml = types.ModuleType("app.services.ml_service")
    fake_ml.risk_service = mock_risk_svc
    fake_ml.AcademicRiskService = MagicMock(return_value=mock_risk_svc)
    sys.modules["app.services.ml_service"] = fake_ml

    return fake_db


_DB_STUB = _stub_heavy_deps()

# Safe to import app now
from app.main import app  # noqa: E402
from app.application.schemas.user import PaginatedResponse, UserRead  # noqa: E402
from app.domain.enums import RoleEnum, UserStatusEnum  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_user_read(
    *,
    email: str = "test@example.com",
    full_name: str = "Test User",
    role: RoleEnum = RoleEnum.STUDENT,
    status: UserStatusEnum = UserStatusEnum.ACTIVE,
    ml_consent: bool = False,
) -> UserRead:
    return UserRead(
        id=uuid.uuid4(),
        email=email,
        full_name=full_name,
        role=role,
        status=status,
        ml_consent=ml_consent,
        created_at=_now(),
        updated_at=_now(),
    )


def _paginated(users: list[UserRead], skip: int = 0, limit: int = 20) -> PaginatedResponse[UserRead]:
    return PaginatedResponse[UserRead](
        data=users,
        total=len(users),
        skip=skip,
        limit=limit,
    )


def _mock_service(**method_overrides):
    """Return a MagicMock UserService with async methods pre-configured."""
    svc = MagicMock()
    svc.list_users = AsyncMock()
    svc.create_user = AsyncMock()
    svc.get_user = AsyncMock()
    svc.update_user = AsyncMock()
    svc.update_user_status = AsyncMock()
    for method, return_value in method_overrides.items():
        if isinstance(return_value, Exception):
            getattr(svc, method).side_effect = return_value
        else:
            getattr(svc, method).return_value = return_value
    return svc


# ---------------------------------------------------------------------------
# Fixture: client con dependency_overrides[get_session]
# Requisito 8.9
# ---------------------------------------------------------------------------

# anyio_backend and client fixtures are provided by tests/conftest.py


# ---------------------------------------------------------------------------
# POST /users — Requisitos 2.1, 2.2, 2.3, 2.5
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_user_payload() -> dict:
    return {
        "email": f"user_{uuid.uuid4().hex[:8]}@example.com",
        "full_name": "Jane Doe",
        "role": "STUDENT",
    }


@pytest.mark.anyio
async def test_create_user_returns_201(client, valid_user_payload):
    """POST /users con datos válidos → HTTP 201, respuesta contiene id, email, status=ACTIVE."""
    user = _make_user_read(email=valid_user_payload["email"])
    svc = _mock_service(create_user=user)
    with patch("app.api.v1.endpoints.users.UserService", return_value=svc):
        resp = await client.post("/api/v1/users", json=valid_user_payload)

    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    assert body["email"] == valid_user_payload["email"]
    assert body["status"] == "ACTIVE"


@pytest.mark.anyio
async def test_create_user_no_password_hash_in_response(client, valid_user_payload):
    """POST /users → respuesta nunca contiene password_hash. Requisito 2.5"""
    user = _make_user_read(email=valid_user_payload["email"])
    svc = _mock_service(create_user=user)
    with patch("app.api.v1.endpoints.users.UserService", return_value=svc):
        resp = await client.post("/api/v1/users", json=valid_user_payload)

    assert "password_hash" not in resp.json()


@pytest.mark.anyio
async def test_create_user_duplicate_email_returns_409(client, valid_user_payload):
    """POST /users con email duplicado → HTTP 409. Requisito 2.2"""
    svc = _mock_service(
        create_user=HTTPException(status_code=409, detail="El email ya está registrado")
    )
    with patch("app.api.v1.endpoints.users.UserService", return_value=svc):
        resp = await client.post("/api/v1/users", json=valid_user_payload)

    assert resp.status_code == 409
    assert resp.json()["detail"] == "El email ya está registrado"


@pytest.mark.anyio
async def test_create_user_missing_required_field_returns_422(client):
    """POST /users sin campo requerido → HTTP 422. Requisito 2.3"""
    resp = await client.post("/api/v1/users", json={"email": "x@example.com"})
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_create_user_invalid_email_returns_422(client):
    """POST /users con email inválido → HTTP 422."""
    resp = await client.post(
        "/api/v1/users",
        json={"email": "not-an-email", "full_name": "X", "role": "STUDENT"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /users/{user_id} — Requisitos 3.1, 3.2, 3.3, 3.4
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_get_user_returns_200(client):
    """GET /users/{user_id} con UUID existente → HTTP 200, campos correctos. Requisito 3.1"""
    user = _make_user_read(email="alice@example.com", full_name="Alice")
    svc = _mock_service(get_user=user)
    with patch("app.api.v1.endpoints.users.UserService", return_value=svc):
        resp = await client.get(f"/api/v1/users/{user.id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["email"] == "alice@example.com"
    assert body["full_name"] == "Alice"


@pytest.mark.anyio
async def test_get_user_not_found_returns_404(client):
    """GET /users/{user_id} con UUID inexistente → HTTP 404. Requisito 3.2"""
    svc = _mock_service(
        get_user=HTTPException(status_code=404, detail="Usuario no encontrado")
    )
    with patch("app.api.v1.endpoints.users.UserService", return_value=svc):
        resp = await client.get(f"/api/v1/users/{uuid.uuid4()}")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Usuario no encontrado"


@pytest.mark.anyio
async def test_get_user_invalid_uuid_returns_422(client):
    """GET /users/{user_id} con UUID inválido → HTTP 422. Requisito 3.3"""
    resp = await client.get("/api/v1/users/not-a-uuid")
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_get_user_no_password_hash_in_response(client):
    """GET /users/{user_id} → respuesta nunca contiene password_hash. Requisito 3.4"""
    user = _make_user_read()
    svc = _mock_service(get_user=user)
    with patch("app.api.v1.endpoints.users.UserService", return_value=svc):
        resp = await client.get(f"/api/v1/users/{user.id}")

    assert "password_hash" not in resp.json()


# ---------------------------------------------------------------------------
# PATCH /users/{user_id} — Requisitos 4.1, 4.2, 4.5, 4.6
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_update_user_partial_returns_200(client):
    """PATCH /users/{user_id} → solo los campos enviados cambian, HTTP 200. Requisito 4.1"""
    user = _make_user_read(full_name="Updated Name")
    svc = _mock_service(update_user=user)
    with patch("app.api.v1.endpoints.users.UserService", return_value=svc):
        resp = await client.patch(
            f"/api/v1/users/{user.id}", json={"full_name": "Updated Name"}
        )

    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Updated Name"


@pytest.mark.anyio
async def test_update_user_not_found_returns_404(client):
    """PATCH /users/{user_id} con UUID inexistente → HTTP 404. Requisito 4.2"""
    svc = _mock_service(
        update_user=HTTPException(status_code=404, detail="Usuario no encontrado")
    )
    with patch("app.api.v1.endpoints.users.UserService", return_value=svc):
        resp = await client.patch(
            f"/api/v1/users/{uuid.uuid4()}", json={"full_name": "Ghost"}
        )

    assert resp.status_code == 404


@pytest.mark.anyio
async def test_update_user_invalid_body_returns_422(client):
    """PATCH /users/{user_id} con body inválido → HTTP 422. Requisito 4.5"""
    resp = await client.patch(
        f"/api/v1/users/{uuid.uuid4()}", json={"role": "INVALID_ROLE"}
    )
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_update_user_no_password_hash_in_response(client):
    """PATCH /users/{user_id} → respuesta nunca contiene password_hash. Requisito 4.6"""
    user = _make_user_read()
    svc = _mock_service(update_user=user)
    with patch("app.api.v1.endpoints.users.UserService", return_value=svc):
        resp = await client.patch(
            f"/api/v1/users/{user.id}", json={"full_name": "New Name"}
        )

    assert "password_hash" not in resp.json()


# ---------------------------------------------------------------------------
# PATCH /users/{user_id}/status — Requisitos 5.1, 5.2, 5.3, 5.4
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_update_status_to_inactive_returns_200(client):
    """PATCH /users/{user_id}/status → status=INACTIVE, HTTP 200. Requisito 5.1"""
    user = _make_user_read(status=UserStatusEnum.INACTIVE)
    svc = _mock_service(update_user_status=user)
    with patch("app.api.v1.endpoints.users.UserService", return_value=svc):
        resp = await client.patch(
            f"/api/v1/users/{user.id}/status", json={"status": "INACTIVE"}
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "INACTIVE"


@pytest.mark.anyio
async def test_update_status_to_active_returns_200(client):
    """PATCH /users/{user_id}/status → status=ACTIVE, HTTP 200. Requisito 5.1"""
    user = _make_user_read(status=UserStatusEnum.ACTIVE)
    svc = _mock_service(update_user_status=user)
    with patch("app.api.v1.endpoints.users.UserService", return_value=svc):
        resp = await client.patch(
            f"/api/v1/users/{user.id}/status", json={"status": "ACTIVE"}
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "ACTIVE"


@pytest.mark.anyio
async def test_update_status_not_found_returns_404(client):
    """PATCH /users/{user_id}/status con UUID inexistente → HTTP 404. Requisito 5.2"""
    svc = _mock_service(
        update_user_status=HTTPException(status_code=404, detail="Usuario no encontrado")
    )
    with patch("app.api.v1.endpoints.users.UserService", return_value=svc):
        resp = await client.patch(
            f"/api/v1/users/{uuid.uuid4()}/status", json={"status": "INACTIVE"}
        )

    assert resp.status_code == 404


@pytest.mark.anyio
async def test_update_status_invalid_uuid_returns_422(client):
    """PATCH /users/{user_id}/status con UUID inválido → HTTP 422. Requisito 5.3"""
    resp = await client.patch("/api/v1/users/not-a-uuid/status", json={"status": "INACTIVE"})
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_update_status_invalid_value_returns_422(client):
    """PATCH /users/{user_id}/status con valor inválido → HTTP 422. Requisito 5.4"""
    resp = await client.patch(
        f"/api/v1/users/{uuid.uuid4()}/status", json={"status": "DELETED"}
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /users — Requisitos 1.1, 1.2, 1.4, 1.5, 1.6, 1.7, 1.9
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_list_users_default_returns_active_only(client):
    """GET /users sin parámetros → solo retorna usuarios ACTIVE. Requisito 1.4"""
    active_users = [_make_user_read(status=UserStatusEnum.ACTIVE) for _ in range(2)]
    paginated = _paginated(active_users)
    svc = _mock_service(list_users=paginated)
    with patch("app.api.v1.endpoints.users.UserService", return_value=svc):
        resp = await client.get("/api/v1/users")

    assert resp.status_code == 200
    body = resp.json()
    assert all(u["status"] == "ACTIVE" for u in body["data"])


@pytest.mark.anyio
async def test_list_users_status_inactive_filter(client):
    """GET /users?status=INACTIVE → retorna usuarios INACTIVE. Requisito 1.5"""
    inactive_users = [_make_user_read(status=UserStatusEnum.INACTIVE)]
    paginated = _paginated(inactive_users)
    svc = _mock_service(list_users=paginated)
    with patch("app.api.v1.endpoints.users.UserService", return_value=svc):
        resp = await client.get("/api/v1/users?status=INACTIVE")

    assert resp.status_code == 200
    assert resp.json()["data"][0]["status"] == "INACTIVE"


@pytest.mark.anyio
async def test_list_users_role_filter(client):
    """GET /users?role=STUDENT → solo retorna estudiantes. Requisito 1.2"""
    students = [_make_user_read(role=RoleEnum.STUDENT) for _ in range(3)]
    paginated = _paginated(students)
    svc = _mock_service(list_users=paginated)
    with patch("app.api.v1.endpoints.users.UserService", return_value=svc):
        resp = await client.get("/api/v1/users?role=STUDENT")

    assert resp.status_code == 200
    assert all(u["role"] == "STUDENT" for u in resp.json()["data"])


@pytest.mark.anyio
async def test_list_users_limit_over_100_returns_422(client):
    """GET /users?limit=101 → HTTP 422. Requisito 1.7"""
    resp = await client.get("/api/v1/users?limit=101")
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_list_users_negative_skip_returns_422(client):
    """GET /users?skip=-1 → HTTP 422. Requisito 1.6"""
    resp = await client.get("/api/v1/users?skip=-1")
    assert resp.status_code == 422


@pytest.mark.anyio
async def test_list_users_no_password_hash_in_response(client):
    """GET /users → respuesta nunca contiene password_hash. Requisito 1.9"""
    users = [_make_user_read() for _ in range(2)]
    paginated = _paginated(users)
    svc = _mock_service(list_users=paginated)
    with patch("app.api.v1.endpoints.users.UserService", return_value=svc):
        resp = await client.get("/api/v1/users")

    for user in resp.json()["data"]:
        assert "password_hash" not in user


@pytest.mark.anyio
async def test_list_users_returns_paginated_schema(client):
    """GET /users → respuesta incluye data, total, skip, limit. Requisito 1.1"""
    paginated = _paginated([_make_user_read()], skip=0, limit=20)
    svc = _mock_service(list_users=paginated)
    with patch("app.api.v1.endpoints.users.UserService", return_value=svc):
        resp = await client.get("/api/v1/users")

    body = resp.json()
    assert "data" in body
    assert "total" in body
    assert "skip" in body
    assert "limit" in body
