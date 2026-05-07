"""Add flat indicator columns to enrollments (asistencia, seguimiento, etc).

Revision ID: 0020
Revises: 0019
Create Date: 2026-05-06

These columns were in the ORM model but never created in the DB because the
original migration (0014_add_flat_grade_fields) was replaced during refactoring
without preserving these additions.
"""

from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE enrollments
            ADD COLUMN IF NOT EXISTS asistencia     NUMERIC(5, 2),
            ADD COLUMN IF NOT EXISTS seguimiento    NUMERIC(3, 2),
            ADD COLUMN IF NOT EXISTS nota_parcial_1 NUMERIC(3, 2),
            ADD COLUMN IF NOT EXISTS logins         INTEGER,
            ADD COLUMN IF NOT EXISTS uso_tutorias   BOOLEAN
    """)


def downgrade() -> None:
    op.drop_column("enrollments", "uso_tutorias")
    op.drop_column("enrollments", "logins")
    op.drop_column("enrollments", "nota_parcial_1")
    op.drop_column("enrollments", "seguimiento")
    op.drop_column("enrollments", "asistencia")
