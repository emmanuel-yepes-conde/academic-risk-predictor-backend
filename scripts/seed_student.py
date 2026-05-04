"""
Seed script — crea un estudiante completo listo para validar desde el frontend.

Crea (si no existen):
  1. Program    — Ingeniería de Sistemas
  2. Professor  — Docente asignado al curso
  3. Course     — CALC-01 Pre-cálculo (vinculado al programa y al docente)
  4. Student    — Usuario con rol STUDENT
  5. StudentProfile — Perfil académico del estudiante
  6. Enrollment — Inscripción activa en el curso con notas completas
  7. Consent    — Consentimiento ML aceptado (requerido para /risk)

Uso:
    python3 -m scripts.seed_student

El script es idempotente: si alguna entidad ya existe por email/código, la omite.
"""

import asyncio
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select

from app.core.security import hash_password
from app.domain.enums import CourseStatusEnum, EnrollmentStatusEnum, RoleEnum, UserStatusEnum
from app.infrastructure.database import AsyncSessionFactory, engine
from app.infrastructure.models.consent import Consent
from app.infrastructure.models.course import Course
from app.infrastructure.models.enrollment import Enrollment
from app.infrastructure.models.program import Program
from app.infrastructure.models.student_profile import StudentProfile
from app.infrastructure.models.user import User

# ---------------------------------------------------------------------------
# Datos del seed
# ---------------------------------------------------------------------------

PROGRAM = {
    "institution": "USBCO",
    "degree_type": "PREG",
    "program_code": "S0100",
    "program_name": "Ingeniería de Sistemas",
    "location": "SEDE PRINCIPAL",
    "snies_code": 9999,
}

PROFESSOR = {
    "email": "camila.perez@universidad.edu",
    "full_name": "Camila Perez",
    "role": RoleEnum.PROFESSOR,
    "status": UserStatusEnum.ACTIVE,
    "password": "Professor123!",
}

COURSE = {
    "code": "CALC-01",
    "name": "Pre-cálculo",
    "credits": 3,
    "academic_period": "2026-1",
    "status": CourseStatusEnum.ACTIVE,
}

STUDENT = {
    "email": "estudiante@universidad.edu",
    "full_name": "Juan Pérez García",
    "role": RoleEnum.STUDENT,
    "status": UserStatusEnum.ACTIVE,
    "password": "Student123!",
}

STUDENT_PROFILE = {
    "student_institutional_id": "30001234567",
    "document_type": "CC",
    "document_number": "1234567890",
    "birth_date": date(2002, 5, 15),
    "gender": "M",
    "phone": "3101234567",
    "socioeconomic_stratum": 3,
    "academic_cycle": 1,
    "academic_year": 2026,
    "semester": 1,
    "program_action": "RLOA",
    "enrollment_status": "AC",
    "enrolled_credits": Decimal("12"),
    "academic_level": 1,
    "cohort": "2026-1",
}

# Notas completas: 3 cohortes con parcial y seguimiento.
# Los pesos suman 100% en total (30 + 30 + 40).
GRADES = {
    "first_cohort": {
        "weight": "30%",
        "parcial": {"note": 3.8, "weight": "15%"},
        "seguimiento": {
            "taller_1":      {"note": 4.2, "weight": "5%"},
            "quiz_1":        {"note": 3.9, "weight": "5%"},
            "laboratorio_1": {"note": 4.5, "weight": "5%"},
        },
    },
    "second_cohort": {
        "weight": "30%",
        "parcial": {"note": 3.5, "weight": "15%"},
        "seguimiento": {
            "taller_2":        {"note": 4.0, "weight": "10%"},
            "proyecto_parcial": {"note": 3.7, "weight": "5%"},
        },
    },
    "third_cohort": {
        "weight": "40%",
        "parcial": {"note": 3.2, "weight": "20%"},
        "seguimiento": {
            "proyecto_final": {"note": 4.1, "weight": "12%"},
            "sustentacion":   {"note": 3.8, "weight": "8%"},
        },
    },
}

# Columnas calculadas (precomputadas para coherencia):
# first_cohort_grade  = (3.8*15 + 4.2*5 + 3.9*5 + 4.5*5) / 30 = 4.00
# second_cohort_grade = (3.5*15 + 4.0*10 + 3.7*5) / 30        = 3.70
# third_cohort_grade  = (3.2*20 + 4.1*12 + 3.8*8) / 40        = 3.59
# final_grade         = 4.00*0.30 + 3.70*0.30 + 3.59*0.40     = 3.75
FIRST_COHORT_GRADE  = Decimal("4.00")
SECOND_COHORT_GRADE = Decimal("3.70")
THIRD_COHORT_GRADE  = Decimal("3.59")
FINAL_GRADE         = Decimal("3.75")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.utcnow()


async def _get_or_create_program(session) -> Program:
    result = await session.execute(
        select(Program).where(Program.program_code == PROGRAM["program_code"])
    )
    existing = result.scalar_one_or_none()
    if existing:
        print(f"  ✓ Program ya existe: {existing.program_name}")
        return existing

    program = Program(**PROGRAM)
    session.add(program)
    await session.flush()
    await session.refresh(program)
    print(f"  + Program creado: {program.program_name}")
    return program


async def _get_or_create_professor(session) -> User:
    result = await session.execute(
        select(User).where(User.email == PROFESSOR["email"])
    )
    existing = result.scalar_one_or_none()
    if existing:
        print(f"  ✓ Professor ya existe: {existing.full_name}")
        return existing

    professor = User(
        email=PROFESSOR["email"],
        full_name=PROFESSOR["full_name"],
        role=PROFESSOR["role"],
        status=PROFESSOR["status"],
        password_hash=hash_password(PROFESSOR["password"]),
    )
    session.add(professor)
    await session.flush()
    await session.refresh(professor)
    print(f"  + Professor creado: {professor.full_name}")
    return professor


async def _get_or_create_course(session, program: Program, professor: User) -> Course:
    result = await session.execute(
        select(Course).where(Course.code == COURSE["code"])
    )
    existing = result.scalar_one_or_none()
    if existing:
        print(f"  ✓ Course ya existe: {existing.name}")
        return existing

    course = Course(
        **COURSE,
        program_id=program.id,
        professor_id=professor.id,
    )
    session.add(course)
    await session.flush()
    await session.refresh(course)
    print(f"  + Course creado: {course.name} ({course.code})")
    return course


async def _get_or_create_student(session) -> User:
    result = await session.execute(
        select(User).where(User.email == STUDENT["email"])
    )
    existing = result.scalar_one_or_none()
    if existing:
        print(f"  ✓ Student ya existe: {existing.full_name}")
        return existing

    student = User(
        email=STUDENT["email"],
        full_name=STUDENT["full_name"],
        role=STUDENT["role"],
        status=STUDENT["status"],
        password_hash=hash_password(STUDENT["password"]),
    )
    session.add(student)
    await session.flush()
    await session.refresh(student)
    print(f"  + Student creado: {student.full_name}")
    return student


async def _get_or_create_profile(session, student: User, program: Program) -> StudentProfile:
    result = await session.execute(
        select(StudentProfile).where(StudentProfile.user_id == student.id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        print(f"  ✓ StudentProfile ya existe: {existing.student_institutional_id}")
        return existing

    profile = StudentProfile(
        **STUDENT_PROFILE,
        user_id=student.id,
        program_id=program.id,
    )
    session.add(profile)
    await session.flush()
    await session.refresh(profile)
    print(f"  + StudentProfile creado: {profile.student_institutional_id}")
    return profile


async def _get_or_create_enrollment(session, student: User, course: Course) -> Enrollment:
    result = await session.execute(
        select(Enrollment).where(
            Enrollment.student_id == student.id,
            Enrollment.course_id == course.id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        print(f"  ✓ Enrollment ya existe (id: {existing.id})")
        # Actualizar notas si aún no las tiene
        if existing.grades is None:
            existing.grades = GRADES
            existing.first_cohort_grade  = FIRST_COHORT_GRADE
            existing.second_cohort_grade = SECOND_COHORT_GRADE
            existing.third_cohort_grade  = THIRD_COHORT_GRADE
            existing.final_grade         = FINAL_GRADE
            session.add(existing)
            await session.flush()
            await session.refresh(existing)
            print("  + Notas añadidas al enrollment existente")
        return existing

    enrollment = Enrollment(
        student_id=student.id,
        course_id=course.id,
        status=EnrollmentStatusEnum.ACTIVE,
        grades=GRADES,
        first_cohort_grade=FIRST_COHORT_GRADE,
        second_cohort_grade=SECOND_COHORT_GRADE,
        third_cohort_grade=THIRD_COHORT_GRADE,
        final_grade=FINAL_GRADE,
    )
    session.add(enrollment)
    await session.flush()
    await session.refresh(enrollment)
    print(f"  + Enrollment creado con notas (nota final: {FINAL_GRADE})")
    return enrollment


async def _get_or_create_consent(session, student: User) -> Consent:
    result = await session.execute(
        select(Consent).where(Consent.student_id == student.id)
    )
    existing = result.scalar_one_or_none()
    if existing:
        print(f"  ✓ Consent ya existe (accepted={existing.accepted})")
        return existing

    consent = Consent(
        student_id=student.id,
        accepted=True,
        terms_version="1.0",
        accepted_at=_now(),
    )
    session.add(consent)
    await session.flush()
    await session.refresh(consent)
    print("  + Consent ML creado (accepted=True)")
    return consent


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def seed() -> None:
    async with AsyncSessionFactory() as session:
        print("\n[1/7] Program...")
        program = await _get_or_create_program(session)

        print("[2/7] Professor...")
        professor = await _get_or_create_professor(session)

        print("[3/7] Course...")
        course = await _get_or_create_course(session, program, professor)

        print("[4/7] Student...")
        student = await _get_or_create_student(session)

        print("[5/7] StudentProfile...")
        await _get_or_create_profile(session, student, program)

        print("[6/7] Enrollment + Grades...")
        enrollment = await _get_or_create_enrollment(session, student, course)

        print("[7/7] Consent ML...")
        await _get_or_create_consent(session, student)

        await session.commit()

        print("\n" + "=" * 55)
        print("  SEED COMPLETADO — Credenciales de acceso")
        print("=" * 55)
        print(f"\n  ESTUDIANTE")
        print(f"    Email:    {STUDENT['email']}")
        print(f"    Password: {STUDENT['password']}")
        print(f"    Role:     STUDENT")
        print(f"\n  DOCENTE")
        print(f"    Email:    {PROFESSOR['email']}")
        print(f"    Password: {PROFESSOR['password']}")
        print(f"    Role:     PROFESSOR")
        print(f"\n  CURSO")
        print(f"    Código:   {COURSE['code']}")
        print(f"    Nombre:   {COURSE['name']}")
        print(f"    Período:  {COURSE['academic_period']}")
        print(f"\n  NOTAS DEL ESTUDIANTE")
        print(f"    Cohorte 1: {FIRST_COHORT_GRADE} / 5.0")
        print(f"    Cohorte 2: {SECOND_COHORT_GRADE} / 5.0")
        print(f"    Cohorte 3: {THIRD_COHORT_GRADE} / 5.0")
        print(f"    Final:     {FINAL_GRADE} / 5.0  (aprobado ✓)")
        print(f"\n  ENROLLMENT ID")
        print(f"    {enrollment.id}")
        print(f"\n  ENDPOINTS PARA VALIDAR")
        print(f"    GET  /enrollments/{enrollment.id}/grades")
        print(f"    POST /enrollments/{enrollment.id}/risk")
        print("=" * 55 + "\n")


async def main() -> None:
    try:
        await seed()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
