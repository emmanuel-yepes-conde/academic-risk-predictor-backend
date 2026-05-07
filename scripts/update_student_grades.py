"""
Actualiza las notas del estudiante de prueba en la BD local.

Uso:
    python3 -m scripts.update_student_grades
"""

import asyncio
from decimal import Decimal

from sqlalchemy import select

from app.application.services.grade_service import (
    _calculate_cohort_grade,
    _calculate_final_grade,
)
from app.infrastructure.database import AsyncSessionFactory, engine
from app.infrastructure.models.enrollment import Enrollment
from app.infrastructure.models.user import User

STUDENT_EMAIL = "estudiante@universidad.edu"

GRADES = {
    "first_cohort": {
        "weight": "30%",
        "parcial": {"note": 3.8, "weight": "15%"},
        "seguimiento": {
            "quiz_1":        {"note": 2.0, "weight": "5%"},
            "taller_1":      {"note": 3.3, "weight": "5%"},
            "laboratorio_1": {"note": 4.5, "weight": "5%"},
        },
    },
    "second_cohort": {
        "weight": "30%",
        "parcial": {"note": 3.5, "weight": "15%"},
        "seguimiento": {
            "taller_2":         {"note": 4.0, "weight": "10%"},
            "proyecto_parcial": {"note": 3.7, "weight": "5%"},
        },
    },
    "third_cohort": {
        "weight": "40%",
        "parcial": {"note": 3.2, "weight": "20%"},
        "seguimiento": {
            "sustentacion":  {"note": 3.8, "weight": "8%"},
            "proyecto_final": {"note": 4.1, "weight": "12%"},
        },
    },
}


async def update() -> None:
    async with AsyncSessionFactory() as session:
        # 1. Buscar estudiante
        result = await session.execute(
            select(User).where(User.email == STUDENT_EMAIL)
        )
        student = result.scalar_one_or_none()
        if not student:
            print(f"ERROR: estudiante '{STUDENT_EMAIL}' no encontrado.")
            return
        print(f"  ✓ Estudiante: {student.full_name} ({student.id})")

        # 2. Buscar enrollment
        result = await session.execute(
            select(Enrollment).where(Enrollment.student_id == student.id)
        )
        enrollment = result.scalar_one_or_none()
        if not enrollment:
            print("ERROR: no se encontró inscription para este estudiante.")
            return
        print(f"  ✓ Enrollment: {enrollment.id}")

        # 3. Calcular notas por cohorte y final
        first  = _calculate_cohort_grade(GRADES["first_cohort"])
        second = _calculate_cohort_grade(GRADES["second_cohort"])
        third  = _calculate_cohort_grade(GRADES["third_cohort"])
        final  = _calculate_final_grade(GRADES)

        # 4. Actualizar
        enrollment.grades              = GRADES
        enrollment.first_cohort_grade  = Decimal(str(first))  if first  is not None else None
        enrollment.second_cohort_grade = Decimal(str(second)) if second is not None else None
        enrollment.third_cohort_grade  = Decimal(str(third))  if third  is not None else None
        enrollment.final_grade         = Decimal(str(final))  if final  is not None else None

        session.add(enrollment)
        await session.commit()

        print("\n  Notas actualizadas:")
        print(f"    Corte 1: {first}")
        print(f"    Corte 2: {second}")
        print(f"    Corte 3: {third}")
        print(f"    Final:   {final}")
        print(f"\n  GET /enrollments/{enrollment.id}/grades")


async def main() -> None:
    try:
        await update()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
