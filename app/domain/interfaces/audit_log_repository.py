from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.application.schemas.audit_log import AuditLogCreate
    from app.infrastructure.models.audit_log import AuditLog


class IAuditLogRepository(ABC):
    """Interface for audit log persistence — insert-only (Req 6.3, 9.4)."""

    @abstractmethod
    async def register(self, log: AuditLogCreate) -> AuditLog: ...
