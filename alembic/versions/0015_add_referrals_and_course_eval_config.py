"""add_referrals_and_course_eval_config

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-04

Cambios:
  1. Nueva tabla `referrals` — remisiones a permanencia/consejería.
  2. Nueva columna `evaluation_config` JSONB en `courses` — configuración de cortes.
"""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Tabla referrals ───────────────────────────────────────────────────
    op.create_table(
        "referrals",
        sa.Column("id",                    sa.UUID(),          nullable=False, primary_key=True),
        sa.Column("enrollment_id",         sa.UUID(),          nullable=False),
        sa.Column("created_by",            sa.UUID(),          nullable=False),
        sa.Column("tipo_remision",         sa.VARCHAR(100),    nullable=False),
        sa.Column("tipo_remision_otro",    sa.Text(),          nullable=True),
        sa.Column("observaciones",         sa.Text(),          nullable=False),
        sa.Column("observaciones_remision",sa.Text(),          nullable=True),
        sa.Column("fecha_remision",        sa.Date(),          nullable=False),
        sa.Column("asistio",               sa.VARCHAR(20),     nullable=False, server_default="Sin confirmar"),
        sa.Column("status",                sa.VARCHAR(20),     nullable=False, server_default="PENDIENTE"),
        sa.Column("created_at",            sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at",            sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["enrollment_id"], ["enrollments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"],    ["users.id"],       ondelete="RESTRICT"),
    )
    op.create_index("ix_referrals_enrollment_id", "referrals", ["enrollment_id"])
    op.create_index("ix_referrals_created_by",    "referrals", ["created_by"])

    # ── 2. evaluation_config en courses ──────────────────────────────────────
    op.execute(
        "ALTER TABLE courses ADD COLUMN IF NOT EXISTS evaluation_config JSONB"
    )


def downgrade() -> None:
    op.drop_column("courses", "evaluation_config")
    op.drop_index("ix_referrals_created_by",    table_name="referrals")
    op.drop_index("ix_referrals_enrollment_id", table_name="referrals")
    op.drop_table("referrals")
