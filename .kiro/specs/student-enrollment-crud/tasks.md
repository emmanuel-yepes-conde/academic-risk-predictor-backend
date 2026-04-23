# Implementation Plan: CRUD de Inscripciones de Estudiantes

## Overview

Implementar las operaciones CRUD completas para inscripciones (enrollments) de estudiantes en cursos, siguiendo la Clean Architecture existente (Domain → Application → Infrastructure). Se agregan campos `status` y `updated_at` al modelo Enrollment, se crea la interfaz de repositorio, repositorio con audit logging, servicio con lógica de negocio, schemas Pydantic y endpoints FastAPI. Todas las operaciones de escritura registran logs de auditoría y el acceso se controla mediante JWT con roles.

## Tasks

- [x] 1. Alembic migration and domain enum
  - [x] 1.1 Add `EnrollmentStatusEnum` to `app/domain/enums.py`
    - Add `EnrollmentStatusEnum(str, Enum)` with values `ACTIVE` and `CANCELLED`
    - Follow the same pattern as `CourseStatusEnum` and `UserStatusEnum`
    - _Requirements: 3.5_

  - [x] 1.2 Create Alembic migration `alembic/versions/0010_add_enrollment_status.py`
    - Add `status` column (Enum ACTIVE/CANCELLED, NOT NULL, server_default ACTIVE)
    - Add `updated_at` column (DateTime with timezone, NOT NULL, server_default now())
    - Create indexes `ix_enrollments_student_id` and `ix_enrollments_course_id`
    - Include proper `downgrade()` that drops indexes, columns, and enum type
    - _Requirements: 3.5_

  - [x] 1.3 Update `app/infrastructure/models/enrollment.py` with `status` and `updated_at` fields
    - Add `status: EnrollmentStatusEnum` field with default ACTIVE and `sa_column_kwargs={"server_default": "ACTIVE"}`
    - Add `updated_at: datetime` field with timezone-aware default
    - Add `index=True` to `student_id` and `course_id` fields
    - Update `enrollment_date` to use `datetime.now(timezone.utc)` (timezone-aware)
    - _Requirements: 3.5, 6.4_

- [x] 2. Domain interface and Pydantic schemas
  - [x] 2.1 Create `app/domain/interfaces/enrollment_repository.py` with `IEnrollmentRepository`
    - Define abstract methods: `create`, `get_by_id`, `get_by_student_and_course`, `update_course`, `update_status`, `list_by_student`, `list_by_student_filtered_by_professor`
    - Follow the same pattern as `ICourseRepository` with `ABC` and `@abstractmethod`
    - Use `TYPE_CHECKING` for type imports to avoid circular dependencies
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.1_

  - [x] 2.2 Create `app/application/schemas/enrollment.py` with Pydantic schemas
    - `EnrollmentCreate`: `student_id` (UUID) and `course_id` (UUID) with `Field(description=...)`
    - `EnrollmentUpdate`: `course_id` (UUID) with `Field(description=...)`
    - `EnrollmentStatusUpdate`: `status` (EnrollmentStatusEnum) with `Field(description=...)`
    - `EnrollmentRead`: all fields with `model_config = {"from_attributes": True}`
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

- [x] 3. Repository implementation
  - [x] 3.1 Create `app/infrastructure/repositories/enrollment_repository.py` implementing `IEnrollmentRepository`
    - Constructor receives `AsyncSession`, initializes `AuditLogRepository`
    - `create()`: INSERT enrollment + audit log with operation INSERT
    - `get_by_id()`: SELECT by ID
    - `get_by_student_and_course()`: SELECT by (student_id, course_id) without status filter
    - `update_course()`: UPDATE course_id + audit log with previous_data and new_data
    - `update_status()`: UPDATE status + audit log with previous and new status
    - `list_by_student()`: SELECT with optional status filter (default returns all)
    - `list_by_student_filtered_by_professor()`: SELECT with JOIN to courses WHERE professor_id matches AND status ACTIVE
    - Follow the same audit logging pattern as `CourseRepository`
    - _Requirements: 1.1, 1.8, 2.1, 2.6, 3.1, 3.3, 4.1, 4.4, 5.1_

  - [x] 3.2 Write unit tests for `EnrollmentRepository` in `tests/unit/test_enrollment_repository.py`
    - Test create persists enrollment and registers audit log
    - Test get_by_id returns enrollment or None
    - Test update_course changes course_id and registers audit log
    - Test update_status changes status and registers audit log
    - Test list_by_student returns filtered results
    - _Requirements: 1.1, 1.8, 2.1, 2.6, 3.1, 3.3_

- [x] 4. Checkpoint — Verify migration and repository layer
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Service layer implementation
  - [x] 5.1 Create `app/application/services/enrollment_service.py` with `EnrollmentService`
    - Constructor receives `IEnrollmentRepository` and `AsyncSession` (for auxiliary queries)
    - `create_enrollment(data, user_id)`: validate student exists with role STUDENT, validate course exists and ACTIVE, check for duplicate ACTIVE enrollment (409), reactivate CANCELLED enrollment if exists, otherwise create new
    - `update_enrollment(enrollment_id, data, user_id)`: validate enrollment exists, validate destination course exists and ACTIVE, check no duplicate in destination (409), update course_id
    - `cancel_enrollment(enrollment_id, user_id)`: validate enrollment exists, set status to CANCELLED
    - `get_enrollment(enrollment_id)`: validate enrollment exists, return detail
    - `list_student_enrollments(student_id, current_user)`: if PROFESSOR, filter by professor's courses (RB-04); if ADMIN, return all ACTIVE
    - All error messages in Spanish as defined in design error handling table
    - _Requirements: 1.1–1.9, 2.1–2.7, 3.1–3.5, 4.1–4.4, 5.1–5.3_

  - [x] 5.2 Write unit tests for `EnrollmentService` in `tests/unit/test_enrollment_service.py`
    - Test create_enrollment success (new enrollment)
    - Test create_enrollment reactivates CANCELLED enrollment
    - Test create_enrollment rejects duplicate ACTIVE (409)
    - Test create_enrollment rejects invalid student (422)
    - Test create_enrollment rejects invalid course (404)
    - Test update_enrollment success
    - Test update_enrollment rejects duplicate in destination (409)
    - Test cancel_enrollment success
    - Test get_enrollment returns detail
    - Test list_student_enrollments filters by professor (RB-04)
    - Use `AsyncMock` for repository and session dependencies
    - _Requirements: 1.1–1.9, 2.1–2.7, 3.1–3.5, 4.1–4.4, 5.1–5.3_

- [x] 6. Checkpoint — Verify service layer
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. API endpoints and router registration
  - [x] 7.1 Create `app/api/v1/endpoints/enrollments.py` with enrollment router
    - `POST /enrollments` — require ADMIN, status 201, create enrollment
    - `PATCH /enrollments/{enrollment_id}` — require ADMIN, status 200, update course
    - `PATCH /enrollments/{enrollment_id}/status` — require ADMIN, status 200, cancel enrollment
    - `GET /enrollments/{enrollment_id}` — require ADMIN, status 200, get detail
    - `GET /students/{student_id}/enrollments` — require ADMIN or PROFESSOR, status 200, list enrollments
    - Use dependency injection for `EnrollmentService` (same pattern as courses.py)
    - Include `summary`, `description`, `response_model`, `status_code`, and `tags=["Inscripciones"]` on every endpoint
    - _Requirements: 1.1, 1.9, 2.1, 2.7, 3.1, 3.4, 4.1, 4.3, 5.1, 5.3_

  - [x] 7.2 Register enrollment router in `app/main.py`
    - Import `enrollments` from `app.api.v1.endpoints`
    - Add `app.include_router(enrollments.router, prefix="/api/v1", tags=["Inscripciones"])`
    - Follow the same pattern as the courses router registration
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.1_

- [x] 8. Checkpoint — Verify endpoints compile and register correctly
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Integration tests
  - [x] 9.1 Write integration tests in `tests/integration/test_enrollment_endpoints.py`
    - Test POST /enrollments returns 201 with valid data
    - Test POST /enrollments returns 409 for duplicate active enrollment
    - Test POST /enrollments returns 422 for invalid student
    - Test POST /enrollments returns 404 for invalid course
    - Test POST /enrollments reactivates cancelled enrollment
    - Test PATCH /enrollments/{id} returns 200 with updated course
    - Test PATCH /enrollments/{id} returns 409 for duplicate in destination
    - Test PATCH /enrollments/{id}/status returns 200 with CANCELLED status
    - Test GET /enrollments/{id} returns 200 with enrollment detail
    - Test GET /students/{id}/enrollments returns 200 with list
    - Test role-based access control (403 for unauthorized roles)
    - _Requirements: 1.1–1.9, 2.1–2.7, 3.1–3.5, 4.1–4.4, 5.1–5.3_

- [x] 10. Property-based tests
  - [x] 10.1 Write property test for enrollment creation round-trip
    - **Property 1: Enrollment creation round-trip**
    - For any valid student and course, creating and querying returns matching data with status ACTIVE
    - **Validates: Requirements 1.1, 6.4**

  - [x] 10.2 Write property test for entity validation on write operations
    - **Property 2: Entity validation on write operations**
    - For any user role and course status combination, verify correct acceptance/rejection
    - **Validates: Requirements 1.2, 1.3, 2.3**

  - [x] 10.3 Write property test for active enrollment uniqueness invariant
    - **Property 3: Active enrollment uniqueness invariant**
    - For any (student, course) pair, at most one ACTIVE enrollment can exist; duplicates get 409
    - **Validates: Requirements 1.6, 2.5**

  - [x] 10.4 Write property test for cancelled enrollment reactivation
    - **Property 4: Cancelled enrollment reactivation**
    - For any cancelled enrollment, re-enrolling reactivates existing record (count stays 1)
    - **Validates: Requirements 1.7**

  - [x] 10.5 Write property test for audit trail on all write operations
    - **Property 5: Audit trail on all write operations**
    - For any successful write, an audit log entry is registered with correct operation, table, and record_id
    - **Validates: Requirements 1.8, 2.6, 3.3**

  - [x] 10.6 Write property test for role-based access control
    - **Property 6: Role-based access control**
    - For any user role, verify correct access/rejection per endpoint
    - **Validates: Requirements 1.9, 2.7, 3.4, 4.3, 5.3**

  - [x] 10.7 Write property test for update changes course correctly
    - **Property 7: Update changes course correctly**
    - For any active enrollment and valid destination course, update changes course_id while preserving student_id and enrollment_date
    - **Validates: Requirements 2.1**

  - [x] 10.8 Write property test for soft delete preserves record
    - **Property 8: Soft delete preserves record**
    - For any active enrollment, cancelling sets status to CANCELLED and record remains retrievable
    - **Validates: Requirements 3.1, 3.5**

  - [x] 10.9 Write property test for list returns only ACTIVE enrollments
    - **Property 9: List returns only ACTIVE enrollments**
    - For any student with mixed statuses, listing returns only ACTIVE enrollments
    - **Validates: Requirements 4.1**

  - [x] 10.10 Write property test for professor RB-04 visibility filter
    - **Property 10: Professor RB-04 visibility filter**
    - For any professor, listing returns only enrollments in their assigned courses
    - **Validates: Requirements 4.4**

- [x] 11. Documentation update
  - [x] 11.1 Update `README.md` with enrollment endpoints documentation
    - Add enrollment endpoints to the API endpoints section
    - Update ER diagram to include `status` and `updated_at` fields in enrollments
    - Document the new migration `0010_add_enrollment_status.py`
    - _Requirements: 1.1, 2.1, 3.1, 4.1, 5.1_

- [x] 12. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate the 10 universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The implementation follows existing patterns from CourseRepository, CourseService, and courses.py endpoints
- All user-facing error messages are in Spanish as defined in the design document
- All property-based tests use Hypothesis with `@settings(max_examples=100)`
