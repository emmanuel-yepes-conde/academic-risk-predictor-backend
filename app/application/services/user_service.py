"""
UserService — lógica de negocio para operaciones CRUD de usuarios.
"""

import asyncio
from uuid import UUID

from fastapi import HTTPException

from app.application.schemas.user import PaginatedResponse, UserCreate, UserRead, UserUpdate
from app.core.security import hash_password
from app.domain.enums import RoleEnum, UserStatusEnum
from app.domain.interfaces.user_repository import IUserRepository


class UserService:
    """
    Servicio de aplicación que encapsula la lógica de negocio de usuarios.
    Recibe IUserRepository como dependencia inyectada (DIP).
    """

    def __init__(self, repo: IUserRepository) -> None:
        self._repo = repo

    async def list_users(
        self,
        role: RoleEnum | None,
        professor_id: UUID | None,
        status: UserStatusEnum | None,
        skip: int,
        limit: int,
        program_id: UUID | None = None,
    ) -> PaginatedResponse[UserRead]:
        """
        Lista usuarios con filtros opcionales y paginación.
        Aplica status=ACTIVE como default cuando status es None (RB).
        Ejecuta list y count en paralelo con asyncio.gather.
        """
        if status is None:
            status = UserStatusEnum.ACTIVE

        users, total = await asyncio.gather(
            self._repo.list(role=role, professor_id=professor_id, status=status, skip=skip, limit=limit, program_id=program_id),
            self._repo.count(role=role, professor_id=professor_id, status=status, program_id=program_id),
        )

        return PaginatedResponse[UserRead](
            data=[UserRead.model_validate(u) for u in users],
            total=total,
            skip=skip,
            limit=limit,
        )

    async def create_user(self, data: UserCreate) -> UserRead:
        """
        Crea un nuevo usuario.
        Hashea la contraseña antes de persistir.
        Lanza HTTPException(409) si el email ya está registrado.
        """
        existing = await self._repo.get_by_email(data.email)
        if existing is not None:
            raise HTTPException(status_code=409, detail="El email ya está registrado")

        # Build dict for the repository, hashing the plain password
        user_data = data.model_dump(exclude={"password"})
        if data.password:
            user_data["password_hash"] = hash_password(data.password)

        user = await self._repo.create_from_dict(user_data)
        return UserRead.model_validate(user)

    async def get_user(self, id: UUID) -> UserRead:
        """
        Obtiene un usuario por ID.
        Lanza HTTPException(404) si no existe.
        """
        user = await self._repo.get_by_id(id)
        if user is None:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        return UserRead.model_validate(user)

    async def update_user(self, id: UUID, data: UserUpdate) -> UserRead:
        """
        Actualiza parcialmente un usuario.
        Hashea la contraseña si se proporciona en texto plano.
        Lanza HTTPException(404) si no existe.
        """
        updates = data.model_dump(exclude_unset=True)
        if "password" in updates:
            plain = updates.pop("password")
            if plain:
                updates["password_hash"] = hash_password(plain)

        user = await self._repo.update_from_dict(id, updates)
        if user is None:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        return UserRead.model_validate(user)

    async def get_user_history(self, id: UUID) -> list:
        """
        Devuelve el historial de auditoría de un usuario.
        Lanza HTTPException(404) si el usuario no existe.
        """
        user = await self._repo.get_by_id(id)
        if user is None:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        return await self._repo.get_audit_history(id)

    async def update_user_status(self, id: UUID, status: UserStatusEnum) -> UserRead:
        """
        Actualiza el status de un usuario.
        Lanza HTTPException(404) si no existe.
        """
        user = await self._repo.update_status(id, status)
        if user is None:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        return UserRead.model_validate(user)
