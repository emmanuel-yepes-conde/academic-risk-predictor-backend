"""add_university_and_multi_university_support

Revision ID: 0004
Revises: 0003
Create Date: 2025-01-01 00:00:00.000000

"""
import os
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------------------------------------------------------
    # 1. Crear tabla universities
    # ---------------------------------------------------------------
    op.create_table(
        "universities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sqlmodel.AutoString(), nullable=False),
        sa.Column("code", sqlmodel.AutoString(), nullable=False),
        sa.Column("country", sqlmodel.AutoString(), nullable=False),
        sa.Column("city", sqlmodel.AutoString(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(
        op.f("ix_universities_code"), "universities", ["code"], unique=True
    )

    # ---------------------------------------------------------------
    # 2. Agregar university_id a programs (nullable inicialmente)
    # ---------------------------------------------------------------
    op.add_column(
        "programs",
        sa.Column("university_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # ---------------------------------------------------------------
    # 3. Migrar datos existentes: asignar DEFAULT_UNIVERSITY_ID
    # ---------------------------------------------------------------
    default_university_id = os.environ.get("DEFAULT_UNIVERSITY_ID")

    # Verificar si hay programas existentes que necesiten migración
    conn = op.get_bind()
    result = conn.execute(sa.text("SELECT COUNT(*) FROM programs"))
    program_count = result.scalar()

    if program_count > 0:
        if not default_university_id:
            raise SystemExit(
                "DEFAULT_UNIVERSITY_ID no está configurado. "
                "Configure esta variable de entorno antes de ejecutar la migración. "
                "Esta variable es necesaria para asignar los programas existentes "
                "a una universidad por defecto."
            )
        conn.execute(
            sa.text("UPDATE programs SET university_id = :uid"),
            {"uid": default_university_id},
        )

    # ---------------------------------------------------------------
    # 4. ALTER university_id a NOT NULL
    # ---------------------------------------------------------------
    op.alter_column(
        "programs", "university_id", existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_programs_university_id", "programs", "universities",
        ["university_id"], ["id"],
    )
    op.create_index(
        op.f("ix_programs_university_id"), "programs", ["university_id"],
        unique=False,
    )

    # ---------------------------------------------------------------
    # 5. Cambiar UniqueConstraint de program_code: global → scoped por universidad
    # ---------------------------------------------------------------
    # Eliminar constraint e índice global de program_code
    op.drop_index(op.f("ix_programs_program_code"), table_name="programs")
    op.drop_constraint("programs_program_code_key", "programs", type_="unique")

    # Crear índice no-unique y constraint scoped
    op.create_index(
        op.f("ix_programs_program_code"), "programs", ["program_code"], unique=False
    )
    op.create_unique_constraint(
        "uq_program_code_university", "programs",
        ["program_code", "university_id"],
    )

    # ---------------------------------------------------------------
    # 6. ALTER courses.program_id a NOT NULL
    # ---------------------------------------------------------------
    op.alter_column(
        "courses", "program_id", existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.create_index(
        op.f("ix_courses_program_id"), "courses", ["program_id"], unique=False
    )

    # ---------------------------------------------------------------
    # 7. Cambiar UniqueConstraint de professor_courses:
    #    (professor_id, course_id) → (course_id)
    # ---------------------------------------------------------------
    op.drop_constraint(
        "professor_courses_professor_id_course_id_key",
        "professor_courses",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_professor_courses_course_id", "professor_courses", ["course_id"]
    )


def downgrade() -> None:
    # ---------------------------------------------------------------
    # 7. Revertir UniqueConstraint de professor_courses
    # ---------------------------------------------------------------
    op.drop_constraint(
        "uq_professor_courses_course_id", "professor_courses", type_="unique"
    )
    op.create_unique_constraint(
        "professor_courses_professor_id_course_id_key",
        "professor_courses",
        ["professor_id", "course_id"],
    )

    # ---------------------------------------------------------------
    # 6. Revertir courses.program_id a nullable
    # ---------------------------------------------------------------
    op.drop_index(op.f("ix_courses_program_id"), table_name="courses")
    op.alter_column(
        "courses", "program_id", existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )

    # ---------------------------------------------------------------
    # 5. Revertir UniqueConstraint de program_code a global
    # ---------------------------------------------------------------
    op.drop_constraint("uq_program_code_university", "programs", type_="unique")
    op.drop_index(op.f("ix_programs_program_code"), table_name="programs")

    # Restaurar índice y constraint global
    op.create_index(
        op.f("ix_programs_program_code"), "programs", ["program_code"], unique=True
    )
    op.create_unique_constraint(
        "programs_program_code_key", "programs", ["program_code"]
    )

    # ---------------------------------------------------------------
    # 4. Revertir university_id en programs
    # ---------------------------------------------------------------
    op.drop_index(op.f("ix_programs_university_id"), table_name="programs")
    op.drop_constraint("fk_programs_university_id", "programs", type_="foreignkey")
    op.drop_column("programs", "university_id")

    # ---------------------------------------------------------------
    # 1. Eliminar tabla universities
    # ---------------------------------------------------------------
    op.drop_index(op.f("ix_universities_code"), table_name="universities")
    op.drop_table("universities")
