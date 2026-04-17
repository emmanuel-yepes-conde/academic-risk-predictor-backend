"""
Tests unitarios para CampusRepository.

Verifica las operaciones CRUD del repositorio de campus usando mocks
de AsyncSession y AuditLogRepository (sin acceso a base de datos).

Requirements: 2.1, 2.4, 2.5, 2.6
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.application.schemas.campus import CampusCreate, CampusUpdate
from app.domain.enums import OperationEnum
from app.infrastructure.models.campus import Campus
from app.infrastructure.repositories.campus_repository import CampusRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _make_session() -> AsyncMock:
    """Build a mock AsyncSession with default async stubs."""
    session = AsyncMock()
    session.add = MagicMock()  # add() is synchronous
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    return session


# ---------------------------------------------------------------------------
# Tests: create() — inserta registro y registra audit_log (Req 2.1)
# ---------------------------------------------------------------------------

class TestCampusRepositoryCreate:
    """create() inserts a campus record and registers an audit_log entry."""

    @pytest.mark.anyio
    @patch(
        "app.infrastructure.repositories.campus_repository.AuditLogRepository"
    )
    async def test_create_adds_campus_to_session(self, MockAuditRepo):
        mock_audit = AsyncMock()
        MockAuditRepo.return_value = mock_audit

        session = _make_session()
        repo = CampusRepository(session)

        university_id = uuid.uuid4()
        data = CampusCreate(
            campus_code="BOG",
            name="Sede Bogotá",
            city="Bogotá",
        )

        await repo.create(university_id, data)

        # session.add was called with a Campus instance
        session.add.assert_called_once()
        added_obj = session.add.call_args[0][0]
        assert isinstance(added_obj, Campus)
        assert added_obj.university_id == university_id
        assert added_obj.campus_code == "BOG"
        assert added_obj.name == "Sede Bogotá"
        assert added_obj.city == "Bogotá"
        assert added_obj.active is True

    @pytest.mark.anyio
    @patch(
        "app.infrastructure.repositories.campus_repository.AuditLogRepository"
    )
    async def test_create_flushes_and_refreshes(self, MockAuditRepo):
        MockAuditRepo.return_value = AsyncMock()

        session = _make_session()
        repo = CampusRepository(session)

        data = CampusCreate(campus_code="CAL", name="Sede Cali", city="Cali")
        await repo.create(uuid.uuid4(), data)

        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once()

    @pytest.mark.anyio
    @patch(
        "app.infrastructure.repositories.campus_repository.AuditLogRepository"
    )
    async def test_create_registers_audit_log(self, MockAuditRepo):
        mock_audit = AsyncMock()
        MockAuditRepo.return_value = mock_audit

        session = _make_session()
        repo = CampusRepository(session)

        university_id = uuid.uuid4()
        data = CampusCreate(
            campus_code="MED",
            name="Sede Medellín",
            city="Medellín",
        )

        await repo.create(university_id, data)

        mock_audit.register.assert_awaited_once()
        audit_arg = mock_audit.register.call_args[0][0]
        assert audit_arg.table_name == "campuses"
        assert audit_arg.operation == OperationEnum.INSERT
        assert audit_arg.new_data["campus_code"] == "MED"
        assert audit_arg.new_data["university_id"] == str(university_id)

    @pytest.mark.anyio
    @patch(
        "app.infrastructure.repositories.campus_repository.AuditLogRepository"
    )
    async def test_create_returns_campus_instance(self, MockAuditRepo):
        MockAuditRepo.return_value = AsyncMock()

        session = _make_session()
        repo = CampusRepository(session)

        data = CampusCreate(campus_code="BOG", name="Sede Bogotá", city="Bogotá")
        result = await repo.create(uuid.uuid4(), data)

        assert isinstance(result, Campus)
        assert result.campus_code == "BOG"


# ---------------------------------------------------------------------------
# Tests: get_by_id() — retorna None si no existe (Req 2.5)
# ---------------------------------------------------------------------------

class TestCampusRepositoryGetById:
    """get_by_id() returns None when the campus does not exist."""

    @pytest.mark.anyio
    @patch(
        "app.infrastructure.repositories.campus_repository.AuditLogRepository"
    )
    async def test_get_by_id_returns_none_when_not_found(self, MockAuditRepo):
        MockAuditRepo.return_value = AsyncMock()

        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        repo = CampusRepository(session)
        result = await repo.get_by_id(uuid.uuid4())

        assert result is None
        session.execute.assert_awaited_once()

    @pytest.mark.anyio
    @patch(
        "app.infrastructure.repositories.campus_repository.AuditLogRepository"
    )
    async def test_get_by_id_returns_campus_when_found(self, MockAuditRepo):
        MockAuditRepo.return_value = AsyncMock()

        campus = _make_campus()
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = campus
        session.execute.return_value = mock_result

        repo = CampusRepository(session)
        result = await repo.get_by_id(campus.id)

        assert result is campus


# ---------------------------------------------------------------------------
# Tests: get_by_university_and_code() — busca por combinación correcta (Req 2.1)
# ---------------------------------------------------------------------------

class TestCampusRepositoryGetByUniversityAndCode:
    """get_by_university_and_code() searches by the correct university_id + campus_code."""

    @pytest.mark.anyio
    @patch(
        "app.infrastructure.repositories.campus_repository.AuditLogRepository"
    )
    async def test_get_by_university_and_code_returns_campus(self, MockAuditRepo):
        MockAuditRepo.return_value = AsyncMock()

        campus = _make_campus(campus_code="MED")
        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = campus
        session.execute.return_value = mock_result

        repo = CampusRepository(session)
        result = await repo.get_by_university_and_code(
            campus.university_id, "MED"
        )

        assert result is campus
        session.execute.assert_awaited_once()

    @pytest.mark.anyio
    @patch(
        "app.infrastructure.repositories.campus_repository.AuditLogRepository"
    )
    async def test_get_by_university_and_code_returns_none_when_not_found(
        self, MockAuditRepo
    ):
        MockAuditRepo.return_value = AsyncMock()

        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        repo = CampusRepository(session)
        result = await repo.get_by_university_and_code(uuid.uuid4(), "NOPE")

        assert result is None


# ---------------------------------------------------------------------------
# Tests: list_by_university() — filtra por university_id (Req 2.4)
# ---------------------------------------------------------------------------

class TestCampusRepositoryListByUniversity:
    """list_by_university() filters campuses by university_id."""

    @pytest.mark.anyio
    @patch(
        "app.infrastructure.repositories.campus_repository.AuditLogRepository"
    )
    async def test_list_by_university_returns_list(self, MockAuditRepo):
        MockAuditRepo.return_value = AsyncMock()

        uni_id = uuid.uuid4()
        campuses = [
            _make_campus(university_id=uni_id, campus_code="MED"),
            _make_campus(university_id=uni_id, campus_code="BOG"),
        ]

        session = _make_session()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = campuses
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        session.execute.return_value = mock_result

        repo = CampusRepository(session)
        result = await repo.list_by_university(uni_id, skip=0, limit=20)

        assert len(result) == 2
        assert result[0].campus_code == "MED"
        assert result[1].campus_code == "BOG"
        session.execute.assert_awaited_once()

    @pytest.mark.anyio
    @patch(
        "app.infrastructure.repositories.campus_repository.AuditLogRepository"
    )
    async def test_list_by_university_returns_empty_list(self, MockAuditRepo):
        MockAuditRepo.return_value = AsyncMock()

        session = _make_session()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = []
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        session.execute.return_value = mock_result

        repo = CampusRepository(session)
        result = await repo.list_by_university(uuid.uuid4(), skip=0, limit=20)

        assert result == []


# ---------------------------------------------------------------------------
# Tests: update() — modifica solo campos provistos (Req 2.6)
# ---------------------------------------------------------------------------

class TestCampusRepositoryUpdate:
    """update() modifies only the provided fields and registers audit_log."""

    @pytest.mark.anyio
    @patch(
        "app.infrastructure.repositories.campus_repository.AuditLogRepository"
    )
    async def test_update_modifies_only_provided_fields(self, MockAuditRepo):
        mock_audit = AsyncMock()
        MockAuditRepo.return_value = mock_audit

        campus = _make_campus(name="Sede Vieja", city="Medellín", active=True)

        session = _make_session()
        # get_by_id is called internally via execute
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = campus
        session.execute.return_value = mock_result

        repo = CampusRepository(session)
        data = CampusUpdate(name="Sede Nueva")

        result = await repo.update(campus.id, data)

        assert result is not None
        assert result.name == "Sede Nueva"
        # Unchanged fields remain the same
        assert result.city == "Medellín"
        assert result.active is True

    @pytest.mark.anyio
    @patch(
        "app.infrastructure.repositories.campus_repository.AuditLogRepository"
    )
    async def test_update_returns_none_when_not_found(self, MockAuditRepo):
        MockAuditRepo.return_value = AsyncMock()

        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        repo = CampusRepository(session)
        data = CampusUpdate(name="No importa")

        result = await repo.update(uuid.uuid4(), data)

        assert result is None

    @pytest.mark.anyio
    @patch(
        "app.infrastructure.repositories.campus_repository.AuditLogRepository"
    )
    async def test_update_registers_audit_log(self, MockAuditRepo):
        mock_audit = AsyncMock()
        MockAuditRepo.return_value = mock_audit

        campus = _make_campus(name="Sede Vieja", city="Medellín")

        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = campus
        session.execute.return_value = mock_result

        repo = CampusRepository(session)
        data = CampusUpdate(city="Bogotá")

        await repo.update(campus.id, data)

        mock_audit.register.assert_awaited_once()
        audit_arg = mock_audit.register.call_args[0][0]
        assert audit_arg.table_name == "campuses"
        assert audit_arg.operation == OperationEnum.UPDATE
        assert audit_arg.previous_data == {"city": "Medellín"}
        assert audit_arg.new_data == {"city": "Bogotá"}

    @pytest.mark.anyio
    @patch(
        "app.infrastructure.repositories.campus_repository.AuditLogRepository"
    )
    async def test_update_flushes_and_refreshes(self, MockAuditRepo):
        MockAuditRepo.return_value = AsyncMock()

        campus = _make_campus()

        session = _make_session()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = campus
        session.execute.return_value = mock_result

        repo = CampusRepository(session)
        data = CampusUpdate(active=False)

        await repo.update(campus.id, data)

        session.flush.assert_awaited_once()
        session.refresh.assert_awaited_once()
