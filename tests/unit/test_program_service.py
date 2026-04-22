"""
Unit tests for ProgramService.

Tests cover specific examples and edge cases for create and update flows:
- test_create_program_success — happy path with valid data
- test_create_program_duplicate_program_code_returns_409
- test_create_program_duplicate_snies_code_returns_409
- test_update_program_success — happy path partial update
- test_update_program_not_found_returns_404
- test_update_program_duplicate_program_code_different_program_returns_409
- test_update_program_duplicate_snies_code_different_program_returns_409
- test_update_program_same_codes_no_conflict — self-update

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.application.schemas.program import ProgramCreate, ProgramRead, ProgramUpdate
from app.application.services.program_service import ProgramService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROGRAM_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_OTHER_PROGRAM_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")


def _make_program(
    *,
    program_id: uuid.UUID = _PROGRAM_ID,
    institution: str = "USBCO",
    degree_type: str = "PREG",
    program_code: str = "M0200",
    program_name: str = "Psicología",
    academic_group: str = "MFPSI",
    location: str = "SAN BENITO",
    snies_code: int = 12345,
) -> MagicMock:
    """Create a mock Program with the given attributes."""
    program = MagicMock()
    program.id = program_id
    program.institution = institution
    program.degree_type = degree_type
    program.program_code = program_code
    program.program_name = program_name
    program.academic_group = academic_group
    program.location = location
    program.snies_code = snies_code
    program.created_at = datetime.now(timezone.utc)
    return program


def _make_repo() -> AsyncMock:
    """Create a mock IProgramRepository with default return values."""
    repo = AsyncMock()
    repo.get_by_program_code.return_value = None
    repo.get_by_snies_code.return_value = None
    return repo


def _valid_create_data() -> ProgramCreate:
    return ProgramCreate(
        institution="USBCO",
        degree_type="PREG",
        program_code="M0200",
        program_name="Psicología",
        academic_group="MFPSI",
        location="SAN BENITO",
        snies_code=12345,
    )


# ===================================================================
# Create: happy path (Requirement 5.2, 5.3)
# ===================================================================


class TestCreateProgramSuccess:
    @pytest.mark.anyio
    async def test_create_program_success(self):
        """A valid ProgramCreate must persist and return ProgramRead."""
        repo = _make_repo()
        program = _make_program()
        repo.create.return_value = program
        service = ProgramService(repo)

        result = await service.create_program(_valid_create_data())

        assert isinstance(result, ProgramRead)
        assert result.id == _PROGRAM_ID
        assert result.program_code == "M0200"
        assert result.snies_code == 12345
        repo.create.assert_awaited_once()


# ===================================================================
# Create: duplicate program_code (Requirement 5.4)
# ===================================================================


class TestCreateProgramDuplicateProgramCode:
    @pytest.mark.anyio
    async def test_create_program_duplicate_program_code_returns_409(self):
        """Duplicate program_code must raise HTTPException 409."""
        repo = _make_repo()
        repo.get_by_program_code.return_value = _make_program()
        service = ProgramService(repo)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_program(_valid_create_data())

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == "El program_code ya está registrado"
        repo.create.assert_not_awaited()


# ===================================================================
# Create: duplicate snies_code (Requirement 5.5)
# ===================================================================


class TestCreateProgramDuplicateSniesCode:
    @pytest.mark.anyio
    async def test_create_program_duplicate_snies_code_returns_409(self):
        """Duplicate snies_code must raise HTTPException 409."""
        repo = _make_repo()
        repo.get_by_program_code.return_value = None
        repo.get_by_snies_code.return_value = _make_program()
        service = ProgramService(repo)

        with pytest.raises(HTTPException) as exc_info:
            await service.create_program(_valid_create_data())

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == "El snies_code ya está registrado"
        repo.create.assert_not_awaited()


# ===================================================================
# Update: happy path (Requirement 5.6)
# ===================================================================


class TestUpdateProgramSuccess:
    @pytest.mark.anyio
    async def test_update_program_success(self):
        """A valid partial update must persist and return ProgramRead."""
        repo = _make_repo()
        updated_program = _make_program(program_name="Psicología Clínica")
        repo.update.return_value = updated_program
        service = ProgramService(repo)

        data = ProgramUpdate(program_name="Psicología Clínica")
        result = await service.update_program(_PROGRAM_ID, data)

        assert isinstance(result, ProgramRead)
        assert result.program_name == "Psicología Clínica"
        repo.update.assert_awaited_once_with(_PROGRAM_ID, data)


# ===================================================================
# Update: not found (Requirement 5.6)
# ===================================================================


class TestUpdateProgramNotFound:
    @pytest.mark.anyio
    async def test_update_program_not_found_returns_404(self):
        """Non-existent program_id must raise HTTPException 404."""
        repo = _make_repo()
        repo.update.return_value = None
        service = ProgramService(repo)

        data = ProgramUpdate(program_name="Nuevo Nombre")
        with pytest.raises(HTTPException) as exc_info:
            await service.update_program(_PROGRAM_ID, data)

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Programa no encontrado"


# ===================================================================
# Update: duplicate program_code from different program (Requirement 5.7)
# ===================================================================


class TestUpdateProgramDuplicateProgramCode:
    @pytest.mark.anyio
    async def test_update_program_duplicate_program_code_different_program_returns_409(self):
        """program_code belonging to another program must raise 409."""
        repo = _make_repo()
        other_program = _make_program(program_id=_OTHER_PROGRAM_ID, program_code="X0100")
        repo.get_by_program_code.return_value = other_program
        service = ProgramService(repo)

        data = ProgramUpdate(program_code="X0100")
        with pytest.raises(HTTPException) as exc_info:
            await service.update_program(_PROGRAM_ID, data)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == "El program_code ya está registrado"
        repo.update.assert_not_awaited()


# ===================================================================
# Update: duplicate snies_code from different program (Requirement 5.8)
# ===================================================================


class TestUpdateProgramDuplicateSniesCode:
    @pytest.mark.anyio
    async def test_update_program_duplicate_snies_code_different_program_returns_409(self):
        """snies_code belonging to another program must raise 409."""
        repo = _make_repo()
        other_program = _make_program(program_id=_OTHER_PROGRAM_ID, snies_code=99999)
        repo.get_by_snies_code.return_value = other_program
        service = ProgramService(repo)

        data = ProgramUpdate(snies_code=99999)
        with pytest.raises(HTTPException) as exc_info:
            await service.update_program(_PROGRAM_ID, data)

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail == "El snies_code ya está registrado"
        repo.update.assert_not_awaited()


# ===================================================================
# Update: self-update with own codes — no conflict (Requirement 5.9)
# ===================================================================


class TestUpdateProgramSameCodesNoConflict:
    @pytest.mark.anyio
    async def test_update_program_same_codes_no_conflict(self):
        """Updating a program with its own program_code and snies_code must succeed."""
        repo = _make_repo()
        existing_program = _make_program()
        repo.get_by_program_code.return_value = existing_program
        repo.get_by_snies_code.return_value = existing_program
        updated_program = _make_program(program_name="Psicología Actualizada")
        repo.update.return_value = updated_program
        service = ProgramService(repo)

        data = ProgramUpdate(
            program_code="M0200",
            snies_code=12345,
            program_name="Psicología Actualizada",
        )
        result = await service.update_program(_PROGRAM_ID, data)

        assert isinstance(result, ProgramRead)
        assert result.program_name == "Psicología Actualizada"
        repo.update.assert_awaited_once()
