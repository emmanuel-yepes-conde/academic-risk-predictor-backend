"""add_cascade_delete_to_program

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-04 00:00:00.000000

Agrega ON DELETE CASCADE a las FKs que dependen de programs y courses,
de modo que al eliminar un programa se eliminen en cascada:
  programs → courses → enrollments
  programs → student_profiles (SET NULL, ya que es nullable)
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. courses.program_id → programs.id  (CASCADE)
    #    Constraint original: fk_courses_program_id (creada en 0003)
    # ------------------------------------------------------------------
    op.drop_constraint("fk_courses_program_id", "courses", type_="foreignkey")
    op.create_foreign_key(
        "fk_courses_program_id",
        "courses",
        "programs",
        ["program_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # ------------------------------------------------------------------
    # 2. enrollments.course_id → courses.id  (CASCADE)
    #    Constraint original sin nombre explícito → Alembic la nombra
    #    "enrollments_course_id_fkey" (convención PostgreSQL).
    # ------------------------------------------------------------------
    op.drop_constraint("enrollments_course_id_fkey", "enrollments", type_="foreignkey")
    op.create_foreign_key(
        "fk_enrollments_course_id",
        "enrollments",
        "courses",
        ["course_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # ------------------------------------------------------------------
    # 3. student_profiles.program_id → programs.id  (SET NULL)
    #    La columna es nullable, por lo que SET NULL es semánticamente
    #    correcto: el perfil del estudiante se conserva pero pierde la
    #    referencia al programa eliminado.
    #    Constraint original sin nombre explícito → "student_profiles_program_id_fkey"
    # ------------------------------------------------------------------
    op.drop_constraint(
        "student_profiles_program_id_fkey", "student_profiles", type_="foreignkey"
    )
    op.create_foreign_key(
        "fk_student_profiles_program_id",
        "student_profiles",
        "programs",
        ["program_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # Revertir en orden inverso
    # ------------------------------------------------------------------

    # 3. student_profiles.program_id → restaurar sin acción
    op.drop_constraint(
        "fk_student_profiles_program_id", "student_profiles", type_="foreignkey"
    )
    op.create_foreign_key(
        "student_profiles_program_id_fkey",
        "student_profiles",
        "programs",
        ["program_id"],
        ["id"],
    )

    # 2. enrollments.course_id → restaurar sin acción
    op.drop_constraint(
        "fk_enrollments_course_id", "enrollments", type_="foreignkey"
    )
    op.create_foreign_key(
        "enrollments_course_id_fkey",
        "enrollments",
        "courses",
        ["course_id"],
        ["id"],
    )

    # 1. courses.program_id → restaurar sin acción
    op.drop_constraint("fk_courses_program_id", "courses", type_="foreignkey")
    op.create_foreign_key(
        "fk_courses_program_id",
        "courses",
        "programs",
        ["program_id"],
        ["id"],
    )
