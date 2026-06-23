"""
User repository implementation (Req 6.1, 7.1, 7.2, 7.3).
Each write operation registers an atomic AuditLog entry in the same session.
RB-04 privacy filter applied when professor_id is provided.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.audit_log import AuditLogCreate
from app.application.schemas.user import UserCreate, UserUpdate
from app.domain.enums import OperationEnum, RoleEnum, UserStatusEnum
from app.domain.interfaces.user_repository import IUserRepository
from app.infrastructure.models.course import Course
from app.infrastructure.models.enrollment import Enrollment
from app.infrastructure.models.student_profile import StudentProfile
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
        program_id: UUID | None = None,
    ) -> Select:
        """
        Build a SELECT statement with the appropriate filters applied.
        When professor_id is provided, applies RB-04 privacy filter via JOIN.
        When program_id is provided, filters students by program via student_profiles.
        The repository is agnostic to the status=ACTIVE default — that default
        is applied in UserService, not here.
        """
        if professor_id is not None:
            # RB-04: JOIN through Enrollment and Course.professor_id
            stmt = (
                select(User)
                .join(Enrollment, Enrollment.student_id == User.id)
                .join(
                    Course,
                    Course.id == Enrollment.course_id,
                )
                .where(Course.professor_id == professor_id)
                .distinct()
            )
        else:
            stmt = select(User)
            if role is not None:
                stmt = stmt.where(User.role == role)

        if program_id is not None:
            # Filter by program: join student_profiles on user_id
            stmt = (
                stmt.join(StudentProfile, StudentProfile.user_id == User.id)
                .where(StudentProfile.program_id == program_id)
            )

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

    async def create_from_dict(self, data: dict[str, Any]) -> User:
        """Create a user from a pre-processed dict (password already hashed)."""
        new_user = User(**data)
        self._session.add(new_user)
        await self._session.flush()
        await self._session.refresh(new_user)
        await self._audit.register(AuditLogCreate(
            table_name="users",
            operation=OperationEnum.INSERT,
            record_id=new_user.id,
            new_data={k: v for k, v in data.items() if k != "password_hash"},
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
        program_id: UUID | None = None,
    ) -> list[User]:
        """
        List users with optional filters.
        When professor_id is provided, applies RB-04 privacy filter:
        only returns students enrolled in courses assigned to that professor.
        When program_id is provided, filters by student program.
        """
        stmt = self._build_filter_stmt(role, professor_id, status, program_id)
        stmt = stmt.offset(skip).limit(limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(
        self,
        role: RoleEnum | None = None,
        professor_id: UUID | None = None,
        status: UserStatusEnum | None = None,
        program_id: UUID | None = None,
    ) -> int:
        """
        Count users matching the same filters as list(), without loading records.
        Uses SELECT COUNT(*) for efficiency.
        """
        filter_stmt = self._build_filter_stmt(role, professor_id, status, program_id)
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

    async def update_from_dict(self, id: UUID, data: dict[str, Any]) -> User | None:
        """Update user from a pre-processed dict (e.g. with password already hashed). Registers audit log."""
        user = await self.get_by_id(id)
        if user is None:
            return None

        previous = {
            k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
            for k, v in user.model_dump().items()
        }
        for field, value in data.items():
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
            new_data={k: v for k, v in data.items() if k != "password_hash"},
        ))
        return user

    async def update_fields(self, id: UUID, fields: dict[str, Any]) -> User | None:
        """Lightweight internal update — no audit log (used for last_login stamp)."""
        user = await self.get_by_id(id)
        if user is None:
            return None
        for k, v in fields.items():
            setattr(user, k, v)
        self._session.add(user)
        await self._session.flush()
        return user

    async def count_audit_history(self, record_id: UUID) -> int:
        """Total audit log entries for a user record."""
        from app.infrastructure.models.audit_log import AuditLog
        stmt = (
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.table_name == "users")
            .where(AuditLog.record_id == record_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def get_audit_history(
        self, record_id: UUID, skip: int = 0, limit: int = 50
    ) -> list[Any]:
        """Return audit log entries for a user record, newest first."""
        from app.infrastructure.models.audit_log import AuditLog
        stmt = (
            select(AuditLog, User)
            .outerjoin(User, User.id == AuditLog.user_id)
            .where(AuditLog.table_name == "users")
            .where(AuditLog.record_id == record_id)
            .order_by(AuditLog.timestamp.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        rows = result.all()
        return [
            {
                "id": str(log.id),
                "operation": log.operation.value if hasattr(log.operation, "value") else log.operation,
                "changed_by_id": str(log.user_id) if log.user_id else None,
                "changed_by_name": changer.full_name if changer else None,
                "previous_data": log.previous_data,
                "new_data": log.new_data,
                "timestamp": log.timestamp,
            }
            for log, changer in rows
        ]

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
