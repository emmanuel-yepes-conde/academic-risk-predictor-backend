"""add last_login to users

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-24
"""
from alembic import op
import sqlalchemy as sa

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ADD COLUMN IF NOT EXISTS — safe to run even if the column was already added manually
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login TIMESTAMP WITH TIME ZONE")


def downgrade() -> None:
    op.drop_column('users', 'last_login')
