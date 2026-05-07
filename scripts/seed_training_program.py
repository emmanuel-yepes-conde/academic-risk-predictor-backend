#!/usr/bin/env python3
"""
Seed masivo para entrenamiento ML:
- Crea un programa completo (semestres 1..5)
- Crea docentes, materias, secciones y estudiantes
- Crea matrículas con grades JSONB (parcial + seguimiento + asistencia)
- Exporta dataset de entrenamiento a datasets/dataset_estudiantes_decimal.csv

Uso:
    python3 -m scripts.seed_training_program
"""

from __future__ import annotations

import asyncio
import csv
import random
import uuid
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.application.services.grade_service import (
    _calculate_cohort_grade,
    _calculate_final_grade,
)
from app.core.security import hash_password
from app.domain.enums import CourseStatusEnum, EnrollmentStatusEnum, RoleEnum, UserStatusEnum
from app.infrastructure.database import AsyncSessionFactory, engine
from app.infrastructure.models.consent import Consent
from app.infrastructure.models.course import Course
from app.infrastructure.models.enrollment import Enrollment
from app.infrastructure.models.program import Program
from app.infrastructure.models.student_profile import StudentProfile
from app.infrastructure.models.subject import Subject
from app.infrastructure.models.user import User


ROOT = Path(__file__).resolve().parent.parent
DATASET_PATH = ROOT / "datasets" / "dataset_estudiantes_decimal.csv"

SEED_TAG = "seedtrain.local"
RANDOM_SEED = 42
PASSWORD = "Demo123!"

PROGRAM_DEF = {
    "institution": "USBCO",
    "degree_type": "PREG",
    "program_code": "S0500",
    "program_name": "Ingeniería de Sistemas (Seed Entrenamiento)",
    "location": "SAN BENITO",
    "snies_code": 950500,
}

SEMESTER_PERIOD = {
    1: "2024-1",
    2: "2024-2",
    3: "2025-1",
    4: "2025-2",
    5: "2026-1",
}

# (code, name, credits)
SUBJECTS_BY_SEMESTER: dict[int, list[tuple[str, str, int]]] = {
    1: [
        ("MAT101", "Cálculo I", 4),
        ("PRG101", "Programación I", 4),
        ("ALG101", "Álgebra Lineal", 3),
        ("LOG101", "Lógica Matemática", 3),
        ("COM101", "Comunicación Académica", 2),
    ],
    2: [
        ("MAT201", "Cálculo II", 4),
        ("PRG201", "Programación II", 4),
        ("EST201", "Estadística", 3),
        ("BDD201", "Bases de Datos I", 3),
        ("FIS201", "Física I", 3),
    ],
    3: [
        ("EDA301", "Estructuras de Datos", 4),
        ("SO301", "Sistemas Operativos", 3),
        ("BDD301", "Bases de Datos II", 3),
        ("FIS301", "Física II", 3),
        ("ING301", "Inglés Técnico I", 2),
    ],
    4: [
        ("ARQ401", "Arquitectura de Software", 3),
        ("RED401", "Redes", 3),
        ("WEB401", "Desarrollo Web", 4),
        ("IA401", "Introducción a IA", 3),
        ("ING401", "Inglés Técnico II", 2),
    ],
    5: [
        ("ML501", "Aprendizaje Automático", 4),
        ("NUBE501", "Cloud Computing", 3),
        ("SEG501", "Seguridad Informática", 3),
        ("PROY501", "Proyecto Integrador I", 4),
        ("ETI501", "Ética Profesional", 2),
    ],
}

PROFESSORS = [
    ("andres.rios", "Andrés Ríos"),
    ("camila.perez", "Camila Pérez"),
    ("laura.giraldo", "Laura Giraldo"),
    ("daniel.suarez", "Daniel Suárez"),
    ("maria.gomez", "María Gómez"),
    ("juan.marin", "Juan Marín"),
]

STUDENTS_PER_SEMESTER = {1: 30, 2: 28, 3: 26, 4: 24, 5: 22}


@dataclass
class TrainingRow:
    nota_corte_1: float
    nota_corte_2: float
    nota_corte_final: float
    nota_total: float
    riesgo_reprobacion: int


def _pick_profile(semester: int) -> str:
    # Distribución simple: semestres altos tienden más a estabilidad.
    base = random.random()
    if semester <= 2:
        if base < 0.30:
            return "high"
        if base < 0.70:
            return "medium"
        return "low"
    if semester <= 4:
        if base < 0.20:
            return "high"
        if base < 0.60:
            return "medium"
        return "low"
    if base < 0.15:
        return "high"
    if base < 0.50:
        return "medium"
    return "low"


def _rand_note(profile: str) -> float:
    if profile == "low":
        return round(random.uniform(4.0, 5.0), 1)
    if profile == "medium":
        return round(random.uniform(3.0, 4.0), 1)
    return round(random.uniform(1.5, 3.2), 1)


def _attendance_counter(profile: str) -> dict[str, int]:
    total = random.randint(18, 26)
    if profile == "low":
        assist = random.randint(int(total * 0.82), total)
    elif profile == "medium":
        assist = random.randint(int(total * 0.65), int(total * 0.82))
    else:
        assist = random.randint(int(total * 0.35), int(total * 0.65))
    return {"assist": assist, "not_asist": total - assist}


def _cohort_block(
    profile: str,
    cohort_name: str,
    cohort_weight: str,
    parcial_label: str,
    act_a: str,
    act_b: str,
) -> dict:
    att = _attendance_counter(profile)
    return {
        "name": cohort_name,
        "weight": cohort_weight,
        "attendance": att,
        # Parcial/final activity tiene mayor peso dentro del cohorte.
        "parcial": {
            "id": f"{cohort_name.lower().replace(' ', '_')}_parcial",
            "name": parcial_label,
            "note": _rand_note(profile),
            "weight": "70%",
        },
        "seguimiento": {
            f"{cohort_name.lower().replace(' ', '_')}_act_a": {
                "id": f"{cohort_name.lower().replace(' ', '_')}_act_a",
                "name": act_a,
                "note": _rand_note(profile),
                "weight": "15%",
            },
            f"{cohort_name.lower().replace(' ', '_')}_act_b": {
                "id": f"{cohort_name.lower().replace(' ', '_')}_act_b",
                "name": act_b,
                "note": _rand_note(profile),
                "weight": "15%",
            },
        },
    }


def _build_grades(profile: str) -> dict:
    return {
        "first_cohort": _cohort_block(
            profile, "Corte 1", "30%", "Parcial 1", "Taller 1", "Quiz 1"
        ),
        "second_cohort": _cohort_block(
            profile, "Corte 2", "30%", "Parcial 2", "Laboratorio", "Proyecto Parcial"
        ),
        "third_cohort": _cohort_block(
            profile, "Corte Final", "40%", "Actividad Final", "Sustentación", "Proyecto Final"
        ),
    }


def _extract_training_row(
    *,
    first_grade: float | None,
    second_grade: float | None,
    third_grade: float | None,
    final_grade: float | None,
) -> TrainingRow:
    c1 = round(float(first_grade or 0.0), 2)
    c2 = round(float(second_grade or 0.0), 2)
    c3 = round(float(third_grade or 0.0), 2)
    total = round(float(final_grade or 0.0), 2)

    risk = 1 if total < 3.0 else 0

    return TrainingRow(
        nota_corte_1=c1,
        nota_corte_2=c2,
        nota_corte_final=c3,
        nota_total=total,
        riesgo_reprobacion=risk,
    )


async def _get_or_create_program(session) -> Program:
    result = await session.execute(
        select(Program).where(Program.program_code == PROGRAM_DEF["program_code"])
    )
    program = result.scalar_one_or_none()
    if program:
        return program
    program = Program(**PROGRAM_DEF)
    session.add(program)
    await session.flush()
    await session.refresh(program)
    return program


async def _upsert_professors(session) -> list[User]:
    profs: list[User] = []
    for username, full_name in PROFESSORS:
        email = f"{username}@{SEED_TAG}"
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                email=email,
                full_name=full_name,
                role=RoleEnum.PROFESSOR,
                status=UserStatusEnum.ACTIVE,
                password_hash=hash_password(PASSWORD),
                ml_consent=True,
            )
            session.add(user)
            await session.flush()
            await session.refresh(user)
        profs.append(user)
    return profs


async def _upsert_subjects_and_courses(session, program: Program, professors: list[User]) -> dict[int, list[Course]]:
    courses_by_sem: dict[int, list[Course]] = {}
    prof_idx = 0
    for semester, subjects in SUBJECTS_BY_SEMESTER.items():
        sem_courses: list[Course] = []
        for code, name, credits in subjects:
            subject_code = f"{code}-S{semester}"
            result = await session.execute(
                select(Subject).where(
                    Subject.code == subject_code,
                    Subject.program_id == program.id,
                )
            )
            subject = result.scalar_one_or_none()
            if subject is None:
                subject = Subject(
                    code=subject_code,
                    name=name,
                    credits=credits,
                    program_id=program.id,
                    status=CourseStatusEnum.ACTIVE,
                )
                session.add(subject)
                await session.flush()
                await session.refresh(subject)

            period = SEMESTER_PERIOD[semester]
            result = await session.execute(
                select(Course).where(
                    Course.subject_id == subject.id,
                    Course.section == "A",
                    Course.academic_period == period,
                )
            )
            course = result.scalar_one_or_none()
            if course is None:
                course = Course(
                    subject_id=subject.id,
                    section="A",
                    academic_period=period,
                    professor_id=professors[prof_idx % len(professors)].id,
                    status=CourseStatusEnum.ACTIVE,
                )
                session.add(course)
                await session.flush()
                await session.refresh(course)
            sem_courses.append(course)
            prof_idx += 1
        courses_by_sem[semester] = sem_courses
    return courses_by_sem


async def _cleanup_old_seed_students(session) -> None:
    res = await session.execute(
        select(User).where(User.email.like(f"%@{SEED_TAG}"), User.role == RoleEnum.STUDENT)
    )
    students = list(res.scalars().all())
    for stu in students:
        enr = await session.execute(select(Enrollment).where(Enrollment.student_id == stu.id))
        for e in enr.scalars().all():
            await session.delete(e)
        con = await session.execute(select(Consent).where(Consent.student_id == stu.id))
        c = con.scalar_one_or_none()
        if c:
            await session.delete(c)
        prof = await session.execute(select(StudentProfile).where(StudentProfile.user_id == stu.id))
        p = prof.scalar_one_or_none()
        if p:
            await session.delete(p)
        await session.delete(stu)
    await session.flush()


async def seed() -> None:
    random.seed(RANDOM_SEED)
    dataset_rows: list[TrainingRow] = []

    async with AsyncSessionFactory() as session:
        async with session.begin():
            await _cleanup_old_seed_students(session)
            program = await _get_or_create_program(session)
            professors = await _upsert_professors(session)
            courses_by_sem = await _upsert_subjects_and_courses(session, program, professors)

            student_seq = 1
            for semester, count in STUDENTS_PER_SEMESTER.items():
                for i in range(count):
                    email = f"est{semester:01d}{student_seq:03d}@{SEED_TAG}"
                    full_name = f"Estudiante Sem{semester} #{i + 1:02d}"
                    user = User(
                        email=email,
                        institutional_email=f"{semester:01d}{student_seq:04d}@usb.edu.co",
                        full_name=full_name,
                        role=RoleEnum.STUDENT,
                        status=UserStatusEnum.ACTIVE,
                        password_hash=hash_password(PASSWORD),
                        ml_consent=True,
                    )
                    session.add(user)
                    await session.flush()
                    await session.refresh(user)

                    profile = StudentProfile(
                        user_id=user.id,
                        student_institutional_id=f"30{semester:01d}{student_seq:05d}",
                        document_type="CC",
                        document_number=f"10{semester:01d}{student_seq:07d}",
                        gender=random.choice(["M", "F"]),
                        socioeconomic_stratum=random.randint(1, 6),
                        academic_cycle=semester,
                        academic_year=int(SEMESTER_PERIOD[semester].split("-")[0]),
                        semester=semester,
                        program_action="RLOA",
                        enrollment_status="AC",
                        enrolled_credits=Decimal(str(random.choice([16, 17, 18, 19]))),
                        academic_level=semester,
                        cohort=f"{SEMESTER_PERIOD[1]}",
                        program_id=program.id,
                    )
                    session.add(profile)

                    consent = Consent(
                        student_id=user.id,
                        accepted=True,
                        terms_version="v2.0-seed-training",
                    )
                    session.add(consent)

                    # Inscribe al estudiante en todos los semestres cursados hasta su nivel actual.
                    for sem in range(1, semester + 1):
                        profile_type = _pick_profile(semester)
                        for course in courses_by_sem[sem]:
                            grades = _build_grades(profile_type)
                            first = _calculate_cohort_grade(grades["first_cohort"])
                            second = _calculate_cohort_grade(grades["second_cohort"])
                            third = _calculate_cohort_grade(grades["third_cohort"])
                            final = _calculate_final_grade(grades)
                            enrollment = Enrollment(
                                student_id=user.id,
                                course_id=course.id,
                                status=(
                                    EnrollmentStatusEnum.ACTIVE
                                    if sem == semester
                                    else EnrollmentStatusEnum.COMPLETED
                                ),
                                grades=grades,
                                first_cohort_grade=Decimal(str(first)) if first is not None else None,
                                second_cohort_grade=Decimal(str(second)) if second is not None else None,
                                third_cohort_grade=Decimal(str(third)) if third is not None else None,
                                final_grade=Decimal(str(final)) if final is not None else None,
                            )
                            session.add(enrollment)

                            # Dataset: una fila por inscripción.
                            dataset_rows.append(
                                _extract_training_row(
                                    first_grade=first,
                                    second_grade=second,
                                    third_grade=third,
                                    final_grade=final,
                                )
                            )
                    student_seq += 1

    DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
    with DATASET_PATH.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "nota_corte_1",
                "nota_corte_2",
                "nota_corte_final",
                "nota_total",
                "riesgo_reprobacion",
            ]
        )
        for row in dataset_rows:
            writer.writerow(
                [
                    row.nota_corte_1,
                    row.nota_corte_2,
                    row.nota_corte_final,
                    row.nota_total,
                    row.riesgo_reprobacion,
                ]
            )

    print("Seed completado.")
    print(f"- Programa: {PROGRAM_DEF['program_name']}")
    print(f"- Estudiantes creados: {sum(STUDENTS_PER_SEMESTER.values())}")
    print(f"- Filas dataset: {len(dataset_rows)}")
    print(f"- Dataset exportado: {DATASET_PATH}")
    print(f"- Password seed users: {PASSWORD}")


async def main() -> None:
    try:
        await seed()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
