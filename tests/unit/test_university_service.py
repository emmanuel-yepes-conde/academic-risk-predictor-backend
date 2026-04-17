"""
Tests unitarios para UniversityService.

Verifica los casos de error del servicio de universidades usando mocks
del repositorio (sin acceso a base de datos).

Requirements: 1.2, 1.3, 1.5, 1.6, 1.7
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.application.schemas.university import UniversityCreate, UniversityUpdate
from app.application.services.university_service import UniversityService
from app.domain.enums import RoleEnum
from app.infrastructure.models.university import University


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_university(**overrides) -> University:
    """Build a University ORM instance with sensible defaults."""
    defaults = dict(
        id=uuid.uuid4(),
        name="Universidad de Prueba",
        code="UTEST",
        country="Colombia",
        city="Bogotá",
        active=True,
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return University(**defaults)


def _make_repo(**method_overrides) -> AsyncMock:
    """Build a mock IUniversityRepository with default return values."""
    repo = AsyncMock()
    repo.create = AsyncMock(side_effect=lambda data: _make_university(
        name=data.name, code=data.code, country=data.country, city=data.city, active=data.active,
    ))
    repo.get_by_id = AsyncMock(return_value=None)
    repo.get_by_code = AsyncMock(return_value=None)
    repo.list = AsyncMock(return_value=[])
    repo.count = AsyncMock(return_value=0)
    repo.update = AsyncMock(return_value=None)
    for name, value in method_overrides.items():
        setattr(repo, name, value)
    return repo


# ---------------------------------------------------------------------------
# Tests: create() — 409 Conflict cuando code duplicado (Req 1.3)
# ---------------------------------------------------------------------------

class TestCreateDuplicateCode:
    """create() lanza HTTPException(409) cuando el código de universidad ya existe."""

    @pytest.mark.anyio
    async def test_create_duplicate_code_returns_409(self):
        existing = _make_university(code="DUP01")
        repo = _make_repo(get_by_code=AsyncMock(return_value=existing))
        service = UniversityService(repo)

        data = UniversityCreate(
            name="Nueva Universidad",
            code="DUP01",
            country="Colombia",
            city="Medellín",
        )

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await service.create(data, actor_role=RoleEnum.ADMIN)

        assert exc_info.value.status_code == 409
        assert "ya existe" in exc_info.value.detail

    @pytest.mark.anyio
    async def test_create_duplicate_code_does_not_call_repo_create(self):
        """El repositorio no debe recibir la llamada create si el código ya existe."""
        existing = _make_university(code="DUP02")
        repo = _make_repo(get_by_code=AsyncMock(return_value=existing))
        service = UniversityService(repo)

        data = UniversityCreate(
            name="Otra Universidad",
            code="DUP02",
            country="Colombia",
            city="Cali",
        )

        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            await service.create(data, actor_role=RoleEnum.ADMIN)

        repo.create.assert_not_awaited()


# ---------------------------------------------------------------------------
# Tests: create() — 403 Forbidden para roles no-ADMIN (Req 1.7)
# ---------------------------------------------------------------------------

class TestCreateForbiddenForNonAdmin:
    """create() lanza HTTPException(403) cuando el actor no es ADMIN."""

    @pytest.mark.anyio
    @pytest.mark.parametrize("role", [RoleEnum.STUDENT, RoleEnum.PROFESSOR])
    async def test_create_non_admin_returns_403(self, role: RoleEnum):
        repo = _make_repo()
        service = UniversityService(repo)

        data = UniversityCreate(
            name="Universidad Prohibida",
            code="FORB01",
            country="Colombia",
            city="Barranquilla",
        )

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await service.create(data, actor_role=role)

        assert exc_info.value.status_code == 403
        assert "ADMIN" in exc_info.value.detail

    @pytest.mark.anyio
    async def test_create_non_admin_does_not_check_code_uniqueness(self):
        """La verificación de rol ocurre antes de consultar el repositorio."""
        repo = _make_repo()
        service = UniversityService(repo)

        data = UniversityCreate(
            name="Universidad Prohibida",
            code="FORB02",
            country="Colombia",
            city="Cartagena",
        )

        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            await service.create(data, actor_role=RoleEnum.STUDENT)

        repo.get_by_code.assert_not_awaited()
        repo.create.assert_not_awaited()


# ---------------------------------------------------------------------------
# Tests: get() — 404 Not Found cuando no existe (Req 1.5)
# ---------------------------------------------------------------------------

class TestGetNotFound:
    """get() lanza HTTPException(404) cuando la universidad no existe."""

    @pytest.mark.anyio
    async def test_get_nonexistent_returns_404(self):
        repo = _make_repo(get_by_id=AsyncMock(return_value=None))
        service = UniversityService(repo)

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await service.get(uuid.uuid4())

        assert exc_info.value.status_code == 404
        assert "no encontrada" in exc_info.value.detail

    @pytest.mark.anyio
    async def test_get_existing_returns_university_read(self):
        """Caso positivo: get() retorna UniversityRead cuando la universidad existe."""
        uni = _make_university(code="EXIST01")
        repo = _make_repo(get_by_id=AsyncMock(return_value=uni))
        service = UniversityService(repo)

        result = await service.get(uni.id)

        assert result.id == uni.id
        assert result.code == "EXIST01"
        assert result.name == uni.name


# ---------------------------------------------------------------------------
# Tests: update() — 403 Forbidden para roles no-ADMIN (Req 1.7)
# ---------------------------------------------------------------------------

class TestUpdateForbiddenForNonAdmin:
    """update() lanza HTTPException(403) cuando el actor no es ADMIN."""

    @pytest.mark.anyio
    @pytest.mark.parametrize("role", [RoleEnum.STUDENT, RoleEnum.PROFESSOR])
    async def test_update_non_admin_returns_403(self, role: RoleEnum):
        repo = _make_repo()
        service = UniversityService(repo)

        data = UniversityUpdate(name="Nombre Actualizado")

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            await service.update(uuid.uuid4(), data, actor_role=role)

        assert exc_info.value.status_code == 403
        assert "ADMIN" in exc_info.value.detail

    @pytest.mark.anyio
    async def test_update_non_admin_does_not_call_repo_update(self):
        """La verificación de rol ocurre antes de llamar al repositorio."""
        repo = _make_repo()
        service = UniversityService(repo)

        data = UniversityUpdate(city="Manizales")

        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            await service.update(uuid.uuid4(), data, actor_role=RoleEnum.PROFESSOR)

        repo.update.assert_not_awaited()
