"""
Tests unitarios para el modelo SQLModel Campus.

Verifica la estructura del modelo Campus: campos, tipos, valores por defecto,
tabla, índices y UniqueConstraint.

Requirements: 1.1, 1.2, 1.3, 1.4
"""

import uuid
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa

from app.infrastructure.models.campus import Campus


class TestCampusModelFields:
    """Verificar que el modelo Campus tiene los campos correctos con los tipos esperados."""

    def test_campus_has_id_field_uuid(self):
        """El campo id debe ser UUID y PK."""
        campus = Campus(
            university_id=uuid.uuid4(),
            campus_code="MED",
            name="Sede Medellín",
            city="Medellín",
        )
        assert isinstance(campus.id, uuid.UUID)

    def test_campus_has_university_id_field(self):
        """El campo university_id debe aceptar UUID."""
        uid = uuid.uuid4()
        campus = Campus(
            university_id=uid,
            campus_code="BOG",
            name="Sede Bogotá",
            city="Bogotá",
        )
        assert campus.university_id == uid

    def test_campus_has_campus_code_field(self):
        """El campo campus_code debe ser str."""
        campus = Campus(
            university_id=uuid.uuid4(),
            campus_code="CAL",
            name="Sede Cali",
            city="Cali",
        )
        assert campus.campus_code == "CAL"

    def test_campus_has_name_field(self):
        """El campo name debe ser str."""
        campus = Campus(
            university_id=uuid.uuid4(),
            campus_code="MED",
            name="Sede Medellín",
            city="Medellín",
        )
        assert campus.name == "Sede Medellín"

    def test_campus_has_city_field(self):
        """El campo city debe ser str."""
        campus = Campus(
            university_id=uuid.uuid4(),
            campus_code="MED",
            name="Sede Medellín",
            city="Medellín",
        )
        assert campus.city == "Medellín"

    def test_campus_active_defaults_to_true(self):
        """El campo active debe tener valor por defecto True."""
        campus = Campus(
            university_id=uuid.uuid4(),
            campus_code="MED",
            name="Sede Medellín",
            city="Medellín",
        )
        assert campus.active is True

    def test_campus_active_can_be_set_to_false(self):
        """El campo active puede establecerse explícitamente en False."""
        campus = Campus(
            university_id=uuid.uuid4(),
            campus_code="MED",
            name="Sede Medellín",
            city="Medellín",
            active=False,
        )
        assert campus.active is False

    def test_campus_created_at_has_default(self):
        """El campo created_at debe tener un valor por defecto (datetime con timezone)."""
        campus = Campus(
            university_id=uuid.uuid4(),
            campus_code="MED",
            name="Sede Medellín",
            city="Medellín",
        )
        assert isinstance(campus.created_at, datetime)
        assert campus.created_at.tzinfo is not None


class TestCampusTableConfig:
    """Verificar la configuración a nivel de tabla del modelo Campus."""

    def test_tablename_is_campuses(self):
        """La tabla en BD debe llamarse 'campuses'."""
        assert Campus.__tablename__ == "campuses"

    def test_table_is_orm_model(self):
        """El modelo debe estar marcado como table=True (tiene __table__)."""
        assert hasattr(Campus, "__table__")

    def test_unique_constraint_university_campus_code(self):
        """Debe existir el UniqueConstraint (university_id, campus_code)."""
        table: sa.Table = Campus.__table__
        unique_constraints = [
            c for c in table.constraints if isinstance(c, sa.UniqueConstraint)
        ]
        uq_names = [c.name for c in unique_constraints]
        assert "uq_university_campus_code" in uq_names

    def test_unique_constraint_columns(self):
        """El UniqueConstraint debe incluir las columnas university_id y campus_code."""
        table: sa.Table = Campus.__table__
        unique_constraints = [
            c for c in table.constraints if isinstance(c, sa.UniqueConstraint)
        ]
        uq = next(c for c in unique_constraints if c.name == "uq_university_campus_code")
        col_names = {col.name for col in uq.columns}
        assert col_names == {"university_id", "campus_code"}

    def test_university_id_is_indexed(self):
        """El campo university_id debe tener un índice (Req 1.3)."""
        table: sa.Table = Campus.__table__
        indexed_columns = set()
        for idx in table.indexes:
            for col in idx.columns:
                indexed_columns.add(col.name)
        assert "university_id" in indexed_columns

    def test_campus_code_is_indexed(self):
        """El campo campus_code debe tener un índice (Req 1.4)."""
        table: sa.Table = Campus.__table__
        indexed_columns = set()
        for idx in table.indexes:
            for col in idx.columns:
                indexed_columns.add(col.name)
        assert "campus_code" in indexed_columns

    def test_university_id_is_foreign_key_to_universities(self):
        """El campo university_id debe ser FK a universities.id."""
        table: sa.Table = Campus.__table__
        col = table.c.university_id
        fk_targets = [fk.target_fullname for fk in col.foreign_keys]
        assert "universities.id" in fk_targets

    def test_created_at_column_has_timezone(self):
        """El campo created_at debe usar DateTime(timezone=True)."""
        table: sa.Table = Campus.__table__
        col = table.c.created_at
        assert isinstance(col.type, sa.DateTime)
        assert col.type.timezone is True


class TestCampusModelExport:
    """Verificar que Campus se exporta correctamente desde el módulo de modelos."""

    def test_campus_importable_from_models_package(self):
        """Campus debe ser importable desde app.infrastructure.models."""
        from app.infrastructure.models import Campus as CampusFromInit
        assert CampusFromInit is Campus
