"""Fix subject code uniqueness: global → per program.

Revision ID: 0015
Revises: 0014
Create Date: 2026-05-05

Cambios:
- Elimina constraint UNIQUE global en subjects.code (uq_subjects_code).
- Crea constraint UNIQUE compuesto en (code, program_id) (uq_subject_code_program).
  Mismo código puede existir en distintos programas.
"""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_subjects_code", "subjects", type_="unique")
    op.create_unique_constraint(
        "uq_subject_code_program",
        "subjects",
        ["code", "program_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_subject_code_program", "subjects", type_="unique")
    op.create_unique_constraint("uq_subjects_code", "subjects", ["code"])
