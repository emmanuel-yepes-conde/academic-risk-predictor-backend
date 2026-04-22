from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.application.schemas.course import CourseCreate, CourseUpdate
    from app.domain.enums import CourseStatusEnum
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

    # --- Métodos CRUD nuevos ---

    @abstractmethod
    async def create(self, data: dict) -> Course: ...

    @abstractmethod
    async def update(self, course_id: UUID, data: CourseUpdate) -> Course | None: ...

    @abstractmethod
    async def get_by_code(self, code: str) -> Course | None: ...

    @abstractmethod
    async def list_all(
        self, skip: int, limit: int, status: CourseStatusEnum | None = None
    ) -> list[Course]: ...

    @abstractmethod
    async def count_all(self, status: CourseStatusEnum | None = None) -> int: ...

    @abstractmethod
    async def update_status(
        self, course_id: UUID, status: CourseStatusEnum
    ) -> Course | None: ...
