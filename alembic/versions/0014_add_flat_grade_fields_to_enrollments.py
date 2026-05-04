"""add flat grade fields to enrollments

Revision ID: 0014
Revises: 0013
Create Date: 2026-05-03

Adds asistencia, seguimiento, nota_parcial_1, logins, uso_tutorias columns.
Uses IF NOT EXISTS so it is safe to run even if the columns were already
added manually or by a previous migration attempt.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.exc import ProgrammingError

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def _add_if_not_exists(table, column):
    try:
        op.add_column(table, column)
    except ProgrammingError:
        pass  # column already exists


def upgrade() -> None:
    _add_if_not_exists('enrollments', sa.Column('asistencia',     sa.Numeric(5, 2), nullable=True))
    _add_if_not_exists('enrollments', sa.Column('seguimiento',    sa.Numeric(3, 2), nullable=True))
    _add_if_not_exists('enrollments', sa.Column('nota_parcial_1', sa.Numeric(3, 2), nullable=True))
    _add_if_not_exists('enrollments', sa.Column('logins',         sa.Integer(),     nullable=True))
    _add_if_not_exists('enrollments', sa.Column('uso_tutorias',   sa.Boolean(),     nullable=True))


def downgrade() -> None:
    op.drop_column('enrollments', 'uso_tutorias')
    op.drop_column('enrollments', 'logins')
    op.drop_column('enrollments', 'nota_parcial_1')
    op.drop_column('enrollments', 'seguimiento')
    op.drop_column('enrollments', 'asistencia')
