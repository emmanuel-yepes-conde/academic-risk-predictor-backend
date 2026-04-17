"""
University repository implementation (Req 1.2, 1.3, 1.4, 1.5, 1.6).
Provides async CRUD operations for the University entity with audit logging.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.audit_log import AuditLogCreate
from app.application.schemas.university import UniversityCreate, UniversityUpdate
from app.domain.enums import OperationEnum
from app.domain.interfaces.university_repository import IUniversityRepository
from app.infrastructure.models.university import University
from app.infrastructure.repositories.audit_log_repository import AuditLogRepository


class UniversityRepository(IUniversityRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit = AuditLogRepository(session)

    async def create(self, data: UniversityCreate) -> University:
        university = University(**data.model_dump())
        self._session.add(university)
        await self._session.flush()
        await self._session.refresh(university)
        await self._audit.register(
            AuditLogCreate(
                table_name="universities",
                operation=OperationEnum.INSERT,
                record_id=university.id,
                new_data=data.model_dump(),
            )
        )
        return university

    async def get_by_id(self, id: UUID) -> University | None:
        result = await self._session.execute(
            select(University).where(University.id == id)
        )
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> University | None:
        result = await self._session.execute(
            select(University).where(University.code == code)
        )
        return result.scalar_one_or_none()

    async def list(self, skip: int, limit: int) -> list[University]:
        result = await self._session.execute(
            select(University).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def count(self) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(University)
        )
        return result.scalar_one()

    async def update(self, id: UUID, data: UniversityUpdate) -> University | None:
        university = await self.get_by_id(id)
        if university is None:
            return None

        update_fields = data.model_dump(exclude_unset=True)
        previous_data = {
            field: getattr(university, field) for field in update_fields
        }

        for field, value in update_fields.items():
            setattr(university, field, value)

        self._session.add(university)
        await self._session.flush()
        await self._session.refresh(university)

        await self._audit.register(
            AuditLogCreate(
                table_name="universities",
                operation=OperationEnum.UPDATE,
                record_id=university.id,
                previous_data=previous_data,
                new_data=update_fields,
            )
        )
        return university
