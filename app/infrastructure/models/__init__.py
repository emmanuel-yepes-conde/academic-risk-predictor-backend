"""
Modelos ORM SQLModel para la capa de infraestructura.
"""

from app.infrastructure.models.user import User
from app.infrastructure.models.course import Course
from app.infrastructure.models.enrollment import Enrollment
from app.infrastructure.models.audit_log import AuditLog
from app.infrastructure.models.consent import Consent
from app.infrastructure.models.program import Program
from app.infrastructure.models.student_profile import StudentProfile

__all__ = [
    "User",
    "Course",
    "Enrollment",
    "AuditLog",
    "Consent",
    "Program",
    "StudentProfile",
]
