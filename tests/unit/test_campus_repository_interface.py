"""
Unit tests for ICampusRepository interface.
Validates: Requirements 2.1, 2.4, 2.5, 2.6
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.domain.interfaces.campus_repository import ICampusRepository


class TestICampusRepositoryInterface:
    """Verify the ICampusRepository ABC defines all required abstract methods."""

    def test_cannot_instantiate_abstract_class(self):
        """ICampusRepository is abstract and cannot be instantiated directly."""
        with pytest.raises(TypeError):
            ICampusRepository()

    def test_concrete_implementation_with_all_methods(self):
        """A concrete class implementing all abstract methods can be instantiated."""

        class ConcreteCampusRepo(ICampusRepository):
            async def create(self, university_id, data):
                ...

            async def get_by_id(self, campus_id):
                ...

            async def get_by_university_and_code(self, university_id, campus_code):
                ...

            async def list_by_university(self, university_id, skip, limit):
                ...

            async def count_by_university(self, university_id):
                ...

            async def update(self, campus_id, data):
                ...

        repo = ConcreteCampusRepo()
        assert isinstance(repo, ICampusRepository)

    def test_missing_create_raises_type_error(self):
        """Omitting 'create' prevents instantiation."""

        class IncompleteCampusRepo(ICampusRepository):
            async def get_by_id(self, campus_id):
                ...

            async def get_by_university_and_code(self, university_id, campus_code):
                ...

            async def list_by_university(self, university_id, skip, limit):
                ...

            async def count_by_university(self, university_id):
                ...

            async def update(self, campus_id, data):
                ...

        with pytest.raises(TypeError):
            IncompleteCampusRepo()

    def test_missing_get_by_id_raises_type_error(self):
        """Omitting 'get_by_id' prevents instantiation."""

        class IncompleteCampusRepo(ICampusRepository):
            async def create(self, university_id, data):
                ...

            async def get_by_university_and_code(self, university_id, campus_code):
                ...

            async def list_by_university(self, university_id, skip, limit):
                ...

            async def count_by_university(self, university_id):
                ...

            async def update(self, campus_id, data):
                ...

        with pytest.raises(TypeError):
            IncompleteCampusRepo()

    def test_missing_get_by_university_and_code_raises_type_error(self):
        """Omitting 'get_by_university_and_code' prevents instantiation."""

        class IncompleteCampusRepo(ICampusRepository):
            async def create(self, university_id, data):
                ...

            async def get_by_id(self, campus_id):
                ...

            async def list_by_university(self, university_id, skip, limit):
                ...

            async def count_by_university(self, university_id):
                ...

            async def update(self, campus_id, data):
                ...

        with pytest.raises(TypeError):
            IncompleteCampusRepo()

    def test_missing_list_by_university_raises_type_error(self):
        """Omitting 'list_by_university' prevents instantiation."""

        class IncompleteCampusRepo(ICampusRepository):
            async def create(self, university_id, data):
                ...

            async def get_by_id(self, campus_id):
                ...

            async def get_by_university_and_code(self, university_id, campus_code):
                ...

            async def count_by_university(self, university_id):
                ...

            async def update(self, campus_id, data):
                ...

        with pytest.raises(TypeError):
            IncompleteCampusRepo()

    def test_missing_count_by_university_raises_type_error(self):
        """Omitting 'count_by_university' prevents instantiation."""

        class IncompleteCampusRepo(ICampusRepository):
            async def create(self, university_id, data):
                ...

            async def get_by_id(self, campus_id):
                ...

            async def get_by_university_and_code(self, university_id, campus_code):
                ...

            async def list_by_university(self, university_id, skip, limit):
                ...

            async def update(self, campus_id, data):
                ...

        with pytest.raises(TypeError):
            IncompleteCampusRepo()

    def test_missing_update_raises_type_error(self):
        """Omitting 'update' prevents instantiation."""

        class IncompleteCampusRepo(ICampusRepository):
            async def create(self, university_id, data):
                ...

            async def get_by_id(self, campus_id):
                ...

            async def get_by_university_and_code(self, university_id, campus_code):
                ...

            async def list_by_university(self, university_id, skip, limit):
                ...

            async def count_by_university(self, university_id):
                ...

        with pytest.raises(TypeError):
            IncompleteCampusRepo()

    def test_interface_has_correct_docstring(self):
        """The interface should have a descriptive docstring."""
        assert ICampusRepository.__doc__ is not None
        assert "campus" in ICampusRepository.__doc__.lower()

    def test_interface_is_exported_from_init(self):
        """ICampusRepository should be importable from the interfaces package."""
        from app.domain.interfaces import ICampusRepository as ExportedInterface

        assert ExportedInterface is ICampusRepository
