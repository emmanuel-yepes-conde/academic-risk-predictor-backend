"""
Enrollment repository implementation (Req 1.1, 1.8, 2.1, 2.6, 3.1, 3.3, 4.1, 4.4, 5.1).
Each write operation registers an atomic AuditLog entry in the same session.
get_by_student_and_course does NOT filter by status — intentional for reactivation detection.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.schemas.audit_log import AuditLogCreate
from app.domain.enums import EnrollmentStatusEnum, OperationEnum
from app.domain.interfaces.enrollment_repository import IEnrollmentRepository
from app.infrastructure.models.course import Course
from app.infrastructure.models.enrollment import Enrollment
from app.infrastructure.repositories.audit_log_repository import AuditLogRepository


class EnrollmentRepository(IEnrollmentRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._audit = AuditLogRepository(session)

    async def create(self, data: dict, user_id: UUID) -> Enrollment:
        """Persist a new Enrollment and register an INSERT audit log."""
        enrollment = Enrollment(**data)
        self._session.add(enrollment)
        await self._session.flush()
        await self._session.refresh(enrollment)
        await self._audit.register(AuditLogCreate(
            table_name="enrollments",
            operation=OperationEnum.INSERT,
            record_id=enrollment.id,
            user_id=user_id,
            new_data=data,
        ))
        return enrollment

    async def get_by_id(self, enrollment_id: UUID) -> Enrollment | None:
        """SELECT enrollment by ID."""
        result = await self._session.execute(
            select(Enrollment).where(Enrollment.id == enrollment_id)
        )
        return result.scalar_one_or_none()

    async def get_by_student_and_course(
        self, student_id: UUID, course_id: UUID
    ) -> Enrollment | None:
        """
        SELECT by (student_id, course_id) without status filter.
        This is intentional so the service layer can detect CANCELLED enrollments
        for reactivation.
        """
        result = await self._session.execute(
            select(Enrollment).where(
                Enrollment.student_id == student_id,
                Enrollment.course_id == course_id,
            )
        )
        return result.scalar_one_or_none()

    async def update_course(
        self, enrollment_id: UUID, new_course_id: UUID, user_id: UUID
    ) -> Enrollment | None:
        """UPDATE course_id and register an UPDATE audit log with previous and new data."""
        enrollment = await self.get_by_id(enrollment_id)
        if enrollment is None:
            return None

        previous_course_id = enrollment.course_id
        enrollment.course_id = new_course_id

        self._session.add(enrollment)
        await self._session.flush()
        await self._session.refresh(enrollment)
        await self._audit.register(AuditLogCreate(
            table_name="enrollments",
            operation=OperationEnum.UPDATE,
            record_id=enrollment_id,
            user_id=user_id,
            previous_data={"course_id": previous_course_id},
            new_data={"course_id": new_course_id},
        ))
        return enrollment

    async def update_status(
        self, enrollment_id: UUID, status: EnrollmentStatusEnum, user_id: UUID
    ) -> Enrollment | None:
        """UPDATE status and register an UPDATE audit log with previous and new status."""
        enrollment = await self.get_by_id(enrollment_id)
        if enrollment is None:
            return None

        previous_status = enrollment.status
        enrollment.status = status

        self._session.add(enrollment)
        await self._session.flush()
        await self._session.refresh(enrollment)
        await self._audit.register(AuditLogCreate(
            table_name="enrollments",
            operation=OperationEnum.UPDATE,
            record_id=enrollment_id,
            user_id=user_id,
            previous_data={"status": previous_status},
            new_data={"status": status},
        ))
        return enrollment

    async def list_by_student(
        self, student_id: UUID, status: EnrollmentStatusEnum | None = None
    ) -> list[Enrollment]:
        """
        SELECT enrollments for a student with optional status filter.
        When status is None, returns all enrollments regardless of status.
        """
        stmt = select(Enrollment).where(Enrollment.student_id == student_id)
        if status is not None:
            stmt = stmt.where(Enrollment.status == status)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def update_grades(
        self,
        enrollment_id: UUID,
        grades: dict,
        first_cohort_grade: float | None,
        second_cohort_grade: float | None,
        third_cohort_grade: float | None,
        final_grade: float | None,
        user_id: UUID,
    ) -> Enrollment | None:
        """UPDATE grades JSON + calculated cohort/final grades and register an audit log."""
        enrollment = await self.get_by_id(enrollment_id)
        if enrollment is None:
            return None

        enrollment.grades = grades
        enrollment.first_cohort_grade = first_cohort_grade
        enrollment.second_cohort_grade = second_cohort_grade
        enrollment.third_cohort_grade = third_cohort_grade
        enrollment.final_grade = final_grade

        self._session.add(enrollment)
        await self._session.flush()
        await self._session.refresh(enrollment)
        await self._audit.register(AuditLogCreate(
            table_name="enrollments",
            operation=OperationEnum.UPDATE,
            record_id=enrollment_id,
            user_id=user_id,
            new_data={"grades": grades},
        ))
        return enrollment

    async def update_indicators(
        self,
        enrollment_id: UUID,
        fields: dict,
        user_id: UUID,
    ) -> "Enrollment | None":
        """UPDATE flat indicator columns and register an audit log."""
        from datetime import datetime, timezone

        enrollment = await self.get_by_id(enrollment_id)
        if enrollment is None:
            return None

        for key, value in fields.items():
            setattr(enrollment, key, value)
        enrollment.updated_at = datetime.now(timezone.utc)

        self._session.add(enrollment)
        await self._session.flush()
        await self._session.refresh(enrollment)
        await self._audit.register(AuditLogCreate(
            table_name="enrollments",
            operation=OperationEnum.UPDATE,
            record_id=enrollment_id,
            user_id=user_id,
            new_data=fields,
        ))
        return enrollment

    async def list_by_student_filtered_by_professor(
        self, student_id: UUID, professor_id: UUID,
        status: EnrollmentStatusEnum | None = None,
    ) -> list[Enrollment]:
        """
        SELECT enrollments with JOIN to courses WHERE professor_id matches (RB-04).
        When status is provided, filter by that status.
        When status is None, return all statuses.
        """
        stmt = (
            select(Enrollment)
            .join(Course, Enrollment.course_id == Course.id)
            .where(
                Enrollment.student_id == student_id,
                Course.professor_id == professor_id,
            )
        )
        if status is not None:
            stmt = stmt.where(Enrollment.status == status)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
