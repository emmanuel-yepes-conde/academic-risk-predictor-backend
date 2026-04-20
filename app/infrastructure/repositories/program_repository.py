"""
Program repository implementation (Req 6.2).
Provides async query operations for programs.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.interfaces.program_repository import IProgramRepository
from app.infrastructure.models.program import Program


class ProgramRepository(IProgramRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, program_id: UUID) -> Program | None:
        result = await self._session.execute(
            select(Program).where(Program.id == program_id)
        )
        return result.scalar_one_or_none()

    async def list_all(self, skip: int, limit: int) -> list[Program]:
        result = await self._session.execute(
            select(Program).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def count_all(self) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(Program)
        )
        return result.scalar_one()
