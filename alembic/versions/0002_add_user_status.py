"""add_user_status

Revision ID: 0002
Revises: 0001
Create Date: 2024-01-02 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE userstatusenum AS ENUM ('ACTIVE', 'INACTIVE')")
    op.add_column(
        "users",
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "INACTIVE", name="userstatusenum"),
            nullable=False,
            server_default="ACTIVE",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "status")
    op.execute("DROP TYPE IF EXISTS userstatusenum")
