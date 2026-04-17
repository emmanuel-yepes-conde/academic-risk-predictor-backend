"""Infrastructure repositories."""

from app.infrastructure.repositories.audit_log_repository import AuditLogRepository
from app.infrastructure.repositories.campus_repository import CampusRepository
from app.infrastructure.repositories.consent_repository import ConsentRepository
from app.infrastructure.repositories.course_repository import CourseRepository
from app.infrastructure.repositories.program_repository import ProgramRepository
from app.infrastructure.repositories.university_repository import UniversityRepository
from app.infrastructure.repositories.user_repository import UserRepository

__all__ = [
    "AuditLogRepository",
    "CampusRepository",
    "ConsentRepository",
    "CourseRepository",
    "ProgramRepository",
    "UniversityRepository",
    "UserRepository",
]
