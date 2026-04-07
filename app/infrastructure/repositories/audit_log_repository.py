"""
AuditLog repository — insert-only (Req 6.3, 9.4).
UPDATE and DELETE are explicitly forbidden at the repository level.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.audit_log import AuditLogCreate
from app.domain.interfaces.audit_log_repository import IAuditLogRepository
from app.infrastructure.models.audit_log import AuditLog


class AuditLogRepository(IAuditLogRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def register(self, log: AuditLogCreate) -> AuditLog:
        """Persist a new audit log entry within the current session."""
        entry = AuditLog(
            table_name=log.table_name,
            operation=log.operation,
            record_id=log.record_id,
            user_id=log.user_id,
            previous_data=log.previous_data,
            new_data=log.new_data,
        )
        self._session.add(entry)
        await self._session.flush()
        await self._session.refresh(entry)
        return entry

    async def update(self, *args, **kwargs):  # type: ignore[override]
        raise NotImplementedError("AuditLog records are immutable — UPDATE is forbidden.")

    async def delete(self, *args, **kwargs):  # type: ignore[override]
        raise NotImplementedError("AuditLog records are immutable — DELETE is forbidden.")
