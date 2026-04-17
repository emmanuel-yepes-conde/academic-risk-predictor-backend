"""
Tests unitarios para aislamiento de datos por campus.

Verifica que las consultas filtradas por campus retornan únicamente
los recursos de ese campus, que la cadena jerárquica
universidad → campus → programa → cursos respeta el aislamiento,
y que dos campus de la misma universidad pueden tener programas
con el mismo program_code.

Requirements: 5.1, 5.2, 5.3
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.application.services.campus_service import CampusService
from app.infrastructure.models.campus import Campus
from app.infrastructure.models.course import Course
from app.infrastructure.models.program import Program


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_campus(**overrides) -> Campus:
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


def _make_course(**overrides) -> Course:
    defaults = dict(
        id=uuid.uuid4(),
        code="MAT101",
        name="Cálculo I",
        credits=4,
        academic_period="2024-1",
        program_id=uuid.uuid4(),
        created_at=datetime.now(timezone.utc),
    )
    defaults.update(overrides)
    return Course(**defaults)


def _make_repos() -> dict:
    """Build mock repositories with default return values."""
    campus_repo = AsyncMock()
    campus_repo.get_by_id = AsyncMock(return_value=None)
    campus_repo.list_by_university = AsyncMock(return_value=[])
    campus_repo.count_by_university = AsyncMock(return_value=0)

    university_repo = AsyncMock()
    university_repo.get_by_id = AsyncMock(return_value=None)

    program_repo = AsyncMock()
    program_repo.list_by_campus = AsyncMock(return_value=[])
    program_repo.count_by_campus = AsyncMock(return_value=0)
    program_repo.get_by_id = AsyncMock(return_value=None)

    course_repo = AsyncMock()
    course_repo.listar_por_campus_y_programa = AsyncMock(return_value=[])

    return dict(
        campus_repo=campus_repo,
        university_repo=university_repo,
        program_repo=program_repo,
        course_repo=course_repo,
    )


def _make_service(repos: dict) -> CampusService:
    return CampusService(
        campus_repo=repos["campus_repo"],
        university_repo=repos["university_repo"],
        program_repo=repos["program_repo"],
        course_repo=repos["course_repo"],
    )


# ---------------------------------------------------------------------------
# Test: query filtered by campus_id returns only programs of that campus
# (Req 5.1)
# ---------------------------------------------------------------------------

class TestProgramFilterByCampus:
    """list_programs_by_campus() retorna solo programas del campus indicado."""

    @pytest.mark.anyio
    async def test_list_programs_filters_by_campus_id(self):
        """
        Validates: Requirements 5.1

        Given two campuses with their own programs, calling
        list_programs_by_campus for campus_a must pass campus_a.id
        to program_repo.list_by_campus and return only its programs.
        """
        uni_id = uuid.uuid4()
        campus_a = _make_campus(id=uuid.uuid4(), university_id=uni_id, campus_code="MED")
        campus_b = _make_campus(id=uuid.uuid4(), university_id=uni_id, campus_code="BOG")

        prog_a1 = _make_program(campus_id=campus_a.id, university_id=uni_id, program_code="PSI", snies_code=1001)
        prog_a2 = _make_program(campus_id=campus_a.id, university_id=uni_id, program_code="ING", snies_code=1002)
        # prog_b belongs to campus_b — should NOT appear
        _make_program(campus_id=campus_b.id, university_id=uni_id, program_code="DER", snies_code=1003)

        repos = _make_repos()
        repos["campus_repo"].get_by_id.return_value = campus_a
        repos["program_repo"].list_by_campus.return_value = [prog_a1, prog_a2]
        repos["program_repo"].count_by_campus.return_value = 2

        service = _make_service(repos)
        result = await service.list_programs_by_campus(uni_id, campus_a.id, skip=0, limit=20)

        # The service must have called list_by_campus with campus_a.id
        repos["program_repo"].list_by_campus.assert_awaited_once_with(
            campus_a.id, skip=0, limit=20
        )
        assert result.total == 2
        returned_ids = {p.id for p in result.data}
        assert returned_ids == {prog_a1.id, prog_a2.id}

    @pytest.mark.anyio
    async def test_list_programs_empty_for_campus_without_programs(self):
        """
        Validates: Requirements 5.1

        A campus with no programs returns an empty list.
        """
        uni_id = uuid.uuid4()
        campus = _make_campus(university_id=uni_id)

        repos = _make_repos()
        repos["campus_repo"].get_by_id.return_value = campus
        repos["program_repo"].list_by_campus.return_value = []
        repos["program_repo"].count_by_campus.return_value = 0

        service = _make_service(repos)
        result = await service.list_programs_by_campus(uni_id, campus.id, skip=0, limit=20)

        repos["program_repo"].list_by_campus.assert_awaited_once_with(
            campus.id, skip=0, limit=20
        )
        assert result.total == 0
        assert result.data == []


# ---------------------------------------------------------------------------
# Test: hierarchical query university → campus → program → courses
# respects isolation (Req 5.2)
# ---------------------------------------------------------------------------

class TestHierarchicalIsolation:
    """list_courses_by_campus_and_program() validates the full ownership chain."""

    @pytest.mark.anyio
    async def test_full_chain_returns_courses_for_valid_hierarchy(self):
        """
        Validates: Requirements 5.2

        When the full chain university → campus → program is valid,
        the service delegates to course_repo.listar_por_campus_y_programa
        with the correct campus_id and program_id.
        """
        uni_id = uuid.uuid4()
        campus = _make_campus(university_id=uni_id)
        program = _make_program(campus_id=campus.id, university_id=uni_id, snies_code=2001)
        course1 = _make_course(program_id=program.id, code="MAT101")
        course2 = _make_course(program_id=program.id, code="FIS201")

        repos = _make_repos()
        repos["campus_repo"].get_by_id.return_value = campus
        repos["program_repo"].get_by_id.return_value = program
        repos["course_repo"].listar_por_campus_y_programa.return_value = [course1, course2]

        service = _make_service(repos)
        result = await service.list_courses_by_campus_and_program(
            uni_id, campus.id, program.id
        )

        # Verify each level of the chain was checked
        repos["campus_repo"].get_by_id.assert_awaited_once_with(campus.id)
        repos["program_repo"].get_by_id.assert_awaited_once_with(program.id)
        repos["course_repo"].listar_por_campus_y_programa.assert_awaited_once_with(
            campus.id, program.id
        )
        assert len(result) == 2
        returned_codes = {c.code for c in result}
        assert returned_codes == {"MAT101", "FIS201"}

    @pytest.mark.anyio
    async def test_campus_belonging_to_wrong_university_is_rejected(self):
        """
        Validates: Requirements 5.2

        If the campus does not belong to the university in the URL,
        the service raises 404 before checking the program.
        """
        uni_id = uuid.uuid4()
        other_uni_id = uuid.uuid4()
        campus = _make_campus(university_id=other_uni_id)

        repos = _make_repos()
        repos["campus_repo"].get_by_id.return_value = campus

        service = _make_service(repos)
        with pytest.raises(Exception) as exc_info:
            await service.list_courses_by_campus_and_program(
                uni_id, campus.id, uuid.uuid4()
            )

        assert exc_info.value.status_code == 404  # type: ignore[union-attr]
        # Program repo should never be consulted
        repos["program_repo"].get_by_id.assert_not_awaited()
        repos["course_repo"].listar_por_campus_y_programa.assert_not_awaited()

    @pytest.mark.anyio
    async def test_program_belonging_to_wrong_campus_is_rejected(self):
        """
        Validates: Requirements 5.2

        If the program does not belong to the campus, the service
        raises 404 before fetching courses.
        """
        uni_id = uuid.uuid4()
        campus = _make_campus(university_id=uni_id)
        other_campus_id = uuid.uuid4()
        program = _make_program(campus_id=other_campus_id, university_id=uni_id, snies_code=3001)

        repos = _make_repos()
        repos["campus_repo"].get_by_id.return_value = campus
        repos["program_repo"].get_by_id.return_value = program

        service = _make_service(repos)
        with pytest.raises(Exception) as exc_info:
            await service.list_courses_by_campus_and_program(
                uni_id, campus.id, program.id
            )

        assert exc_info.value.status_code == 404  # type: ignore[union-attr]
        repos["course_repo"].listar_por_campus_y_programa.assert_not_awaited()


# ---------------------------------------------------------------------------
# Test: two campuses of the same university can have programs with the
# same program_code (Req 5.3 / 3.4)
# ---------------------------------------------------------------------------

class TestProgramCodeScopedToCampus:
    """The UniqueConstraint on Program is scoped to campus_id, not university_id."""

    def test_same_program_code_different_campuses_allowed(self):
        """
        Validates: Requirements 5.3

        Two Program instances with the same program_code but different
        campus_ids can coexist. The model-level UniqueConstraint
        ("program_code", "campus_id") permits this.
        """
        uni_id = uuid.uuid4()
        campus_a_id = uuid.uuid4()
        campus_b_id = uuid.uuid4()
        shared_code = "ING001"

        prog_a = _make_program(
            campus_id=campus_a_id,
            university_id=uni_id,
            program_code=shared_code,
            snies_code=4001,
        )
        prog_b = _make_program(
            campus_id=campus_b_id,
            university_id=uni_id,
            program_code=shared_code,
            snies_code=4002,
        )

        # Both instances are valid and share the same program_code
        assert prog_a.program_code == prog_b.program_code == shared_code
        # But they belong to different campuses
        assert prog_a.campus_id != prog_b.campus_id
        # And they are distinct entities
        assert prog_a.id != prog_b.id

    def test_unique_constraint_is_scoped_to_campus(self):
        """
        Validates: Requirements 5.3

        The Program model's __table_args__ contains a UniqueConstraint
        on ("program_code", "campus_id"), confirming the scope.
        """
        table_args = Program.__table_args__
        # Find the UniqueConstraint in __table_args__
        unique_constraints = [
            arg for arg in table_args
            if hasattr(arg, "columns") or hasattr(arg, "name")
        ]
        assert len(unique_constraints) >= 1

        uq = unique_constraints[0]
        assert uq.name == "uq_program_code_campus"
        # The constraint columns should include program_code and campus_id
        col_names = [col.name for col in uq.columns]
        assert "program_code" in col_names
        assert "campus_id" in col_names
        # university_id should NOT be part of this constraint
        assert "university_id" not in col_names
