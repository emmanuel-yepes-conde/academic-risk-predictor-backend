"""
CourseService — lógica de negocio para operaciones CRUD de cursos.
"""

import asyncio
from uuid import UUID

from fastapi import HTTPException

from app.application.schemas.course import CourseCreate, CourseRead, CourseUpdate
from app.application.schemas.user import PaginatedResponse
from app.domain.enums import CourseStatusEnum
from app.domain.interfaces.course_repository import ICourseRepository


class CourseService:
    """
    Servicio de aplicación que encapsula la lógica de negocio de cursos.
    Recibe ICourseRepository vía inyección de constructor (DIP).
    """

    def __init__(self, repo: ICourseRepository) -> None:
        self._repo = repo

    async def create_course(self, data: CourseCreate) -> CourseRead:
        """
        Crea un nuevo curso con validación de unicidad en code.
        Lanza HTTPException(409) si el code ya está registrado.
        """
        existing = await self._repo.get_by_code(data.code)
        if existing is not None:
            raise HTTPException(status_code=409, detail="El code ya está registrado")

        course = await self._repo.create(data.model_dump())
        return CourseRead.model_validate(course)

    async def get_course(self, course_id: UUID) -> CourseRead:
        """
        Obtiene un curso por ID.
        Lanza HTTPException(404) si no existe.
        """
        course = await self._repo.obtener_por_id(course_id)
        if course is None:
            raise HTTPException(status_code=404, detail="Curso no encontrado")
        return CourseRead.model_validate(course)

    async def list_courses(
        self,
        status: CourseStatusEnum | None,
        skip: int,
        limit: int,
    ) -> PaginatedResponse[CourseRead]:
        """
        Lista cursos con paginación y filtro de status.
        Aplica status=ACTIVE como default cuando status es None.
        Ejecuta list_all y count_all en paralelo con asyncio.gather.
        """
        if status is None:
            status = CourseStatusEnum.ACTIVE

        courses, total = await asyncio.gather(
            self._repo.list_all(skip=skip, limit=limit, status=status),
            self._repo.count_all(status=status),
        )

        return PaginatedResponse[CourseRead](
            data=[CourseRead.model_validate(c) for c in courses],
            total=total,
            skip=skip,
            limit=limit,
        )

    async def update_course(self, course_id: UUID, data: CourseUpdate) -> CourseRead:
        """
        Actualiza parcialmente un curso con validación de unicidad en code.
        Lanza HTTPException(409) si el code pertenece a otro curso.
        Lanza HTTPException(404) si el curso no existe.
        """
        if data.code is not None:
            existing = await self._repo.get_by_code(data.code)
            if existing is not None and existing.id != course_id:
                raise HTTPException(
                    status_code=409, detail="El code ya está registrado"
                )

        course = await self._repo.update(course_id, data)
        if course is None:
            raise HTTPException(status_code=404, detail="Curso no encontrado")

        return CourseRead.model_validate(course)

    async def update_course_status(
        self, course_id: UUID, status: CourseStatusEnum
    ) -> CourseRead:
        """
        Actualiza el status de un curso (soft delete / reactivación).
        Lanza HTTPException(404) si no existe.
        """
        course = await self._repo.update_status(course_id, status)
        if course is None:
            raise HTTPException(status_code=404, detail="Curso no encontrado")
        return CourseRead.model_validate(course)
