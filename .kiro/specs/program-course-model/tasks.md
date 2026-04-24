# Implementation Plan: Simplificación del Modelo de Datos — Programa → Curso

## Overview

Simplificar el modelo de datos del sistema MPRA de una jerarquía de cuatro niveles (Universidad → Campus → Programa → Curso) a una relación directa de dos niveles (Programa → Curso). Esto implica crear una migración Alembic destructiva, eliminar toda la infraestructura de University y Campus (modelos, repos, interfaces, servicios, schemas, endpoints), simplificar el modelo Program, y reubicar endpoints existentes a routers dedicados.

## Tasks

- [x] 1. Create Alembic migration 0006 to simplify the database schema
  - [x] 1.1 Create migration file `alembic/versions/0006_simplify_program_course_model.py`
    - Revision parent: `0005`
    - `upgrade()`: drop `uq_program_code_campus` constraint, drop `ix_programs_campus_id` index, drop `fk_programs_campus_id` FK, drop `campus_id` column from `programs`, drop `ix_programs_university_id` index, drop `fk_programs_university_id` FK, drop `university_id` column from `programs`, drop indexes on `campuses`, drop `campuses` table, drop indexes on `universities`, drop `universities` table, create unique constraint on `program_code` globally
    - `downgrade()`: reverse all changes (recreate tables, columns, FKs, indexes, constraints — columns nullable since data is lost)
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 1.1, 1.2, 2.1, 2.2, 3.4_

- [x] 2. Simplify the Program ORM model and schema
  - [x] 2.1 Modify `app/infrastructure/models/program.py` — remove `campus_id`, `university_id` fields and `UniqueConstraint("program_code", "campus_id")`; set `program_code` as `unique=True`; remove `pensum` field (not in design target)
    - Remove `campus_id: uuid.UUID` field and its FK to `campuses.id`
    - Remove `university_id: uuid.UUID` field and its FK to `universities.id`
    - Remove `__table_args__` with `UniqueConstraint("program_code", "campus_id")`
    - Set `program_code` field to `unique=True`
    - _Requirements: 3.1, 3.2, 3.3_

  - [x] 2.2 Modify `app/application/schemas/program.py` — remove `university_id` and `campus_id` from `ProgramRead`
    - Remove `university_id: UUID` and `campus_id: UUID` fields
    - _Requirements: 3.5_

  - [ ]* 2.3 Write property test for Program uniqueness constraints
    - **Property 1: Uniqueness of program_code and snies_code**
    - **Validates: Requirements 3.2, 3.3**
    - File: `tests/property/test_program_course_model_property.py`
    - Generate pairs of programs with colliding `program_code` or `snies_code`, verify IntegrityError on second insert

- [x] 3. Simplify domain interfaces and repositories
  - [x] 3.1 Modify `app/domain/interfaces/program_repository.py` — replace `list_by_campus`/`count_by_campus` with `list_all`/`count_all`
    - Remove `list_by_campus(campus_id, skip, limit)` method
    - Remove `count_by_campus(campus_id)` method
    - Add `list_all(skip, limit) -> list[Program]` method
    - Add `count_all() -> int` method
    - Keep `get_by_id(program_id)` unchanged
    - _Requirements: 6.1_

  - [x] 3.2 Modify `app/infrastructure/repositories/program_repository.py` — implement `list_all` and `count_all`, remove campus-scoped methods
    - Replace `list_by_campus` with `list_all` (no WHERE clause, just offset/limit)
    - Replace `count_by_campus` with `count_all` (no WHERE clause)
    - _Requirements: 6.2_

  - [x] 3.3 Modify `app/domain/interfaces/course_repository.py` — remove hierarchy methods
    - Remove `listar_por_universidad_y_programa` method
    - Remove `listar_por_campus_y_programa` method
    - Keep `listar_por_programa`, `crear`, `obtener_por_id`, `listar_por_docente`, `listar_estudiantes_inscritos`
    - _Requirements: 6.3_

  - [x] 3.4 Modify `app/infrastructure/repositories/course_repository.py` — remove hierarchy methods and unused imports
    - Remove `listar_por_universidad_y_programa` method implementation
    - Remove `listar_por_campus_y_programa` method implementation
    - Remove import of `Program` model (no longer needed for joins)
    - _Requirements: 6.4, 6.5_

  - [ ]* 3.5 Write property test for list_all returning all programs
    - **Property 4: list_all returns all programs without hierarchy filters**
    - **Validates: Requirements 6.2**
    - File: `tests/property/test_program_course_model_property.py`
    - Generate N programs with varied fields, verify `list_all` returns all and `count_all` matches

- [x] 4. Checkpoint — Ensure model and repository changes are consistent
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Delete University and Campus infrastructure
  - [x] 5.1 Delete University infrastructure files
    - Delete `app/infrastructure/models/university.py`
    - Delete `app/infrastructure/repositories/university_repository.py`
    - Delete `app/domain/interfaces/university_repository.py`
    - Delete `app/application/services/university_service.py`
    - Delete `app/application/schemas/university.py`
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 1.7_

  - [x] 5.2 Delete Campus infrastructure files
    - Delete `app/infrastructure/models/campus.py`
    - Delete `app/infrastructure/repositories/campus_repository.py`
    - Delete `app/domain/interfaces/campus_repository.py`
    - Delete `app/application/services/campus_service.py`
    - Delete `app/application/schemas/campus.py`
    - _Requirements: 2.3, 2.4, 2.5, 2.6, 2.7_

  - [x] 5.3 Update `app/infrastructure/models/__init__.py` — remove University and Campus imports
    - Remove `from app.infrastructure.models.university import University`
    - Remove `from app.infrastructure.models.campus import Campus`
    - Remove `"University"` and `"Campus"` from `__all__`
    - _Requirements: 1.10_

- [x] 6. Restructure API endpoints
  - [x] 6.1 Create `app/api/v1/endpoints/programs.py` — new router for program-scoped endpoints
    - Implement `GET /programs/{program_id}/courses` endpoint (relocated from `universities.py`)
    - Validate program exists, return 404 with "Programa no encontrado" if not found
    - Use `CourseRepository.listar_por_programa` for data access
    - Use `ProgramRepository.get_by_id` to validate program existence
    - Include proper `summary`, `description`, `response_model`, `status_code`, `tags`
    - _Requirements: 4.2, 4.3, 4.4, 5.3, 5.4_

  - [x] 6.2 Create `app/api/v1/endpoints/courses.py` — new router for course-scoped endpoints
    - Relocate professor-course endpoints from `universities.py`:
      - `POST /courses/{course_id}/professor` — assign professor to course
      - `GET /courses/{course_id}/professor` — get assigned professor
      - `GET /professors/{professor_id}/courses` — list professor's courses
      - `GET /courses/{course_id}/students` — list enrolled students
    - Maintain existing behavior and dependencies (`ProfessorCourseService`)
    - Include proper `summary`, `description`, `response_model`, `status_code`, `tags`
    - _Requirements: 5.1, 5.2_

  - [x] 6.3 Delete `app/api/v1/endpoints/universities.py` — remove all university endpoints
    - _Requirements: 1.8, 5.1_

  - [x] 6.4 Delete `app/api/v1/endpoints/campuses.py` — remove all campus endpoints
    - _Requirements: 2.8, 5.2_

  - [x] 6.5 Update `app/main.py` — remove old routers, register new ones
    - Remove import and `include_router` for `universities` router
    - Remove import and `include_router` for `campuses` router
    - Add import and `include_router` for new `programs` router (prefix `/api/v1`, tags `["Programas"]`)
    - Add import and `include_router` for new `courses` router (prefix `/api/v1`, tags `["Cursos"]`)
    - _Requirements: 1.9, 2.9_

- [x] 7. Checkpoint — Ensure all deletions and endpoint restructuring are consistent
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Write property-based tests for Course → Program relationship
  - [ ]* 8.1 Write property test for referential integrity Course → Program
    - **Property 2: Referential integrity Course → Program**
    - **Validates: Requirements 4.1**
    - File: `tests/property/test_program_course_model_property.py`
    - Generate programs and courses with valid/invalid `program_id`, verify FK constraint enforcement

  - [ ]* 8.2 Write property test for listing courses by program
    - **Property 3: Listing courses by program returns exactly matching courses**
    - **Validates: Requirements 4.3, 6.5**
    - File: `tests/property/test_program_course_model_property.py`
    - Generate N programs with M courses distributed among them, verify `listar_por_programa` returns exactly matching courses

- [x] 9. Write unit and integration tests
  - [ ]* 9.1 Write unit tests for simplified models and interfaces
    - File: `tests/unit/test_program_model.py`
    - Verify `Program` model has correct fields (no `campus_id`, no `university_id`)
    - Verify `ProgramRead` schema excludes `campus_id` and `university_id`
    - Verify `IProgramRepository` exposes `get_by_id`, `list_all`, `count_all`
    - Verify `ICourseRepository` does not have hierarchy methods
    - _Requirements: 3.1, 3.5, 6.1, 6.3_

  - [ ]* 9.2 Write integration tests for program and course endpoints
    - File: `tests/integration/test_program_endpoints.py`
    - Test `GET /programs/{program_id}/courses` returns 200 with correct courses
    - Test `GET /programs/{program_id}/courses` returns 404 for non-existent program
    - Test that `/universities/...` endpoints return 404 (removed)
    - Test that `/campuses/...` endpoints return 404 (removed)
    - Test that professor-course endpoints still work at new paths
    - _Requirements: 4.2, 4.3, 4.4, 5.1, 5.2, 5.3, 5.4, 8.1, 8.2_

- [x] 10. Update project documentation
  - [x] 10.1 Update `README.md` to reflect simplified data model
    - Update ER diagram (Mermaid) to show only Program → Course relationships
    - Update API endpoints section — remove university/campus endpoints, add program/course endpoints
    - Update data model description to reflect Programa → Curso simplification
    - _Requirements: 9.1, 9.2, 9.3_

- [x] 11. Final checkpoint — Ensure all tests pass and documentation is up to date
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The migration (task 1) should be created first but applied only after model changes are in place
- Deletion of University/Campus files (task 5) depends on repository and interface changes (task 3) being complete
- Endpoint restructuring (task 6) depends on deletions (task 5) to avoid import conflicts
