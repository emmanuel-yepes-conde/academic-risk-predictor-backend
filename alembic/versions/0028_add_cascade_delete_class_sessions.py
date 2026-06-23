"""add_cascade_delete_to_class_sessions

Revision ID: 0028
Revises: 0027
Create Date: 2026-06-23 00:00:00.000000

Cierra el último hueco de la cadena de borrado en cascada de
materias/secciones. `class_sessions.course_id` solo tenía un índice,
sin FK, por lo que al eliminar un curso quedaban sesiones huérfanas.

Cadena completa tras esta migración:
  subjects → courses → enrollments → referrals      (CASCADE)
  subjects → courses → class_sessions → attendances (CASCADE)

Las asistencias ya borran en cascada desde class_sessions (mig 0024).
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Limpiar sesiones huérfanas previas (sin FK no estaban garantizadas).
    op.execute(
        "DELETE FROM class_sessions "
        "WHERE course_id NOT IN (SELECT id FROM courses)"
    )
    op.create_foreign_key(
        "fk_class_sessions_course_id",
        "class_sessions",
        "courses",
        ["course_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_class_sessions_course_id", "class_sessions", type_="foreignkey"
    )
