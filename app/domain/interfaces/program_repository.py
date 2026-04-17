from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.infrastructure.models.program import Program


class IProgramRepository(ABC):
    """Interface for program query operations needed by CampusService (Req 4.1, 5.1)."""

    @abstractmethod
    async def list_by_campus(
        self, campus_id: UUID, skip: int, limit: int
    ) -> list[Program]: ...

    @abstractmethod
    async def count_by_campus(self, campus_id: UUID) -> int: ...

    @abstractmethod
    async def get_by_id(self, program_id: UUID) -> Program | None: ...
