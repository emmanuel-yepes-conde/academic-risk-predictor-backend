"""simplify_program_course_model

Revision ID: 0006
Revises: 0005
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------------------------------------------------------
    # 1. Eliminar constraint uq_program_code_campus de programs
    # ---------------------------------------------------------------
    op.drop_constraint("uq_program_code_campus", "programs", type_="unique")

    # ---------------------------------------------------------------
    # 2. Eliminar campus_id de programs (índice, FK, columna)
    # ---------------------------------------------------------------
    op.drop_index(op.f("ix_programs_campus_id"), table_name="programs")
    op.drop_constraint("fk_programs_campus_id", "programs", type_="foreignkey")
    op.drop_column("programs", "campus_id")

    # ---------------------------------------------------------------
    # 3. Eliminar university_id de programs (índice, FK, columna)
    # ---------------------------------------------------------------
    op.drop_index(op.f("ix_programs_university_id"), table_name="programs")
    op.drop_constraint("fk_programs_university_id", "programs", type_="foreignkey")
    op.drop_column("programs", "university_id")

    # ---------------------------------------------------------------
    # 4. Eliminar tabla campuses (índices primero)
    # ---------------------------------------------------------------
    op.drop_index(op.f("ix_campuses_campus_code"), table_name="campuses")
    op.drop_index(op.f("ix_campuses_university_id"), table_name="campuses")
    op.drop_table("campuses")

    # ---------------------------------------------------------------
    # 5. Eliminar tabla universities (índice primero)
    # ---------------------------------------------------------------
    op.drop_index(op.f("ix_universities_code"), table_name="universities")
    op.drop_table("universities")

    # ---------------------------------------------------------------
    # 6. Restaurar unicidad global de program_code
    #    (reemplaza el índice no-unique creado en 0004)
    # ---------------------------------------------------------------
    op.drop_index(op.f("ix_programs_program_code"), table_name="programs")
    op.create_index(
        op.f("ix_programs_program_code"), "programs", ["program_code"], unique=True
    )
    op.create_unique_constraint(
        "uq_programs_program_code", "programs", ["program_code"]
    )


def downgrade() -> None:
    # ---------------------------------------------------------------
    # 1. Eliminar unicidad global de program_code
    # ---------------------------------------------------------------
    op.drop_constraint("uq_programs_program_code", "programs", type_="unique")
    op.drop_index(op.f("ix_programs_program_code"), table_name="programs")

    # Restaurar índice no-unique (estado de 0004)
    op.create_index(
        op.f("ix_programs_program_code"), "programs", ["program_code"], unique=False
    )

    # ---------------------------------------------------------------
    # 2. Recrear tabla universities
    # ---------------------------------------------------------------
    op.create_table(
        "universities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sqlmodel.AutoString(), nullable=False),
        sa.Column("code", sqlmodel.AutoString(), nullable=False),
        sa.Column("country", sqlmodel.AutoString(), nullable=False),
        sa.Column("city", sqlmodel.AutoString(), nullable=False),
        sa.Column(
            "active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(
        op.f("ix_universities_code"), "universities", ["code"], unique=True
    )

    # ---------------------------------------------------------------
    # 3. Recrear tabla campuses
    # ---------------------------------------------------------------
    op.create_table(
        "campuses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("university_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campus_code", sqlmodel.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.AutoString(), nullable=False),
        sa.Column("city", sqlmodel.AutoString(), nullable=False),
        sa.Column(
            "active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["university_id"], ["universities.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "university_id", "campus_code", name="uq_university_campus_code"
        ),
    )
    op.create_index(
        op.f("ix_campuses_university_id"),
        "campuses",
        ["university_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_campuses_campus_code"),
        "campuses",
        ["campus_code"],
        unique=False,
    )

    # ---------------------------------------------------------------
    # 4. Agregar university_id a programs (nullable — datos perdidos)
    # ---------------------------------------------------------------
    op.add_column(
        "programs",
        sa.Column("university_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_programs_university_id",
        "programs",
        "universities",
        ["university_id"],
        ["id"],
    )
    op.create_index(
        op.f("ix_programs_university_id"),
        "programs",
        ["university_id"],
        unique=False,
    )

    # ---------------------------------------------------------------
    # 5. Agregar campus_id a programs (nullable — datos perdidos)
    # ---------------------------------------------------------------
    op.add_column(
        "programs",
        sa.Column("campus_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_programs_campus_id",
        "programs",
        "campuses",
        ["campus_id"],
        ["id"],
    )
    op.create_index(
        op.f("ix_programs_campus_id"),
        "programs",
        ["campus_id"],
        unique=False,
    )

    # ---------------------------------------------------------------
    # 6. Restaurar constraint uq_program_code_campus
    # ---------------------------------------------------------------
    op.create_unique_constraint(
        "uq_program_code_campus",
        "programs",
        ["program_code", "campus_id"],
    )
