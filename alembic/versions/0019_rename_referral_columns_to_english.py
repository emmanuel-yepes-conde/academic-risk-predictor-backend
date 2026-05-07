"""rename referral columns to english

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-05

Renames Spanish column names in `referrals` to English snake_case
to match the naming standard of all other tables.

  tipo_remision        → referral_type
  tipo_remision_otro   → referral_type_other
  observaciones        → observations
  observaciones_remision → counselor_observations
  fecha_remision       → referral_date
  asistio              → attended
"""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

_RENAMES = [
    ("tipo_remision",         "referral_type"),
    ("tipo_remision_otro",    "referral_type_other"),
    ("observaciones",         "observations"),
    ("observaciones_remision","counselor_observations"),
    ("fecha_remision",        "referral_date"),
    ("asistio",               "attended"),
]


def upgrade() -> None:
    for old, new in _RENAMES:
        op.alter_column("referrals", old, new_column_name=new)


def downgrade() -> None:
    for old, new in _RENAMES:
        op.alter_column("referrals", new, new_column_name=old)
