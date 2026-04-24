# Implementation Plan: Vista "Mi Progreso" del Estudiante (Backend)

## Overview

Implementar los cambios backend necesarios para soportar la vista "Mi Progreso" del estudiante. Se realizan tres cambios principales: (1) permitir al estudiante consultar sus propias inscripciones mediante auto-acceso en `GET /students/{student_id}/enrollments`, (2) agregar los estados COMPLETED y PENDING al `EnrollmentStatusEnum` con migración Alembic, filtro por query param `status`, y actualización del endpoint PATCH de status, y (3) crear el endpoint `GET /programs/{program_id}` para obtener un programa individual por ID. Se sigue la Clean Architecture existente y los patrones establecidos en el proyecto.

## Tasks

- [x] 1. Add PENDING and COMPLETED to EnrollmentStatusEnum and Alembic migration
  - [x] 1.1 Update `app/domain/enums.py` to add PENDING and COMPLETED values
    - Add `PENDING = "PENDING"` and `COMPLETED = "COMPLETED"` to `EnrollmentStatusEnum`
    - Maintain existing ACTIVE and CANCELLED values unchanged
    - Final order: PENDING, ACTIVE, COMPLETED, CANCELLED
    - _Requirements: 2.1_

  - [x] 1.2 Create Alembic migration `alembic/versions/0011_add_pending_completed_enrollment_status.py`
    - Use `op.execute("ALTER TYPE enrollmentstatusenum ADD VALUE IF NOT EXISTS 'PENDING'")` and same for `'COMPLETED'`
    - Revises: `0010_add_enrollment_status`
    - Downgrade is a no-op (PostgreSQL does not support DROP VALUE from enum)
    - Existing records with ACTIVE and CANCELLED must not be modified
    - _Requirements: 2.5, 2.6_

  - [x] 1.3 Update `app/application/schemas/enrollment.py` — update `EnrollmentStatusUpdate` description
    - Change the `status` field description from `"Nuevo estado (ACTIVE o CANCELLED)"` to `"Nuevo estado: PENDING, ACTIVE, COMPLETED o CANCELLED"`
    - No changes needed in `EnrollmentCreate`, `EnrollmentUpdate`, or `EnrollmentRead` — they already use `EnrollmentStatusEnum`
    - _Requirements: 2.2, 2.3, 5.2_

- [x] 2. Checkpoint — Verify enum and migration
  - Ensure all existing tests still pass after enum changes, ask the user if questions arise.

- [x] 3. Update enrollment repository to support status filter on professor query
  - [x] 3.1 Update `IEnrollmentRepository` interface in `app/domain/interfaces/enrollment_repository.py`
    - Add `status: EnrollmentStatusEnum | None = None` parameter to `list_by_student_filtered_by_professor`
    - _Requirements: 3.1, 3.4_

  - [x] 3.2 Update `EnrollmentRepository.list_by_student_filtered_by_professor` in `app/infrastructure/repositories/enrollment_repository.py`
    - Add `status: EnrollmentStatusEnum | None = None` parameter
    - When `status` is provided, filter by that status instead of hardcoding `EnrollmentStatusEnum.ACTIVE`
    - When `status` is None, remove the status filter entirely (return all statuses)
    - _Requirements: 3.1, 3.4_

  - [x] 3.3 Write unit tests for updated repository method in `tests/unit/test_enrollment_repository.py`
    - Test `list_by_student_filtered_by_professor` with explicit status filter
    - Test `list_by_student_filtered_by_professor` without status filter returns all statuses
    - Test `list_by_student_filtered_by_professor` still applies professor course filter (RB-04)
    - _Requirements: 3.1, 3.4_

- [x] 4. Update EnrollmentService for status filter and multi-role support
  - [x] 4.1 Update `EnrollmentService.list_student_enrollments` in `app/application/services/enrollment_service.py`
    - Add `status: EnrollmentStatusEnum | None = None` parameter
    - STUDENT role: call `list_by_student(student_id, status)` — when status is None, return all enrollments (all statuses for progress view)
    - PROFESSOR role: call `list_by_student_filtered_by_professor(student_id, professor_id, status)` — apply RB-04 + status filter
    - ADMIN role: call `list_by_student(student_id, status)` — when status is None, default to ACTIVE (preserve current behavior)
    - _Requirements: 1.1, 1.5, 3.1, 3.2, 3.4_

  - [x] 4.2 Rename `EnrollmentService.cancel_enrollment` to `update_enrollment_status` in `app/application/services/enrollment_service.py`
    - Accept the status from the `EnrollmentStatusUpdate` body instead of hardcoding CANCELLED
    - Pass `body.status` to `self._repo.update_status()`
    - Update docstring to reflect it now handles any valid status transition
    - _Requirements: 2.2, 2.3, 2.4_

  - [x] 4.3 Write unit tests for updated service methods in `tests/unit/test_enrollment_service.py`
    - Test `list_student_enrollments` with STUDENT role returns all statuses when no filter
    - Test `list_student_enrollments` with STUDENT role filters by status when provided
    - Test `list_student_enrollments` with ADMIN role defaults to ACTIVE when no filter
    - Test `list_student_enrollments` with PROFESSOR role applies RB-04 + status filter
    - Test `update_enrollment_status` sets status to COMPLETED
    - Test `update_enrollment_status` sets status to PENDING
    - Use `AsyncMock` for repository and session dependencies
    - _Requirements: 1.1, 1.5, 2.2, 2.3, 3.1, 3.2, 3.4_

- [x] 5. Checkpoint — Verify service layer changes
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Create `require_student_self_or_roles` auth dependency
  - [x] 6.1 Add `require_student_self_or_roles` to `app/api/v1/dependencies/auth.py`
    - New async dependency that reads `student_id: UUID = Path(...)` from the path
    - If `current_user.role == STUDENT` and `current_user.id == student_id` → allow (self-access)
    - If `current_user.role == STUDENT` and `current_user.id != student_id` → 403
    - If `current_user.role == ADMIN` → allow always
    - If `current_user.role == PROFESSOR` → allow only if student is enrolled in one of the professor's courses (RB-04, same query pattern as `require_self_or_roles`)
    - Any other case → 403 with message "No tiene permisos para esta acción"
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6_

  - [x] 6.2 Write unit tests for `require_student_self_or_roles` in `tests/unit/test_auth_dependencies.py`
    - Test STUDENT self-access allowed (student_id == current_user.id)
    - Test STUDENT accessing another student's data returns 403
    - Test ADMIN access allowed for any student_id
    - Test PROFESSOR access allowed when student is enrolled in professor's course
    - Test PROFESSOR access denied when student is not in professor's courses
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6_

- [x] 7. Update enrollment endpoints for student self-access and status filter
  - [x] 7.1 Update `list_student_enrollments` endpoint in `app/api/v1/endpoints/enrollments.py`
    - Change auth dependency from `require_roles(RoleEnum.ADMIN, RoleEnum.PROFESSOR)` to `require_student_self_or_roles`
    - Add query param `status: EnrollmentStatusEnum | None = Query(default=None, description="Filtrar por estado de inscripción")`
    - Pass `status` to `service.list_student_enrollments(student_id, current_user, status)`
    - Update `description` to mention STUDENT self-access and status filter
    - _Requirements: 1.1, 1.5, 3.1, 3.2, 3.3, 5.1_

  - [x] 7.2 Update `cancel_enrollment` endpoint in `app/api/v1/endpoints/enrollments.py`
    - Rename handler function from `cancel_enrollment` to `update_enrollment_status`
    - Update `summary` to "Actualizar estado de inscripción"
    - Update `description` to mention all valid states (PENDING, ACTIVE, COMPLETED, CANCELLED)
    - Pass `body.status` to `service.update_enrollment_status(enrollment_id, body, current_user.id)`
    - _Requirements: 2.2, 2.3, 2.4, 5.2_

- [x] 8. Add GET /programs/{program_id} endpoint
  - [x] 8.1 Add `get_program` method to `ProgramService` in `app/application/services/program_service.py`
    - Fetch program by ID using `self._repo.get_by_id(program_id)`
    - If None, raise `HTTPException(status_code=404, detail="Programa no encontrado")`
    - Return `ProgramRead.model_validate(program)`
    - _Requirements: 4.1, 4.2_

  - [x] 8.2 Add `GET /programs/{program_id}` endpoint in `app/api/v1/endpoints/programs.py`
    - Auth: `get_current_user` (any authenticated user)
    - Response model: `ProgramRead`, status code: 200
    - Include `summary="Obtener un programa académico por ID"`, `description`, and `tags=["Programas"]`
    - Use the existing `_get_service` dependency helper
    - _Requirements: 4.1, 4.2, 4.3, 5.3_

  - [x] 8.3 Write unit tests for `ProgramService.get_program` in `tests/unit/test_program_service.py`
    - Test get_program returns ProgramRead when program exists
    - Test get_program raises 404 when program does not exist
    - _Requirements: 4.1, 4.2_

- [x] 9. Checkpoint — Verify all endpoints compile and register correctly
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Integration tests
  - [x] 10.1 Write integration tests in `tests/integration/test_student_progress_endpoints.py`
    - Test GET /students/{student_id}/enrollments with STUDENT self-access returns 200
    - Test GET /students/{student_id}/enrollments with STUDENT accessing another student returns 403
    - Test GET /students/{student_id}/enrollments with ADMIN returns 200
    - Test GET /students/{student_id}/enrollments with PROFESSOR (RB-04) returns 200
    - Test GET /students/{student_id}/enrollments with `status=COMPLETED` filter returns only COMPLETED
    - Test GET /students/{student_id}/enrollments with `status=PENDING` filter returns only PENDING
    - Test GET /students/{student_id}/enrollments with invalid status returns 422
    - Test PATCH /enrollments/{id}/status with COMPLETED returns 200
    - Test PATCH /enrollments/{id}/status with PENDING returns 200
    - Test GET /programs/{program_id} with valid ID returns 200
    - Test GET /programs/{program_id} with non-existent ID returns 404
    - Test GET /programs/{program_id} accessible by STUDENT, PROFESSOR, and ADMIN
    - _Requirements: 1.1–1.6, 2.2, 2.3, 3.1–3.4, 4.1–4.3, 5.1–5.4_

- [x] 11. Documentation update
  - [x] 11.1 Update `README.md` with new and modified endpoints
    - Document STUDENT self-access on GET /students/{student_id}/enrollments
    - Document `status` query param on enrollment listing endpoint
    - Document updated PATCH /enrollments/{id}/status accepting all valid states
    - Document new GET /programs/{program_id} endpoint
    - Update ER diagram to show PENDING and COMPLETED in enrollment status
    - Document migration `0011_add_pending_completed_enrollment_status.py`
    - _Requirements: 1.1, 2.1, 3.1, 4.1_

- [x] 12. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- The design does not include Correctness Properties, so property-based tests are not included; unit and integration tests provide coverage
- The implementation follows existing patterns from `EnrollmentRepository`, `EnrollmentService`, and `enrollments.py` endpoints
- All user-facing error messages are in Spanish as defined in the design document
- The `require_student_self_or_roles` dependency follows the same pattern as the existing `require_self_or_roles` but reads `student_id` from the path
