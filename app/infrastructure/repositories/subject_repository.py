"""SubjectRepository — persistencia de materias (definiciones académicas)."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.audit_log import AuditLogCreate
from app.application.schemas.subject import SubjectUpdate
from app.domain.enums import CourseStatusEnum, OperationEnum
from app.domain.interfaces.subject_repository import ISubjectRepository
from app.infrastructure.models.subject import Subject
from app.infrastructure.repositories.audit_log_repository import AuditLogRepository


class SubjectRepository(ISubjectRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit = AuditLogRepository(session)

    async def create(self, data: dict) -> Subject:
        subject = Subject(**data)
        self._session.add(subject)
        await self._session.flush()
        await self._session.refresh(subject)
        await self._audit.register(AuditLogCreate(
            table_name="subjects",
            operation=OperationEnum.INSERT,
            record_id=subject.id,
            new_data={k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
                      for k, v in data.items()},
        ))
        return subject

    async def get_by_id(self, subject_id: UUID) -> Subject | None:
        result = await self._session.execute(
            select(Subject).where(Subject.id == subject_id)
        )
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str, program_id: UUID) -> Subject | None:
        result = await self._session.execute(
            select(Subject).where(Subject.code == code, Subject.program_id == program_id)
        )
        return result.scalar_one_or_none()

    async def list_by_program(self, program_id: UUID) -> list[Subject]:
        stmt = select(Subject).where(Subject.program_id == program_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def list_all(
        self, skip: int, limit: int, status: CourseStatusEnum | None = None
    ) -> list[Subject]:
        stmt = select(Subject)
        if status is not None:
            stmt = stmt.where(Subject.status == status)
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_all(self, status: CourseStatusEnum | None = None) -> int:
        stmt = select(func.count()).select_from(Subject)
        if status is not None:
            stmt = stmt.where(Subject.status == status)
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def update(self, subject_id: UUID, data: SubjectUpdate) -> Subject | None:
        subject = await self.get_by_id(subject_id)
        if subject is None:
            return None
        previous = {
            k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
            for k, v in subject.model_dump().items()
        }
        updates = data.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(subject, field, value)
        self._session.add(subject)
        await self._session.flush()
        await self._session.refresh(subject)
        await self._audit.register(AuditLogCreate(
            table_name="subjects",
            operation=OperationEnum.UPDATE,
            record_id=subject_id,
            previous_data=previous,
            new_data=updates,
        ))
        return subject

    async def update_status(
        self, subject_id: UUID, status: CourseStatusEnum
    ) -> Subject | None:
        subject = await self.get_by_id(subject_id)
        if subject is None:
            return None
        previous_status = subject.status
        subject.status = status
        self._session.add(subject)
        await self._session.flush()
        await self._session.refresh(subject)
        await self._audit.register(AuditLogCreate(
            table_name="subjects",
            operation=OperationEnum.UPDATE,
            record_id=subject_id,
            previous_data={"status": previous_status},
            new_data={"status": status},
        ))
        return subject
