"""Application schemas (DTOs)."""

from app.application.schemas.campus import CampusCreate, CampusRead, CampusUpdate
from app.application.schemas.university import UniversityCreate, UniversityRead, UniversityUpdate
from app.application.schemas.professor_course import ProfessorAssign, ProfessorCourseRead
from app.application.schemas.course import CourseCreate, CourseRead
from app.application.schemas.user import PaginatedResponse, UserRead

__all__ = [
    "CampusCreate",
    "CampusRead",
    "CampusUpdate",
    "UniversityCreate",
    "UniversityRead",
    "UniversityUpdate",
    "ProfessorAssign",
    "ProfessorCourseRead",
    "CourseCreate",
    "CourseRead",
    "PaginatedResponse",
    "UserRead",
]
