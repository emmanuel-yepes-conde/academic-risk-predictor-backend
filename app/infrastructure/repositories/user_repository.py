"""
User repository implementation (Req 6.1, 7.1, 7.2, 7.3).
Each write operation registers an atomic AuditLog entry in the same session.
RB-04 privacy filter applied when professor_id is provided.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.audit_log import AuditLogCreate
from app.application.schemas.user import UserCreate, UserUpdate
from app.domain.enums import OperationEnum, RoleEnum, UserStatusEnum
from app.domain.interfaces.user_repository import IUserRepository
from app.infrastructure.models.enrollment import Enrollment
from app.infrastructure.models.professor_course import ProfessorCourse
from app.infrastructure.models.user import User
from app.infrastructure.repositories.audit_log_repository import AuditLogRepository


class UserRepository(IUserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit = AuditLogRepository(session)

    def _build_filter_stmt(
        self,
        role: RoleEnum | None,
        professor_id: UUID | None,
        status: UserStatusEnum | None,
    ) -> Select:
        """
        Build a SELECT statement with the appropriate filters applied.
        When professor_id is provided, applies RB-04 privacy filter via JOIN.
        The repository is agnostic to the status=ACTIVE default — that default
        is applied in UserService, not here.
        """
        if professor_id is not None:
            # RB-04: JOIN through Enrollment and ProfessorCourse
            stmt = (
                select(User)
                .join(Enrollment, Enrollment.student_id == User.id)
                .join(
                    ProfessorCourse,
                    ProfessorCourse.course_id == Enrollment.course_id,
                )
                .where(ProfessorCourse.professor_id == professor_id)
                .distinct()
            )
        else:
            stmt = select(User)
            if role is not None:
                stmt = stmt.where(User.role == role)

        if status is not None:
            stmt = stmt.where(User.status == status)

        return stmt

    async def create(self, user: UserCreate) -> User:
        new_user = User(**user.model_dump())
        self._session.add(new_user)
        await self._session.flush()
        await self._session.refresh(new_user)
        await self._audit.register(AuditLogCreate(
            table_name="users",
            operation=OperationEnum.INSERT,
            record_id=new_user.id,
            new_data=user.model_dump(),
        ))
        return new_user

    async def get_by_id(self, id: UUID) -> User | None:
        result = await self._session.execute(select(User).where(User.id == id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_microsoft_oid(self, oid: str) -> User | None:
        result = await self._session.execute(
            select(User).where(User.microsoft_oid == oid)
        )
        return result.scalar_one_or_none()

    async def get_by_google_oid(self, oid: str) -> User | None:
        result = await self._session.execute(
            select(User).where(User.google_oid == oid)
        )
        return result.scalar_one_or_none()

    async def list(
        self,
        role: RoleEnum | None = None,
        professor_id: UUID | None = None,
        status: UserStatusEnum | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[User]:
        """
        List users with optional filters.
        When professor_id is provided, applies RB-04 privacy filter:
        only returns students enrolled in courses assigned to that professor.
        """
        stmt = self._build_filter_stmt(role, professor_id, status)
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(
        self,
        role: RoleEnum | None = None,
        professor_id: UUID | None = None,
        status: UserStatusEnum | None = None,
    ) -> int:
        """
        Count users matching the same filters as list(), without loading records.
        Uses SELECT COUNT(*) for efficiency.
        """
        filter_stmt = self._build_filter_stmt(role, professor_id, status)
        # Wrap the filtered query as a subquery for COUNT
        count_stmt = select(func.count()).select_from(filter_stmt.subquery())
        result = await self._session.execute(count_stmt)
        return result.scalar_one()

    async def update(self, id: UUID, data: UserUpdate) -> User | None:
        user = await self.get_by_id(id)
        if user is None:
            return None

        previous = {
            k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
            for k, v in user.model_dump().items()
        }
        updates = data.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(user, field, value)
        user.updated_at = datetime.now(timezone.utc)

        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)
        await self._audit.register(AuditLogCreate(
            table_name="users",
            operation=OperationEnum.UPDATE,
            record_id=id,
            previous_data=previous,
            new_data=updates,
        ))
        return user

    async def update_status(self, id: UUID, status: UserStatusEnum) -> User | None:
        """
        Update only the status field of a user and register an audit log entry.
        Returns None if the user does not exist.
        """
        user = await self.get_by_id(id)
        if user is None:
            return None

        previous_status = user.status
        user.status = status
        user.updated_at = datetime.now(timezone.utc)

        self._session.add(user)
        await self._session.flush()
        await self._session.refresh(user)
        await self._audit.register(AuditLogCreate(
            table_name="users",
            operation=OperationEnum.UPDATE,
            record_id=id,
            previous_data={"status": previous_status},
            new_data={"status": status},
        ))
        return user
