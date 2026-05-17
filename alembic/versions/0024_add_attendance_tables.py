"""Add class_sessions and attendances tables for QR attendance.

Revision ID: 0024
Revises: 0023
Create Date: 2026-05-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "class_sessions",
        sa.Column("id",             sa.Uuid(),     primary_key=True, nullable=False),
        sa.Column("course_id",      sa.Uuid(),     nullable=False),
        sa.Column("professor_id",   sa.Uuid(),     nullable=False),
        sa.Column("window_seconds", sa.Integer(),  nullable=False, server_default="60"),
        sa.Column("qr_seed",        sa.Text(),     nullable=False),
        sa.Column("label",          sa.Text(),     nullable=True),
        sa.Column("is_active",      sa.Boolean(),  nullable=False, server_default="true"),
        sa.Column("created_at",     sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("closed_at",      sa.DateTime(), nullable=True),
    )
    op.create_index("ix_class_sessions_course_id", "class_sessions", ["course_id"])

    op.create_table(
        "attendances",
        sa.Column("id",            sa.Uuid(),     primary_key=True, nullable=False),
        sa.Column("session_id",    sa.Uuid(),     nullable=False),
        sa.Column("student_id",    sa.Uuid(),     nullable=False),
        sa.Column("recorded_at",   sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("qr_token_used", sa.Text(),     nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["class_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"],  ["users.id"],         ondelete="CASCADE"),
    )
    op.create_index("ix_attendances_session_id", "attendances", ["session_id"])
    op.create_index("ix_attendances_student_id", "attendances", ["student_id"])
    # Un estudiante solo puede registrar una asistencia por sesión
    op.create_unique_constraint(
        "uq_attendance_student_session", "attendances", ["student_id", "session_id"]
    )

    # Columna phone en users (solo si no existe — ya fue agregada manualmente en local)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='users' AND column_name='phone'
            ) THEN
                ALTER TABLE users ADD COLUMN phone VARCHAR;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS phone")
    op.drop_index("ix_attendances_student_id",  table_name="attendances")
    op.drop_index("ix_attendances_session_id",  table_name="attendances")
    op.drop_table("attendances")
    op.drop_index("ix_class_sessions_course_id", table_name="class_sessions")
    op.drop_table("class_sessions")
