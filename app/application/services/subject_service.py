"""SubjectService — lógica de negocio para materias (definiciones académicas)."""

import csv
import io
from uuid import UUID

from fastapi import HTTPException

from app.application.schemas.subject import (
    SubjectBulkRowResult,
    SubjectBulkUploadResponse,
    SubjectCreate,
    SubjectRead,
    SubjectStatusUpdate,
    SubjectUpdate,
)
from app.domain.enums import CourseStatusEnum
from app.domain.interfaces.subject_repository import ISubjectRepository


class SubjectService:
    def __init__(self, repo: ISubjectRepository) -> None:
        self._repo = repo

    async def create_subject(self, data: SubjectCreate) -> SubjectRead:
        existing = await self._repo.get_by_code(data.code, data.program_id)
        if existing is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Ya existe una materia con el código '{data.code}' en este programa",
            )
        subject = await self._repo.create(data.model_dump())
        return SubjectRead.model_validate(subject)

    async def get_subject(self, subject_id: UUID) -> SubjectRead:
        subject = await self._repo.get_by_id(subject_id)
        if subject is None:
            raise HTTPException(status_code=404, detail="Materia no encontrada")
        return SubjectRead.model_validate(subject)

    async def list_by_program(self, program_id: UUID) -> list[SubjectRead]:
        subjects = await self._repo.list_by_program(program_id)
        return [SubjectRead.model_validate(s) for s in subjects]

    async def update_subject(
        self, subject_id: UUID, data: SubjectUpdate
    ) -> SubjectRead:
        subject = await self._repo.update(subject_id, data)
        if subject is None:
            raise HTTPException(status_code=404, detail="Materia no encontrada")
        return SubjectRead.model_validate(subject)

    async def update_status(
        self, subject_id: UUID, data: SubjectStatusUpdate
    ) -> SubjectRead:
        subject = await self._repo.update_status(subject_id, data.status)
        if subject is None:
            raise HTTPException(status_code=404, detail="Materia no encontrada")
        return SubjectRead.model_validate(subject)

    async def bulk_create_from_csv(
        self,
        file_content: bytes,
        program_id: UUID,
    ) -> SubjectBulkUploadResponse:
        """
        Crea materias desde un CSV con columnas: code, name, credits.
        program_id se recibe como parámetro (del programa seleccionado en la UI).
        Procesa todas las filas independientemente.
        """
        text = file_content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))

        required_columns = {"code", "name", "credits"}
        if reader.fieldnames is None or not required_columns.issubset(
            set(f.strip() for f in reader.fieldnames)
        ):
            raise HTTPException(
                status_code=422,
                detail="El CSV debe tener las columnas: code, name, credits",
            )

        results: list[SubjectBulkRowResult] = []

        for row_num, row in enumerate(reader, start=1):
            row = {k.strip(): v.strip() for k, v in row.items()}
            code = row.get("code", "")

            missing = [c for c in required_columns if not row.get(c)]
            if missing:
                results.append(SubjectBulkRowResult(
                    row=row_num, code=code, status="error",
                    detail=f"Campos vacíos o faltantes: {', '.join(missing)}",
                ))
                continue

            try:
                credits = int(row["credits"])
                if credits <= 0:
                    raise ValueError
            except ValueError:
                results.append(SubjectBulkRowResult(
                    row=row_num, code=code, status="error",
                    detail=f"credits debe ser entero positivo, se recibió '{row['credits']}'",
                ))
                continue

            existing = await self._repo.get_by_code(code, program_id)
            if existing is not None:
                results.append(SubjectBulkRowResult(
                    row=row_num, code=code, status="error",
                    detail=f"El código '{code}' ya está registrado en este programa",
                ))
                continue

            try:
                subject = await self._repo.create({
                    "code": code,
                    "name": row["name"],
                    "credits": credits,
                    "program_id": program_id,
                })
                results.append(SubjectBulkRowResult(
                    row=row_num, code=code, status="created",
                    subject=SubjectRead.model_validate(subject),
                ))
            except Exception as exc:
                results.append(SubjectBulkRowResult(
                    row=row_num, code=code, status="error", detail=str(exc),
                ))

        created = sum(1 for r in results if r.status == "created")
        failed = sum(1 for r in results if r.status == "error")
        return SubjectBulkUploadResponse(
            total_rows=len(results),
            created=created,
            failed=failed,
            results=results,
        )
