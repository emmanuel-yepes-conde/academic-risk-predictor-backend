"""
Program repository implementation (Req 6.2).
Provides async query operations for programs.
Each write operation registers an atomic AuditLog entry in the same session.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.audit_log import AuditLogCreate
from app.application.schemas.program import ProgramUpdate
from app.domain.enums import OperationEnum
from app.domain.interfaces.program_repository import IProgramRepository
from app.infrastructure.models.program import Program
from app.infrastructure.repositories.audit_log_repository import AuditLogRepository


class ProgramRepository(IProgramRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit = AuditLogRepository(session)

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

    async def create(self, data: dict) -> Program:
        """Persist a new Program and register an INSERT audit log."""
        program = Program(**data)
        self._session.add(program)
        await self._session.flush()
        await self._session.refresh(program)
        await self._audit.register(AuditLogCreate(
            table_name="programs",
            operation=OperationEnum.INSERT,
            record_id=program.id,
            new_data=data,
        ))
        return program

    async def update(self, program_id: UUID, data: ProgramUpdate) -> Program | None:
        """Apply partial update and register an UPDATE audit log."""
        program = await self.get_by_id(program_id)
        if program is None:
            return None

        previous_data = {
            k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
            for k, v in program.model_dump().items()
        }
        updates = data.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(program, field, value)

        self._session.add(program)
        await self._session.flush()
        await self._session.refresh(program)
        await self._audit.register(AuditLogCreate(
            table_name="programs",
            operation=OperationEnum.UPDATE,
            record_id=program_id,
            previous_data=previous_data,
            new_data=updates,
        ))
        return program

    async def get_by_program_code(self, program_code: str) -> Program | None:
        """SELECT ... WHERE program_code = :code"""
        result = await self._session.execute(
            select(Program).where(Program.program_code == program_code)
        )
        return result.scalar_one_or_none()

    async def get_by_snies_code(self, snies_code: int) -> Program | None:
        """SELECT ... WHERE snies_code = :snies"""
        result = await self._session.execute(
            select(Program).where(Program.snies_code == snies_code)
        )
        return result.scalar_one_or_none()
