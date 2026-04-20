from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.infrastructure.models.program import Program


class IProgramRepository(ABC):
    """Interface for program query operations (Req 6.1)."""

    @abstractmethod
    async def get_by_id(self, program_id: UUID) -> Program | None: ...

    @abstractmethod
    async def list_all(self, skip: int, limit: int) -> list[Program]: ...

    @abstractmethod
    async def count_all(self) -> int: ...
