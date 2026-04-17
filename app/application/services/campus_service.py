"""
CampusService — lógica de negocio para operaciones CRUD de campus
y endpoints jerárquicos universidad → campus → programa → curso.
Requisitos: 2.1–2.7, 4.1–4.4, 5.1–5.3
"""

import asyncio
from uuid import UUID

from fastapi import HTTPException

from app.application.schemas.campus import CampusCreate, CampusRead, CampusUpdate
from app.application.schemas.course import CourseRead
from app.application.schemas.program import ProgramRead
from app.application.schemas.user import PaginatedResponse
from app.domain.enums import RoleEnum
from app.domain.interfaces.campus_repository import ICampusRepository
from app.domain.interfaces.course_repository import ICourseRepository
from app.domain.interfaces.program_repository import IProgramRepository
from app.domain.interfaces.university_repository import IUniversityRepository


class CampusService:
    """
    Servicio de aplicación que encapsula la lógica de negocio de campus.
    Recibe ICampusRepository, IUniversityRepository, IProgramRepository
    e ICourseRepository como dependencias inyectadas (DIP).
    """

    def __init__(
        self,
        campus_repo: ICampusRepository,
        university_repo: IUniversityRepository,
        program_repo: IProgramRepository,
        course_repo: ICourseRepository,
    ) -> None:
        self._campus_repo = campus_repo
        self._university_repo = university_repo
        self._program_repo = program_repo
        self._course_repo = course_repo

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _verify_university_exists(self, university_id: UUID) -> None:
        """Lanza 404 si la universidad no existe."""
        university = await self._university_repo.get_by_id(university_id)
        if university is None:
            raise HTTPException(status_code=404, detail="Universidad no encontrada")

    async def _get_campus_belonging_to_university(
        self, university_id: UUID, campus_id: UUID
    ):
        """
        Retorna el campus si existe y pertenece a la universidad.
        Lanza 404 con mensaje descriptivo en caso contrario.
        """
        campus = await self._campus_repo.get_by_id(campus_id)
        if campus is None:
            raise HTTPException(status_code=404, detail="Campus no encontrado")
        if campus.university_id != university_id:
            raise HTTPException(
                status_code=404,
                detail="El campus no pertenece a la universidad indicada",
            )
        return campus

    # ------------------------------------------------------------------
    # CRUD de campus (Req 2.1–2.7)
    # ------------------------------------------------------------------

    async def create(
        self, university_id: UUID, data: CampusCreate, actor_role: RoleEnum
    ) -> CampusRead:
        """
        Crea un nuevo campus asociado a una universidad.
        Lanza HTTPException(403) si el actor no es ADMIN.
        Lanza HTTPException(404) si la universidad no existe.
        Lanza HTTPException(409) si la combinación university_id+campus_code ya existe.
        """
        if actor_role != RoleEnum.ADMIN:
            raise HTTPException(status_code=403, detail="Se requiere rol ADMIN")

        await self._verify_university_exists(university_id)

        existing = await self._campus_repo.get_by_university_and_code(
            university_id, data.campus_code
        )
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail="La combinación university_id + campus_code ya existe",
            )

        campus = await self._campus_repo.create(university_id, data)
        return CampusRead.model_validate(campus)

    async def list_by_university(
        self, university_id: UUID, skip: int, limit: int
    ) -> PaginatedResponse[CampusRead]:
        """
        Lista campus de una universidad con paginación.
        Ejecuta list y count en paralelo con asyncio.gather.
        """
        campuses, total = await asyncio.gather(
            self._campus_repo.list_by_university(
                university_id, skip=skip, limit=limit
            ),
            self._campus_repo.count_by_university(university_id),
        )

        return PaginatedResponse[CampusRead](
            data=[CampusRead.model_validate(c) for c in campuses],
            total=total,
            skip=skip,
            limit=limit,
        )

    async def get(self, university_id: UUID, campus_id: UUID) -> CampusRead:
        """
        Obtiene un campus por ID, verificando que pertenezca a la universidad.
        Lanza HTTPException(404) si no existe o no pertenece a la universidad.
        """
        campus = await self._get_campus_belonging_to_university(
            university_id, campus_id
        )
        return CampusRead.model_validate(campus)

    async def update(
        self,
        university_id: UUID,
        campus_id: UUID,
        data: CampusUpdate,
        actor_role: RoleEnum,
    ) -> CampusRead:
        """
        Actualiza parcialmente un campus.
        Lanza HTTPException(403) si el actor no es ADMIN.
        Lanza HTTPException(404) si no existe o no pertenece a la universidad.
        """
        if actor_role != RoleEnum.ADMIN:
            raise HTTPException(status_code=403, detail="Se requiere rol ADMIN")

        await self._get_campus_belonging_to_university(university_id, campus_id)

        campus = await self._campus_repo.update(campus_id, data)
        if campus is None:
            raise HTTPException(status_code=404, detail="Campus no encontrado")
        return CampusRead.model_validate(campus)

    # ------------------------------------------------------------------
    # Endpoints jerárquicos (Req 4.1–4.4, 5.1–5.3)
    # ------------------------------------------------------------------

    async def list_programs_by_campus(
        self, university_id: UUID, campus_id: UUID, skip: int, limit: int
    ) -> PaginatedResponse[ProgramRead]:
        """
        Lista programas de un campus con paginación.
        Valida que el campus pertenezca a la universidad (404).
        """
        await self._get_campus_belonging_to_university(university_id, campus_id)

        programs, total = await asyncio.gather(
            self._program_repo.list_by_campus(campus_id, skip=skip, limit=limit),
            self._program_repo.count_by_campus(campus_id),
        )

        return PaginatedResponse[ProgramRead](
            data=[ProgramRead.model_validate(p) for p in programs],
            total=total,
            skip=skip,
            limit=limit,
        )

    async def list_courses_by_campus_and_program(
        self, university_id: UUID, campus_id: UUID, program_id: UUID
    ) -> list[CourseRead]:
        """
        Lista cursos de un programa dentro de un campus.
        Valida la cadena completa: universidad → campus → programa (404 en cada nivel).
        """
        # 1. Validar campus pertenece a universidad
        await self._get_campus_belonging_to_university(university_id, campus_id)

        # 2. Validar programa pertenece al campus
        program = await self._program_repo.get_by_id(program_id)
        if program is None:
            raise HTTPException(status_code=404, detail="Programa no encontrado")
        if program.campus_id != campus_id:
            raise HTTPException(
                status_code=404,
                detail="El programa no pertenece al campus indicado",
            )

        # 3. Obtener cursos del programa en el campus
        courses = await self._course_repo.listar_por_campus_y_programa(
            campus_id, program_id
        )
        return [CourseRead.model_validate(c) for c in courses]
