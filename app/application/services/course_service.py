"""CourseService — lógica de negocio para secciones de materias."""

from uuid import UUID

from fastapi import HTTPException

from app.application.schemas.course import (
    CourseCreate,
    CourseRead,
    CourseStatusUpdate,
    CourseUpdate,
)
from app.application.schemas.user import PaginatedResponse
from app.domain.enums import CourseStatusEnum
from app.domain.interfaces.course_repository import ICourseRepository


class CourseService:
    def __init__(self, repo: ICourseRepository) -> None:
        self._repo = repo

    async def create_course(self, data: CourseCreate) -> CourseRead:
        result = await self._repo.create(data.model_dump())
        return result

    async def get_course(self, course_id: UUID) -> CourseRead:
        course = await self._repo.get_by_id(course_id)
        if course is None:
            raise HTTPException(status_code=404, detail="Sección no encontrada")
        return course

    async def list_courses(
        self,
        status: CourseStatusEnum | None,
        skip: int,
        limit: int,
    ) -> PaginatedResponse[CourseRead]:
        items = await self._repo.list_all(skip, limit, status)
        total = await self._repo.count_all(status)
        return PaginatedResponse(items=items, total=total, skip=skip, limit=limit)

    async def update_course(
        self, course_id: UUID, data: CourseUpdate
    ) -> CourseRead:
        course = await self._repo.update(course_id, data)
        if course is None:
            raise HTTPException(status_code=404, detail="Sección no encontrada")
        return course

    async def update_course_status(
        self, course_id: UUID, data: CourseStatusUpdate
    ) -> CourseRead:
        course = await self._repo.update_status(course_id, data.status)
        if course is None:
            raise HTTPException(status_code=404, detail="Sección no encontrada")
        return course
