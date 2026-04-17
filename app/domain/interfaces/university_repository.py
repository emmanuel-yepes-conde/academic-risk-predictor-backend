from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.application.schemas.university import UniversityCreate, UniversityUpdate
    from app.infrastructure.models.university import University


class IUniversityRepository(ABC):
    """Interface for university persistence operations (Req 1.2, 1.4, 1.5, 1.6)."""

    @abstractmethod
    async def create(self, data: UniversityCreate) -> University: ...

    @abstractmethod
    async def get_by_id(self, id: UUID) -> University | None: ...

    @abstractmethod
    async def get_by_code(self, code: str) -> University | None: ...

    @abstractmethod
    async def list(self, skip: int, limit: int) -> list[University]: ...

    @abstractmethod
    async def count(self) -> int: ...

    @abstractmethod
    async def update(self, id: UUID, data: UniversityUpdate) -> University | None: ...
