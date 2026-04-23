"""add_course_status

Revision ID: 0008
Revises: 0007
Create Date: 2024-01-08 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE coursestatusenum AS ENUM ('ACTIVE', 'INACTIVE')")
    op.add_column(
        "courses",
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "INACTIVE", name="coursestatusenum"),
            nullable=False,
            server_default="ACTIVE",
        ),
    )


def downgrade() -> None:
    op.drop_column("courses", "status")
    op.execute("DROP TYPE IF EXISTS coursestatusenum")
