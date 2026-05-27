#!/usr/bin/env python3
"""
Seed masivo — 50 000 estudiantes con escenarios realistas de vida universitaria.

Genera:
  - 1 administrador
  - 1 programa (Ingeniería de Sistemas, USBCO)
  - 25 materias (5 por nivel semestral 1-5)
  - 5 profesores
  - 500 cursos (25 materias × 5 períodos × 4 secciones)
  - 50 000 estudiantes con StudentProfile y Consent
  - ~750 000 inscripciones con notas JSONB y notas calculadas
  - Sesiones de clase (todos los cursos) + asistencias individuales (2026-1)
  - Remisiones para estudiantes en riesgo de períodos recientes

Archetypes de estudiante:
  genius          5%  — siempre alta, alta asistencia
  good           15%  — buenas notas, buena asistencia
  average        30%  — notas medias, asistencia media
  barely_passing 10%  — roza el 3.0
  ghost_passer    8%  — no va a clase pero aprueba
  attend_failer   7%  — asiste pero reprueba
  burnout         5%  — empieza bien, termina mal
  late_bloomer    5%  — empieza mal, mejora
  chronic_failer 10%  — reprueba consistentemente
  dropout         5%  — cancela la inscripción

Períodos: 2024-1, 2024-2, 2025-1, 2025-2, 2026-1

Uso:
    python3 -m scripts.seed_massive

⚠️  Ejecutar scripts/reset_db.py antes si la BD tiene datos.
"""

from __future__ import annotations

import asyncio
import random
import secrets
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import insert, select, or_

from app.application.services.grade_service import (
    _calculate_cohort_grade,
    _calculate_final_grade,
)
from app.core.security import hash_password
from app.domain.enums import (
    AsistioEnum,
    CourseStatusEnum,
    EnrollmentStatusEnum,
    ReferralStatusEnum,
    ReferralTypeEnum,
    RoleEnum,
    UserStatusEnum,
)
from app.infrastructure.database import AsyncSessionFactory, engine
from app.infrastructure.models.attendance import Attendance, ClassSession
from app.infrastructure.models.consent import Consent
from app.infrastructure.models.course import Course
from app.infrastructure.models.enrollment import Enrollment
from app.infrastructure.models.program import Program
from app.infrastructure.models.referral import Referral
from app.infrastructure.models.student_profile import StudentProfile
from app.infrastructure.models.subject import Subject
from app.infrastructure.models.user import User

# ─── Configuración ──────────────────────────────────────────────────────────────

RANDOM_SEED = 2024
ADMIN_PASSWORD = "Admin123!"
STUDENT_PASSWORD = "Demo123!"
STUDENTS_PER_COHORT = 10_000  # 5 cohortes × 10 000 = 50 000
SECTIONS = ["A", "B", "C", "D"]
BATCH_SIZE = 2_000
SUB_BATCH_STUDENTS = 1_000  # flusha cada N estudiantes por cohorte

PERIODS_IN_ORDER = ["2024-1", "2024-2", "2025-1", "2025-2", "2026-1"]
CURRENT_PERIOD = "2026-1"

PERIOD_EVAL_DATES: dict[str, dict[str, str]] = {
    "2024-1": {"c1": "2024-03-15", "c2": "2024-04-26", "c3": "2024-06-07"},
    "2024-2": {"c1": "2024-09-20", "c2": "2024-10-25", "c3": "2024-11-29"},
    "2025-1": {"c1": "2025-03-14", "c2": "2025-04-25", "c3": "2025-06-06"},
    "2025-2": {"c1": "2025-09-19", "c2": "2025-10-24", "c3": "2025-11-28"},
    "2026-1": {"c1": "2026-03-20", "c2": "2026-04-24", "c3": "2026-06-05"},
}

PERIOD_START: dict[str, date] = {
    "2024-1": date(2024, 1, 20),
    "2024-2": date(2024, 7, 20),
    "2025-1": date(2025, 1, 19),
    "2025-2": date(2025, 7, 20),
    "2026-1": date(2026, 1, 18),
}

# ─── Programa y materias ────────────────────────────────────────────────────────

PROGRAM = {
    "institution": "USBCO",
    "degree_type": "PREG",
    "program_code": "M0200",
    "program_name": "Ingeniería de Sistemas",
    "location": "SAN BENITO",
    "snies_code": 1361,
}

SUBJECTS_BY_LEVEL: dict[int, list[tuple[str, str, int]]] = {
    1: [
        ("MAT101", "Cálculo Diferencial", 4),
        ("PRG101", "Programación I", 4),
        ("ALG101", "Álgebra Lineal", 3),
        ("LOG101", "Lógica Matemática", 3),
        ("COM101", "Comunicación Académica", 2),
    ],
    2: [
        ("MAT201", "Cálculo Integral", 4),
        ("PRG201", "Programación II", 4),
        ("EST201", "Estadística Descriptiva", 3),
        ("BDD201", "Bases de Datos I", 3),
        ("FIS201", "Física I", 3),
    ],
    3: [
        ("EDA301", "Estructuras de Datos", 4),
        ("SO301",  "Sistemas Operativos", 3),
        ("BDD301", "Bases de Datos II", 3),
        ("FIS301", "Física II", 3),
        ("ING301", "Inglés Técnico I", 2),
    ],
    4: [
        ("ARQ401", "Arquitectura de Software", 3),
        ("RED401", "Redes de Computadores", 3),
        ("WEB401", "Desarrollo Web", 4),
        ("IA401",  "Introducción a IA", 3),
        ("ING401", "Inglés Técnico II", 2),
    ],
    5: [
        ("ML501",   "Aprendizaje Automático", 4),
        ("NUBE501", "Cloud Computing", 3),
        ("SEG501",  "Seguridad Informática", 3),
        ("PROY501", "Proyecto Integrador", 4),
        ("ETI501",  "Ética Profesional", 2),
    ],
}

# ─── Profesores ─────────────────────────────────────────────────────────────────

PROFESSORS_DATA = [
    ("prof.andres.rios@usbco.edu.co",    "Andrés Ríos Montoya",    "3001234567"),
    ("prof.camila.perez@usbco.edu.co",   "Camila Pérez Gómez",     "3012345678"),
    ("prof.laura.giraldo@usbco.edu.co",  "Laura Giraldo Ospina",   "3023456789"),
    ("prof.daniel.suarez@usbco.edu.co",  "Daniel Suárez Vargas",   "3034567890"),
    ("prof.maria.gomez@usbco.edu.co",    "María Gómez Cardona",    "3045678901"),
]

# ─── Nombres colombianos ────────────────────────────────────────────────────────

NOMBRES_M = [
    "Andrés","Carlos","Daniel","Diego","Felipe","Gabriel","Iván","Jorge","Juan",
    "Luis","Mauricio","Miguel","Nicolás","Pablo","Ricardo","Santiago","Sebastián",
    "Sergio","Tomás","Víctor","Alejandro","Christian","David","Edwin","Fabián",
    "Gustavo","Harold","Jaime","Kevin","Leonardo",
]
NOMBRES_F = [
    "Alejandra","Andrea","Camila","Carolina","Daniela","Diana","Elena","Fernanda",
    "Isabella","Jennifer","Karen","Laura","Luisa","María","Natalia","Paola","Paula",
    "Sara","Sofía","Valentina","Viviana","Adriana","Claudia","Gloria","Juliana",
    "Katherine","Lorena","Monica","Patricia","Sandra",
]
APELLIDOS = [
    "García","Martínez","López","González","Rodríguez","Hernández","Pérez","Sánchez",
    "Ramírez","Torres","Flores","Rivera","Gómez","Díaz","Cruz","Morales","Ortiz",
    "Gutiérrez","Vargas","Reyes","Castillo","Moreno","Jiménez","Ruiz","Vásquez",
    "Medina","Rojas","Castro","Suárez","Ramos","Ospina","Cardona","Aguilar",
    "Salazar","Estrada","Pardo","Ríos","Cortés","Molina","Acosta","Bermúdez",
    "Castaño","Dueñas","Fonseca","Herrera","Ibáñez","Lozano","Nieto","Quintero",
]
TIPOS_DOC = ["CC","CC","CC","CC","TI","CE"]  # CC dominante


# ─── Archetypes ─────────────────────────────────────────────────────────────────

@dataclass
class Archetype:
    name: str
    proportion: float
    # (mean, std, min, max) de nota objetivo por corte
    c1: tuple[float, float, float, float]
    c2: tuple[float, float, float, float]
    c3: tuple[float, float, float, float]
    # (tasa_min, tasa_max) de asistencia por corte
    att_c1: tuple[float, float]
    att_c2: tuple[float, float]
    att_c3: tuple[float, float]
    # Prob. de tener C3 en el período actual (no finalizado)
    has_c3_prob: float = 0.60
    past_status: str = "COMPLETED"
    current_status: str = "ACTIVE"


ARCHETYPES: list[Archetype] = [
    Archetype("genius",         0.05,
              (4.70, 0.15, 4.2, 5.0), (4.80, 0.12, 4.3, 5.0), (4.90, 0.10, 4.5, 5.0),
              (0.90, 1.00), (0.90, 1.00), (0.92, 1.00), 0.80),
    Archetype("good",           0.15,
              (4.10, 0.25, 3.5, 4.9), (4.20, 0.25, 3.5, 4.9), (4.10, 0.28, 3.3, 4.9),
              (0.78, 0.95), (0.76, 0.94), (0.75, 0.94), 0.70),
    Archetype("average",        0.30,
              (3.40, 0.35, 2.7, 4.2), (3.50, 0.35, 2.7, 4.3), (3.40, 0.38, 2.6, 4.4),
              (0.65, 0.82), (0.62, 0.80), (0.60, 0.82), 0.60),
    Archetype("barely_passing", 0.10,
              (3.00, 0.18, 2.7, 3.5), (3.10, 0.18, 2.8, 3.6), (3.00, 0.20, 2.8, 3.5),
              (0.55, 0.72), (0.53, 0.70), (0.50, 0.72), 0.55),
    Archetype("ghost_passer",   0.08,
              (4.20, 0.30, 3.5, 5.0), (4.00, 0.35, 3.2, 5.0), (4.10, 0.30, 3.2, 5.0),
              (0.15, 0.40), (0.12, 0.38), (0.10, 0.38), 0.55),
    Archetype("attend_failer",  0.07,
              (2.20, 0.40, 0.5, 2.9), (2.00, 0.45, 0.5, 2.9), (1.90, 0.45, 0.5, 2.9),
              (0.80, 0.98), (0.82, 0.98), (0.80, 0.98), 0.45),
    Archetype("burnout",        0.05,
              (4.40, 0.20, 4.0, 5.0), (3.00, 0.50, 1.5, 4.0), (2.00, 0.55, 0.5, 3.2),
              (0.85, 0.98), (0.60, 0.80), (0.35, 0.60), 0.40),
    Archetype("late_bloomer",   0.05,
              (2.00, 0.45, 0.5, 2.9), (3.20, 0.45, 2.2, 4.2), (4.20, 0.35, 3.2, 5.0),
              (0.40, 0.60), (0.60, 0.80), (0.82, 0.98), 0.55),
    Archetype("chronic_failer", 0.10,
              (1.80, 0.50, 0.0, 2.9), (1.70, 0.50, 0.0, 2.9), (1.60, 0.55, 0.0, 2.9),
              (0.10, 0.42), (0.08, 0.38), (0.05, 0.35), 0.35),
    Archetype("dropout",        0.05,
              (2.50, 0.60, 0.5, 4.0), (0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0),
              (0.40, 0.70), (0.0, 0.0), (0.0, 0.0),
              has_c3_prob=0.0,
              past_status="CANCELLED", current_status="CANCELLED"),
]

assert abs(sum(a.proportion for a in ARCHETYPES) - 1.0) < 1e-9

# Distribución acumulada para _pick_archetype
_CUMULATIVE: list[tuple[float, Archetype]] = []
_c = 0.0
for _a in ARCHETYPES:
    _c += _a.proportion
    _CUMULATIVE.append((_c, _a))


# ─── Helpers de generación ──────────────────────────────────────────────────────

def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _rand_note(mean: float, std: float, lo: float, hi: float) -> float:
    if hi <= 0:
        return 0.0
    return round(_clamp(random.gauss(mean, std), lo, hi), 1)


def _rand_attend(rate_min: float, rate_max: float) -> dict[str, int]:
    if rate_max <= 0:
        return {"assist": 0, "not_asist": random.randint(18, 26)}
    total = random.randint(20, 28)
    rate = random.uniform(rate_min, rate_max)
    assist = _clamp(int(round(total * rate)), 0, total)
    return {"assist": int(assist), "not_asist": total - int(assist)}


def _cohort_block(
    cohort_id: str, name: str, weight_pct: str,
    parcial_label: str, act_a_label: str, act_b_label: str,
    mean: float, std: float, lo: float, hi: float,
    att_min: float, att_max: float,
) -> dict:
    return {
        "name": name,
        "weight": weight_pct,
        "attendance": _rand_attend(att_min, att_max),
        "parcial": {
            "id": f"{cohort_id}_parcial",
            "name": parcial_label,
            "note": _rand_note(mean, std, lo, hi),
            "weight": "70%",
        },
        "seguimiento": {
            f"{cohort_id}_act_a": {
                "id": f"{cohort_id}_act_a",
                "name": act_a_label,
                "note": _rand_note(mean, std * 1.4, lo, hi),
                "weight": "15%",
            },
            f"{cohort_id}_act_b": {
                "id": f"{cohort_id}_act_b",
                "name": act_b_label,
                "note": _rand_note(mean, std * 1.4, lo, hi),
                "weight": "15%",
            },
        },
    }


def _build_grades(arch: Archetype, include_c3: bool) -> dict:
    grades: dict = {
        "first_cohort": _cohort_block(
            "first_cohort", "Corte 1", "30%",
            "Parcial 1", "Taller 1", "Quiz 1",
            *arch.c1, *arch.att_c1,
        ),
        "second_cohort": _cohort_block(
            "second_cohort", "Corte 2", "30%",
            "Parcial 2", "Laboratorio", "Proyecto Parcial",
            *arch.c2, *arch.att_c2,
        ),
    }
    if include_c3 and arch.c3[3] > 0:
        grades["third_cohort"] = _cohort_block(
            "third_cohort", "Corte Final", "40%",
            "Examen Final", "Sustentación", "Proyecto Final",
            *arch.c3, *arch.att_c3,
        )
    return grades


def _pick_archetype() -> Archetype:
    r = random.random()
    for threshold, arch in _CUMULATIVE:
        if r <= threshold:
            return arch
    return ARCHETYPES[-1]


def _to_dec(val: float | None) -> Decimal | None:
    return None if val is None else Decimal(str(round(val, 2)))


def _enrollment_dt(period: str) -> datetime:
    start = PERIOD_START[period]
    d = start + timedelta(days=random.randint(0, 7))
    return datetime(d.year, d.month, d.day, random.randint(7, 17), random.randint(0, 59), tzinfo=timezone.utc)


def _eval_config(period: str) -> list[dict]:
    d = PERIOD_EVAL_DATES[period]
    return [
        {"id": "first_cohort",  "name": "Corte 1",     "percentage": 30, "date": d["c1"]},
        {"id": "second_cohort", "name": "Corte 2",     "percentage": 30, "date": d["c2"]},
        {"id": "third_cohort",  "name": "Corte Final", "percentage": 40, "date": d["c3"]},
    ]


# ─── Bulk insert helper ─────────────────────────────────────────────────────────

async def _bulk(session, model, rows: list[dict]) -> None:
    if not rows:
        return
    for i in range(0, len(rows), BATCH_SIZE):
        await session.execute(insert(model), rows[i: i + BATCH_SIZE])


# ─── Etapas ─────────────────────────────────────────────────────────────────────

async def _create_admin(session) -> uuid.UUID:
    admin_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    await session.execute(insert(User), [{
        "id": admin_id,
        "email": "admin@usbco.edu.co",
        "institutional_email": "admin@usb.edu.co",
        "full_name": "Administrador del Sistema",
        "role": RoleEnum.ADMIN.value,
        "status": UserStatusEnum.ACTIVE.value,
        "password_hash": hash_password(ADMIN_PASSWORD),
        "ml_consent": True,
        "whatsapp_enabled": True,
        "email_enabled": True,
        "created_at": now,
        "updated_at": now,
    }])
    print(f"  ✓ Admin: admin@usbco.edu.co / {ADMIN_PASSWORD}")
    return admin_id


async def _create_program(session) -> uuid.UUID:
    prog_id = uuid.uuid4()
    await session.execute(insert(Program), [{
        "id": prog_id, **PROGRAM, "created_at": datetime.now(timezone.utc),
    }])
    print(f"  ✓ Programa: {PROGRAM['program_name']}")
    return prog_id


async def _create_subjects(session, program_id: uuid.UUID) -> dict[int, list[uuid.UUID]]:
    """Retorna {nivel: [subject_id × 5]}."""
    subjects_by_level: dict[int, list[uuid.UUID]] = {}
    rows: list[dict] = []
    now = datetime.now(timezone.utc)
    for level, items in SUBJECTS_BY_LEVEL.items():
        ids: list[uuid.UUID] = []
        for code, name, credits in items:
            sid = uuid.uuid4()
            ids.append(sid)
            rows.append({
                "id": sid, "code": code, "name": name, "credits": credits,
                "program_id": program_id,
                "status": CourseStatusEnum.ACTIVE.value,
                "created_at": now,
            })
        subjects_by_level[level] = ids
    await _bulk(session, Subject, rows)
    print(f"  ✓ {len(rows)} materias")
    return subjects_by_level


async def _create_professors(session, student_pw_hash: str) -> list[uuid.UUID]:
    prof_ids: list[uuid.UUID] = []
    rows: list[dict] = []
    now = datetime.now(timezone.utc)
    for email, full_name, phone in PROFESSORS_DATA:
        pid = uuid.uuid4()
        prof_ids.append(pid)
        rows.append({
            "id": pid,
            "email": email,
            "institutional_email": email,
            "full_name": full_name,
            "role": RoleEnum.PROFESSOR.value,
            "status": UserStatusEnum.ACTIVE.value,
            "password_hash": student_pw_hash,
            "ml_consent": True,
            "phone": phone,
            "whatsapp_enabled": True,
            "email_enabled": True,
            "created_at": now,
            "updated_at": now,
        })
    await _bulk(session, User, rows)
    print(f"  ✓ {len(rows)} profesores (password: {STUDENT_PASSWORD})")
    return prof_ids


async def _create_courses(
    session,
    subjects_by_level: dict[int, list[uuid.UUID]],
    prof_ids: list[uuid.UUID],
) -> dict[tuple[int, str, str], list[uuid.UUID]]:
    """
    Retorna {(nivel, seccion, period): [course_id × 5]}.
    500 cursos = 25 materias × 5 períodos × 4 secciones.
    """
    courses_by_lsp: dict[tuple[int, str, str], list[uuid.UUID]] = {}
    rows: list[dict] = []
    now = datetime.now(timezone.utc)
    prof_idx = 0
    for period in PERIODS_IN_ORDER:
        for level in range(1, 6):
            for section in SECTIONS:
                key = (level, section, period)
                courses_by_lsp[key] = []
                for sid in subjects_by_level[level]:
                    cid = uuid.uuid4()
                    courses_by_lsp[key].append(cid)
                    rows.append({
                        "id": cid,
                        "subject_id": sid,
                        "section": section,
                        "academic_period": period,
                        "professor_id": prof_ids[prof_idx % len(prof_ids)],
                        "status": (
                            CourseStatusEnum.ACTIVE.value
                            if period == CURRENT_PERIOD
                            else CourseStatusEnum.INACTIVE.value
                        ),
                        "evaluation_config": _eval_config(period),
                        "created_at": now,
                    })
                    prof_idx += 1
    await _bulk(session, Course, rows)
    print(f"  ✓ {len(rows)} cursos")
    return courses_by_lsp


async def _create_students_and_enrollments(
    session,
    courses_by_lsp: dict[tuple[int, str, str], list[uuid.UUID]],
    student_pw_hash: str,
    program_id: uuid.UUID,
) -> dict[uuid.UUID, str]:
    """
    Crea 50 000 estudiantes, perfiles, consentimientos e inscripciones.
    Procesa en sub-lotes de SUB_BATCH_STUDENTS para controlar memoria.
    Retorna {student_id: archetype_name}.
    """
    archetype_map: dict[uuid.UUID, str] = {}
    student_seq = 0
    total_enrollments = 0

    # Cohortes: índice 0 → 2024-1, ..., índice 4 → 2026-1
    for cohort_idx, cohort_period in enumerate(PERIODS_IN_ORDER):
        # Períodos activos para esta cohorte (sube de nivel por período)
        active_periods = PERIODS_IN_ORDER[cohort_idx:]
        n_students = STUDENTS_PER_COHORT
        print(f"\n  Cohorte {cohort_period} | {n_students:,} estudiantes | {len(active_periods)} semestres activos")

        processed = 0
        while processed < n_students:
            batch_n = min(SUB_BATCH_STUDENTS, n_students - processed)

            user_rows: list[dict] = []
            profile_rows: list[dict] = []
            consent_rows: list[dict] = []
            enrollment_rows: list[dict] = []

            for _ in range(batch_n):
                student_seq += 1
                processed += 1
                uid = uuid.uuid4()
                arch = _pick_archetype()
                archetype_map[uid] = arch.name

                gender = random.choice(["M", "F"])
                first = random.choice(NOMBRES_M if gender == "M" else NOMBRES_F)
                ap1 = random.choice(APELLIDOS)
                ap2 = random.choice(APELLIDOS)
                now = datetime.now(timezone.utc)

                birth_yr = random.randint(now.year - 30, now.year - 17)
                birth_dt = date(birth_yr, random.randint(1, 12), random.randint(1, 28))
                section = SECTIONS[student_seq % len(SECTIONS)]

                user_rows.append({
                    "id": uid,
                    "email": f"est{student_seq:07d}@seed.mpra.edu",
                    "institutional_email": f"est{student_seq:07d}@usb.edu.co",
                    "full_name": f"{first} {ap1} {ap2}",
                    "role": RoleEnum.STUDENT.value,
                    "status": UserStatusEnum.ACTIVE.value,
                    "password_hash": student_pw_hash,
                    "ml_consent": random.random() < 0.85,
                    "phone": f"30{random.randint(10_000_000, 99_999_999)}",
                    "whatsapp_enabled": random.random() < 0.70,
                    "email_enabled": random.random() < 0.90,
                    "created_at": now,
                    "updated_at": now,
                })

                profile_rows.append({
                    "id": uuid.uuid4(),
                    "user_id": uid,
                    "student_institutional_id": f"300{student_seq:07d}",
                    "document_type": random.choice(TIPOS_DOC),
                    "document_number": f"10{student_seq:08d}",
                    "birth_date": birth_dt,
                    "gender": gender,
                    "socioeconomic_stratum": random.randint(1, 6),
                    "academic_cycle": cohort_idx + 1,
                    "academic_year": int(cohort_period.split("-")[0]),
                    "semester": cohort_idx + 1,
                    "program_action": "RLOA",
                    "enrollment_status": "AC" if arch.name != "dropout" else "RE",
                    "enrolled_credits": Decimal(str(random.choice([14, 16, 17, 18]))),
                    "other_credits": Decimal("0"),
                    "academic_level": cohort_idx + 1,
                    "cohort": cohort_period,
                    "program_id": program_id,
                    "created_at": now,
                    "updated_at": now,
                })

                if random.random() < 0.85:
                    consent_rows.append({
                        "id": uuid.uuid4(),
                        "student_id": uid,
                        "accepted": True,
                        "terms_version": "v2.0-2024",
                        "accepted_at": datetime.utcnow(),
                    })

                # Inscripciones por período activo de la cohorte
                for period_offset, period in enumerate(active_periods):
                    level = period_offset + 1
                    is_current = period == CURRENT_PERIOD

                    if arch.name == "dropout":
                        if period_offset != 0:
                            continue
                        status = EnrollmentStatusEnum.CANCELLED.value
                    elif is_current:
                        status = arch.current_status
                    else:
                        status = arch.past_status

                    course_ids = courses_by_lsp.get((level, section, period), [])
                    if not course_ids:
                        continue

                    include_c3 = (
                        not is_current
                        or (arch.name != "dropout" and random.random() < arch.has_c3_prob)
                    )
                    grades = _build_grades(arch, include_c3)

                    c1g = _calculate_cohort_grade(grades.get("first_cohort", {}))
                    c2g = _calculate_cohort_grade(grades.get("second_cohort", {}))
                    c3g = (
                        _calculate_cohort_grade(grades["third_cohort"])
                        if "third_cohort" in grades else None
                    )
                    final = (
                        _calculate_final_grade(grades)
                        if "third_cohort" in grades else None
                    )

                    enroll_dt = _enrollment_dt(period)
                    for course_id in course_ids:
                        enrollment_rows.append({
                            "id": uuid.uuid4(),
                            "student_id": uid,
                            "course_id": course_id,
                            "status": status,
                            "enrollment_date": enroll_dt,
                            "updated_at": enroll_dt,
                            "grades": grades,
                            "first_cohort_grade": _to_dec(c1g),
                            "second_cohort_grade": _to_dec(c2g),
                            "third_cohort_grade": _to_dec(c3g),
                            "final_grade": _to_dec(final),
                        })

            await _bulk(session, User, user_rows)
            await _bulk(session, StudentProfile, profile_rows)
            await _bulk(session, Consent, consent_rows)
            await _bulk(session, Enrollment, enrollment_rows)
            await session.flush()
            total_enrollments += len(enrollment_rows)
            print(f"    → {processed:,}/{n_students:,} estudiantes | {total_enrollments:,} inscripciones acumuladas")

    print(f"\n  ✓ 50 000 estudiantes y {total_enrollments:,} inscripciones creadas")
    return archetype_map


async def _create_class_sessions_and_attendance(
    session,
    courses_by_lsp: dict[tuple[int, str, str], list[uuid.UUID]],
    prof_ids: list[uuid.UUID],
    archetype_map: dict[uuid.UUID, str],
) -> None:
    """
    Sesiones de clase para todos los cursos.
    Registros de asistencia individual solo para 2026-1 (5% de estudiantes por curso).
    """
    session_rows: list[dict] = []
    # {course_id: [session_rows]}  — solo para 2026-1
    sessions_current: dict[uuid.UUID, list[dict]] = {}

    prof_idx = 0
    for (level, section, period), course_ids in courses_by_lsp.items():
        is_current = period == CURRENT_PERIOD
        period_start = PERIOD_START[period]
        n_sessions = 20 if is_current else 28  # 2026-1 aún en curso

        for cid in course_ids:
            prof_id = prof_ids[prof_idx % len(prof_ids)]
            prof_idx += 1
            period_sessions_for_course: list[dict] = []

            for week in range(n_sessions):
                day_offset = 7 * (week // 2) + (week % 2) * 3
                sess_date = period_start + timedelta(days=day_offset)
                sess_dt = datetime(
                    sess_date.year, sess_date.month, sess_date.day,
                    random.choice([7, 8, 9, 10, 11, 14, 15, 16]), 0,
                )  # naive UTC, como el modelo
                closed_dt = sess_dt + timedelta(minutes=random.randint(90, 120))
                is_open = is_current and week == n_sessions - 1

                sid = uuid.uuid4()
                row = {
                    "id": sid,
                    "course_id": cid,
                    "professor_id": prof_id,
                    "window_seconds": 60,
                    "qr_seed": secrets.token_hex(16),
                    "label": f"Clase {week + 1}",
                    "is_active": is_open,
                    "created_at": sess_dt,
                    "closed_at": None if is_open else closed_dt,
                }
                session_rows.append(row)
                if is_current:
                    period_sessions_for_course.append(row)

            if is_current:
                sessions_current[cid] = period_sessions_for_course

    await _bulk(session, ClassSession, session_rows)
    print(f"  ✓ {len(session_rows):,} sesiones de clase")

    # Asistencias individuales: 5% de estudiantes inscritos en cada curso de 2026-1
    current_course_ids = list(sessions_current.keys())
    att_rows: list[dict] = []
    total_att = 0

    for cid in current_course_ids:
        result = await session.execute(
            select(Enrollment.student_id)
            .where(Enrollment.course_id == cid)
            .where(Enrollment.status == EnrollmentStatusEnum.ACTIVE.value)
        )
        enrolled = [row[0] for row in result.all()]
        if not enrolled:
            continue
        sample_n = max(1, int(len(enrolled) * 0.05))
        sample = random.sample(enrolled, sample_n)
        sessions_for_course = sessions_current[cid]

        for student_id in sample:
            arch_name = archetype_map.get(student_id, "average")
            arch = next((a for a in ARCHETYPES if a.name == arch_name), ARCHETYPES[2])
            att_rate = random.uniform(arch.att_c1[0], arch.att_c1[1]) if arch.att_c1[1] > 0 else 0.5

            for sess_row in sessions_for_course:
                if random.random() < att_rate:
                    att_rows.append({
                        "id": uuid.uuid4(),
                        "session_id": sess_row["id"],
                        "student_id": student_id,
                        "recorded_at": sess_row["created_at"] + timedelta(minutes=random.randint(0, 15)),
                        "qr_token_used": secrets.token_hex(8),
                    })

        if len(att_rows) >= BATCH_SIZE * 5:
            await _bulk(session, Attendance, att_rows)
            total_att += len(att_rows)
            att_rows = []

    if att_rows:
        await _bulk(session, Attendance, att_rows)
        total_att += len(att_rows)

    print(f"  ✓ {total_att:,} registros de asistencia individual (2026-1, muestra 5%)")


async def _create_referrals(
    session,
    courses_by_lsp: dict[tuple[int, str, str], list[uuid.UUID]],
    prof_ids: list[uuid.UUID],
) -> None:
    """Remisiones para 30% de estudiantes en riesgo en 2025-2 y 2026-1."""
    target_course_ids: list[uuid.UUID] = []
    for (level, section, period), cids in courses_by_lsp.items():
        if period in ("2025-2", "2026-1"):
            target_course_ids.extend(cids)

    result = await session.execute(
        select(
            Enrollment.id, Enrollment.student_id,
            Enrollment.first_cohort_grade, Enrollment.final_grade,
        )
        .where(Enrollment.course_id.in_(target_course_ids))
        .where(
            or_(
                Enrollment.first_cohort_grade < Decimal("2.5"),
                Enrollment.final_grade < Decimal("3.0"),
            )
        )
    )
    at_risk = result.all()

    obs_pool = [
        "Estudiante presenta bajo rendimiento en el primer corte. Se recomienda seguimiento.",
        "No entrega actividades de seguimiento. Reporta dificultades personales.",
        "Inasistencias reiteradas. Se recomienda intervención de bienestar.",
        "Notas por debajo del mínimo aprobatorio. Solicita asesoría académica.",
        "Dificultades económicas que afectan su desempeño académico.",
        "Señales de estrés académico y bajo rendimiento sostenido.",
        "Incumplimiento de entregas. Requiere seguimiento del consejero.",
    ]
    ref_types = [t for t in ReferralTypeEnum]
    now_date = date(2026, 5, 1)

    ref_rows: list[dict] = []
    for enroll_id, student_id, c1g, fg in at_risk:
        if random.random() > 0.30:
            continue
        ref_type = random.choice(ref_types)
        ref_date = now_date - timedelta(days=random.randint(1, 60))
        attended = random.choice(list(AsistioEnum))
        ref_status = (
            ReferralStatusEnum.ATENDIDA if attended == AsistioEnum.SI
            else ReferralStatusEnum.PENDIENTE
        )
        ref_dt = datetime.combine(ref_date, datetime.min.time()).replace(tzinfo=timezone.utc)
        ref_rows.append({
            "id": uuid.uuid4(),
            "enrollment_id": enroll_id,
            "created_by": random.choice(prof_ids),
            "referral_type": ref_type.value,
            "referral_type_other": None,
            "observations": random.choice(obs_pool),
            "counselor_observations": (
                "Se realizó orientación y se acordó plan de mejoramiento."
                if attended == AsistioEnum.SI else None
            ),
            "referral_date": ref_date,
            "attended": attended.value,
            "status": ref_status.value,
            "created_at": ref_dt,
            "updated_at": ref_dt,
        })

    await _bulk(session, Referral, ref_rows)
    print(f"  ✓ {len(ref_rows):,} remisiones para estudiantes en riesgo")


# ─── Main ────────────────────────────────────────────────────────────────────────

async def seed() -> None:
    random.seed(RANDOM_SEED)
    t0 = datetime.now()

    print("\n" + "=" * 64)
    print("  SEED MASIVO — Academic Risk Predictor")
    print("=" * 64)

    # Pre-computar hash una vez (bcrypt es lento)
    print("\n  Pre-computando hash de contraseña...")
    student_pw_hash = hash_password(STUDENT_PASSWORD)
    print("  ✓ Hash listo")

    async with AsyncSessionFactory() as session:
        async with session.begin():
            print("\n[1/6] Admin, programa, materias, profesores...")
            admin_id = await _create_admin(session)
            program_id = await _create_program(session)
            subjects_by_level = await _create_subjects(session, program_id)
            prof_ids = await _create_professors(session, student_pw_hash)

        async with session.begin():
            print("\n[2/6] Cursos (500 cursos)...")
            courses_by_lsp = await _create_courses(session, subjects_by_level, prof_ids)

        async with session.begin():
            print("\n[3/6] 50 000 estudiantes e inscripciones...")
            archetype_map = await _create_students_and_enrollments(
                session, courses_by_lsp, student_pw_hash, program_id,
            )

        async with session.begin():
            print("\n[4/6] Sesiones de clase y asistencias (2026-1)...")
            await _create_class_sessions_and_attendance(
                session, courses_by_lsp, prof_ids, archetype_map,
            )

        async with session.begin():
            print("\n[5/6] Remisiones para estudiantes en riesgo...")
            await _create_referrals(session, courses_by_lsp, prof_ids)

    elapsed = (datetime.now() - t0).total_seconds()
    total_students = STUDENTS_PER_COHORT * len(PERIODS_IN_ORDER)
    print("\n" + "=" * 64)
    print(f"  ✅ Seed completado en {elapsed:.1f}s")
    print(f"  Estudiantes:   {total_students:,}")
    print(f"  Cohortes:      {', '.join(PERIODS_IN_ORDER)}")
    print(f"  Programa:      {PROGRAM['program_name']}")
    print(f"  Admin:         admin@usbco.edu.co / {ADMIN_PASSWORD}")
    print(f"  Profesores:    {[e for e, *_ in PROFESSORS_DATA]}")
    print(f"  Password seed: {STUDENT_PASSWORD}")
    print("=" * 64 + "\n")


async def main() -> None:
    try:
        await seed()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
