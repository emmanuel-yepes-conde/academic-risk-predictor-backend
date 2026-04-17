from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.infrastructure.models.consent import Consent


class IConsentRepository(ABC):
    """Interface for ML consent persistence operations (Req 6.4, 8.4)."""

    @abstractmethod
    async def register_consent(self, student_id: UUID, version: str, accepted: bool = True) -> Consent: ...

    @abstractmethod
    async def get_consent(self, student_id: UUID) -> Consent | None: ...
