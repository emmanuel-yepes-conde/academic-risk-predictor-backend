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

    @abstractmethod
    async def get_by_id(self, course_id: UUID) -> CourseRead | None: ...

    @abstractmethod
    async def list_by_subject(self, subject_id: UUID) -> list[CourseRead]: ...

    @abstractmethod
    async def list_by_professor(self, professor_id: UUID) -> list[CourseRead]: ...

    @abstractmethod
    async def list_by_program(self, program_id: UUID) -> list[CourseRead]: ...

    @abstractmethod
    async def list_all(
        self, skip: int, limit: int, status: CourseStatusEnum | None = None
    ) -> list[CourseRead]: ...

    @abstractmethod
    async def count_all(self, status: CourseStatusEnum | None = None) -> int: ...

    @abstractmethod
    async def update(self, course_id: UUID, data: CourseUpdate) -> CourseRead | None: ...

    @abstractmethod
    async def update_status(
        self, course_id: UUID, status: CourseStatusEnum
    ) -> CourseRead | None: ...

    @abstractmethod
    async def list_enrolled_students(self, course_id: UUID) -> list[User]: ...
