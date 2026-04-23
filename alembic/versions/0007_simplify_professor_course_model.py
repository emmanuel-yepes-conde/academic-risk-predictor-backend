"""simplify_professor_course_model

Revision ID: 0007
Revises: 0006
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------------------------------------------------------
    # 1. Agregar columna professor_id (UUID, nullable) a courses
    # ---------------------------------------------------------------
    op.add_column(
        "courses",
        sa.Column("professor_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # ---------------------------------------------------------------
    # 2. Crear FK fk_courses_professor_id → users.id
    # ---------------------------------------------------------------
    op.create_foreign_key(
        "fk_courses_professor_id",
        "courses",
        "users",
        ["professor_id"],
        ["id"],
    )

    # ---------------------------------------------------------------
    # 3. Crear índice ix_courses_professor_id
    # ---------------------------------------------------------------
    op.create_index(
        "ix_courses_professor_id",
        "courses",
        ["professor_id"],
        unique=False,
    )

    # ---------------------------------------------------------------
    # 4. Migrar datos: copiar professor_id desde professor_courses
    # ---------------------------------------------------------------
    op.execute(
        """
        UPDATE courses
        SET professor_id = pc.professor_id
        FROM professor_courses pc
        WHERE courses.id = pc.course_id
        """
    )

    # ---------------------------------------------------------------
    # 5. Eliminar tabla professor_courses
    # ---------------------------------------------------------------
    op.drop_table("professor_courses")


def downgrade() -> None:
    # ---------------------------------------------------------------
    # 1. Recrear tabla professor_courses
    # ---------------------------------------------------------------
    op.create_table(
        "professor_courses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("professor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["professor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("course_id", name="uq_professor_courses_course_id"),
    )

    # ---------------------------------------------------------------
    # 2. Migrar datos de vuelta: courses.professor_id → professor_courses
    # ---------------------------------------------------------------
    op.execute(
        """
        INSERT INTO professor_courses (id, professor_id, course_id)
        SELECT gen_random_uuid(), professor_id, id
        FROM courses
        WHERE professor_id IS NOT NULL
        """
    )

    # ---------------------------------------------------------------
    # 3. Eliminar índice ix_courses_professor_id
    # ---------------------------------------------------------------
    op.drop_index("ix_courses_professor_id", table_name="courses")

    # ---------------------------------------------------------------
    # 4. Eliminar FK fk_courses_professor_id
    # ---------------------------------------------------------------
    op.drop_constraint("fk_courses_professor_id", "courses", type_="foreignkey")

    # ---------------------------------------------------------------
    # 5. Eliminar columna professor_id de courses
    # ---------------------------------------------------------------
    op.drop_column("courses", "professor_id")
