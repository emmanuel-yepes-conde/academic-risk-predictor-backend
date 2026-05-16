"""Add subjects table and refactor courses as sections.

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-04

Cambios:
- Crea tabla `subjects` (definición académica de una materia).
- Migra datos de `courses` a `subjects` (code, name, credits, program_id).
- Añade columnas `subject_id` y `section` a `courses`.
- Elimina columnas `code`, `name`, `credits`, `program_id` de `courses`.
- Añade constraint UNIQUE (subject_id, section, academic_period).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Crear tabla subjects ──────────────────────────────────────────────
    op.create_table(
        "subjects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("program_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            sa.String(),
            nullable=False,
            server_default="ACTIVE",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_subjects_code"),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_subjects_code", "subjects", ["code"])
    op.create_index("ix_subjects_program_id", "subjects", ["program_id"])

    # ── 2. Poblar subjects desde courses existentes ──────────────────────────
    op.execute("""
        INSERT INTO subjects (id, code, name, credits, program_id, status, created_at)
        SELECT gen_random_uuid(), code, name, credits, program_id, status, created_at
        FROM courses
    """)

    # ── 3. Añadir subject_id y section a courses (nullable primero) ──────────
    op.add_column("courses", sa.Column("subject_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("courses", sa.Column("section", sa.String(), nullable=True))

    # ── 4. Relacionar cada course con su subject recién creado ───────────────
    op.execute("""
        UPDATE courses c
        SET subject_id = s.id,
            section    = 'A'
        FROM subjects s
        WHERE s.code = c.code
    """)

    # ── 5. Hacer NOT NULL las nuevas columnas ────────────────────────────────
    op.alter_column("courses", "subject_id", nullable=False)
    op.alter_column("courses", "section", nullable=False)

    # ── 6. FK + índice de subject_id ─────────────────────────────────────────
    op.create_foreign_key(
        "fk_courses_subject_id",
        "courses", "subjects",
        ["subject_id"], ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_courses_subject_id", "courses", ["subject_id"])

    # ── 7. Constraint UNIQUE (subject_id, section, academic_period) ──────────
    op.create_unique_constraint(
        "uq_course_subject_section_period",
        "courses",
        ["subject_id", "section", "academic_period"],
    )

    # ── 8. Eliminar columnas antiguas de courses ─────────────────────────────
    op.drop_index("ix_courses_code", table_name="courses", if_exists=True)
    op.drop_constraint("courses_code_key", "courses", type_="unique")
    op.drop_column("courses", "code")
    op.drop_column("courses", "name")
    op.drop_column("courses", "credits")

    op.drop_index("ix_courses_program_id", table_name="courses", if_exists=True)
    op.drop_column("courses", "program_id")


def downgrade() -> None:
    # ── Restaurar columnas en courses ────────────────────────────────────────
    op.add_column("courses", sa.Column("program_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("courses", sa.Column("credits", sa.Integer(), nullable=True))
    op.add_column("courses", sa.Column("name", sa.String(), nullable=True))
    op.add_column("courses", sa.Column("code", sa.String(), nullable=True))

    # Repoblar desde subjects
    op.execute("""
        UPDATE courses c
        SET code       = s.code,
            name       = s.name,
            credits    = s.credits,
            program_id = s.program_id
        FROM subjects s
        WHERE s.id = c.subject_id
    """)

    op.alter_column("courses", "code", nullable=False)
    op.alter_column("courses", "name", nullable=False)
    op.alter_column("courses", "credits", nullable=False)
    op.alter_column("courses", "program_id", nullable=False)

    op.create_index("ix_courses_program_id", "courses", ["program_id"])
    op.create_index("ix_courses_code", "courses", ["code"])
    op.create_unique_constraint("courses_code_key", "courses", ["code"])
    op.create_foreign_key(
        "fk_courses_program_id", "courses", "programs", ["program_id"], ["id"]
    )

    # Eliminar lo agregado en upgrade
    op.drop_constraint("uq_course_subject_section_period", "courses", type_="unique")
    op.drop_index("ix_courses_subject_id", table_name="courses")
    op.drop_constraint("fk_courses_subject_id", "courses", type_="foreignkey")
    op.drop_column("courses", "section")
    op.drop_column("courses", "subject_id")

    op.drop_index("ix_subjects_program_id", table_name="subjects")
    op.drop_index("ix_subjects_code", table_name="subjects")
    op.drop_table("subjects")
