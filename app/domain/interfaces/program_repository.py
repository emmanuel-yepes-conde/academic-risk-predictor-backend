from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.application.schemas.program import ProgramUpdate
    from app.infrastructure.models.program import Program


class IProgramRepository(ABC):
    """Interface for program query operations (Req 6.1)."""

    @abstractmethod
    async def get_by_id(self, program_id: UUID) -> Program | None: ...

    @abstractmethod
    async def list_all(self, skip: int, limit: int) -> list[Program]: ...

    @abstractmethod
    async def count_all(self) -> int: ...

    @abstractmethod
    async def create(self, data: dict) -> Program: ...

    @abstractmethod
    async def update(self, program_id: UUID, data: ProgramUpdate) -> Program | None: ...

    @abstractmethod
    async def get_by_program_code(self, program_code: str) -> Program | None: ...

    @abstractmethod
    async def get_by_snies_code(self, snies_code: int) -> Program | None: ...
