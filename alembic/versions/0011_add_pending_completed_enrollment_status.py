"""add_pending_completed_enrollment_status

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-22 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE enrollmentstatusenum ADD VALUE IF NOT EXISTS 'PENDING'")
    op.execute("ALTER TYPE enrollmentstatusenum ADD VALUE IF NOT EXISTS 'COMPLETED'")


def downgrade() -> None:
    # PostgreSQL does not support DROP VALUE from an enum type.
    # Downgrade is a no-op to avoid data loss in records with PENDING or COMPLETED.
    pass
