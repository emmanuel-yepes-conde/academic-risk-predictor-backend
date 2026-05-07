"""add_grades_to_enrollments

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-03 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Estructura JSONB que almacena la configuración de cortes y notas del estudiante.
    # Ejemplo de estructura esperada:
    # {
    #   "first_cohort": {
    #     "weight": "30%",
    #     "parcial": {"note": 3.0, "weight": "20%"},
    #     "seguimiento": {
    #       "activity_one": {"note": 4.0, "weight": "5%"},
    #       "activity_two": {"note": 4.5, "weight": "5%"}
    #     }
    #   },
    #   "second_cohort": { ... },
    #   "third_cohort": { ... }
    # }
    op.add_column(
        "enrollments",
        sa.Column("grades", JSONB, nullable=True),
    )

    # Columnas calculadas: se recalculan en código al actualizar grades.
    # Escala 0.0–5.0, nota mínima aprobatoria 3.0.
    op.add_column(
        "enrollments",
        sa.Column("first_cohort_grade", sa.Numeric(precision=3, scale=2), nullable=True),
    )
    op.add_column(
        "enrollments",
        sa.Column("second_cohort_grade", sa.Numeric(precision=3, scale=2), nullable=True),
    )
    op.add_column(
        "enrollments",
        sa.Column("third_cohort_grade", sa.Numeric(precision=3, scale=2), nullable=True),
    )
    op.add_column(
        "enrollments",
        sa.Column("final_grade", sa.Numeric(precision=3, scale=2), nullable=True),
    )

    # Índice GIN para queries sobre el contenido del JSONB.
    op.create_index(
        "ix_enrollments_grades",
        "enrollments",
        ["grades"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index("ix_enrollments_grades", table_name="enrollments")
    op.drop_column("enrollments", "final_grade")
    op.drop_column("enrollments", "third_cohort_grade")
    op.drop_column("enrollments", "second_cohort_grade")
    op.drop_column("enrollments", "first_cohort_grade")
    op.drop_column("enrollments", "grades")
