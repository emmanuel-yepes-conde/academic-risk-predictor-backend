from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.application.schemas.course import CourseCreate, CourseRead, CourseUpdate
    from app.domain.enums import CourseStatusEnum
    from app.infrastructure.models.course import Course
    from app.infrastructure.models.user import User


class ICourseRepository(ABC):
    """Interface para operaciones de persistencia de secciones (Course)."""

    @abstractmethod
    async def create(self, data: dict) -> CourseRead: ...

    async def crear(self, data: CourseCreate) -> CourseRead:
        return await self.create(data.model_dump())

    @abstractmethod
    async def get_by_id(self, course_id: UUID) -> CourseRead | None: ...

    @abstractmethod
    async def get_by_code(self, code: str) -> CourseRead | None: ...

    @abstractmethod
    async def list_by_subject(self, subject_id: UUID) -> list[CourseRead]: ...

    @abstractmethod
    async def list_by_professor(
        self, professor_id: UUID, skip: int = 0, limit: int = 50, search: str | None = None
    ) -> list[CourseRead]: ...

    @abstractmethod
    async def count_by_professor(self, professor_id: UUID, search: str | None = None) -> int: ...

    @abstractmethod
    async def list_by_program(
        self, program_id: UUID, skip: int = 0, limit: int = 50
    ) -> list[CourseRead]: ...

    @abstractmethod
    async def count_by_program(self, program_id: UUID) -> int: ...

    @abstractmethod
    async def list_all(
        self,
        skip: int,
        limit: int,
        status: CourseStatusEnum | None = None,
        subject_id: UUID | None = None,
    ) -> list[CourseRead]: ...

    @abstractmethod
    async def count_all(
        self,
        status: CourseStatusEnum | None = None,
        subject_id: UUID | None = None,
    ) -> int: ...

    @abstractmethod
    async def update(self, course_id: UUID, data: CourseUpdate) -> CourseRead | None: ...

    @abstractmethod
    async def update_status(
        self, course_id: UUID, status: CourseStatusEnum
    ) -> CourseRead | None: ...

    @abstractmethod
    async def save_evaluation_config(
        self, course_id: UUID, config: dict
    ) -> CourseRead | None: ...

    @abstractmethod
    async def list_enrolled_students(
        self, course_id: UUID, skip: int = 0, limit: int = 50
    ) -> list[User]: ...

    @abstractmethod
    async def count_enrolled_students(self, course_id: UUID) -> int: ...

    @abstractmethod
    async def delete(self, course_id: UUID) -> bool: ...
