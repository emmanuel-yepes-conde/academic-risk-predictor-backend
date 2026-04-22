# Implementation Plan: Simplificación Profesor-Curso

## Overview

Eliminar la tabla intermedia `professor_courses` y agregar una columna `professor_id` (FK nullable → `users.id`) directamente en la tabla `courses`. La implementación sigue un orden incremental: migración de BD → modelo ORM → schemas → servicio → repositorio → limpieza de artefactos obsoletos → tests → actualización de tests existentes.

## Tasks

- [x] 1. Create Alembic migration 0007 to restructure the database
  - [x] 1.1 Create migration file `alembic/versions/0007_simplify_professor_course_model.py`
    - `upgrade()`: add `professor_id` UUID nullable column to `courses`, create FK `fk_courses_professor_id` → `users.id`, create index `ix_courses_professor_id`, execute data migration SQL from `professor_courses`, drop `professor_courses` table
    - `downgrade()`: recreate `professor_courses` table with `(id, professor_id, course_id)` and `UNIQUE(course_id)`, migrate data back from `courses.professor_id`, drop index, FK, and column
    - Parent revision: `0006`
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_

- [x] 2. Update Course model and schemas
  - [x] 2.1 Add `professor_id` field to `Course` ORM model in `app/infrastructure/models/course.py`
    - Add `professor_id: uuid.UUID | None = Field(default=None, foreign_key="users.id", nullable=True, index=True)`
    - _Requirements: 1.4_

  - [x] 2.2 Add `professor_id` field to `CourseRead` schema in `app/application/schemas/course.py`
    - Add `professor_id: UUID | None = None` to `CourseRead`
    - `CourseCreate` remains unchanged
    - _Requirements: 10.1, 10.2_

  - [x] 2.3 Replace `ProfessorCourseRead` with `ProfessorAssignmentRead` in `app/application/schemas/professor_course.py`
    - Remove `ProfessorCourseRead` class
    - Add `ProfessorAssignmentRead` with fields `id: UUID`, `professor_id: UUID`, `course_id: UUID` and `model_config = {"from_attributes": False}`
    - Keep `ProfessorAssign` unchanged
    - _Requirements: 3.3, 10.3, 7.6_

- [x] 3. Refactor service and repository to use Course.professor_id
  - [x] 3.1 Refactor `ProfessorCourseService` in `app/application/services/professor_course_service.py`
    - Remove import of `ProfessorCourse`
    - Replace `ProfessorCourseRead` import with `ProfessorAssignmentRead`
    - `assign_professor`: update `course.professor_id` directly, return `ProfessorAssignmentRead(id=course.id, professor_id=professor_id, course_id=course.id)`
    - `get_course_professor`: read `course.professor_id` and JOIN with `users` instead of JOIN with `professor_courses`
    - `verify_professor_assigned_to_course`: check `course.professor_id == professor_id` instead of querying `professor_courses`
    - Audit log: change `table_name` from `"professor_courses"` to `"courses"`, use `course.id` as `record_id`
    - _Requirements: 3.5, 4.1, 4.2, 4.3, 4.4, 4.5, 5.1, 5.2, 6.1, 6.2, 6.3, 6.4, 8.1, 8.2, 8.3_

  - [x] 3.2 Simplify `CourseRepository.listar_por_docente` in `app/infrastructure/repositories/course_repository.py`
    - Remove import of `ProfessorCourse`
    - Replace JOIN query with direct filter: `select(Course).where(Course.professor_id == docente_id)`
    - _Requirements: 3.4, 5.3, 5.4_

- [x] 4. Update endpoint import and clean up obsolete artifacts
  - [x] 4.1 Update `app/api/v1/endpoints/courses.py` to import `ProfessorAssignmentRead` instead of `ProfessorCourseRead`
    - Change import and `response_model` on `POST /courses/{course_id}/professor`
    - Change return type annotation on `assign_professor_to_course`
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [x] 4.2 Delete `app/infrastructure/models/professor_course.py`
    - Remove the entire file containing the `ProfessorCourse` ORM model
    - _Requirements: 3.1, 3.2_

  - [x] 4.3 Update `app/infrastructure/models/__init__.py`
    - Remove import and `__all__` entry for `ProfessorCourse`
    - _Requirements: 3.1_

- [x] 5. Checkpoint — Ensure all existing tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Write property-based tests for correctness properties
  - [x] 6.1 Write property test for idempotent assignment (last professor wins)
    - **Property 1: Idempotencia de asignación — el último profesor gana**
    - Generate lists of 2–5 professor UUIDs, assign sequentially to a course, verify `Course.professor_id == last professor` and each intermediate response has correct `professor_id` and `course_id`
    - File: `tests/property/test_professor_course_simplification_property.py`
    - **Validates: Requirements 4.1, 4.2**

  - [x] 6.2 Write property test for assignment round-trip consistency
    - **Property 2: Round-trip de asignación profesor-curso**
    - Assign professor P to course C, then verify: `assign_professor` returns `professor_id == P` and `course_id == C`; `get_course_professor` returns `UserRead` with `id == P`; `list_professor_courses(P)` contains C
    - **Validates: Requirements 5.1, 5.3, 5.4, 7.6**

  - [x] 6.3 Write property test for role validation (non-professors rejected)
    - **Property 3: Validación de rol — usuarios no-profesor son rechazados**
    - Generate users with roles STUDENT, ADMIN, or nonexistent UUIDs, attempt assignment, verify HTTP 422 and `professor_id` unchanged
    - **Validates: Requirements 4.3**

  - [x] 6.4 Write property test for RB-04 access control
    - **Property 4: Control de acceso RB-04 — acceso condicionado a Course.professor_id**
    - Generate (professor, course) pairs where some match `professor_id` and some don't, verify 403 vs access granted for student listing
    - **Validates: Requirements 6.1, 6.2, 6.3**

  - [x] 6.5 Write property test for enrollment guard on grade writes
    - **Property 5: Guarda de inscripción — notas denegadas para estudiantes no inscritos**
    - Generate (professor, course, student) triples where student is not enrolled, verify HTTP 403 even when professor is correctly assigned
    - **Validates: Requirements 6.4**

  - [x] 6.6 Write property test for audit trail correctness
    - **Property 6: Correctitud del audit trail — operaciones referencian tabla "courses"**
    - Generate new assignments and replacements, verify audit log receives `table_name="courses"`, correct operation type (INSERT vs UPDATE), and correct `previous_data`/`new_data`
    - **Validates: Requirements 4.5, 8.1, 8.2, 8.3**

- [x] 7. Write unit and integration tests
  - [x] 7.1 Write unit tests for updated models and schemas
    - Verify `Course` model has `professor_id` field (nullable UUID)
    - Verify `CourseRead` includes `professor_id: UUID | None`
    - Verify `CourseCreate` does not include `professor_id`
    - Verify `ProfessorAssignmentRead` has fields `id`, `professor_id`, `course_id`
    - Verify `ProfessorCourseRead` no longer exists in `professor_course` module
    - File: `tests/unit/test_course_model.py`
    - _Requirements: 1.4, 10.1, 10.2, 3.3_

  - [x] 7.2 Write integration tests for refactored endpoints
    - `POST /courses/{course_id}/professor` returns 200 with `{id, professor_id, course_id}`
    - `GET /courses/{course_id}/professor` returns correct `UserRead`
    - `GET /professors/{professor_id}/courses` returns `list[CourseRead]` with `professor_id` included
    - `GET /courses/{course_id}/students` works with RB-04 via `Course.professor_id`
    - File: `tests/integration/test_course_repository.py` (extend existing)
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

- [x] 8. Update existing tests that reference ProfessorCourse
  - [x] 8.1 Update all test files that import or reference `ProfessorCourse` model
    - Search all files under `tests/` for `ProfessorCourse` imports and references
    - Replace with direct `Course.professor_id` usage
    - Update test fixtures and setup that create `ProfessorCourse` records to instead set `course.professor_id`
    - _Requirements: 11.1, 11.2, 11.3_

  - [x] 8.2 Update existing property tests that reference `ProfessorCourse`
    - Update `tests/property/test_professor_assignment_property.py`, `test_professor_roundtrip_property.py`, `test_rb04_visibility_property.py`, `test_access_control_properties.py`, and any other affected files
    - Replace `ProfessorCourse` model usage with `Course.professor_id`
    - Replace `ProfessorCourseRead` with `ProfessorAssignmentRead`
    - _Requirements: 11.1, 11.2, 11.3_

- [x] 9. Final checkpoint — Ensure all tests pass
  - Run `python3 -m pytest tests/ -v --cov=app` and ensure all tests pass with no errors.
  - Ensure all tests pass, ask the user if questions arise.
  - _Requirements: 11.4_

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate the 6 universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The implementation language is Python (as specified in the design document)
- The project uses Hypothesis for property-based testing (already configured)
