#!/usr/bin/env python3
"""
seed_grades.py — Puebla la base de datos con estudiantes variados y notas
distribuidas en tres perfiles: buenos, regulares y en riesgo de deserción.

Corre desde la raíz del proyecto:
    DOCKER_HOST=unix:///Users/daforonda/.colima/default/docker.sock \\
    PYTHONPATH=. venv/bin/python3 scripts/seed_grades.py
"""

import asyncio
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import bcrypt
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

# ── Conexión ──────────────────────────────────────────────────────────────────
DB_URL = (
    "postgresql+asyncpg://mpra_user:mpra_password@localhost:5433/mpra_db"
)

PROF_ID   = "e80318bc-5662-4bf3-a4f1-47817142cbe1"   # Carlos Mendoza
PROF_EMAIL = "c.mendoza@academicrisk.edu"

# Vamos a usar PRG-101 como curso principal del demo
TARGET_COURSE_CODE = "PRG-101"

PASSWORD = "demo"

def pwd(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

def nid() -> str:
    return str(uuid.uuid4())


# ── Estudiantes ───────────────────────────────────────────────────────────────
#   Perfil    | nota_parcial_1 | asistencia | seguimiento | logins | uso_tutorias
#   BUENO     |  3.8 – 5.0     |  80 – 100  |  3.8 – 5.0  | 15–25  | True
#   REGULAR   |  3.0 – 3.7     |  65 – 79   |  3.0 – 3.7  |  8–14  | varies
#   RIESGO    |  1.0 – 2.9     |  30 – 59   |  1.0 – 2.9  |  1–7   | False / None

STUDENTS_WITH_GRADES = [
    # ── Perfil BUENO ──────────────────────────────────────────────────────────
    {
        "email": "s001@student.demo.edu", "full_name": "Valentina Torres Ruiz",
        "nota": 4.80, "asist": 97.0, "seg": 4.70, "logins": 24, "tutorias": True,
    },
    {
        "email": "s002@student.demo.edu", "full_name": "Andrés Camilo Herrera",
        "nota": 4.50, "asist": 92.0, "seg": 4.30, "logins": 20, "tutorias": True,
    },
    {
        "email": "s003@student.demo.edu", "full_name": "Isabella Moreno Castro",
        "nota": 4.20, "asist": 88.0, "seg": 4.10, "logins": 18, "tutorias": True,
    },
    {
        "email": "s004@student.demo.edu", "full_name": "Juliana Ospina Vélez",
        "nota": 3.90, "asist": 85.0, "seg": 4.00, "logins": 16, "tutorias": False,
    },
    # ── Perfil REGULAR ────────────────────────────────────────────────────────
    {
        "email": "s005@student.demo.edu", "full_name": "Santiago Muñoz Cárdenas",
        "nota": 3.50, "asist": 76.0, "seg": 3.40, "logins": 12, "tutorias": None,
    },
    {
        "email": "s006@student.demo.edu", "full_name": "María Alejandra Gómez",
        "nota": 3.30, "asist": 72.0, "seg": 3.20, "logins": 10, "tutorias": None,
    },
    {
        "email": "s007@student.demo.edu", "full_name": "Felipe Arango Restrepo",
        "nota": 3.10, "asist": 68.0, "seg": 3.00, "logins": 9,  "tutorias": False,
    },
    {
        "email": "s008@student.demo.edu", "full_name": "Natalia Castillo Ibáñez",
        "nota": 3.05, "asist": 65.0, "seg": 3.10, "logins": 8,  "tutorias": None,
    },
    # ── Perfil RIESGO ALTO (nota baja + inasistencia + pocos logins) ─────────
    {
        "email": "s009@student.demo.edu", "full_name": "Sebastián Mora Díaz",
        "nota": 2.50, "asist": 55.0, "seg": 2.40, "logins": 6,  "tutorias": False,
    },
    {
        "email": "s010@student.demo.edu", "full_name": "Luisa Fernanda Bejarano",
        "nota": 2.10, "asist": 48.0, "seg": 2.00, "logins": 4,  "tutorias": False,
    },
    {
        "email": "s011@student.demo.edu", "full_name": "Tomás Guerrero Pinto",
        "nota": 1.80, "asist": 40.0, "seg": 1.70, "logins": 3,  "tutorias": False,
    },
    {
        "email": "s012@student.demo.edu", "full_name": "Laura Sofía Vargas",
        "nota": 1.50, "asist": 35.0, "seg": 1.60, "logins": 2,  "tutorias": False,
    },
    # ── Sin datos aún (para ver el estado "Sin información") ─────────────────
    {
        "email": "s013@student.demo.edu", "full_name": "Camilo Ríos Morales",
        "nota": None, "asist": None,  "seg": None, "logins": None, "tutorias": None,
    },
    {
        "email": "s014@student.demo.edu", "full_name": "Daniela Suárez Palacios",
        "nota": None, "asist": None,  "seg": None, "logins": None, "tutorias": None,
    },
]


async def seed():
    engine = create_async_engine(DB_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    password_hash = pwd(PASSWORD)
    student_emails = [s["email"] for s in STUDENTS_WITH_GRADES]
    emails_sql = ", ".join(f"'{e}'" for e in student_emails)

    async with async_session() as session:
        async with session.begin():

            # ── 1. Borrar enrollments y usuarios demo anteriores ──────────────
            print("🧹 Limpiando datos de seed anteriores...")
            await session.execute(text(f"""
                DELETE FROM referrals
                WHERE enrollment_id IN (
                    SELECT e.id FROM enrollments e
                    JOIN users u ON u.id = e.student_id
                    WHERE u.email IN ({emails_sql})
                )
            """))
            await session.execute(text(f"""
                DELETE FROM enrollments
                WHERE student_id IN (
                    SELECT id FROM users WHERE email IN ({emails_sql})
                )
            """))
            await session.execute(text(f"""
                DELETE FROM users WHERE email IN ({emails_sql})
            """))
            print("   ✓ Limpieza completa")

            # ── 2. Obtener course_id ──────────────────────────────────────────
            r = await session.execute(text(
                "SELECT id FROM courses WHERE code = :code"
            ), {"code": TARGET_COURSE_CODE})
            row = r.fetchone()
            if not row:
                print(f"❌ Curso {TARGET_COURSE_CODE} no encontrado. Abortando.")
                return
            course_id = str(row[0])
            print(f"📚 Curso objetivo: {TARGET_COURSE_CODE} → {course_id}")

            # ── 3. Crear usuarios estudiantes + enrollments con notas ─────────
            print(f"👩‍🎓 Creando {len(STUDENTS_WITH_GRADES)} estudiantes...")

            for stu in STUDENTS_WITH_GRADES:
                uid = nid()
                eid = nid()

                # Crear usuario
                await session.execute(text("""
                    INSERT INTO users (
                        id, email, full_name, role, status,
                        password_hash, ml_consent, created_at, updated_at
                    ) VALUES (
                        :id, :email, :full_name, 'STUDENT', 'ACTIVE',
                        :password_hash, true, now(), now()
                    )
                    ON CONFLICT (email) DO UPDATE SET
                        full_name = EXCLUDED.full_name,
                        password_hash = EXCLUDED.password_hash
                    RETURNING id
                """), {
                    "id":            uid,
                    "email":         stu["email"],
                    "full_name":     stu["full_name"],
                    "password_hash": password_hash,
                })

                # Obtener el id real (por si el email ya existía)
                r2 = await session.execute(text(
                    "SELECT id FROM users WHERE email = :email"
                ), {"email": stu["email"]})
                uid = str(r2.fetchone()[0])

                # Crear enrollment con notas
                await session.execute(text("""
                    INSERT INTO enrollments (
                        id, student_id, course_id, status,
                        enrollment_date, updated_at,
                        nota_parcial_1, asistencia, seguimiento,
                        logins, uso_tutorias
                    ) VALUES (
                        :eid, :uid, :cid, 'ACTIVE',
                        now(), now(),
                        :nota, :asist, :seg,
                        :logins, :tutorias
                    )
                    ON CONFLICT (student_id, course_id) DO UPDATE SET
                        nota_parcial_1 = EXCLUDED.nota_parcial_1,
                        asistencia     = EXCLUDED.asistencia,
                        seguimiento    = EXCLUDED.seguimiento,
                        logins         = EXCLUDED.logins,
                        uso_tutorias   = EXCLUDED.uso_tutorias,
                        updated_at     = now()
                """), {
                    "eid":     eid,
                    "uid":     uid,
                    "cid":     course_id,
                    "nota":    stu["nota"],
                    "asist":   stu["asist"],
                    "seg":     stu["seg"],
                    "logins":  stu["logins"],
                    "tutorias": stu["tutorias"],
                })

                perfil = (
                    "🟢 BUENO  " if stu["nota"] and stu["nota"] >= 3.8
                    else "🟡 REGULAR" if stu["nota"] and stu["nota"] >= 3.0
                    else "🔴 RIESGO " if stu["nota"] is not None
                    else "⚪ SIN DATA"
                )
                print(f"   {perfil} | {stu['full_name']:30} | nota={stu['nota']} asist={stu['asist']}%")

    await engine.dispose()

    print()
    print("✅ Seed de calificaciones completado.")
    print()
    print("   Credenciales:")
    print(f"   Profesor:   {PROF_EMAIL}  / {PASSWORD}")
    print(f"   Estudiante: s001@student.demo.edu  / {PASSWORD}  (y s002..s014)")
    print()
    print(f"   Cursa en: {TARGET_COURSE_CODE} (Programación I)")
    print()
    print("   Distribución:")
    print("   🟢 4 estudiantes — perfil BUENO   (nota ≥ 3.8, asist ≥ 85%)")
    print("   🟡 4 estudiantes — perfil REGULAR (nota 3.0–3.7, asist 65–79%)")
    print("   🔴 4 estudiantes — perfil RIESGO  (nota < 3.0, asist < 60%)  ← candidatos a remisión")
    print("   ⚪ 2 estudiantes — SIN datos aún")


if __name__ == "__main__":
    asyncio.run(seed())
