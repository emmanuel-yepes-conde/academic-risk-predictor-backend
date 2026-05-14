"""Drop flat indicator columns from enrollments.

Grades and ML features are managed via the grades JSONB column.
The flat columns (asistencia, seguimiento, nota_parcial_1, logins,
uso_tutorias) were redundant: the ML prediction endpoint extracts
nota_parcial_1 / seguimiento directly from grades and receives the
rest from the request body.

Revision ID: 0021
Revises: 0020
Create Date: 2026-05-06
"""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE enrollments
            DROP COLUMN IF EXISTS asistencia,
            DROP COLUMN IF EXISTS seguimiento,
            DROP COLUMN IF EXISTS nota_parcial_1,
            DROP COLUMN IF EXISTS logins,
            DROP COLUMN IF EXISTS uso_tutorias
    """)


def downgrade() -> None:
    import sqlalchemy as sa
    op.add_column("enrollments", sa.Column("asistencia",     sa.Numeric(5, 2), nullable=True))
    op.add_column("enrollments", sa.Column("seguimiento",    sa.Numeric(3, 2), nullable=True))
    op.add_column("enrollments", sa.Column("nota_parcial_1", sa.Numeric(3, 2), nullable=True))
    op.add_column("enrollments", sa.Column("logins",         sa.Integer(),     nullable=True))
    op.add_column("enrollments", sa.Column("uso_tutorias",   sa.Boolean(),     nullable=True))
