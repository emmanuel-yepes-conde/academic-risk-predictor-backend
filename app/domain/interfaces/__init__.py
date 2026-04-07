from app.domain.interfaces.user_repository import IUserRepository
from app.domain.interfaces.course_repository import ICourseRepository
from app.domain.interfaces.audit_log_repository import IAuditLogRepository
from app.domain.interfaces.consent_repository import IConsentRepository

__all__ = [
    "IUserRepository",
    "ICourseRepository",
    "IAuditLogRepository",
    "IConsentRepository",
]
