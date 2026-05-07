"""Add flat grade indicator columns to enrollments.

Revision ID: 0017
Revises: 0016
Create Date: 2026-05-05

Columns:
- asistencia (Numeric 5,2): attendance percentage 0–100
- seguimiento (Numeric 3,2): follow-up grade 0–5
- nota_parcial_1 (Numeric 3,2): first partial grade 0–5
- logins (Integer): LMS login count
- uso_tutorias (Boolean): whether student used tutoring
"""

from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "enrollments",
        sa.Column("asistencia", sa.Numeric(precision=5, scale=2), nullable=True),
    )
    op.add_column(
        "enrollments",
        sa.Column("seguimiento", sa.Numeric(precision=3, scale=2), nullable=True),
    )
    op.add_column(
        "enrollments",
        sa.Column("nota_parcial_1", sa.Numeric(precision=3, scale=2), nullable=True),
    )
    op.add_column(
        "enrollments",
        sa.Column("logins", sa.Integer(), nullable=True),
    )
    op.add_column(
        "enrollments",
        sa.Column("uso_tutorias", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("enrollments", "uso_tutorias")
    op.drop_column("enrollments", "logins")
    op.drop_column("enrollments", "nota_parcial_1")
    op.drop_column("enrollments", "seguimiento")
    op.drop_column("enrollments", "asistencia")
