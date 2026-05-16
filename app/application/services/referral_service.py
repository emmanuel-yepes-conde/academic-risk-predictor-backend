"""ReferralService — lógica de negocio para remisiones a permanencia."""

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.referral import (
    EvaluationConfigRead,
    EvaluationConfigUpdate,
    ReferralCreate,
    ReferralRead,
    ReferralUpdate,
)
from app.domain.enums import RoleEnum
from app.infrastructure.models.course import Course
from app.infrastructure.models.enrollment import Enrollment
from app.infrastructure.models.user import User
from app.infrastructure.repositories.referral_repository import ReferralRepository
from app.services.acs_email_service import notify_referral_created

logger = logging.getLogger(__name__)


class ReferralService:
    def __init__(self, repo: ReferralRepository, session: AsyncSession) -> None:
        self._repo    = repo
        self._session = session

    # ── helpers de acceso ────────────────────────────────────────────────────

    async def _get_enrollment(self, enrollment_id: UUID) -> Enrollment:
        result = await self._session.execute(
            select(Enrollment).where(Enrollment.id == enrollment_id)
        )
        enrollment = result.scalar_one_or_none()
        if enrollment is None:
            raise HTTPException(status_code=404, detail="Inscripción no encontrada")
        return enrollment

    async def _get_course(self, course_id: UUID) -> Course:
        result = await self._session.execute(
            select(Course).where(Course.id == course_id)
        )
        course = result.scalar_one_or_none()
        if course is None:
            raise HTTPException(status_code=404, detail="Curso no encontrado")
        return course

    async def _get_user(self, user_id: UUID) -> User | None:
        result = await self._session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def _check_professor_access(self, enrollment: Enrollment, professor_id: UUID) -> None:
        course = await self._get_course(enrollment.course_id)
        if course.professor_id != professor_id:
            raise HTTPException(status_code=403, detail="No tiene permisos sobre esta inscripción")

    # ── CRUD remisiones ──────────────────────────────────────────────────────

    async def create(
        self, enrollment_id: UUID, body: ReferralCreate, current_user: object
    ) -> ReferralRead:
        enrollment = await self._get_enrollment(enrollment_id)

        if current_user.role == RoleEnum.PROFESSOR:
            await self._check_professor_access(enrollment, current_user.id)
        elif current_user.role != RoleEnum.ADMIN:
            raise HTTPException(status_code=403, detail="Acceso denegado")

        referral = await self._repo.create({
            "enrollment_id":         enrollment_id,
            "created_by":            current_user.id,
            "referral_type":         body.referral_type.value,
            "referral_type_other":   body.referral_type_other,
            "observations":          body.observations,
            "referral_date":         body.referral_date,
            "attended":              "Sin confirmar",
            "status":                "PENDIENTE",
            "created_at":            datetime.now(timezone.utc),
            "updated_at":            datetime.now(timezone.utc),
        })

        # ── Notificaciones ACS (fire-and-forget, no bloquea la respuesta) ──
        try:
            course  = await self._get_course(enrollment.course_id)
            student = await self._get_user(enrollment.student_id)

            tipo_display = (
                body.tipo_remision_otro
                if body.tipo_remision.value == "Otros" and body.tipo_remision_otro
                else body.tipo_remision.value
            )

            if student:
                results = await notify_referral_created(
                    student_name=student.full_name,
                    student_email=student.email,
                    professor_name=getattr(current_user, "full_name", "Docente"),
                    course_name=f"{course.code} — {course.name}",
                    tipo_remision=tipo_display,
                    observaciones=body.observaciones or "Sin observaciones.",
                    fecha_remision=str(body.fecha_remision),
                )
                logger.info(
                    "Notificaciones remisión %s → estudiante=%s, consejería=%s",
                    referral.id,
                    results["student"],
                    results["consejeria"],
                )
        except Exception as exc:
            # Las notificaciones nunca deben bloquear la creación de la remisión
            logger.error("Error al enviar notificaciones ACS: %s", exc, exc_info=True)

        return ReferralRead.model_validate(referral)

    async def list_by_enrollment(
        self, enrollment_id: UUID, current_user: object
    ) -> list[ReferralRead]:
        enrollment = await self._get_enrollment(enrollment_id)

        if current_user.role == RoleEnum.STUDENT:
            if enrollment.student_id != current_user.id:
                raise HTTPException(status_code=403, detail="Acceso denegado")
        elif current_user.role == RoleEnum.PROFESSOR:
            await self._check_professor_access(enrollment, current_user.id)

        referrals = await self._repo.list_by_enrollment(enrollment_id)
        return [ReferralRead.model_validate(r) for r in referrals]

    async def list_by_course(
        self, course_id: UUID, current_user: object
    ) -> list[ReferralRead]:
        course = await self._get_course(course_id)

        if current_user.role == RoleEnum.PROFESSOR and course.professor_id != current_user.id:
            raise HTTPException(status_code=403, detail="Acceso denegado")

        referrals = await self._repo.list_by_course(course_id)
        return [ReferralRead.model_validate(r) for r in referrals]

    async def update(
        self, referral_id: UUID, body: ReferralUpdate, current_user: object
    ) -> ReferralRead:
        referral = await self._repo.get_by_id(referral_id)
        if referral is None:
            raise HTTPException(status_code=404, detail="Remisión no encontrada")

        if current_user.role == RoleEnum.PROFESSOR and referral.created_by != current_user.id:
            raise HTTPException(status_code=403, detail="Solo puede editar sus propias remisiones")
        elif current_user.role == RoleEnum.STUDENT:
            raise HTTPException(status_code=403, detail="Acceso denegado")

        fields = body.model_dump(exclude_unset=True)
        # Serializar enums a sus valores string para columnas VARCHAR
        if "attended" in fields and fields["attended"] is not None:
            fields["attended"] = fields["attended"].value if hasattr(fields["attended"], "value") else fields["attended"]
        if "status" in fields and fields["status"] is not None:
            fields["status"] = fields["status"].value if hasattr(fields["status"], "value") else fields["status"]
        updated = await self._repo.update(referral_id, fields)
        return ReferralRead.model_validate(updated)

    # ── Configuración de evaluación del curso ────────────────────────────────

    async def get_evaluation_config(
        self, course_id: UUID, current_user: object
    ) -> EvaluationConfigRead:
        course = await self._get_course(course_id)

        if current_user.role == RoleEnum.STUDENT:
            raise HTTPException(status_code=403, detail="Acceso denegado")

        cuts = (course.evaluation_config or {}).get("cuts", [])
        return EvaluationConfigRead(course_id=course_id, cuts=cuts)

    async def set_evaluation_config(
        self, course_id: UUID, body: EvaluationConfigUpdate, current_user: object
    ) -> EvaluationConfigRead:
        course = await self._get_course(course_id)

        if current_user.role == RoleEnum.PROFESSOR and course.professor_id != current_user.id:
            raise HTTPException(status_code=403, detail="Solo puede configurar sus propios cursos")
        elif current_user.role == RoleEnum.STUDENT:
            raise HTTPException(status_code=403, detail="Acceso denegado")

        cuts_data = [c.model_dump() for c in body.cuts]
        # Serialize evaluation_date to string for JSONB storage
        for cut in cuts_data:
            if cut.get("evaluation_date") is not None:
                cut["evaluation_date"] = str(cut["evaluation_date"])

        course.evaluation_config = {"cuts": cuts_data}
        self._session.add(course)
        await self._session.flush()
        await self._session.refresh(course)

        return EvaluationConfigRead(course_id=course_id, cuts=body.cuts)
