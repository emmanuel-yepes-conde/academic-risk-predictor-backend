"""
Modelos ORM SQLModel para la capa de infraestructura.
"""

from app.infrastructure.models.user import User
from app.infrastructure.models.course import Course
from app.infrastructure.models.enrollment import Enrollment
from app.infrastructure.models.professor_course import ProfessorCourse
from app.infrastructure.models.audit_log import AuditLog
from app.infrastructure.models.consent import Consent

__all__ = [
    "User",
    "Course",
    "Enrollment",
    "ProfessorCourse",
    "AuditLog",
    "Consent",
]
