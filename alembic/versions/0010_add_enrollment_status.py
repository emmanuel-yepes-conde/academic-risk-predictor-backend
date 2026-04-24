"""add_enrollment_status

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-22 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE enrollmentstatusenum AS ENUM ('ACTIVE', 'CANCELLED')")
    op.add_column(
        "enrollments",
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "CANCELLED", name="enrollmentstatusenum"),
            nullable=False,
            server_default="ACTIVE",
        ),
    )
    op.add_column(
        "enrollments",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_enrollments_student_id", "enrollments", ["student_id"])
    op.create_index("ix_enrollments_course_id", "enrollments", ["course_id"])


def downgrade() -> None:
    op.drop_index("ix_enrollments_course_id")
    op.drop_index("ix_enrollments_student_id")
    op.drop_column("enrollments", "updated_at")
    op.drop_column("enrollments", "status")
    op.execute("DROP TYPE IF EXISTS enrollmentstatusenum")
