"""
Unit tests for ICourseRepository interface.
Validates: Requirements 6.3 — simplified interface without hierarchy methods.
"""

from __future__ import annotations

import pytest

from app.domain.interfaces.course_repository import ICourseRepository


class TestICourseRepositoryInterface:
    """Verify ICourseRepository ABC defines the correct simplified methods."""

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

            async def create(self, data):
                ...

            async def update(self, course_id, data):
                ...

            async def get_by_code(self, code):
                ...

            async def list_all(self, skip, limit, status=None):
                ...

            async def count_all(self, status=None):
                ...

            async def update_status(self, course_id, status):
                ...

        repo = ConcreteCourseRepo()
        assert isinstance(repo, ICourseRepository)

    def test_missing_listar_por_programa_raises_type_error(self):
        """Omitting 'listar_por_programa' prevents instantiation (Req 6.3)."""

        class IncompleteCourseRepo(ICourseRepository):
            async def crear(self, asignatura):
                ...

            async def obtener_por_id(self, id):
                ...

            async def listar_por_docente(self, docente_id):
                ...

            async def listar_estudiantes_inscritos(self, course_id):
                ...

        with pytest.raises(TypeError):
            IncompleteCourseRepo()

    def test_no_hierarchy_methods_in_interface(self):
        """The interface must NOT have hierarchy methods (Req 6.3)."""
        abstract_methods = ICourseRepository.__abstractmethods__
        assert "listar_por_universidad_y_programa" not in abstract_methods
        assert "listar_por_campus_y_programa" not in abstract_methods

    def test_required_abstract_methods(self):
        """The interface must define exactly the 11 required methods (5 original + 6 CRUD)."""
        abstract_methods = ICourseRepository.__abstractmethods__
        expected = {
            "crear",
            "obtener_por_id",
            "listar_por_docente",
            "listar_estudiantes_inscritos",
            "listar_por_programa",
            "create",
            "update",
            "get_by_code",
            "list_all",
            "count_all",
            "update_status",
        }
        assert abstract_methods == expected

    def test_interface_is_exported_from_init(self):
        """ICourseRepository should be importable from the interfaces package."""
        from app.domain.interfaces import ICourseRepository as ExportedInterface

        assert ExportedInterface is ICourseRepository
