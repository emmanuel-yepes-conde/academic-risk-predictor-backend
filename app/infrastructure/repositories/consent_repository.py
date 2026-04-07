"""
Consent repository implementation (Req 6.4, 8.1, 8.4).
Consent records are immutable — revocation creates a new record with accepted=False.
No direct modification methods are exposed.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.audit_log import AuditLogCreate
from app.domain.enums import OperationEnum
from app.domain.interfaces.consent_repository import IConsentRepository
from app.infrastructure.models.consent import Consent
from app.infrastructure.repositories.audit_log_repository import AuditLogRepository


class ConsentRepository(IConsentRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit = AuditLogRepository(session)

    async def register_consent(self, student_id: UUID, version: str, accepted: bool = True) -> Consent:
        """
        Create a new immutable consent record.
        To revoke, call with accepted=False — this creates a new record, leaving the original intact.
        """
        consent = Consent(
            student_id=student_id,
            accepted=accepted,
            terms_version=version,
        )
        self._session.add(consent)
        await self._session.flush()
        await self._session.refresh(consent)
        await self._audit.register(AuditLogCreate(
            table_name="consents",
            operation=OperationEnum.INSERT,
            record_id=consent.id,
            new_data={
                "student_id": str(student_id),
                "accepted": accepted,
                "terms_version": version,
            },
        ))
        return consent

    async def get_consent(self, student_id: UUID) -> Consent | None:
        """Return the most recent consent record for the given student."""
        result = await self._session.execute(
            select(Consent)
            .where(Consent.student_id == student_id)
            .order_by(Consent.accepted_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
