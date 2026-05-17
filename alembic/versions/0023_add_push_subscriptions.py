"""Add push_subscriptions table for Web Push Notifications (VAPID).

Revision ID: 0023
Revises: 0022
Create Date: 2026-05-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id",         sa.Uuid(),     primary_key=True, nullable=False),
        sa.Column("user_id",    sa.Uuid(),     nullable=False),
        sa.Column("endpoint",   sa.Text(),     nullable=False),
        sa.Column("p256dh",     sa.Text(),     nullable=False),
        sa.Column("auth",       sa.Text(),     nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_push_subs_user_id", "push_subscriptions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_push_subs_user_id", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
