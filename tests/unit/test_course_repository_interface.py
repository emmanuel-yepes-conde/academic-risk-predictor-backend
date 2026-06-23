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
            async def create(self, data):
                ...

            async def get_by_id(self, course_id):
                ...

            async def list_by_subject(self, subject_id):
                ...

            async def list_by_professor(self, professor_id, skip=0, limit=50):
                ...

            async def count_by_professor(self, professor_id):
                ...

            async def list_by_program(self, program_id, skip=0, limit=50):
                ...

            async def count_by_program(self, program_id):
                ...

            async def update(self, course_id, data):
                ...

            async def get_by_code(self, code):
                ...

            async def list_all(self, skip, limit, status=None, subject_id=None):
                ...

            async def count_all(self, status=None, subject_id=None):
                ...

            async def update_status(self, course_id, status):
                ...

            async def save_evaluation_config(self, course_id, config):
                ...

            async def list_enrolled_students(self, course_id, skip=0, limit=50):
                ...

            async def count_enrolled_students(self, course_id):
                ...

            async def delete(self, course_id):
                ...

        repo = ConcreteCourseRepo()
        assert isinstance(repo, ICourseRepository)

    def test_missing_listar_por_programa_raises_type_error(self):
        """Omitting 'listar_por_programa' prevents instantiation (Req 6.3)."""

        class IncompleteCourseRepo(ICourseRepository):
            async def create(self, data):
                ...

        with pytest.raises(TypeError):
            IncompleteCourseRepo()

    def test_no_hierarchy_methods_in_interface(self):
        """The interface must NOT have hierarchy methods (Req 6.3)."""
        abstract_methods = ICourseRepository.__abstractmethods__
        assert "listar_por_universidad_y_programa" not in abstract_methods
        assert "listar_por_campus_y_programa" not in abstract_methods

    def test_required_abstract_methods(self):
        """The interface must define the current section repository contract."""
        abstract_methods = ICourseRepository.__abstractmethods__
        expected = {
            "create",
            "get_by_id",
            "get_by_code",
            "list_by_subject",
            "list_by_professor",
            "count_by_professor",
            "list_by_program",
            "count_by_program",
            "list_all",
            "count_all",
            "update",
            "update_status",
            "save_evaluation_config",
            "list_enrolled_students",
            "count_enrolled_students",
            "delete",
        }
        assert abstract_methods == expected

    def test_interface_is_exported_from_init(self):
        """ICourseRepository should be importable from the interfaces package."""
        from app.domain.interfaces import ICourseRepository as ExportedInterface

        assert ExportedInterface is ICourseRepository
