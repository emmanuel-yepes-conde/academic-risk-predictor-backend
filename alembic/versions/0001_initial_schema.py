"""initial_schema

Revision ID: 0001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sqlmodel.AutoString(), nullable=False),
        sa.Column("full_name", sqlmodel.AutoString(), nullable=False),
        sa.Column(
            "role",
            sa.Enum("STUDENT", "PROFESSOR", "ADMIN", name="roleenum"),
            nullable=False,
        ),
        sa.Column("microsoft_oid", sqlmodel.AutoString(), nullable=True),
        sa.Column("google_oid", sqlmodel.AutoString(), nullable=True),
        sa.Column("password_hash", sqlmodel.AutoString(), nullable=True),
        sa.Column("ml_consent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("microsoft_oid"),
        sa.UniqueConstraint("google_oid"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    # --- courses ---
    op.create_table(
        "courses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sqlmodel.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.AutoString(), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("academic_period", sqlmodel.AutoString(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_courses_code"), "courses", ["code"], unique=True)

    # --- enrollments ---
    op.create_table(
        "enrollments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("enrollment_date", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id", "course_id"),
    )

    # --- professor_courses ---
    op.create_table(
        "professor_courses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("professor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"]),
        sa.ForeignKeyConstraint(["professor_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("professor_id", "course_id"),
    )

    # --- audit_logs ---
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("table_name", sqlmodel.AutoString(), nullable=False),
        sa.Column(
            "operation",
            sa.Enum("INSERT", "UPDATE", "DELETE", name="operationenum"),
            nullable=False,
        ),
        sa.Column("record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("previous_data", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("new_data", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_logs_timestamp"), "audit_logs", ["timestamp"], unique=False)

    # --- consents ---
    op.create_table(
        "consents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("terms_version", sqlmodel.AutoString(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_id"),
    )


def downgrade() -> None:
    op.drop_table("consents")
    op.drop_index(op.f("ix_audit_logs_timestamp"), table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_table("professor_courses")
    op.drop_table("enrollments")
    op.drop_index(op.f("ix_courses_code"), table_name="courses")
    op.drop_table("courses")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS roleenum")
    op.execute("DROP TYPE IF EXISTS operationenum")
