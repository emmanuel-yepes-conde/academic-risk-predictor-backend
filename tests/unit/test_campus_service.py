"""
Tests unitarios para CampusService.

Verifica los casos de error y éxito del servicio de campus usando mocks
de los repositorios (sin acceso a base de datos).

Requirements: 2.1, 2.2, 2.3, 2.5, 2.6, 2.7, 4.3, 4.4
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.application.schemas.campus import CampusCreate, CampusUpdate
from app.application.services.campus_service import CampusService
from app.domain.enums import RoleEnum
from app.infrastructure.models.campus import Campus
from app.infrastructure.models.program import Program
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


def _make_campus(**overrides) -> Campus:
    """Build a Campus ORM instance with sensible defaults."""
    defaults = dict(
        id=uuid.uuid4(),
        university_id=uuid.uuid4(),
        campus_code="MED",
        name="Sede Medellín",
        city="Medellín",
        active=True,
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return Campus(**defaults)


def _make_program(**overrides) -> Program:
    """Build a Program ORM instance with sensible defaults."""
    defaults = dict(
        id=uuid.uuid4(),
        campus_id=uuid.uuid4(),
        university_id=uuid.uuid4(),
        institution="USBCO",
        degree_type="PREG",
        program_code="M0200",
        program_name="Psicología",
        pensum="M20020142",
        academic_group="MFPSI",
        location="SAN BENITO",
        snies_code=1361,
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return Program(**defaults)


def _make_repos(**overrides) -> dict:
    """Build mock repositories with default return values."""
    campus_repo = AsyncMock()
    campus_repo.create = AsyncMock(return_value=None)
    campus_repo.get_by_id = AsyncMock(return_value=None)
    campus_repo.get_by_university_and_code = AsyncMock(return_value=None)
    campus_repo.list_by_university = AsyncMock(return_value=[])
    campus_repo.count_by_university = AsyncMock(return_value=0)
    campus_repo.update = AsyncMock(return_value=None)

    university_repo = AsyncMock()
    university_repo.get_by_id = AsyncMock(return_value=None)

    program_repo = AsyncMock()
    program_repo.list_by_campus = AsyncMock(return_value=[])
    program_repo.count_by_campus = AsyncMock(return_value=0)
    program_repo.get_by_id = AsyncMock(return_value=None)

    course_repo = AsyncMock()
    course_repo.listar_por_campus_y_programa = AsyncMock(return_value=[])

    repos = dict(
        campus_repo=campus_repo,
        university_repo=university_repo,
        program_repo=program_repo,
        course_repo=course_repo,
    )
    repos.update(overrides)
    return repos


def _make_service(**repo_overrides) -> tuple[CampusService, dict]:
    """Build a CampusService with mocked repos. Returns (service, repos_dict)."""
    repos = _make_repos(**repo_overrides)
    service = CampusService(
        campus_repo=repos["campus_repo"],
        university_repo=repos["university_repo"],
        program_repo=repos["program_repo"],
        course_repo=repos["course_repo"],
    )
    return service, repos


# ---------------------------------------------------------------------------
# Tests: create() — 403 Forbidden para roles no-ADMIN (Req 2.7)
# ---------------------------------------------------------------------------

class TestCreateForbiddenForNonAdmin:
    """create() lanza HTTPException(403) cuando el actor no es ADMIN."""

    @pytest.mark.anyio
    @pytest.mark.parametrize("role", [RoleEnum.STUDENT, RoleEnum.PROFESSOR])
    async def test_create_non_admin_returns_403(self, role: RoleEnum):
        service, repos = _make_service()
        data = CampusCreate(campus_code="MED", name="Sede Medellín", city="Medellín")

        with pytest.raises(HTTPException) as exc_info:
            await service.create(uuid.uuid4(), data, actor_role=role)

        assert exc_info.value.status_code == 403
        assert "ADMIN" in exc_info.value.detail

    @pytest.mark.anyio
    async def test_create_non_admin_does_not_check_university(self):
        """La verificación de rol ocurre antes de consultar el repositorio."""
        service, repos = _make_service()
        data = CampusCreate(campus_code="BOG", name="Sede Bogotá", city="Bogotá")

        with pytest.raises(HTTPException):
            await service.create(uuid.uuid4(), data, actor_role=RoleEnum.STUDENT)

        repos["university_repo"].get_by_id.assert_not_awaited()
        repos["campus_repo"].create.assert_not_awaited()


# ---------------------------------------------------------------------------
# Tests: create() — 404 si universidad no existe (Req 2.2)
# ---------------------------------------------------------------------------

class TestCreateUniversityNotFound:
    """create() lanza HTTPException(404) cuando la universidad no existe."""

    @pytest.mark.anyio
    async def test_create_nonexistent_university_returns_404(self):
        service, repos = _make_service()
        repos["university_repo"].get_by_id.return_value = None
        data = CampusCreate(campus_code="MED", name="Sede Medellín", city="Medellín")

        with pytest.raises(HTTPException) as exc_info:
            await service.create(uuid.uuid4(), data, actor_role=RoleEnum.ADMIN)

        assert exc_info.value.status_code == 404
        assert "Universidad" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Tests: create() — 409 si combinación university_id+campus_code ya existe (Req 2.3)
# ---------------------------------------------------------------------------

class TestCreateDuplicateCampusCode:
    """create() lanza HTTPException(409) cuando la combinación ya existe."""

    @pytest.mark.anyio
    async def test_create_duplicate_campus_code_returns_409(self):
        uni = _make_university()
        existing_campus = _make_campus(university_id=uni.id, campus_code="MED")
        service, repos = _make_service()
        repos["university_repo"].get_by_id.return_value = uni
        repos["campus_repo"].get_by_university_and_code.return_value = existing_campus

        data = CampusCreate(campus_code="MED", name="Otra Sede", city="Medellín")

        with pytest.raises(HTTPException) as exc_info:
            await service.create(uni.id, data, actor_role=RoleEnum.ADMIN)

        assert exc_info.value.status_code == 409
        repos["campus_repo"].create.assert_not_awaited()


# ---------------------------------------------------------------------------
# Tests: create() — caso exitoso retorna CampusRead (Req 2.1)
# ---------------------------------------------------------------------------

class TestCreateSuccess:
    """create() con datos válidos retorna CampusRead."""

    @pytest.mark.anyio
    async def test_create_valid_data_returns_campus_read(self):
        uni = _make_university()
        uni_id = uni.id
        campus = _make_campus(university_id=uni_id, campus_code="CAL", name="Sede Cali", city="Cali")

        service, repos = _make_service()
        repos["university_repo"].get_by_id.return_value = uni
        repos["campus_repo"].get_by_university_and_code.return_value = None
        repos["campus_repo"].create.return_value = campus

        data = CampusCreate(campus_code="CAL", name="Sede Cali", city="Cali")
        result = await service.create(uni_id, data, actor_role=RoleEnum.ADMIN)

        assert result.id == campus.id
        assert result.university_id == uni_id
        assert result.campus_code == "CAL"
        assert result.name == "Sede Cali"
        repos["campus_repo"].create.assert_awaited_once_with(uni_id, data)


# ---------------------------------------------------------------------------
# Tests: get() — 404 si campus no existe o no pertenece a universidad (Req 2.5)
# ---------------------------------------------------------------------------

class TestGetNotFound:
    """get() lanza HTTPException(404) cuando el campus no existe o no pertenece."""

    @pytest.mark.anyio
    async def test_get_nonexistent_campus_returns_404(self):
        service, repos = _make_service()
        repos["campus_repo"].get_by_id.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await service.get(uuid.uuid4(), uuid.uuid4())

        assert exc_info.value.status_code == 404

    @pytest.mark.anyio
    async def test_get_campus_wrong_university_returns_404(self):
        """Campus exists but belongs to a different university."""
        other_uni_id = uuid.uuid4()
        campus = _make_campus(university_id=other_uni_id)
        service, repos = _make_service()
        repos["campus_repo"].get_by_id.return_value = campus

        with pytest.raises(HTTPException) as exc_info:
            await service.get(uuid.uuid4(), campus.id)

        assert exc_info.value.status_code == 404
        assert "no pertenece" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Tests: update() — 403 para roles no-ADMIN (Req 2.7)
# ---------------------------------------------------------------------------

class TestUpdateForbiddenForNonAdmin:
    """update() lanza HTTPException(403) cuando el actor no es ADMIN."""

    @pytest.mark.anyio
    @pytest.mark.parametrize("role", [RoleEnum.STUDENT, RoleEnum.PROFESSOR])
    async def test_update_non_admin_returns_403(self, role: RoleEnum):
        service, repos = _make_service()
        data = CampusUpdate(name="Nuevo Nombre")

        with pytest.raises(HTTPException) as exc_info:
            await service.update(uuid.uuid4(), uuid.uuid4(), data, actor_role=role)

        assert exc_info.value.status_code == 403
        assert "ADMIN" in exc_info.value.detail

    @pytest.mark.anyio
    async def test_update_non_admin_does_not_call_repo(self):
        """La verificación de rol ocurre antes de consultar el repositorio."""
        service, repos = _make_service()
        data = CampusUpdate(city="Cali")

        with pytest.raises(HTTPException):
            await service.update(uuid.uuid4(), uuid.uuid4(), data, actor_role=RoleEnum.PROFESSOR)

        repos["campus_repo"].get_by_id.assert_not_awaited()
        repos["campus_repo"].update.assert_not_awaited()


# ---------------------------------------------------------------------------
# Tests: update() — 404 si campus no existe (Req 2.6)
# ---------------------------------------------------------------------------

class TestUpdateNotFound:
    """update() lanza HTTPException(404) cuando el campus no existe."""

    @pytest.mark.anyio
    async def test_update_nonexistent_campus_returns_404(self):
        service, repos = _make_service()
        repos["campus_repo"].get_by_id.return_value = None
        data = CampusUpdate(name="Nuevo Nombre")

        with pytest.raises(HTTPException) as exc_info:
            await service.update(uuid.uuid4(), uuid.uuid4(), data, actor_role=RoleEnum.ADMIN)

        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Tests: list_programs_by_campus() — 404 si campus no pertenece a universidad (Req 4.3)
# ---------------------------------------------------------------------------

class TestListProgramsByCampusNotFound:
    """list_programs_by_campus() lanza 404 si campus no pertenece a la universidad."""

    @pytest.mark.anyio
    async def test_campus_not_belonging_to_university_returns_404(self):
        other_uni_id = uuid.uuid4()
        campus = _make_campus(university_id=other_uni_id)
        service, repos = _make_service()
        repos["campus_repo"].get_by_id.return_value = campus

        with pytest.raises(HTTPException) as exc_info:
            await service.list_programs_by_campus(uuid.uuid4(), campus.id, skip=0, limit=20)

        assert exc_info.value.status_code == 404
        assert "no pertenece" in exc_info.value.detail

    @pytest.mark.anyio
    async def test_nonexistent_campus_returns_404(self):
        service, repos = _make_service()
        repos["campus_repo"].get_by_id.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await service.list_programs_by_campus(uuid.uuid4(), uuid.uuid4(), skip=0, limit=20)

        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Tests: list_courses_by_campus_and_program() — 404 si programa no pertenece al campus (Req 4.4)
# ---------------------------------------------------------------------------

class TestListCoursesByProgramNotFound:
    """list_courses_by_campus_and_program() lanza 404 si programa no pertenece al campus."""

    @pytest.mark.anyio
    async def test_program_not_belonging_to_campus_returns_404(self):
        uni_id = uuid.uuid4()
        campus = _make_campus(university_id=uni_id)
        other_campus_id = uuid.uuid4()
        program = _make_program(campus_id=other_campus_id, university_id=uni_id)

        service, repos = _make_service()
        repos["campus_repo"].get_by_id.return_value = campus
        repos["program_repo"].get_by_id.return_value = program

        with pytest.raises(HTTPException) as exc_info:
            await service.list_courses_by_campus_and_program(
                uni_id, campus.id, program.id
            )

        assert exc_info.value.status_code == 404
        assert "programa no pertenece" in exc_info.value.detail.lower()

    @pytest.mark.anyio
    async def test_nonexistent_program_returns_404(self):
        uni_id = uuid.uuid4()
        campus = _make_campus(university_id=uni_id)

        service, repos = _make_service()
        repos["campus_repo"].get_by_id.return_value = campus
        repos["program_repo"].get_by_id.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await service.list_courses_by_campus_and_program(
                uni_id, campus.id, uuid.uuid4()
            )

        assert exc_info.value.status_code == 404
        assert "Programa" in exc_info.value.detail
