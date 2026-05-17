"""0025 — notifications table + user notification preferences

Revision ID: 0025
Revises: 0024
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── user preference columns ──────────────────────────────────────────────
    # phone was added manually / in 0024 with IF NOT EXISTS, skip if present
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='users' AND column_name='phone'
            ) THEN
                ALTER TABLE users ADD COLUMN phone VARCHAR;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='users' AND column_name='whatsapp_enabled'
            ) THEN
                ALTER TABLE users ADD COLUMN whatsapp_enabled BOOLEAN NOT NULL DEFAULT TRUE;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='users' AND column_name='email_enabled'
            ) THEN
                ALTER TABLE users ADD COLUMN email_enabled BOOLEAN NOT NULL DEFAULT TRUE;
            END IF;
        END
        $$;
    """)

    # ── notifications table ──────────────────────────────────────────────────
    op.create_table(
        "notifications",
        sa.Column("id",         sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id",    sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("type",       sa.String(),  nullable=False),
        sa.Column("title",      sa.String(120), nullable=False),
        sa.Column("body",       sa.Text(),    nullable=False),
        sa.Column("data",       sa.JSON(),    nullable=True),
        sa.Column("read",       sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_notifications_user_id",    "notifications", ["user_id"])
    op.create_index("ix_notifications_read",       "notifications", ["read"])
    op.create_index("ix_notifications_created_at", "notifications", ["created_at"])
    op.create_foreign_key(
        "fk_notifications_user_id",
        "notifications", "users",
        ["user_id"], ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_table("notifications")
    op.drop_column("users", "email_enabled")
    op.drop_column("users", "whatsapp_enabled")
