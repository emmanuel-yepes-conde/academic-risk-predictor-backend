"""
Program repository implementation (Req 4.1, 5.1).
Provides async query operations for programs needed by CampusService.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.interfaces.program_repository import IProgramRepository
from app.infrastructure.models.program import Program


class ProgramRepository(IProgramRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_campus(
        self, campus_id: UUID, skip: int, limit: int
    ) -> list[Program]:
        result = await self._session.execute(
            select(Program)
            .where(Program.campus_id == campus_id)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_campus(self, campus_id: UUID) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(Program)
            .where(Program.campus_id == campus_id)
        )
        return result.scalar_one()

    async def get_by_id(self, program_id: UUID) -> Program | None:
        result = await self._session.execute(
            select(Program).where(Program.id == program_id)
        )
        return result.scalar_one_or_none()
