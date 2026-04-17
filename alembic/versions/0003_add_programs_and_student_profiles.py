"""add_programs_and_student_profiles

Revision ID: 0003
Revises: 0002
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
import sqlmodel
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- programs ---
    op.create_table(
        "programs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("institution", sqlmodel.AutoString(), nullable=False),
        sa.Column("campus", sqlmodel.AutoString(), nullable=False),
        sa.Column("degree_type", sqlmodel.AutoString(), nullable=False),
        sa.Column("program_code", sqlmodel.AutoString(), nullable=False),
        sa.Column("program_name", sqlmodel.AutoString(), nullable=False),
        sa.Column("pensum", sqlmodel.AutoString(), nullable=False),
        sa.Column("academic_group", sqlmodel.AutoString(), nullable=False),
        sa.Column("location", sqlmodel.AutoString(), nullable=False),
        sa.Column("snies_code", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("program_code"),
        sa.UniqueConstraint("snies_code"),
    )
    op.create_index(
        op.f("ix_programs_program_code"), "programs", ["program_code"], unique=True
    )
    op.create_index(
        op.f("ix_programs_snies_code"), "programs", ["snies_code"], unique=True
    )

    # --- student_profiles ---
    op.create_table(
        "student_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_institutional_id", sqlmodel.AutoString(), nullable=False),
        sa.Column("document_type", sqlmodel.AutoString(), nullable=False),
        sa.Column("document_number", sqlmodel.AutoString(), nullable=False),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("gender", sqlmodel.AutoString(), nullable=True),
        sa.Column("phone", sqlmodel.AutoString(), nullable=True),
        sa.Column("socioeconomic_stratum", sa.Integer(), nullable=True),
        sa.Column("academic_cycle", sa.Integer(), nullable=True),
        sa.Column("academic_year", sa.Integer(), nullable=True),
        sa.Column("semester", sa.Integer(), nullable=True),
        sa.Column("program_action", sqlmodel.AutoString(), nullable=True),
        sa.Column("enrollment_status", sqlmodel.AutoString(), nullable=True),
        sa.Column("enrolled_credits", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("other_credits", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("academic_level", sa.Integer(), nullable=True),
        sa.Column("cohort", sqlmodel.AutoString(), nullable=True),
        sa.Column("action_reason", sqlmodel.AutoString(), nullable=True),
        sa.Column("program_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["program_id"], ["programs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
        sa.UniqueConstraint("student_institutional_id"),
    )
    op.create_index(
        op.f("ix_student_profiles_user_id"),
        "student_profiles",
        ["user_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_student_profiles_student_institutional_id"),
        "student_profiles",
        ["student_institutional_id"],
        unique=True,
    )

    # --- users: agregar institutional_email ---
    op.add_column(
        "users",
        sa.Column("institutional_email", sqlmodel.AutoString(), nullable=True),
    )
    op.create_unique_constraint(
        "uq_users_institutional_email", "users", ["institutional_email"]
    )
    op.create_index(
        op.f("ix_users_institutional_email"),
        "users",
        ["institutional_email"],
        unique=True,
    )

    # --- courses: agregar program_id ---
    op.add_column(
        "courses",
        sa.Column("program_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_courses_program_id", "courses", "programs", ["program_id"], ["id"]
    )


def downgrade() -> None:
    # Revert in reverse order
    op.drop_constraint("fk_courses_program_id", "courses", type_="foreignkey")
    op.drop_column("courses", "program_id")

    op.drop_index(op.f("ix_users_institutional_email"), table_name="users")
    op.drop_constraint("uq_users_institutional_email", "users", type_="unique")
    op.drop_column("users", "institutional_email")

    op.drop_index(
        op.f("ix_student_profiles_student_institutional_id"),
        table_name="student_profiles",
    )
    op.drop_index(
        op.f("ix_student_profiles_user_id"), table_name="student_profiles"
    )
    op.drop_table("student_profiles")

    op.drop_index(op.f("ix_programs_snies_code"), table_name="programs")
    op.drop_index(op.f("ix_programs_program_code"), table_name="programs")
    op.drop_table("programs")
