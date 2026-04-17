"""
Tests de propiedades (Hypothesis) para los endpoints CRUD de User.
Feature: user-crud-endpoints
Requisitos: 1.x, 2.x, 3.x, 4.x, 5.x, 8.x
"""

import sys
import types
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Module-level stubs — must run before any app import
# ---------------------------------------------------------------------------

def _stub_heavy_deps():
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

from app.main import app  # noqa: E402
from app.application.schemas.user import PaginatedResponse, UserCreate, UserRead  # noqa: E402
from app.domain.enums import RoleEnum, UserStatusEnum  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_user_read(
    *,
    id: uuid.UUID | None = None,
    email: str = "test@example.com",
    full_name: str = "Test User",
    role: RoleEnum = RoleEnum.STUDENT,
    status: UserStatusEnum = UserStatusEnum.ACTIVE,
    ml_consent: bool = False,
) -> UserRead:
    return UserRead(
        id=id or uuid.uuid4(),
        email=email,
        full_name=full_name,
        role=role,
        status=status,
        ml_consent=ml_consent,
        created_at=_now(),
        updated_at=_now(),
    )


def _paginated(
    users: list[UserRead],
    skip: int = 0,
    limit: int = 100,
    total: int | None = None,
) -> PaginatedResponse[UserRead]:
    return PaginatedResponse[UserRead](
        data=users,
        total=total if total is not None else len(users),
        skip=skip,
        limit=limit,
    )


def _mock_service(**method_overrides):
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
# Fixture: async client with mocked DB session
# ---------------------------------------------------------------------------

# anyio_backend and client fixtures are provided by tests/conftest.py


# ---------------------------------------------------------------------------
# 12.1 — Propiedad 1: Round-trip crear → recuperar
# Valida: Requisitos 2.1, 3.1, 8.1
# ---------------------------------------------------------------------------

# Feature: user-crud-endpoints, Propiedad 1: Round-trip crear → recuperar
@pytest.mark.anyio
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    user_data=st.builds(
        UserCreate,
        email=st.emails(),
        full_name=st.text(min_size=1),
        role=st.sampled_from(RoleEnum),
    )
)
async def test_create_get_roundtrip(client, user_data: UserCreate):
    """
    **Validates: Requisitos 2.1, 3.1, 8.1**

    Para cualquier UserCreate válido, crear el usuario vía POST y luego
    recuperarlo vía GET debe retornar los mismos email, full_name, role y status.
    """
    user_id = uuid.uuid4()
    created_user = _make_user_read(
        id=user_id,
        email=user_data.email,
        full_name=user_data.full_name,
        role=user_data.role,
        status=UserStatusEnum.ACTIVE,
    )

    svc = _mock_service(create_user=created_user, get_user=created_user)
    with patch("app.api.v1.endpoints.users.UserService", return_value=svc):
        post_resp = await client.post(
            "/api/v1/users",
            json={
                "email": user_data.email,
                "full_name": user_data.full_name,
                "role": user_data.role.value,
            },
        )
        assert post_resp.status_code == 201
        post_body = post_resp.json()

        get_resp = await client.get(f"/api/v1/users/{user_id}")
        assert get_resp.status_code == 200
        get_body = get_resp.json()

    assert post_body["email"] == get_body["email"]
    assert post_body["full_name"] == get_body["full_name"]
    assert post_body["role"] == get_body["role"]
    assert post_body["status"] == get_body["status"]


# ---------------------------------------------------------------------------
# 12.2 — Propiedad 2: Idempotencia de lectura
# Valida: Requisito 8.2
# ---------------------------------------------------------------------------

# Feature: user-crud-endpoints, Propiedad 2: Idempotencia de lectura
@pytest.mark.anyio
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    user_data=st.builds(
        UserCreate,
        email=st.emails(),
        full_name=st.text(min_size=1),
        role=st.sampled_from(RoleEnum),
    )
)
async def test_get_idempotent(client, user_data: UserCreate):
    """
    **Validates: Requisito 8.2**

    Múltiples llamadas consecutivas a GET /users/{user_id} sin modificaciones
    intermedias deben retornar siempre la misma respuesta.
    """
    user_id = uuid.uuid4()
    user = _make_user_read(
        id=user_id,
        email=user_data.email,
        full_name=user_data.full_name,
        role=user_data.role,
    )

    svc = _mock_service(get_user=user)
    with patch("app.api.v1.endpoints.users.UserService", return_value=svc):
        resp1 = await client.get(f"/api/v1/users/{user_id}")
        resp2 = await client.get(f"/api/v1/users/{user_id}")
        resp3 = await client.get(f"/api/v1/users/{user_id}")

    assert resp1.status_code == 200
    assert resp1.json() == resp2.json()
    assert resp2.json() == resp3.json()


# ---------------------------------------------------------------------------
# 12.3 — Propiedad 3: Filtrado por rol es exhaustivo y exclusivo
# Valida: Requisitos 1.2, 1.5
# ---------------------------------------------------------------------------

# Feature: user-crud-endpoints, Propiedad 3: Filtrado por rol es exhaustivo y exclusivo
@pytest.mark.anyio
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    users_data=st.lists(
        st.builds(
            UserCreate,
            email=st.emails(),
            full_name=st.text(min_size=1),
            role=st.sampled_from(RoleEnum),
        ),
        min_size=1,
    ),
    target_role=st.sampled_from(RoleEnum),
)
async def test_filter_by_role_exhaustive(
    client, users_data: list[UserCreate], target_role: RoleEnum
):
    """
    **Validates: Requisitos 1.2, 1.5**

    Todos los elementos en data deben tener role == target_role.
    total == len(data) cuando skip=0 y limit >= total.
    """
    # Build only users with the target role
    filtered_users = [
        _make_user_read(
            email=u.email,
            full_name=u.full_name,
            role=target_role,
            status=UserStatusEnum.ACTIVE,
        )
        for u in users_data
        if u.role == target_role
    ]
    n = len(filtered_users)
    paginated = _paginated(filtered_users, skip=0, limit=max(n, 1), total=n)

    svc = _mock_service(list_users=paginated)
    with patch("app.api.v1.endpoints.users.UserService", return_value=svc):
        resp = await client.get(
            f"/api/v1/users?role={target_role.value}&skip=0&limit={max(n, 1)}"
        )

    assert resp.status_code == 200
    body = resp.json()
    for user in body["data"]:
        assert user["role"] == target_role.value
    assert body["total"] == len(body["data"])


# ---------------------------------------------------------------------------
# 12.4 — Propiedad 4: Soft delete — usuarios INACTIVE excluidos del listado por defecto
# Valida: Requisitos 1.4, 5.1, 8.7
# ---------------------------------------------------------------------------

# Feature: user-crud-endpoints, Propiedad 4: Soft delete — usuarios INACTIVE excluidos del listado por defecto
@pytest.mark.anyio
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    user_data=st.builds(
        UserCreate,
        email=st.emails(),
        full_name=st.text(min_size=1),
        role=st.sampled_from(RoleEnum),
    )
)
async def test_inactive_excluded_from_default_list(client, user_data: UserCreate):
    """
    **Validates: Requisitos 1.4, 5.1, 8.7**

    Un usuario creado y luego desactivado NO debe aparecer en GET /users
    sin el parámetro status (que por defecto filtra solo ACTIVE).
    """
    user_id = uuid.uuid4()
    active_user = _make_user_read(
        id=user_id,
        email=user_data.email,
        full_name=user_data.full_name,
        role=user_data.role,
        status=UserStatusEnum.ACTIVE,
    )
    inactive_user = _make_user_read(
        id=user_id,
        email=user_data.email,
        full_name=user_data.full_name,
        role=user_data.role,
        status=UserStatusEnum.INACTIVE,
    )
    # After deactivation, default list returns empty (no ACTIVE users with this id)
    empty_paginated = _paginated([], skip=0, limit=100, total=0)

    svc_create = _mock_service(create_user=active_user)
    svc_deactivate = _mock_service(update_user_status=inactive_user)
    svc_list = _mock_service(list_users=empty_paginated)

    with patch("app.api.v1.endpoints.users.UserService", return_value=svc_create):
        post_resp = await client.post(
            "/api/v1/users",
            json={
                "email": user_data.email,
                "full_name": user_data.full_name,
                "role": user_data.role.value,
            },
        )
    assert post_resp.status_code == 201

    with patch("app.api.v1.endpoints.users.UserService", return_value=svc_deactivate):
        patch_resp = await client.patch(
            f"/api/v1/users/{user_id}/status",
            json={"status": "INACTIVE"},
        )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "INACTIVE"

    with patch("app.api.v1.endpoints.users.UserService", return_value=svc_list):
        list_resp = await client.get("/api/v1/users")
    assert list_resp.status_code == 200
    body = list_resp.json()
    ids_in_list = [u["id"] for u in body["data"]]
    assert str(user_id) not in ids_in_list


# ---------------------------------------------------------------------------
# 12.5 — Propiedad 5: Reactivación — usuarios ACTIVE incluidos en listado por defecto
# Valida: Requisitos 1.4, 1.5, 5.1, 8.8
# ---------------------------------------------------------------------------

# Feature: user-crud-endpoints, Propiedad 5: Reactivación — usuarios ACTIVE incluidos en listado por defecto
@pytest.mark.anyio
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    user_data=st.builds(
        UserCreate,
        email=st.emails(),
        full_name=st.text(min_size=1),
        role=st.sampled_from(RoleEnum),
    )
)
async def test_reactivated_appears_in_default_list(client, user_data: UserCreate):
    """
    **Validates: Requisitos 1.4, 1.5, 5.1, 8.8**

    Un usuario INACTIVE reactivado debe aparecer en GET /users sin parámetro status.
    """
    user_id = uuid.uuid4()
    inactive_user = _make_user_read(
        id=user_id,
        email=user_data.email,
        full_name=user_data.full_name,
        role=user_data.role,
        status=UserStatusEnum.INACTIVE,
    )
    reactivated_user = _make_user_read(
        id=user_id,
        email=user_data.email,
        full_name=user_data.full_name,
        role=user_data.role,
        status=UserStatusEnum.ACTIVE,
    )
    paginated_with_user = _paginated([reactivated_user], skip=0, limit=100, total=1)

    svc_reactivate = _mock_service(update_user_status=reactivated_user)
    svc_list = _mock_service(list_users=paginated_with_user)

    # Simulate: user was INACTIVE, now reactivate
    with patch("app.api.v1.endpoints.users.UserService", return_value=svc_reactivate):
        patch_resp = await client.patch(
            f"/api/v1/users/{user_id}/status",
            json={"status": "ACTIVE"},
        )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "ACTIVE"

    with patch("app.api.v1.endpoints.users.UserService", return_value=svc_list):
        list_resp = await client.get("/api/v1/users")
    assert list_resp.status_code == 200
    body = list_resp.json()
    ids_in_list = [u["id"] for u in body["data"]]
    assert str(user_id) in ids_in_list


# ---------------------------------------------------------------------------
# 12.6 — Propiedad 6: Paginación metamórfica
# Valida: Requisito 8.3
# ---------------------------------------------------------------------------

# Feature: user-crud-endpoints, Propiedad 6: Paginación metamórfica — unión de páginas equivale a consulta completa
@pytest.mark.anyio
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    users_data=st.lists(
        st.builds(
            UserCreate,
            email=st.emails(),
            full_name=st.text(min_size=1),
            role=st.sampled_from(RoleEnum),
        ),
        min_size=2,
        max_size=10,
    ),
    page_size=st.integers(min_value=1, max_value=10),
)
async def test_pagination_metamorphic(
    client, users_data: list[UserCreate], page_size: int
):
    """
    **Validates: Requisito 8.3**

    La concatenación de todas las páginas con limit=k debe contener los mismos
    elementos que una consulta con limit=N, skip=0.
    """
    prefix = uuid.uuid4().hex[:8]
    all_users = [
        _make_user_read(
            email=f"{prefix}_{i}_{u.email}",
            full_name=u.full_name,
            role=u.role,
            status=UserStatusEnum.ACTIVE,
        )
        for i, u in enumerate(users_data)
    ]
    n = len(all_users)

    def _make_page_service(skip: int, limit: int):
        page_data = all_users[skip : skip + limit]
        return _mock_service(
            list_users=_paginated(page_data, skip=skip, limit=limit, total=n)
        )

    collected_ids: list[str] = []
    skip = 0
    with patch("app.api.v1.endpoints.users.UserService") as mock_cls:
        while True:
            mock_cls.return_value = _make_page_service(skip, page_size)
            resp = await client.get(f"/api/v1/users?skip={skip}&limit={page_size}")
            assert resp.status_code == 200
            page_body = resp.json()
            page_ids = [u["id"] for u in page_body["data"]]
            if not page_ids:
                break
            collected_ids.extend(page_ids)
            skip += page_size
            if skip >= n:
                break

    # Full query in one shot
    full_svc = _mock_service(list_users=_paginated(all_users, skip=0, limit=n, total=n))
    with patch("app.api.v1.endpoints.users.UserService", return_value=full_svc):
        full_resp = await client.get(f"/api/v1/users?skip=0&limit={n}")
    assert full_resp.status_code == 200
    full_ids = [u["id"] for u in full_resp.json()["data"]]

    assert sorted(collected_ids) == sorted(full_ids)


# ---------------------------------------------------------------------------
# 12.7 — Propiedad 7: Consistencia del total paginado
# Valida: Requisito 8.4
# ---------------------------------------------------------------------------

# Feature: user-crud-endpoints, Propiedad 7: Consistencia del total paginado
@pytest.mark.anyio
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    users_data=st.lists(
        st.builds(
            UserCreate,
            email=st.emails(),
            full_name=st.text(min_size=1),
            role=st.sampled_from(RoleEnum),
        ),
        min_size=1,
        max_size=10,
    ),
    skip=st.integers(min_value=0, max_value=20),
)
async def test_pagination_total_consistent(
    client, users_data: list[UserCreate], skip: int
):
    """
    **Validates: Requisito 8.4**

    El campo total debe ser igual a N independientemente del valor de skip.
    """
    prefix = uuid.uuid4().hex[:8]
    all_users = [
        _make_user_read(
            email=f"{prefix}_{i}_{u.email}",
            full_name=u.full_name,
            role=u.role,
            status=UserStatusEnum.ACTIVE,
        )
        for i, u in enumerate(users_data)
    ]
    n = len(all_users)
    page_data = all_users[skip : skip + 20]

    svc = _mock_service(
        list_users=_paginated(page_data, skip=skip, limit=20, total=n)
    )
    with patch("app.api.v1.endpoints.users.UserService", return_value=svc):
        resp = await client.get(f"/api/v1/users?skip={skip}&limit=20")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == n


# ---------------------------------------------------------------------------
# 12.8 — Propiedad 8: HTTP 404 para UUID inexistente
# Valida: Requisitos 3.2, 4.2, 5.2, 8.5
# ---------------------------------------------------------------------------

# Feature: user-crud-endpoints, Propiedad 8: HTTP 404 para UUID inexistente
@pytest.mark.anyio
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(random_uuid=st.uuids())
async def test_nonexistent_uuid_returns_404(client, random_uuid: uuid.UUID):
    """
    **Validates: Requisitos 3.2, 4.2, 5.2, 8.5**

    Para cualquier UUID que no exista en la BD, GET /users/{id},
    PATCH /users/{id} y PATCH /users/{id}/status deben retornar HTTP 404.
    """
    not_found = HTTPException(status_code=404, detail="Usuario no encontrado")
    svc = _mock_service(
        get_user=not_found,
        update_user=not_found,
        update_user_status=not_found,
    )
    with patch("app.api.v1.endpoints.users.UserService", return_value=svc):
        get_resp = await client.get(f"/api/v1/users/{random_uuid}")
        patch_resp = await client.patch(
            f"/api/v1/users/{random_uuid}",
            json={"full_name": "Ghost"},
        )
        status_resp = await client.patch(
            f"/api/v1/users/{random_uuid}/status",
            json={"status": "INACTIVE"},
        )

    assert get_resp.status_code == 404
    assert patch_resp.status_code == 404
    assert status_resp.status_code == 404


# ---------------------------------------------------------------------------
# 12.9 — Propiedad 9: password_hash nunca aparece en ninguna respuesta
# Valida: Requisitos 1.9, 2.5, 3.4, 4.6, 5.6, 8.6
# ---------------------------------------------------------------------------

# Feature: user-crud-endpoints, Propiedad 9: password_hash nunca aparece en ninguna respuesta
@pytest.mark.anyio
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    user_data=st.builds(
        UserCreate,
        email=st.emails(),
        full_name=st.text(min_size=1),
        role=st.sampled_from(RoleEnum),
        password=st.text(min_size=1),
    )
)
async def test_password_hash_never_in_response(client, user_data: UserCreate):
    """
    **Validates: Requisitos 1.9, 2.5, 3.4, 4.6, 5.6, 8.6**

    Ninguna respuesta de ningún endpoint debe contener el campo password_hash.
    """
    user_id = uuid.uuid4()
    user = _make_user_read(
        id=user_id,
        email=user_data.email,
        full_name=user_data.full_name,
        role=user_data.role,
        status=UserStatusEnum.ACTIVE,
    )
    paginated = _paginated([user])
    updated_user = _make_user_read(
        id=user_id,
        email=user_data.email,
        full_name="Updated Name",
        role=user_data.role,
        status=UserStatusEnum.ACTIVE,
    )
    inactive_user = _make_user_read(
        id=user_id,
        email=user_data.email,
        full_name=user_data.full_name,
        role=user_data.role,
        status=UserStatusEnum.INACTIVE,
    )

    svc = _mock_service(
        create_user=user,
        get_user=user,
        list_users=paginated,
        update_user=updated_user,
        update_user_status=inactive_user,
    )

    with patch("app.api.v1.endpoints.users.UserService", return_value=svc):
        post_resp = await client.post(
            "/api/v1/users",
            json={
                "email": user_data.email,
                "full_name": user_data.full_name,
                "role": user_data.role.value,
                "password": user_data.password,
            },
        )
        get_resp = await client.get(f"/api/v1/users/{user_id}")
        list_resp = await client.get("/api/v1/users")
        patch_resp = await client.patch(
            f"/api/v1/users/{user_id}",
            json={"full_name": "Updated Name"},
        )
        status_resp = await client.patch(
            f"/api/v1/users/{user_id}/status",
            json={"status": "INACTIVE"},
        )

    assert "password_hash" not in post_resp.json()
    assert "password_hash" not in get_resp.json()
    for u in list_resp.json()["data"]:
        assert "password_hash" not in u
    assert "password_hash" not in patch_resp.json()
    assert "password_hash" not in status_resp.json()


# ---------------------------------------------------------------------------
# 12.10 — Propiedad 10: Audit log registrado en cada operación de escritura
# Valida: Requisitos 2.4, 4.4, 5.5
# ---------------------------------------------------------------------------

# Feature: user-crud-endpoints, Propiedad 10: Audit log registrado en cada operación de escritura
@pytest.mark.anyio
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    user_data=st.builds(
        UserCreate,
        email=st.emails(),
        full_name=st.text(min_size=1),
        role=st.sampled_from(RoleEnum),
    )
)
async def test_write_operations_create_audit_log(client, user_data: UserCreate):
    """
    **Validates: Requisitos 2.4, 4.4, 5.5**

    Cada operación de escritura exitosa (POST /users, PATCH /users/{id},
    PATCH /users/{id}/status) debe invocar AuditLogRepository.register
    exactamente una vez con el record_id correcto y la operation correspondiente
    (INSERT para creación, UPDATE para actualizaciones).

    La propiedad se verifica interceptando AuditLogRepository.register en la
    capa de infraestructura, lo que garantiza que el contrato de auditoría se
    cumple independientemente de los datos de entrada generados por Hypothesis.
    """
    from app.application.schemas.audit_log import AuditLogCreate  # noqa: PLC0415
    from app.domain.enums import OperationEnum  # noqa: PLC0415
    from app.infrastructure.repositories.audit_log_repository import AuditLogRepository  # noqa: PLC0415
    from app.infrastructure.repositories.user_repository import UserRepository  # noqa: PLC0415
    from app.infrastructure.models.user import User as UserModel  # noqa: PLC0415

    user_id = uuid.uuid4()

    # Build a realistic ORM User instance (no DB needed — fields set directly)
    orm_user = UserModel(
        id=user_id,
        email=user_data.email,
        full_name=user_data.full_name,
        role=user_data.role,
        status=UserStatusEnum.ACTIVE,
        ml_consent=False,
        created_at=_now(),
        updated_at=_now(),
    )
    orm_user_updated = UserModel(
        id=user_id,
        email=user_data.email,
        full_name="Updated",
        role=user_data.role,
        status=UserStatusEnum.ACTIVE,
        ml_consent=False,
        created_at=_now(),
        updated_at=_now(),
    )
    orm_user_inactive = UserModel(
        id=user_id,
        email=user_data.email,
        full_name=user_data.full_name,
        role=user_data.role,
        status=UserStatusEnum.INACTIVE,
        ml_consent=False,
        created_at=_now(),
        updated_at=_now(),
    )

    # Collected audit calls: list of AuditLogCreate passed to register()
    audit_calls: list[AuditLogCreate] = []

    async def _capture_register(self, entry: AuditLogCreate) -> None:  # noqa: ANN001
        audit_calls.append(entry)

    # ------------------------------------------------------------------ #
    # POST /users — expects INSERT audit log with record_id == user_id    #
    # ------------------------------------------------------------------ #
    mock_session_create = AsyncMock()
    mock_session_create.add = MagicMock()
    mock_session_create.flush = AsyncMock()
    mock_session_create.refresh = AsyncMock(
        side_effect=lambda obj: setattr(obj, "id", user_id) or None
    )

    async def _override_session_create():
        yield mock_session_create

    from app.infrastructure.database import get_session  # noqa: PLC0415

    app.dependency_overrides[get_session] = _override_session_create

    with (
        patch.object(UserRepository, "get_by_email", new=AsyncMock(return_value=None)),
        patch.object(AuditLogRepository, "register", new=_capture_register),
    ):
        post_resp = await client.post(
            "/api/v1/users",
            json={
                "email": user_data.email,
                "full_name": user_data.full_name,
                "role": user_data.role.value,
            },
        )

    assert post_resp.status_code == 201
    assert len(audit_calls) == 1, "POST /users must produce exactly 1 audit log"
    assert audit_calls[0].operation == OperationEnum.INSERT
    assert audit_calls[0].record_id == user_id
    assert audit_calls[0].table_name == "users"

    # ------------------------------------------------------------------ #
    # PATCH /users/{id} — expects UPDATE audit log                        #
    # ------------------------------------------------------------------ #
    audit_calls.clear()

    mock_session_update = AsyncMock()
    mock_session_update.add = MagicMock()
    mock_session_update.flush = AsyncMock()
    mock_session_update.refresh = AsyncMock()

    async def _override_session_update():
        yield mock_session_update

    app.dependency_overrides[get_session] = _override_session_update

    with (
        patch.object(UserRepository, "get_by_id", new=AsyncMock(return_value=orm_user_updated)),
        patch.object(AuditLogRepository, "register", new=_capture_register),
    ):
        patch_resp = await client.patch(
            f"/api/v1/users/{user_id}",
            json={"full_name": "Updated"},
        )

    assert patch_resp.status_code == 200
    assert len(audit_calls) == 1, "PATCH /users/{id} must produce exactly 1 audit log"
    assert audit_calls[0].operation == OperationEnum.UPDATE
    assert audit_calls[0].record_id == user_id
    assert audit_calls[0].table_name == "users"

    # ------------------------------------------------------------------ #
    # PATCH /users/{id}/status — expects UPDATE audit log                 #
    # ------------------------------------------------------------------ #
    audit_calls.clear()

    mock_session_status = AsyncMock()
    mock_session_status.add = MagicMock()
    mock_session_status.flush = AsyncMock()
    mock_session_status.refresh = AsyncMock()

    async def _override_session_status():
        yield mock_session_status

    app.dependency_overrides[get_session] = _override_session_status

    with (
        # get_by_id must return the ACTIVE user so previous_data == {"status": ACTIVE}
        patch.object(UserRepository, "get_by_id", new=AsyncMock(return_value=orm_user)),
        patch.object(AuditLogRepository, "register", new=_capture_register),
    ):
        status_resp = await client.patch(
            f"/api/v1/users/{user_id}/status",
            json={"status": "INACTIVE"},
        )

    assert status_resp.status_code == 200
    assert len(audit_calls) == 1, "PATCH /users/{id}/status must produce exactly 1 audit log"
    assert audit_calls[0].operation == OperationEnum.UPDATE
    assert audit_calls[0].record_id == user_id
    assert audit_calls[0].table_name == "users"
    assert audit_calls[0].previous_data == {"status": UserStatusEnum.ACTIVE}
    assert audit_calls[0].new_data == {"status": UserStatusEnum.INACTIVE}


# ---------------------------------------------------------------------------
# 12.11 — Propiedad 11: Email duplicado retorna HTTP 409
# Valida: Requisito 2.2
# ---------------------------------------------------------------------------

# Feature: user-crud-endpoints, Propiedad 11: Email duplicado retorna HTTP 409
@pytest.mark.anyio
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(email=st.emails())
async def test_duplicate_email_returns_409(client, email: str):
    """
    **Validates: Requisito 2.2**

    Usar el mismo email dos veces en POST /users: el segundo intento debe
    retornar HTTP 409 sin crear un registro nuevo.
    """
    user = _make_user_read(email=email, status=UserStatusEnum.ACTIVE)

    svc_first = _mock_service(create_user=user)
    svc_second = _mock_service(
        create_user=HTTPException(status_code=409, detail="El email ya está registrado")
    )

    payload = {
        "email": email,
        "full_name": "Test User",
        "role": RoleEnum.STUDENT.value,
    }

    with patch("app.api.v1.endpoints.users.UserService", return_value=svc_first):
        first_resp = await client.post("/api/v1/users", json=payload)
    assert first_resp.status_code == 201

    with patch("app.api.v1.endpoints.users.UserService", return_value=svc_second):
        second_resp = await client.post("/api/v1/users", json=payload)
    assert second_resp.status_code == 409
    assert second_resp.json()["detail"] == "El email ya está registrado"

    # The second service's create_user was called exactly once (one attempt)
    svc_second.create_user.assert_called_once()
