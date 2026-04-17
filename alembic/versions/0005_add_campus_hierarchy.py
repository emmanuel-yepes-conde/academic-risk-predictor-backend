"""add_campus_hierarchy

Revision ID: 0005
Revises: 0004
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------------------------------------------------------
    # 1. Crear tabla campuses con esquema completo
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
    # 2. Agregar campus_id como nullable a programs
    # ---------------------------------------------------------------
    op.add_column(
        "programs",
        sa.Column("campus_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # ---------------------------------------------------------------
    # 3. Data migration: poblar campuses desde programs.campus
    #    Maneja BD vacía sin errores (los SELECTs simplemente no
    #    retornan filas y los INSERTs/UPDATEs no ejecutan nada).
    # ---------------------------------------------------------------
    conn = op.get_bind()

    # 3a. Insertar campuses únicos a partir de valores existentes
    conn.execute(
        sa.text(
            """
            INSERT INTO campuses (id, university_id, campus_code, name, city, active, created_at)
            SELECT
                gen_random_uuid(),
                p.university_id,
                p.campus,
                p.campus,
                'Por definir',
                true,
                now()
            FROM (
                SELECT DISTINCT university_id, campus
                FROM programs
            ) AS p
            """
        )
    )

    # 3b. Asignar campus_id a cada programa existente
    conn.execute(
        sa.text(
            """
            UPDATE programs
            SET campus_id = c.id
            FROM campuses c
            WHERE c.university_id = programs.university_id
              AND c.campus_code = programs.campus
            """
        )
    )

    # ---------------------------------------------------------------
    # 4. ALTER campus_id a NOT NULL y crear FK + índice
    # ---------------------------------------------------------------
    op.alter_column(
        "programs",
        "campus_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
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
    # 5. Cambiar UniqueConstraint: university scope → campus scope
    # ---------------------------------------------------------------
    op.drop_constraint("uq_program_code_university", "programs", type_="unique")
    op.create_unique_constraint(
        "uq_program_code_campus",
        "programs",
        ["program_code", "campus_id"],
    )

    # ---------------------------------------------------------------
    # 6. Eliminar columna campus (texto) de programs
    # ---------------------------------------------------------------
    op.drop_column("programs", "campus")


def downgrade() -> None:
    # ---------------------------------------------------------------
    # 1. Agregar columna campus (texto, nullable inicialmente)
    # ---------------------------------------------------------------
    op.add_column(
        "programs",
        sa.Column("campus", sqlmodel.AutoString(), nullable=True),
    )

    # ---------------------------------------------------------------
    # 2. Repoblar campus texto desde la tabla campuses
    #    Maneja BD vacía sin errores.
    # ---------------------------------------------------------------
    conn = op.get_bind()

    conn.execute(
        sa.text(
            """
            UPDATE programs
            SET campus = c.campus_code
            FROM campuses c
            WHERE c.id = programs.campus_id
            """
        )
    )

    # ---------------------------------------------------------------
    # 3. ALTER campus a NOT NULL
    # ---------------------------------------------------------------
    op.alter_column(
        "programs",
        "campus",
        existing_type=sa.String(),
        nullable=False,
    )

    # ---------------------------------------------------------------
    # 4. Revertir UniqueConstraint: campus scope → university scope
    # ---------------------------------------------------------------
    op.drop_constraint("uq_program_code_campus", "programs", type_="unique")
    op.create_unique_constraint(
        "uq_program_code_university",
        "programs",
        ["program_code", "university_id"],
    )

    # ---------------------------------------------------------------
    # 5. Eliminar campus_id de programs
    # ---------------------------------------------------------------
    op.drop_index(op.f("ix_programs_campus_id"), table_name="programs")
    op.drop_constraint("fk_programs_campus_id", "programs", type_="foreignkey")
    op.drop_column("programs", "campus_id")

    # ---------------------------------------------------------------
    # 6. Eliminar tabla campuses
    # ---------------------------------------------------------------
    op.drop_index(op.f("ix_campuses_campus_code"), table_name="campuses")
    op.drop_index(op.f("ix_campuses_university_id"), table_name="campuses")
    op.drop_table("campuses")
