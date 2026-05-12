"""
EnrollmentRouter — endpoints CRUD para inscripciones de estudiantes en cursos.
Requisitos: 1.1, 1.9, 2.1, 2.7, 3.1, 3.4, 4.1, 4.3, 5.1, 5.3
"""

from decimal import Decimal
from uuid import UUID

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.enrollment import (
    CourseGradesStructureRead,
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
    extract_cohort_attendance_percentage,
    extract_cohort_parcial,
    extract_cohort_seguimiento,
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
from app.infrastructure.models.student_profile import StudentProfile
from app.schemas.student import CohortRiskOutput, PredictionOutput
from app.services.ml_service import AcademicRiskService, risk_service


class StudentProfileRead(BaseModel):
    semester:         int     | None
    academic_year:    int     | None
    enrolled_credits: Decimal | None

    model_config = {"from_attributes": True}

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
    "/students/{student_id}/profile",
    response_model=StudentProfileRead,
    status_code=200,
    summary="Perfil académico de un estudiante",
    description=(
        "Retorna datos del perfil académico del estudiante (semestre, año académico, "
        "créditos matriculados). Retorna 404 si no existe perfil. "
        "STUDENT: solo su propio perfil. ADMIN/PROFESSOR: acceso amplio."
    ),
    tags=["Inscripciones"],
)
async def get_student_profile(
    student_id: UUID,
    current_user: CurrentUser = Depends(require_student_self_or_roles),
    session: AsyncSession = Depends(get_session),
) -> StudentProfileRead:
    result = await session.execute(
        select(StudentProfile).where(StudentProfile.user_id == student_id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Perfil académico no encontrado")
    return StudentProfileRead.model_validate(profile)


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
    "/courses/{course_id}/grades-structure",
    response_model=CourseGradesStructureRead,
    status_code=200,
    summary="Consultar estructura JSON de notas de un curso",
    description=(
        "Retorna la estructura completa del JSON de notas (grades) tomada de una "
        "inscripción del curso. Se usa para persistir y restaurar la distribución "
        "de cortes/actividades en frontend."
    ),
    tags=["Inscripciones"],
)
async def get_course_grades_structure(
    course_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),
    service: GradeService = Depends(_get_grade_service),
) -> CourseGradesStructureRead:
    grades = await service.get_course_grades_structure(course_id, current_user)
    return CourseGradesStructureRead(course_id=course_id, grades=grades)


@router.put(
    "/courses/{course_id}/grades-structure",
    response_model=CourseGradesStructureRead,
    status_code=200,
    summary="Guardar estructura JSON de notas en inscripciones del curso",
    description=(
        "Guarda la estructura completa del JSON de notas (grades) en la tabla "
        "`enrollments` para todas las inscripciones del curso."
    ),
    tags=["Inscripciones"],
)
async def set_course_grades_structure(
    course_id: UUID,
    body: GradesUpdate,
    current_user: CurrentUser = Depends(get_current_user),
    service: GradeService = Depends(_get_grade_service),
) -> CourseGradesStructureRead:
    await service.set_course_grades_structure(course_id, body.grades, current_user)
    return CourseGradesStructureRead(course_id=course_id, grades=body.grades)

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
        "Calcula el riesgo de reprobación del estudiante usando exclusivamente "
        "las notas por cohorte y la nota total calculadas en la inscripción. "
        "Requiere consentimiento ML activo. "
        "STUDENT: solo puede calcular riesgo de sus propias inscripciones. "
        "PROFESSOR: solo puede calcular riesgo de estudiantes en sus cursos (RB-04). "
        "ADMIN: acceso total."
    ),
)
async def calculate_enrollment_risk(
    enrollment_id: UUID,
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

    # 2. Extraer features desde columnas calculadas de la inscripción
    if (
        grades_data.first_cohort_grade is None
        or grades_data.second_cohort_grade is None
        or grades_data.third_cohort_grade is None
        or grades_data.final_grade is None
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Faltan notas por cohorte para calcular riesgo. "
                "Verifica que estén registrados corte 1, corte 2, corte final y total."
            ),
        )

    nota_corte_1 = float(grades_data.first_cohort_grade)
    nota_corte_2 = float(grades_data.second_cohort_grade)
    nota_corte_final = float(grades_data.third_cohort_grade)
    nota_total = float(grades_data.final_grade)

    feature_vector = [
        nota_corte_1,
        nota_corte_2,
        nota_corte_final,
        nota_total,
    ]

    datos_estudiante = {
        "nota_corte_1": nota_corte_1,
        "nota_corte_2": nota_corte_2,
        "nota_corte_final": nota_corte_final,
        "nota_total": nota_total,
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
            "labels": ["Corte 1", "Corte 2", "Corte final", "Total"],
            "estudiante": [
                nota_corte_1,
                nota_corte_2,
                nota_corte_final,
                nota_total,
            ],
            "promedio_aprobado": [
                promedio_aprobados["nota_corte_1"],
                promedio_aprobados["nota_corte_2"],
                promedio_aprobados["nota_corte_final"],
                promedio_aprobados["nota_total"],
            ],
        },
        detalles_matematicos=detalles_matematicos,
    )


@router.post(
    "/enrollments/{enrollment_id}/risk/cohort",
    response_model=CohortRiskOutput,
    status_code=200,
    summary="Calcular riesgo por cohorte desde notas de la inscripción",
    description=(
        "Calcula riesgo de un cohorte específico usando su parcial, promedio "
        "de seguimiento y asistencia del mismo cohorte. Requiere consentimiento ML activo."
    ),
)
async def calculate_enrollment_cohort_risk(
    enrollment_id: UUID,
    cohort_key: str = Query(
        ...,
        description="Cohorte a evaluar: first_cohort, second_cohort o third_cohort",
    ),
    current_user: CurrentUser = Depends(get_current_user),
    grade_service: GradeService = Depends(_get_grade_service),
    ml: AcademicRiskService = Depends(_get_ml_service),
    ml_app: MLApplicationService = Depends(_get_ml_app_service),
) -> CohortRiskOutput:
    grades_data = await grade_service.get_grades(enrollment_id, current_user)
    if grades_data.grades is None:
        raise HTTPException(
            status_code=422,
            detail="No hay notas registradas para esta inscripción",
        )

    nota_parcial = extract_cohort_parcial(grades_data.grades, cohort_key)
    promedio_seguimiento = extract_cohort_seguimiento(grades_data.grades, cohort_key)
    porcentaje_asistencia = extract_cohort_attendance_percentage(grades_data.grades, cohort_key)

    result = await ml_app.predict_cohort_with_consent_check(
        student_id=grades_data.student_id,
        cohort_key=cohort_key,
        nota_parcial=nota_parcial,
        promedio_seguimiento=promedio_seguimiento,
        porcentaje_asistencia=porcentaje_asistencia,
    )

    return CohortRiskOutput(
        cohort_key=result["cohort_key"],
        cohort_name=result["cohort_name"],
        probabilidad_riesgo=result["probability"],
        porcentaje_riesgo=result["probability"] * 100,
        nivel_riesgo=result["risk_level"],
        datos_cohorte={
            "nota_parcial": nota_parcial,
            "promedio_seguimiento": promedio_seguimiento,
            "porcentaje_asistencia": porcentaje_asistencia,
        },
        detalles_modelo=result["component_scores"],
    )
