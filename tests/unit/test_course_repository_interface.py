"""
Unit tests for ICourseRepository interface.
Validates: Requirements 4.2 — listar_por_campus_y_programa abstract method.
"""

from __future__ import annotations

import uuid

import pytest

from app.domain.interfaces.course_repository import ICourseRepository


class TestICourseRepositoryInterface:
    """Verify ICourseRepository ABC defines listar_por_campus_y_programa."""

    def test_cannot_instantiate_abstract_class(self):
        """ICourseRepository is abstract and cannot be instantiated directly."""
        with pytest.raises(TypeError):
            ICourseRepository()

    def test_concrete_implementation_with_all_methods(self):
        """A concrete class implementing all abstract methods can be instantiated."""

        class ConcreteCourseRepo(ICourseRepository):
            async def crear(self, asignatura):
                ...

            async def obtener_por_id(self, id):
                ...

            async def listar_por_docente(self, docente_id):
                ...

            async def listar_estudiantes_inscritos(self, course_id):
                ...

            async def listar_por_programa(self, program_id):
                ...

            async def listar_por_universidad_y_programa(self, university_id, program_id):
                ...

            async def listar_por_campus_y_programa(self, campus_id, program_id):
                ...

        repo = ConcreteCourseRepo()
        assert isinstance(repo, ICourseRepository)

    def test_missing_listar_por_campus_y_programa_raises_type_error(self):
        """Omitting 'listar_por_campus_y_programa' prevents instantiation (Req 4.2)."""

        class IncompleteCourseRepo(ICourseRepository):
            async def crear(self, asignatura):
                ...

            async def obtener_por_id(self, id):
                ...

            async def listar_por_docente(self, docente_id):
                ...

            async def listar_estudiantes_inscritos(self, course_id):
                ...

            async def listar_por_programa(self, program_id):
                ...

            async def listar_por_universidad_y_programa(self, university_id, program_id):
                ...

        with pytest.raises(TypeError):
            IncompleteCourseRepo()

    def test_listar_por_campus_y_programa_is_abstract_method(self):
        """The method listar_por_campus_y_programa must be defined as abstract."""
        abstract_methods = ICourseRepository.__abstractmethods__
        assert "listar_por_campus_y_programa" in abstract_methods

    def test_interface_is_exported_from_init(self):
        """ICourseRepository should be importable from the interfaces package."""
        from app.domain.interfaces import ICourseRepository as ExportedInterface

        assert ExportedInterface is ICourseRepository
