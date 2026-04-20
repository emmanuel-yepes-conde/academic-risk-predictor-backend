"""Application schemas (DTOs)."""

from app.application.schemas.professor_course import ProfessorAssign, ProfessorCourseRead
from app.application.schemas.course import CourseCreate, CourseRead
from app.application.schemas.user import PaginatedResponse, UserRead

__all__ = [
    "ProfessorAssign",
    "ProfessorCourseRead",
    "CourseCreate",
    "CourseRead",
    "PaginatedResponse",
    "UserRead",
]
