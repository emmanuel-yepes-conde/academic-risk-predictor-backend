"""
Tests unitarios para los schemas Pydantic de Campus.

Verifica la validación de entrada (CampusCreate, CampusUpdate) y la
serialización de salida (CampusRead) para la entidad Campus.

Requirements: 6.1, 6.2, 6.3, 6.5
"""

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError


class TestCampusCreate:
    """Tests para CampusCreate — Requirement 6.1, 6.5."""

    def test_valid_campus_create(self):
        """CampusCreate acepta todos los campos requeridos."""
        from app.application.schemas.campus import CampusCreate

        schema = CampusCreate(
            campus_code="MED",
            name="Sede Medellín",
            city="Medellín",
        )

        assert schema.campus_code == "MED"
        assert schema.name == "Sede Medellín"
        assert schema.city == "Medellín"
        assert schema.active is True  # default

    def test_campus_create_active_default_true(self):
        """active tiene valor por defecto True."""
        from app.application.schemas.campus import CampusCreate

        schema = CampusCreate(
            campus_code="BOG",
            name="Sede Bogotá",
            city="Bogotá",
        )

        assert schema.active is True

    def test_campus_create_active_explicit_false(self):
        """active puede establecerse explícitamente como False."""
        from app.application.schemas.campus import CampusCreate

        schema = CampusCreate(
            campus_code="CAL",
            name="Sede Cali",
            city="Cali",
            active=False,
        )

        assert schema.active is False

    def test_campus_create_missing_campus_code_raises(self):
        """Falta campus_code → ValidationError (Req 6.5)."""
        from app.application.schemas.campus import CampusCreate

        with pytest.raises(ValidationError) as exc_info:
            CampusCreate(name="Sede", city="Ciudad")

        assert any("campus_code" in str(e) for e in exc_info.value.errors())

    def test_campus_create_missing_name_raises(self):
        """Falta name → ValidationError (Req 6.5)."""
        from app.application.schemas.campus import CampusCreate

        with pytest.raises(ValidationError) as exc_info:
            CampusCreate(campus_code="MED", city="Medellín")

        assert any("name" in str(e) for e in exc_info.value.errors())

    def test_campus_create_missing_city_raises(self):
        """Falta city → ValidationError (Req 6.5)."""
        from app.application.schemas.campus import CampusCreate

        with pytest.raises(ValidationError) as exc_info:
            CampusCreate(campus_code="MED", name="Sede Medellín")

        assert any("city" in str(e) for e in exc_info.value.errors())

    def test_campus_create_fields_have_descriptions(self):
        """Todos los campos tienen Field(description=...) para Swagger docs."""
        from app.application.schemas.campus import CampusCreate

        fields = CampusCreate.model_fields
        for field_name in ("campus_code", "name", "city", "active"):
            assert field_name in fields, f"Missing field: {field_name}"
            assert fields[field_name].description is not None, (
                f"Field '{field_name}' lacks description"
            )


class TestCampusUpdate:
    """Tests para CampusUpdate — Requirement 6.2."""

    def test_campus_update_all_fields_optional(self):
        """CampusUpdate acepta un body vacío (todos opcionales)."""
        from app.application.schemas.campus import CampusUpdate

        schema = CampusUpdate()

        assert schema.name is None
        assert schema.city is None
        assert schema.active is None

    def test_campus_update_partial(self):
        """CampusUpdate acepta solo un subconjunto de campos."""
        from app.application.schemas.campus import CampusUpdate

        schema = CampusUpdate(name="Nombre Actualizado")

        assert schema.name == "Nombre Actualizado"
        assert schema.city is None
        assert schema.active is None

    def test_campus_update_all_fields(self):
        """CampusUpdate acepta todos los campos a la vez."""
        from app.application.schemas.campus import CampusUpdate

        schema = CampusUpdate(
            name="Nuevo Nombre",
            city="Nueva Ciudad",
            active=False,
        )

        assert schema.name == "Nuevo Nombre"
        assert schema.city == "Nueva Ciudad"
        assert schema.active is False


class TestCampusRead:
    """Tests para CampusRead — Requirement 6.3."""

    def test_campus_read_from_dict(self):
        """CampusRead se crea correctamente a partir de un dict."""
        from app.application.schemas.campus import CampusRead

        campus_id = uuid.uuid4()
        university_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        schema = CampusRead(
            id=campus_id,
            university_id=university_id,
            campus_code="MED",
            name="Sede Medellín",
            city="Medellín",
            active=True,
            created_at=now,
        )

        assert schema.id == campus_id
        assert schema.university_id == university_id
        assert schema.campus_code == "MED"
        assert schema.name == "Sede Medellín"
        assert schema.city == "Medellín"
        assert schema.active is True
        assert schema.created_at == now

    def test_campus_read_from_attributes(self):
        """CampusRead soporta model_config from_attributes=True (ORM mode)."""
        from app.application.schemas.campus import CampusRead

        campus_id = uuid.uuid4()
        university_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        # Simulate an ORM object with attributes
        class FakeCampusORM:
            def __init__(self):
                self.id = campus_id
                self.university_id = university_id
                self.campus_code = "BOG"
                self.name = "Sede Bogotá"
                self.city = "Bogotá"
                self.active = True
                self.created_at = now

        orm_obj = FakeCampusORM()
        schema = CampusRead.model_validate(orm_obj)

        assert schema.id == campus_id
        assert schema.university_id == university_id
        assert schema.campus_code == "BOG"
        assert schema.name == "Sede Bogotá"
        assert schema.city == "Bogotá"
        assert schema.active is True
        assert schema.created_at == now

    def test_campus_read_has_all_required_fields(self):
        """CampusRead expone todos los campos requeridos por Req 6.3."""
        from app.application.schemas.campus import CampusRead

        required_fields = {"id", "university_id", "campus_code", "name", "city", "active", "created_at"}
        actual_fields = set(CampusRead.model_fields.keys())
        assert required_fields == actual_fields
