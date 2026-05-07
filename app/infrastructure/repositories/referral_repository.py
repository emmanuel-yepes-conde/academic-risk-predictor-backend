"""Referral repository — acceso a datos para la tabla referrals."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.models.referral import Referral


class ReferralRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, data: dict) -> Referral:
        referral = Referral(**data)
        self._session.add(referral)
        await self._session.flush()
        await self._session.refresh(referral)
        return referral

    async def get_by_id(self, referral_id: UUID) -> Referral | None:
        result = await self._session.execute(
            select(Referral).where(Referral.id == referral_id)
        )
        return result.scalar_one_or_none()

    async def list_by_enrollment(self, enrollment_id: UUID) -> list[Referral]:
        result = await self._session.execute(
            select(Referral)
            .where(Referral.enrollment_id == enrollment_id)
            .order_by(Referral.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_by_professor(self, professor_id: UUID) -> list[Referral]:
        """Todas las remisiones creadas por un profesor."""
        result = await self._session.execute(
            select(Referral)
            .where(Referral.created_by == professor_id)
            .order_by(Referral.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_by_course(self, course_id: UUID) -> list[Referral]:
        """Remisiones de todos los estudiantes de un curso."""
        from app.infrastructure.models.enrollment import Enrollment
        result = await self._session.execute(
            select(Referral)
            .join(Enrollment, Referral.enrollment_id == Enrollment.id)
            .where(Enrollment.course_id == course_id)
            .order_by(Referral.created_at.desc())
        )
        return list(result.scalars().all())

    async def update(self, referral_id: UUID, fields: dict) -> Referral | None:
        referral = await self.get_by_id(referral_id)
        if referral is None:
            return None
        for key, value in fields.items():
            setattr(referral, key, value)
        referral.updated_at = datetime.now(timezone.utc)
        self._session.add(referral)
        await self._session.flush()
        await self._session.refresh(referral)
        return referral
