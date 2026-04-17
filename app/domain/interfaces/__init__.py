from app.domain.interfaces.auth_provider import IAuthProvider
from app.domain.interfaces.user_repository import IUserRepository
from app.domain.interfaces.course_repository import ICourseRepository
from app.domain.interfaces.audit_log_repository import IAuditLogRepository
from app.domain.interfaces.consent_repository import IConsentRepository
from app.domain.interfaces.university_repository import IUniversityRepository
from app.domain.interfaces.campus_repository import ICampusRepository
from app.domain.interfaces.program_repository import IProgramRepository

__all__ = [
    "IAuthProvider",
    "IUserRepository",
    "ICourseRepository",
    "IAuditLogRepository",
    "IConsentRepository",
    "IUniversityRepository",
    "ICampusRepository",
    "IProgramRepository",
]
