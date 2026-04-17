from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.application.schemas.course import CourseCreate
    from app.infrastructure.models.course import Course
    from app.infrastructure.models.user import User


class ICourseRepository(ABC):
    """Interface for course persistence operations (Req 6.2)."""

    @abstractmethod
    async def crear(self, asignatura: CourseCreate) -> Course: ...

    @abstractmethod
    async def obtener_por_id(self, id: UUID) -> Course | None: ...

    @abstractmethod
    async def listar_por_docente(self, docente_id: UUID) -> list[Course]: ...

    @abstractmethod
    async def listar_estudiantes_inscritos(self, course_id: UUID) -> list[User]: ...

    @abstractmethod
    async def listar_por_programa(self, program_id: UUID) -> list[Course]: ...

    @abstractmethod
    async def listar_por_universidad_y_programa(
        self, university_id: UUID, program_id: UUID
    ) -> list[Course]: ...

    @abstractmethod
    async def listar_por_campus_y_programa(
        self, campus_id: UUID, program_id: UUID
    ) -> list[Course]: ...
