#!/usr/bin/env python3
"""
seed_demo.py — Populate the backend database with demo data that matches
the frontend mockData.ts.

Run from the project root:
    python3 scripts/seed_demo.py

Requirements:
    pip install asyncpg sqlalchemy sqlmodel bcrypt pydantic python-dotenv
"""

import asyncio
import os
import sys
import uuid
from pathlib import Path

# ── Load .env from project root ───────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import bcrypt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# ── DB URL ────────────────────────────────────────────────────────────────────
DB_URL = os.getenv("DATABASE_URL") or (
    f"postgresql+asyncpg://{os.getenv('DB_USER', 'mpra_user')}:"
    f"{os.getenv('DB_PASSWORD', 'mpra_password')}@"
    f"{os.getenv('DB_HOST', 'localhost')}:"
    f"{os.getenv('DB_PORT', '5432')}/"
    f"{os.getenv('DB_NAME', 'mpra_db')}"
)

DEMO_PASSWORD = "demo"

# ── Helper ────────────────────────────────────────────────────────────────────

def pwd(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

def new_id() -> str:
    return str(uuid.uuid4())

# ── Demo data (mirrors frontend mockData.ts) ──────────────────────────────────

UNIVERSITY = {
    "id":      new_id(),
    "name":    "Universidad Academicrisk",
    "code":    "UARK",
    "country": "Colombia",
    "city":    "Bogotá",
    "active":  True,
}

CAMPUS = {
    "id":            new_id(),
    "university_id": None,  # filled below
    "campus_code":   "MAIN",
    "name":          "Campus Principal",
    "city":          "Bogotá",
    "active":        True,
}

PROGRAMS = [
    {"id": new_id(), "name": "Ingeniería de Sistemas",  "degree_type": "Pregrado",    "program_code": "IS",  "pensum": "2024", "academic_group": "Ingeniería",  "snies_code": 100001},
    {"id": new_id(), "name": "Ingeniería Civil",        "degree_type": "Pregrado",    "program_code": "IC",  "pensum": "2024", "academic_group": "Ingeniería",  "snies_code": 100002},
    {"id": new_id(), "name": "Matemáticas",             "degree_type": "Pregrado",    "program_code": "MAT", "pensum": "2024", "academic_group": "Ciencias",    "snies_code": 100003},
    {"id": new_id(), "name": "Administración",          "degree_type": "Pregrado",    "program_code": "ADM", "pensum": "2024", "academic_group": "Negocios",    "snies_code": 100004},
]

# We'll use the first program (IS) as the "default" program for courses
COURSES_DATA = [
    {"id": new_id(), "code": "IS-101", "name": "Programación Orientada a Objetos", "credits": 4, "academic_period": "2024-I", "prof_email": "c.mendoza@academicrisk.edu"},
    {"id": new_id(), "code": "IS-102", "name": "Estructuras de Datos",             "credits": 4, "academic_period": "2024-I", "prof_email": "c.mendoza@academicrisk.edu"},
    {"id": new_id(), "code": "MAT-201","name": "Cálculo Diferencial",              "credits": 3, "academic_period": "2024-I", "prof_email": "a.garcia@academicrisk.edu"},
    {"id": new_id(), "code": "MAT-202","name": "Álgebra Lineal",                   "credits": 3, "academic_period": "2024-I", "prof_email": "a.garcia@academicrisk.edu"},
    {"id": new_id(), "code": "MAT-301","name": "Matemáticas Discretas",            "credits": 3, "academic_period": "2024-I", "prof_email": "l.torres@academicrisk.edu"},
]

PROFESSORS = [
    {"id": new_id(), "email": "c.mendoza@academicrisk.edu", "full_name": "Carlos Mendoza",  "role": "PROFESSOR"},
    {"id": new_id(), "email": "a.garcia@academicrisk.edu",  "full_name": "Ana García",      "role": "PROFESSOR"},
    {"id": new_id(), "email": "l.torres@academicrisk.edu",  "full_name": "Luis Torres",     "role": "PROFESSOR"},
]

STUDENTS = [
    {"id": new_id(), "email": "2021100001@student.academicrisk.edu", "full_name": "Valentina Ramos Ortiz",   "role": "STUDENT"},
    {"id": new_id(), "email": "2021100002@student.academicrisk.edu", "full_name": "Sebastián Mora Díaz",     "role": "STUDENT"},
    {"id": new_id(), "email": "2021100003@student.academicrisk.edu", "full_name": "Daniela Castro Herrera",  "role": "STUDENT"},
    {"id": new_id(), "email": "2021100004@student.academicrisk.edu", "full_name": "Andrés Felipe Suárez",    "role": "STUDENT"},
    {"id": new_id(), "email": "2021100005@student.academicrisk.edu", "full_name": "Laura Sofía Peña",        "role": "STUDENT"},
    {"id": new_id(), "email": "2021100006@student.academicrisk.edu", "full_name": "Camilo Andrés Torres",    "role": "STUDENT"},
    {"id": new_id(), "email": "2021100007@student.academicrisk.edu", "full_name": "Isabella Martínez Cruz",  "role": "STUDENT"},
    {"id": new_id(), "email": "2021100008@student.academicrisk.edu", "full_name": "David Esteban López",     "role": "STUDENT"},
    {"id": new_id(), "email": "2021100009@student.academicrisk.edu", "full_name": "María Alejandra Gómez",   "role": "STUDENT"},
    {"id": new_id(), "email": "2021100010@student.academicrisk.edu", "full_name": "Juan Pablo Vargas",       "role": "STUDENT"},
    {"id": new_id(), "email": "2021200001@student.academicrisk.edu", "full_name": "Juliana Ríos Morales",    "role": "STUDENT"},
    {"id": new_id(), "email": "2021200002@student.academicrisk.edu", "full_name": "Santiago Muñoz Cárdenas", "role": "STUDENT"},
    {"id": new_id(), "email": "2021200003@student.academicrisk.edu", "full_name": "Natalia Ospina Vega",     "role": "STUDENT"},
    {"id": new_id(), "email": "2021200004@student.academicrisk.edu", "full_name": "Tomás Bejarano Silva",    "role": "STUDENT"},
    {"id": new_id(), "email": "2021200005@student.academicrisk.edu", "full_name": "Mariana Guerrero Pinto",  "role": "STUDENT"},
    {"id": new_id(), "email": "2022100001@student.academicrisk.edu", "full_name": "Felipe Arango Restrepo",  "role": "STUDENT"},
    {"id": new_id(), "email": "2022100002@student.academicrisk.edu", "full_name": "Sara Quintero Ibáñez",    "role": "STUDENT"},
    {"id": new_id(), "email": "2022100003@student.academicrisk.edu", "full_name": "Alejandro Palacios Ruiz", "role": "STUDENT"},
    {"id": new_id(), "email": "2022100004@student.academicrisk.edu", "full_name": "Luisa Fernanda Castillo", "role": "STUDENT"},
    {"id": new_id(), "email": "2022100005@student.academicrisk.edu", "full_name": "Nicolás Echeverri Duque", "role": "STUDENT"},
]

ADMIN = {
    "id":       new_id(),
    "email":    "admin@academicrisk.edu",
    "full_name": "Administrador",
    "role":     "ADMIN",
}

# Course → student enrollment mapping (mirrors mockData.ts studentIds by index)
# student indexes are 0-based into STUDENTS list
ENROLLMENTS = {
    "IS-101":  list(range(0, 15)),   # s01..s15
    "IS-102":  [0,2,4,6,8,10,11,12,13,14,15,16],
    "MAT-201": [0,1,3,5,7,9,10,12,14,15,16,17,18,19],
    "MAT-202": [1,3,5,7,9,11,13,15,17,19],
    "MAT-301": list(range(0, 12)),
}


async def seed():
    engine = create_async_engine(DB_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    password_hash = pwd(DEMO_PASSWORD)

    async with async_session() as session:
        async with session.begin():

            # ── Clean up existing demo data ──────────────────────────────────
            print("Limpiando datos anteriores del seed...")
            demo_emails = (
                [ADMIN["email"]]
                + [p["email"] for p in PROFESSORS]
                + [s["email"] for s in STUDENTS]
            )
            placeholders = ", ".join(f"'{e}'" for e in demo_emails)

            await session.execute(text(f"""
                DELETE FROM professor_courses
                WHERE professor_id IN (
                    SELECT id FROM users WHERE email IN ({placeholders})
                )
            """))
            await session.execute(text(f"""
                DELETE FROM enrollments
                WHERE student_id IN (
                    SELECT id FROM users WHERE email IN ({placeholders})
                )
            """))
            await session.execute(text(f"""
                DELETE FROM audit_logs
                WHERE user_id IN (
                    SELECT id FROM users WHERE email IN ({placeholders})
                )
            """))
            await session.execute(text(f"""
                DELETE FROM users WHERE email IN ({placeholders})
            """))

            # Clean demo courses
            demo_course_codes = [c["code"] for c in COURSES_DATA]
            codes_placeholder = ", ".join(f"'{c}'" for c in demo_course_codes)
            await session.execute(text(f"DELETE FROM courses WHERE code IN ({codes_placeholder})"))

            # Clean demo programs
            prog_codes = ", ".join(f"'{p['program_code']}'" for p in PROGRAMS)
            await session.execute(text(f"DELETE FROM programs WHERE program_code IN ({prog_codes})"))

            # Clean campus / university
            await session.execute(text("DELETE FROM campuses WHERE name = 'Campus Principal'"))
            await session.execute(text("DELETE FROM universities WHERE code = 'UARK'"))

            # ── University & Campus ───────────────────────────────────────────
            print("Creando universidad y campus...")
            await session.execute(text("""
                INSERT INTO universities (id, name, code, country, city, active, created_at)
                VALUES (:id, :name, :code, :country, :city, :active, now())
                ON CONFLICT (code) DO NOTHING
            """), UNIVERSITY)

            CAMPUS["university_id"] = UNIVERSITY["id"]
            await session.execute(text("""
                INSERT INTO campuses (id, university_id, campus_code, name, city, active, created_at)
                VALUES (:id, :university_id, :campus_code, :name, :city, :active, now())
                ON CONFLICT DO NOTHING
            """), CAMPUS)

            # ── Programs ──────────────────────────────────────────────────────
            print("Creando programas...")
            for prog in PROGRAMS:
                await session.execute(text("""
                    INSERT INTO programs (
                        id, university_id, campus_id, institution, degree_type,
                        program_code, program_name, pensum, academic_group,
                        location, snies_code, created_at
                    ) VALUES (
                        :id, :university_id, :campus_id, :institution, :degree_type,
                        :program_code, :program_name, :pensum, :academic_group,
                        :location, :snies_code, now()
                    )
                    ON CONFLICT DO NOTHING
                """), {
                    **prog,
                    "university_id": UNIVERSITY["id"],
                    "campus_id":     CAMPUS["id"],
                    "institution":   UNIVERSITY["name"],
                    "program_name":  prog["name"],
                    "location":      UNIVERSITY["city"],
                })

            # ── Admin ─────────────────────────────────────────────────────────
            print("Creando admin...")
            await session.execute(text("""
                INSERT INTO users (id, email, full_name, role, status, password_hash, ml_consent, created_at, updated_at)
                VALUES (:id, :email, :full_name, :role, 'ACTIVE', :password_hash, false, now(), now())
                ON CONFLICT (email) DO NOTHING
            """), {**ADMIN, "password_hash": password_hash})

            # ── Professors ────────────────────────────────────────────────────
            print("Creando profesores...")
            prof_by_email: dict[str, str] = {}
            for prof in PROFESSORS:
                await session.execute(text("""
                    INSERT INTO users (id, email, full_name, role, status, password_hash, ml_consent, created_at, updated_at)
                    VALUES (:id, :email, :full_name, :role, 'ACTIVE', :password_hash, false, now(), now())
                    ON CONFLICT (email) DO NOTHING
                """), {**prof, "password_hash": password_hash})
                prof_by_email[prof["email"]] = prof["id"]

            # ── Students ──────────────────────────────────────────────────────
            print("Creando estudiantes...")
            for stu in STUDENTS:
                await session.execute(text("""
                    INSERT INTO users (id, email, full_name, role, status, password_hash, ml_consent, created_at, updated_at)
                    VALUES (:id, :email, :full_name, :role, 'ACTIVE', :password_hash, true, now(), now())
                    ON CONFLICT (email) DO NOTHING
                """), {**stu, "password_hash": password_hash})

            # ── Courses ───────────────────────────────────────────────────────
            print("Creando cursos...")
            # Use IS program as default program for all courses
            default_program_id = PROGRAMS[0]["id"]
            course_id_by_code: dict[str, str] = {}

            for course in COURSES_DATA:
                await session.execute(text("""
                    INSERT INTO courses (id, code, name, credits, academic_period, program_id, created_at)
                    VALUES (:id, :code, :name, :credits, :academic_period, :program_id, now())
                    ON CONFLICT DO NOTHING
                """), {
                    "id":              course["id"],
                    "code":            course["code"],
                    "name":            course["name"],
                    "credits":         course["credits"],
                    "academic_period": course["academic_period"],
                    "program_id":      default_program_id,
                })
                course_id_by_code[course["code"]] = course["id"]

            # ── Professor-Course assignments ──────────────────────────────────
            print("Asignando profesores a cursos...")
            for course in COURSES_DATA:
                prof_id = prof_by_email.get(course["prof_email"])
                if not prof_id:
                    continue
                course_id = course_id_by_code[course["code"]]
                await session.execute(text("""
                    INSERT INTO professor_courses (id, professor_id, course_id)
                    VALUES (gen_random_uuid(), :professor_id, :course_id)
                    ON CONFLICT DO NOTHING
                """), {"professor_id": prof_id, "course_id": course_id})

            # ── Enrollments ───────────────────────────────────────────────────
            print("Inscribiendo estudiantes en cursos...")
            for course_code, student_indexes in ENROLLMENTS.items():
                course_id = course_id_by_code.get(course_code)
                if not course_id:
                    continue
                for idx in student_indexes:
                    if idx >= len(STUDENTS):
                        continue
                    stu_id = STUDENTS[idx]["id"]
                    await session.execute(text("""
                        INSERT INTO enrollments (id, student_id, course_id, enrollment_date)
                        VALUES (gen_random_uuid(), :student_id, :course_id, now())
                        ON CONFLICT DO NOTHING
                    """), {"student_id": stu_id, "course_id": course_id})

    await engine.dispose()
    print("\n✅ Seed completado.")
    print(f"   Admin:      admin@academicrisk.edu  / {DEMO_PASSWORD}")
    print(f"   Profesor:   c.mendoza@academicrisk.edu  / {DEMO_PASSWORD}")
    print(f"   Estudiante: 2021100001@student.academicrisk.edu  / {DEMO_PASSWORD}")
    print(f"   (Todos los usuarios usan la contraseña '{DEMO_PASSWORD}')")


if __name__ == "__main__":
    asyncio.run(seed())
