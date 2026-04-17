"""
Tests unitarios para el modelo SQLModel Program (post-campus-hierarchy).

Verifica la estructura modificada del modelo Program:
- Nuevo campo campus_id (FK → campuses.id)
- university_id mantenido como campo denormalizado
- Campo de texto 'campus' eliminado
- UniqueConstraint cambiado a ("program_code", "campus_id")

Requirements: 3.1, 3.2, 3.3, 3.4
"""

import uuid
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy import UniqueConstraint

from app.infrastructure.models.program import Program


class TestProgramModelCampusId:
    """Verificar que el modelo Program tiene el campo campus_id (Req 3.1)."""

    def test_program_has_campus_id_field(self):
        """El campo campus_id debe aceptar UUID."""
        campus_id = uuid.uuid4()
        program = Program(
            campus_id=campus_id,
            university_id=uuid.uuid4(),
            institution="USBCO",
            degree_type="PREG",
            program_code="M0200",
            program_name="Psicología",
            pensum="M20020142",
            academic_group="MFPSI",
            location="SAN BENITO",
            snies_code=1361,
        )
        assert program.campus_id == campus_id

    def test_campus_id_is_foreign_key_to_campuses(self):
        """El campo campus_id debe ser FK a campuses.id (Req 3.1)."""
        table: sa.Table = Program.__table__
        col = table.c.campus_id
        fk_targets = [fk.target_fullname for fk in col.foreign_keys]
        assert "campuses.id" in fk_targets

    def test_campus_id_is_indexed(self):
        """El campo campus_id debe tener un índice."""
        table: sa.Table = Program.__table__
        indexed_columns = set()
        for idx in table.indexes:
            for col in idx.columns:
                indexed_columns.add(col.name)
        assert "campus_id" in indexed_columns

    def test_campus_id_is_not_nullable(self):
        """El campo campus_id no debe ser nullable."""
        table: sa.Table = Program.__table__
        col = table.c.campus_id
        assert col.nullable is False


class TestProgramModelCampusFieldRemoved:
    """Verificar que el campo de texto 'campus' fue eliminado (Req 3.2)."""

    def test_program_has_no_campus_text_field(self):
        """El modelo Program no debe tener un campo 'campus' de texto."""
        table: sa.Table = Program.__table__
        column_names = {col.name for col in table.columns}
        assert "campus" not in column_names

    def test_program_constructor_rejects_campus_text(self):
        """El constructor no debe aceptar 'campus' como argumento válido del modelo."""
        # SQLModel silently ignores extra keyword args in some versions,
        # so we check at the table level instead (see test above).
        # Here we verify at the object attribute level.
        program = Program(
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
        )
        assert not hasattr(program, "campus") or "campus" not in Program.model_fields


class TestProgramModelUniversityIdDenormalized:
    """Verificar que university_id se mantiene como campo denormalizado (Req 3.3)."""

    def test_university_id_still_exists(self):
        """El campo university_id debe seguir existiendo."""
        uid = uuid.uuid4()
        program = Program(
            campus_id=uuid.uuid4(),
            university_id=uid,
            institution="USBCO",
            degree_type="PREG",
            program_code="M0200",
            program_name="Psicología",
            pensum="M20020142",
            academic_group="MFPSI",
            location="SAN BENITO",
            snies_code=1361,
        )
        assert program.university_id == uid

    def test_university_id_is_foreign_key_to_universities(self):
        """El campo university_id debe seguir siendo FK a universities.id."""
        table: sa.Table = Program.__table__
        col = table.c.university_id
        fk_targets = [fk.target_fullname for fk in col.foreign_keys]
        assert "universities.id" in fk_targets

    def test_university_id_is_indexed(self):
        """El campo university_id debe seguir indexado."""
        table: sa.Table = Program.__table__
        indexed_columns = set()
        for idx in table.indexes:
            for col in idx.columns:
                indexed_columns.add(col.name)
        assert "university_id" in indexed_columns


class TestProgramModelUniqueConstraint:
    """Verificar el cambio de UniqueConstraint (Req 3.4)."""

    def test_unique_constraint_is_program_code_campus_id(self):
        """Debe existir el UniqueConstraint uq_program_code_campus."""
        table: sa.Table = Program.__table__
        unique_constraints = [
            c for c in table.constraints if isinstance(c, sa.UniqueConstraint)
        ]
        uq_names = [c.name for c in unique_constraints]
        assert "uq_program_code_campus" in uq_names

    def test_unique_constraint_columns_are_correct(self):
        """El UniqueConstraint debe incluir program_code y campus_id."""
        table: sa.Table = Program.__table__
        unique_constraints = [
            c for c in table.constraints if isinstance(c, sa.UniqueConstraint)
        ]
        uq = next(c for c in unique_constraints if c.name == "uq_program_code_campus")
        col_names = {col.name for col in uq.columns}
        assert col_names == {"program_code", "campus_id"}

    def test_old_unique_constraint_removed(self):
        """El UniqueConstraint uq_program_code_university no debe existir."""
        table: sa.Table = Program.__table__
        unique_constraints = [
            c for c in table.constraints if isinstance(c, sa.UniqueConstraint)
        ]
        uq_names = [c.name for c in unique_constraints]
        assert "uq_program_code_university" not in uq_names


class TestProgramModelRemainingFields:
    """Verificar que los demás campos del modelo se mantienen intactos."""

    def test_program_has_all_expected_columns(self):
        """El modelo debe tener todas las columnas esperadas (sin 'campus' texto)."""
        table: sa.Table = Program.__table__
        expected_columns = {
            "id", "campus_id", "university_id", "institution", "degree_type",
            "program_code", "program_name", "pensum", "academic_group",
            "location", "snies_code", "created_at",
        }
        actual_columns = {col.name for col in table.columns}
        assert actual_columns == expected_columns

    def test_program_id_is_primary_key(self):
        """El campo id debe ser PK."""
        table: sa.Table = Program.__table__
        pk_cols = {col.name for col in table.primary_key.columns}
        assert "id" in pk_cols
