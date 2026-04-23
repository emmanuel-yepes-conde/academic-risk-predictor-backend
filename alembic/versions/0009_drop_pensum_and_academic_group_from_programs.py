"""drop_pensum_and_academic_group_from_programs

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("programs", "pensum")
    op.drop_column("programs", "academic_group")


def downgrade() -> None:
    op.add_column(
        "programs",
        sa.Column("academic_group", sqlmodel.AutoString(), nullable=False, server_default=""),
    )
    op.add_column(
        "programs",
        sa.Column("pensum", sqlmodel.AutoString(), nullable=False, server_default=""),
    )
