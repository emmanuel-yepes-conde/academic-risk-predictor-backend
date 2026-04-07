"""
UserRouter — endpoints CRUD para la entidad User.
Requisitos: 1.x, 2.x, 3.x, 4.x, 5.x, 7.x
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.user import (
    PaginatedResponse,
    UserCreate,
    UserRead,
    UserStatusUpdate,
    UserUpdate,
)
from app.application.services.user_service import UserService
from app.domain.enums import RoleEnum, UserStatusEnum
from app.infrastructure.database import get_session
from app.infrastructure.repositories.user_repository import UserRepository

router = APIRouter()


def _get_service(session: AsyncSession = Depends(get_session)) -> UserService:
    return UserService(UserRepository(session))


@router.get("/users", response_model=PaginatedResponse[UserRead], status_code=200)
async def list_users(
    role: Optional[RoleEnum] = None,
    professor_id: Optional[UUID] = None,
    status: Optional[UserStatusEnum] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    service: UserService = Depends(_get_service),
) -> PaginatedResponse[UserRead]:
    """Lista usuarios con filtros opcionales y paginación. Requisitos: 1.1–1.7"""
    return await service.list_users(
        role=role,
        professor_id=professor_id,
        status=status,
        skip=skip,
        limit=limit,
    )


@router.post("/users", response_model=UserRead, status_code=201)
async def create_user(
    body: UserCreate,
    service: UserService = Depends(_get_service),
) -> UserRead:
    """Crea un nuevo usuario. Requisitos: 2.1–2.3"""
    return await service.create_user(body)


@router.get("/users/{user_id}", response_model=UserRead, status_code=200)
async def get_user(
    user_id: UUID,
    service: UserService = Depends(_get_service),
) -> UserRead:
    """Obtiene un usuario por ID. Requisitos: 3.1–3.3"""
    return await service.get_user(user_id)


@router.patch("/users/{user_id}", response_model=UserRead, status_code=200)
async def update_user(
    user_id: UUID,
    body: UserUpdate,
    service: UserService = Depends(_get_service),
) -> UserRead:
    """Actualiza parcialmente un usuario. Requisitos: 4.1–4.3, 4.5"""
    return await service.update_user(user_id, body)


@router.patch("/users/{user_id}/status", response_model=UserRead, status_code=200)
async def update_user_status(
    user_id: UUID,
    body: UserStatusUpdate,
    service: UserService = Depends(_get_service),
) -> UserRead:
    """Cambia el estado de un usuario (soft delete / reactivación). Requisitos: 5.1–5.4"""
    return await service.update_user_status(user_id, body.status)
