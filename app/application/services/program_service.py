"""
ProgramService — lógica de negocio para operaciones CRUD de programas.
Requirements: 4.1, 4.2, 5.3
"""

from uuid import UUID

from fastapi import HTTPException

from app.application.schemas.program import ProgramCreate, ProgramRead, ProgramUpdate
from app.domain.interfaces.program_repository import IProgramRepository


class ProgramService:
    """
    Servicio de aplicación que encapsula la lógica de negocio de programas.
    Recibe IProgramRepository como dependencia inyectada (DIP).
    """

    def __init__(self, repo: IProgramRepository) -> None:
        self._repo = repo

    async def create_program(self, data: ProgramCreate) -> ProgramRead:
        """
        Crea un nuevo programa con validación de unicidad.
        Lanza HTTPException(409) si program_code o snies_code ya existen.
        """
        existing = await self._repo.get_by_program_code(data.program_code)
        if existing is not None:
            raise HTTPException(
                status_code=409, detail="El program_code ya está registrado"
            )

        existing = await self._repo.get_by_snies_code(data.snies_code)
        if existing is not None:
            raise HTTPException(
                status_code=409, detail="El snies_code ya está registrado"
            )

        program = await self._repo.create(data.model_dump())
        return ProgramRead.model_validate(program)

    async def update_program(
        self, program_id: UUID, data: ProgramUpdate
    ) -> ProgramRead:
        """
        Actualiza parcialmente un programa con validación de unicidad.
        Lanza HTTPException(404) si no existe.
        Lanza HTTPException(409) si program_code o snies_code pertenecen a otro programa.
        """
        if data.program_code is not None:
            existing = await self._repo.get_by_program_code(data.program_code)
            if existing is not None and existing.id != program_id:
                raise HTTPException(
                    status_code=409, detail="El program_code ya está registrado"
                )

        if data.snies_code is not None:
            existing = await self._repo.get_by_snies_code(data.snies_code)
            if existing is not None and existing.id != program_id:
                raise HTTPException(
                    status_code=409, detail="El snies_code ya está registrado"
                )

        program = await self._repo.update(program_id, data)
        if program is None:
            raise HTTPException(status_code=404, detail="Programa no encontrado")

        return ProgramRead.model_validate(program)

    async def get_program(self, program_id: UUID) -> ProgramRead:
        """
        Obtiene un programa por su ID.
        Lanza HTTPException(404) si no existe.

        Requirements: 4.1, 4.2
        """
        program = await self._repo.get_by_id(program_id)
        if program is None:
            raise HTTPException(status_code=404, detail="Programa no encontrado")
        return ProgramRead.model_validate(program)
