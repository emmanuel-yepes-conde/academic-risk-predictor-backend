from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.application.schemas.subject import SubjectUpdate
    from app.domain.enums import CourseStatusEnum
    from app.infrastructure.models.subject import Subject


class ISubjectRepository(ABC):

    @abstractmethod
    async def create(self, data: dict) -> Subject: ...

    @abstractmethod
    async def get_by_id(self, subject_id: UUID) -> Subject | None: ...

    @abstractmethod
    async def get_by_code(self, code: str, program_id: UUID) -> Subject | None: ...

    @abstractmethod
    async def list_by_program(
        self, program_id: UUID, skip: int = 0, limit: int = 50
    ) -> list[Subject]: ...

    @abstractmethod
    async def count_by_program(self, program_id: UUID) -> int: ...

    @abstractmethod
    async def list_all(
        self, skip: int, limit: int, status: CourseStatusEnum | None = None
    ) -> list[Subject]: ...

    @abstractmethod
    async def count_all(self, status: CourseStatusEnum | None = None) -> int: ...

    @abstractmethod
    async def update(self, subject_id: UUID, data: SubjectUpdate) -> Subject | None: ...

    @abstractmethod
    async def update_status(
        self, subject_id: UUID, status: CourseStatusEnum
    ) -> Subject | None: ...

    @abstractmethod
    async def delete(self, subject_id: UUID) -> bool: ...
