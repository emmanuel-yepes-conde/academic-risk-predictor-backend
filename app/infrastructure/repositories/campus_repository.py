"""
Campus repository implementation (Req 2.1, 2.3, 2.4, 2.5, 2.6).
Provides async CRUD operations for the Campus entity with audit logging.
"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.audit_log import AuditLogCreate
from app.application.schemas.campus import CampusCreate, CampusUpdate
from app.domain.enums import OperationEnum
from app.domain.interfaces.campus_repository import ICampusRepository
from app.infrastructure.models.campus import Campus
from app.infrastructure.repositories.audit_log_repository import AuditLogRepository


class CampusRepository(ICampusRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit = AuditLogRepository(session)

    async def create(self, university_id: UUID, data: CampusCreate) -> Campus:
        campus = Campus(university_id=university_id, **data.model_dump())
        self._session.add(campus)
        await self._session.flush()
        await self._session.refresh(campus)
        await self._audit.register(
            AuditLogCreate(
                table_name="campuses",
                operation=OperationEnum.INSERT,
                record_id=campus.id,
                new_data={"university_id": str(university_id), **data.model_dump()},
            )
        )
        return campus

    async def get_by_id(self, campus_id: UUID) -> Campus | None:
        result = await self._session.execute(
            select(Campus).where(Campus.id == campus_id)
        )
        return result.scalar_one_or_none()

    async def get_by_university_and_code(
        self, university_id: UUID, campus_code: str
    ) -> Campus | None:
        result = await self._session.execute(
            select(Campus).where(
                Campus.university_id == university_id,
                Campus.campus_code == campus_code,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_university(
        self, university_id: UUID, skip: int, limit: int
    ) -> list[Campus]:
        result = await self._session.execute(
            select(Campus)
            .where(Campus.university_id == university_id)
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def count_by_university(self, university_id: UUID) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(Campus).where(
                Campus.university_id == university_id
            )
        )
        return result.scalar_one()

    async def update(self, campus_id: UUID, data: CampusUpdate) -> Campus | None:
        campus = await self.get_by_id(campus_id)
        if campus is None:
            return None

        update_fields = data.model_dump(exclude_unset=True)
        previous_data = {
            field: getattr(campus, field) for field in update_fields
        }

        for field, value in update_fields.items():
            setattr(campus, field, value)

        self._session.add(campus)
        await self._session.flush()
        await self._session.refresh(campus)

        await self._audit.register(
            AuditLogCreate(
                table_name="campuses",
                operation=OperationEnum.UPDATE,
                record_id=campus.id,
                previous_data=previous_data,
                new_data=update_fields,
            )
        )
        return campus
