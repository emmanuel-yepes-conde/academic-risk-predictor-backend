from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.domain.enums import RoleEnum, UserStatusEnum

if TYPE_CHECKING:
    from app.application.schemas.user import UserCreate, UserUpdate
    from app.infrastructure.models.user import User


class IUserRepository(ABC):
    """Interface for user persistence operations (Req 6.1)."""

    @abstractmethod
    async def create(self, user: UserCreate) -> User: ...

    @abstractmethod
    async def create_from_dict(self, data: dict[str, Any]) -> User: ...

    @abstractmethod
    async def get_by_id(self, id: UUID) -> User | None: ...

    @abstractmethod
    async def get_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    async def get_by_microsoft_oid(self, oid: str) -> User | None: ...

    @abstractmethod
    async def get_by_google_oid(self, oid: str) -> User | None: ...

    @abstractmethod
    async def list(
        self,
        role: RoleEnum | None,
        professor_id: UUID | None,
        status: UserStatusEnum | None,
        skip: int,
        limit: int,
    ) -> list[User]: ...

    @abstractmethod
    async def count(
        self,
        role: RoleEnum | None,
        professor_id: UUID | None,
        status: UserStatusEnum | None,
    ) -> int: ...

    @abstractmethod
    async def update(self, id: UUID, data: UserUpdate) -> User | None: ...

    @abstractmethod
    async def update_status(self, id: UUID, status: UserStatusEnum) -> User | None: ...
