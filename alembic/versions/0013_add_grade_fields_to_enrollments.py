"""add grade fields to enrollments

Adds academic indicator columns to the enrollments table so that professors
can record student grades and the ML predictor can read them directly.

Columns added:
  asistencia           NUMERIC(5,2)  — attendance percentage 0-100
  seguimiento          NUMERIC(3,2)  — engagement/follow-up grade 0-5
  nota_parcial_1       NUMERIC(3,2)  — first partial exam grade 0-5
  logins               INTEGER       — LMS session count
  uso_tutorias         BOOLEAN       — whether the student uses tutoring

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-01
"""
from alembic import op
import sqlalchemy as sa

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('enrollments', sa.Column('asistencia',     sa.Numeric(5, 2), nullable=True))
    op.add_column('enrollments', sa.Column('seguimiento',    sa.Numeric(3, 2), nullable=True))
    op.add_column('enrollments', sa.Column('nota_parcial_1', sa.Numeric(3, 2), nullable=True))
    op.add_column('enrollments', sa.Column('logins',         sa.Integer(),     nullable=True))
    op.add_column('enrollments', sa.Column('uso_tutorias',   sa.Boolean(),     nullable=True))


def downgrade() -> None:
    op.drop_column('enrollments', 'uso_tutorias')
    op.drop_column('enrollments', 'logins')
    op.drop_column('enrollments', 'nota_parcial_1')
    op.drop_column('enrollments', 'seguimiento')
    op.drop_column('enrollments', 'asistencia')
