from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from app.domain.enums import EnrollmentStatusEnum
    from app.infrastructure.models.enrollment import Enrollment


class IEnrollmentRepository(ABC):
    """Interface for enrollment persistence operations (Req 1.1, 2.1, 3.1, 4.1, 5.1)."""

    @abstractmethod
    async def create(self, data: dict, user_id: UUID) -> Enrollment: ...

    @abstractmethod
    async def get_by_id(self, enrollment_id: UUID) -> Enrollment | None: ...

    @abstractmethod
    async def get_by_student_and_course(
        self, student_id: UUID, course_id: UUID
    ) -> Enrollment | None: ...

    @abstractmethod
    async def update_course(
        self, enrollment_id: UUID, new_course_id: UUID, user_id: UUID
    ) -> Enrollment | None: ...

    @abstractmethod
    async def update_status(
        self, enrollment_id: UUID, status: EnrollmentStatusEnum, user_id: UUID
    ) -> Enrollment | None: ...

    @abstractmethod
    async def list_by_student(
        self, student_id: UUID, status: EnrollmentStatusEnum | None = None
    ) -> list[Enrollment]: ...

    @abstractmethod
    async def list_by_student_filtered_by_professor(
        self, student_id: UUID, professor_id: UUID,
        status: EnrollmentStatusEnum | None = None,
    ) -> list[Enrollment]: ...

    @abstractmethod
    async def list_by_course(
        self, course_id: UUID, status: EnrollmentStatusEnum | None = None
    ) -> list[Enrollment]: ...

    @abstractmethod
    async def update_grades(
        self,
        enrollment_id: UUID,
        grades: dict,
        first_cohort_grade: float | None,
        second_cohort_grade: float | None,
        third_cohort_grade: float | None,
        final_grade: float | None,
        user_id: UUID,
    ) -> "Enrollment | None": ...
