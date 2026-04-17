from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.application.schemas.campus import CampusCreate, CampusUpdate
    from app.infrastructure.models.campus import Campus


class ICampusRepository(ABC):
    """Interface for campus persistence operations (Req 2.1, 2.4, 2.5, 2.6)."""

    @abstractmethod
    async def create(self, university_id: UUID, data: CampusCreate) -> Campus: ...

    @abstractmethod
    async def get_by_id(self, campus_id: UUID) -> Campus | None: ...

    @abstractmethod
    async def get_by_university_and_code(
        self, university_id: UUID, campus_code: str
    ) -> Campus | None: ...

    @abstractmethod
    async def list_by_university(
        self, university_id: UUID, skip: int, limit: int
    ) -> list[Campus]: ...

    @abstractmethod
    async def count_by_university(self, university_id: UUID) -> int: ...

    @abstractmethod
    async def update(self, campus_id: UUID, data: CampusUpdate) -> Campus | None: ...
