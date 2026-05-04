"""
EnrollmentRouter — endpoints CRUD para inscripciones de estudiantes en cursos.
Requisitos: 1.1, 1.9, 2.1, 2.7, 3.1, 3.4, 4.1, 4.3, 5.1, 5.3
"""

from uuid import UUID

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.enrollment import (
    EnrollmentCreate,
    EnrollmentRead,
    EnrollmentStatusUpdate,
    EnrollmentUpdate,
    GradesRead,
    GradesUpdate,
    RiskFromEnrollmentRequest,
)
from app.application.services.enrollment_service import EnrollmentService
from app.application.services.grade_service import (
    GradeService,
    extract_nota_parcial_1,
    extract_promedio_seguimiento,
)
from app.application.services.ml_service import MLApplicationService
from app.application.services.consent_service import ConsentService
from app.api.v1.dependencies.auth import (
    CurrentUser,
    get_current_user,
    require_roles,
    require_student_self_or_roles,
)
from app.domain.enums import EnrollmentStatusEnum, RoleEnum
from app.infrastructure.database import get_session
from app.infrastructure.repositories.consent_repository import ConsentRepository
from app.infrastructure.repositories.enrollment_repository import EnrollmentRepository
from app.schemas.student import PredictionOutput
from app.services.ml_service import AcademicRiskService, risk_service

router = APIRouter()


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------

def _get_enrollment_service(
    session: AsyncSession = Depends(get_session),
) -> EnrollmentService:
    repo = EnrollmentRepository(session)
    return EnrollmentService(repo, session)


def _get_grade_service(
    session: AsyncSession = Depends(get_session),
) -> GradeService:
    repo = EnrollmentRepository(session)
    return GradeService(repo, session)


def _get_ml_service() -> AcademicRiskService:
    return risk_service


def _get_ml_app_service(
    session: AsyncSession = Depends(get_session),
    ml: AcademicRiskService = Depends(_get_ml_service),
) -> MLApplicationService:
    consent_repo = ConsentRepository(session)
    return MLApplicationService(ml, ConsentService(consent_repo))


# ===========================================================================
# CRUD endpoints
# ===========================================================================

@router.post(
    "/enrollments",
    response_model=EnrollmentRead,
    status_code=201,
    summary="Inscribir un estudiante en un curso",
    description=(
        "Crea una nueva inscripción para un estudiante en un curso. "
        "Si ya existe una inscripción cancelada para la misma combinación "
        "(student_id, course_id), se reactiva en lugar de crear una nueva. "
        "Requiere rol ADMIN."
    ),
    tags=["Inscripciones"],
)
async def create_enrollment(
    body: EnrollmentCreate,
    current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN)),
    service: EnrollmentService = Depends(_get_enrollment_service),
) -> EnrollmentRead:
    return await service.create_enrollment(body, current_user.id)


@router.patch(
    "/enrollments/{enrollment_id}",
    response_model=EnrollmentRead,
    status_code=200,
    summary="Actualizar inscripción (cambio de curso)",
    description=(
        "Actualiza el curso de una inscripción existente. "
        "Valida que el curso destino exista, esté activo y que no exista "
        "una inscripción activa duplicada en el curso destino. "
        "Requiere rol ADMIN."
    ),
    tags=["Inscripciones"],
)
async def update_enrollment(
    enrollment_id: UUID,
    body: EnrollmentUpdate,
    current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN)),
    service: EnrollmentService = Depends(_get_enrollment_service),
) -> EnrollmentRead:
    return await service.update_enrollment(enrollment_id, body, current_user.id)


@router.patch(
    "/enrollments/{enrollment_id}/status",
    response_model=EnrollmentRead,
    status_code=200,
    summary="Actualizar estado de inscripción",
    description=(
        "Actualiza el estado de una inscripción a cualquier estado válido: "
        "PENDING, ACTIVE, COMPLETED o CANCELLED. "
        "El registro se preserva en la base de datos con el campo status actualizado. "
        "Requiere rol ADMIN."
    ),
    tags=["Inscripciones"],
)
async def update_enrollment_status(
    enrollment_id: UUID,
    body: EnrollmentStatusUpdate,
    current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN)),
    service: EnrollmentService = Depends(_get_enrollment_service),
) -> EnrollmentRead:
    return await service.update_enrollment_status(enrollment_id, body, current_user.id)


@router.get(
    "/enrollments/{enrollment_id}",
    response_model=EnrollmentRead,
    status_code=200,
    summary="Obtener detalle de una inscripción",
    description=(
        "Retorna los datos completos de una inscripción específica. "
        "Retorna 404 si la inscripción no existe. "
        "Requiere rol ADMIN."
    ),
    tags=["Inscripciones"],
)
async def get_enrollment(
    enrollment_id: UUID,
    current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN)),
    service: EnrollmentService = Depends(_get_enrollment_service),
) -> EnrollmentRead:
    return await service.get_enrollment(enrollment_id)


@router.get(
    "/students/{student_id}/enrollments",
    response_model=list[EnrollmentRead],
    status_code=200,
    summary="Listar inscripciones de un estudiante",
    description=(
        "Retorna la lista de inscripciones de un estudiante. "
        "Si el usuario autenticado es STUDENT, permite auto-acceso a sus propias inscripciones "
        "(retorna todos los estados para la vista de progreso). "
        "Si el usuario autenticado es PROFESSOR, solo retorna inscripciones "
        "en cursos asignados al profesor (RB-04). "
        "Acepta un query param opcional `status` para filtrar por estado de inscripción. "
        "Requiere rol STUDENT (auto-acceso), ADMIN o PROFESSOR."
    ),
    tags=["Inscripciones"],
)
async def list_student_enrollments(
    student_id: UUID,
    status: EnrollmentStatusEnum | None = Query(
        default=None, description="Filtrar por estado de inscripción"
    ),
    current_user: CurrentUser = Depends(require_student_self_or_roles),
    service: EnrollmentService = Depends(_get_enrollment_service),
) -> list[EnrollmentRead]:
    return await service.list_student_enrollments(student_id, current_user, status)


# ===========================================================================
# Grades & Risk endpoints
# ===========================================================================

@router.get(
    "/enrollments/{enrollment_id}/grades",
    response_model=GradesRead,
    status_code=200,
    summary="Consultar notas de una inscripción",
    description=(
        "Retorna las notas registradas para una inscripción junto con las notas "
        "calculadas por cohorte y la nota final. "
        "STUDENT: solo puede consultar sus propias inscripciones. "
        "PROFESSOR: solo puede consultar inscripciones en sus cursos (RB-04). "
        "ADMIN: acceso total."
    ),
    tags=["Inscripciones"],
)
async def get_enrollment_grades(
    enrollment_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: GradeService = Depends(_get_grade_service),
) -> GradesRead:
    return await service.get_grades(enrollment_id, current_user)


@router.put(
    "/enrollments/{enrollment_id}/grades",
    response_model=GradesRead,
    status_code=200,
    summary="Registrar / actualizar notas de una inscripción",
    description=(
        "Registra o reemplaza el JSON de notas de una inscripción y recalcula "
        "automáticamente las notas por cohorte y la nota final. "
        "La estructura del JSON debe incluir los cohortes con sus pesos y actividades. "
        "PROFESSOR: solo puede registrar notas en inscripciones de sus cursos. "
        "ADMIN: acceso total. "
        "STUDENT: sin acceso."
    ),
    tags=["Inscripciones"],
)
async def set_enrollment_grades(
    enrollment_id: UUID,
    body: GradesUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    service: GradeService = Depends(_get_grade_service),
) -> GradesRead:
    return await service.set_grades(enrollment_id, body.grades, current_user)


@router.post(
    "/enrollments/{enrollment_id}/risk",
    response_model=PredictionOutput,
    status_code=200,
    summary="Calcular riesgo académico desde las notas de la inscripción",
    description=(
        "Calcula el riesgo de reprobación del estudiante usando las notas registradas "
        "en la inscripción. El sistema extrae automáticamente `nota_parcial_1` y "
        "`promedio_seguimiento` del JSON de notas. El estudiante debe proveer "
        "`promedio_asistencia`, `inicios_sesion_plataforma` y `uso_tutorias`. "
        "Requiere consentimiento ML activo. "
        "STUDENT: solo puede calcular riesgo de sus propias inscripciones. "
        "PROFESSOR: solo puede calcular riesgo de estudiantes en sus cursos (RB-04). "
        "ADMIN: acceso total."
    ),
)
async def calculate_enrollment_risk(
    enrollment_id: UUID,
    body: RiskFromEnrollmentRequest,
    current_user: CurrentUser = Depends(get_current_user),
    grade_service: GradeService = Depends(_get_grade_service),
    ml: AcademicRiskService = Depends(_get_ml_service),
    ml_app: MLApplicationService = Depends(_get_ml_app_service),
) -> PredictionOutput:
    # 1. Obtener notas (también verifica acceso por rol)
    grades_data = await grade_service.get_grades(enrollment_id, current_user)

    if grades_data.grades is None:
        raise HTTPException(
            status_code=422,
            detail="No hay notas registradas para esta inscripción",
        )

    # 2. Extraer features desde el JSON de notas
    nota_parcial_1 = extract_nota_parcial_1(grades_data.grades)
    promedio_seguimiento = extract_promedio_seguimiento(grades_data.grades)

    feature_vector = [
        body.promedio_asistencia,
        promedio_seguimiento,
        nota_parcial_1,
        float(body.inicios_sesion_plataforma),
        float(body.uso_tutorias),
    ]

    datos_estudiante = {
        "promedio_asistencia": body.promedio_asistencia,
        "promedio_seguimiento": promedio_seguimiento,
        "nota_parcial_1": nota_parcial_1,
        "inicios_sesion_plataforma": body.inicios_sesion_plataforma,
        "uso_tutorias": body.uso_tutorias,
    }

    # 3. Predecir con verificación de consentimiento ML
    result = await ml_app.predict_with_consent_check(
        grades_data.student_id, feature_vector
    )
    probabilidad_riesgo = result["probability"]
    nivel_riesgo = result["risk_level"]
    features_scaled = np.array(result["scaled_features"])

    # 4. Construir respuesta completa
    analisis_ia = ml.generar_analisis_ia(datos_estudiante, probabilidad_riesgo)
    detalles_matematicos = ml.calcular_detalles_matematicos(features_scaled, probabilidad_riesgo)
    promedio_aprobados = ml.get_promedio_aprobados()

    return PredictionOutput(
        probabilidad_riesgo=probabilidad_riesgo,
        porcentaje_riesgo=probabilidad_riesgo * 100,
        nivel_riesgo=nivel_riesgo,
        analisis_ia=analisis_ia,
        datos_radar={
            "labels": ["Asistencia (%)", "Seguimiento", "Parcial 1", "Logins", "Tutorías"],
            "estudiante": [
                body.promedio_asistencia,
                promedio_seguimiento,
                nota_parcial_1,
                body.inicios_sesion_plataforma,
                body.uso_tutorias,
            ],
            "promedio_aprobado": [
                promedio_aprobados["promedio_asistencia"],
                promedio_aprobados["promedio_seguimiento"],
                promedio_aprobados["nota_parcial_1"],
                promedio_aprobados["inicios_sesion_plataforma"],
                promedio_aprobados["uso_tutorias"],
            ],
        },
        detalles_matematicos=detalles_matematicos,
    )
