"""
UniversityService — lógica de negocio para operaciones CRUD de universidades.
"""

import asyncio
from uuid import UUID

from fastapi import HTTPException

from app.application.schemas.university import UniversityCreate, UniversityRead, UniversityUpdate
from app.application.schemas.user import PaginatedResponse
from app.domain.enums import RoleEnum
from app.domain.interfaces.university_repository import IUniversityRepository


class UniversityService:
    """
    Servicio de aplicación que encapsula la lógica de negocio de universidades.
    Recibe IUniversityRepository como dependencia inyectada (DIP).
    """

    def __init__(self, repo: IUniversityRepository) -> None:
        self._repo = repo

    async def create(self, data: UniversityCreate, actor_role: RoleEnum) -> UniversityRead:
        """
        Crea una nueva universidad.
        Lanza HTTPException(403) si el actor no es ADMIN.
        Lanza HTTPException(409) si el código ya existe.
        """
        if actor_role != RoleEnum.ADMIN:
            raise HTTPException(status_code=403, detail="Se requiere rol ADMIN")

        existing = await self._repo.get_by_code(data.code)
        if existing is not None:
            raise HTTPException(status_code=409, detail="El código de universidad ya existe")

        university = await self._repo.create(data)
        return UniversityRead.model_validate(university)

    async def list(self, skip: int, limit: int) -> PaginatedResponse[UniversityRead]:
        """
        Lista universidades con paginación.
        Ejecuta list y count en paralelo con asyncio.gather.
        """
        universities, total = await asyncio.gather(
            self._repo.list(skip=skip, limit=limit),
            self._repo.count(),
        )

        return PaginatedResponse[UniversityRead](
            data=[UniversityRead.model_validate(u) for u in universities],
            total=total,
            skip=skip,
            limit=limit,
        )

    async def get(self, id: UUID) -> UniversityRead:
        """
        Obtiene una universidad por ID.
        Lanza HTTPException(404) si no existe.
        """
        university = await self._repo.get_by_id(id)
        if university is None:
            raise HTTPException(status_code=404, detail="Universidad no encontrada")
        return UniversityRead.model_validate(university)

    async def update(
        self, id: UUID, data: UniversityUpdate, actor_role: RoleEnum
    ) -> UniversityRead:
        """
        Actualiza parcialmente una universidad.
        Lanza HTTPException(403) si el actor no es ADMIN.
        Lanza HTTPException(404) si no existe.
        """
        if actor_role != RoleEnum.ADMIN:
            raise HTTPException(status_code=403, detail="Se requiere rol ADMIN")

        university = await self._repo.update(id, data)
        if university is None:
            raise HTTPException(status_code=404, detail="Universidad no encontrada")
        return UniversityRead.model_validate(university)
