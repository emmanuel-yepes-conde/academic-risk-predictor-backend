# Implementation Plan: Multi-University Support

## Overview

Este plan implementa la entidad `University` como raíz de la jerarquía académica (`University → Programs → Courses`), incluyendo CRUD completo, migración de datos existentes, restricciones de unicidad por universidad, asignación de profesor único por curso, control de acceso por universidad/curso, y endpoints jerárquicos anidados. Sigue la Clean Architecture existente (Domain → Application → Infrastructure → API) y el stack Python 3.12 + FastAPI + SQLModel + PostgreSQL.

## Tasks

- [x] 1. Crear modelo de datos University y migración Alembic
  - [x] 1.1 Crear modelo SQLModel `University` en `app/infrastructure/models/university.py`
    - Campos: `id` (UUID PK), `name`, `code` (unique, indexed), `country`, `city`, `active` (default True), `created_at`
    - Seguir el patrón de `app/infrastructure/models/program.py`
    - _Requirements: 1.1_

  - [x] 1.2 Agregar `DEFAULT_UNIVERSITY_ID` a `app/core/config.py`
    - Agregar campo `DEFAULT_UNIVERSITY_ID: uuid.UUID | None = Field(default=None, ...)`
    - _Requirements: 2.6, 7.2, 7.3_

  - [x] 1.3 Modificar modelo `Program` en `app/infrastructure/models/program.py`
    - Agregar `university_id: uuid.UUID = Field(foreign_key="universities.id", nullable=False, index=True)`
    - Cambiar `program_code` de `unique=True` a no-unique en el campo, y agregar `__table_args__` con `UniqueConstraint("program_code", "university_id")`
    - _Requirements: 2.1, 2.5_

  - [x] 1.4 Modificar modelo `Course` en `app/infrastructure/models/course.py`
    - Cambiar `program_id` de `nullable=True` a `nullable=False` con `index=True`
    - _Requirements: 3.1_

  - [x] 1.5 Modificar modelo `ProfessorCourse` en `app/infrastructure/models/professor_course.py`
    - Cambiar `UniqueConstraint("professor_id", "course_id")` a `UniqueConstraint("course_id")`
    - _Requirements: 4.1_

  - [x] 1.6 Crear migración Alembic `alembic/versions/0004_add_university_and_multi_university_support.py`
    - `upgrade()`: crear tabla `universities`, agregar `university_id` nullable a `programs`, UPDATE con `DEFAULT_UNIVERSITY_ID` (fallar si no configurado), ALTER a NOT NULL, cambiar UniqueConstraint de `program_code` a scoped por universidad, ALTER `courses.program_id` a NOT NULL, cambiar UniqueConstraint de `professor_courses`
    - `downgrade()`: revertir todos los cambios en orden inverso
    - Seguir el patrón de `alembic/versions/0003_add_programs_and_student_profiles.py`
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 2. Checkpoint — Verificar modelos y migración
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Implementar capa de dominio e interfaz de repositorio de universidades
  - [x] 3.1 Crear interfaz `IUniversityRepository` en `app/domain/interfaces/university_repository.py`
    - Métodos abstractos: `create`, `get_by_id`, `get_by_code`, `list`, `count`, `update`
    - Seguir el patrón de `app/domain/interfaces/user_repository.py`
    - _Requirements: 1.2, 1.4, 1.5, 1.6_

  - [x] 3.2 Extender interfaz `ICourseRepository` en `app/domain/interfaces/course_repository.py`
    - Agregar métodos: `listar_por_programa(program_id)`, `listar_por_universidad_y_programa(university_id, program_id)`
    - _Requirements: 3.4, 3.5_

- [x] 4. Implementar schemas Pydantic para universidades
  - [x] 4.1 Crear schemas en `app/application/schemas/university.py`
    - `UniversityCreate`: name, code, country, city, active (con `Field(description=...)`)
    - `UniversityUpdate`: name, country, city, active (todos opcionales)
    - `UniversityRead`: todos los campos con `model_config = {"from_attributes": True}`
    - Seguir el patrón de `app/application/schemas/user.py`
    - _Requirements: 1.1, 1.2, 1.6_

  - [x] 4.2 Modificar `CourseCreate` en `app/application/schemas/course.py`
    - Agregar `program_id: UUID` como campo requerido
    - _Requirements: 3.1, 3.2_

- [x] 5. Implementar repositorio de universidades y extender repositorio de cursos
  - [x] 5.1 Crear `UniversityRepository` en `app/infrastructure/repositories/university_repository.py`
    - Implementar todos los métodos de `IUniversityRepository`
    - Incluir registro de audit_log en `create` y `update`
    - Seguir el patrón de `app/infrastructure/repositories/course_repository.py`
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x] 5.2 Extender `CourseRepository` en `app/infrastructure/repositories/course_repository.py`
    - Implementar `listar_por_programa(program_id)` y `listar_por_universidad_y_programa(university_id, program_id)`
    - _Requirements: 3.4, 3.5_

  - [x] 5.3 Escribir test de propiedad: round-trip de universidad por ID
    - **Property 3: Round-trip de universidad por ID**
    - **Validates: Requirements 1.5**

  - [x] 5.4 Escribir test de propiedad: actualización parcial no modifica campos no provistos
    - **Property 4: Actualización parcial no modifica campos no provistos**
    - **Validates: Requirements 1.6**

- [x] 6. Implementar servicio de universidades
  - [x] 6.1 Crear `UniversityService` en `app/application/services/university_service.py`
    - `create(data, actor_role)`: verificar rol ADMIN (403), verificar unicidad de code (409), delegar a repo
    - `list(skip, limit)`: retornar `PaginatedResponse[UniversityRead]`
    - `get(id)`: retornar UniversityRead o 404
    - `update(id, data, actor_role)`: verificar rol ADMIN (403), 404 si no existe
    - Seguir el patrón de `app/application/services/user_service.py`
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [x] 6.2 Escribir test de propiedad: creación de universidad con datos válidos
    - **Property 1: Creación de universidad con datos válidos siempre retorna el recurso creado**
    - **Validates: Requirements 1.2**

  - [x] 6.3 Escribir test de propiedad: listado paginado consistente con total
    - **Property 2: Listado paginado es consistente con el total**
    - **Validates: Requirements 1.4**

  - [x] 6.4 Escribir test de propiedad: usuarios no-ADMIN no pueden escribir universidades
    - **Property 5: Usuarios no-ADMIN no pueden escribir universidades**
    - **Validates: Requirements 1.7**

- [x] 7. Checkpoint — Verificar servicio y repositorio de universidades
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implementar endpoints de universidades y jerarquía
  - [x] 8.1 Crear router `app/api/v1/endpoints/universities.py`
    - `POST /api/v1/universities` → 201 UniversityRead
    - `GET /api/v1/universities` → 200 PaginatedResponse[UniversityRead]
    - `GET /api/v1/universities/{university_id}` → 200 UniversityRead | 404
    - `PATCH /api/v1/universities/{university_id}` → 200 UniversityRead | 403 | 404
    - Cada endpoint con `summary`, `description`, `response_model`, `status_code`, `tags`
    - Seguir el patrón de `app/api/v1/endpoints/users.py`
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [x] 8.2 Agregar endpoints jerárquicos al router de universidades
    - `GET /api/v1/universities/{university_id}/programs` → 200 PaginatedResponse[ProgramRead]
    - `GET /api/v1/programs/{program_id}/courses` → 200 list[CourseRead]
    - `GET /api/v1/universities/{university_id}/programs/{program_id}/courses` → 200 list[CourseRead] | 404
    - Validar que el programa pertenezca a la universidad en el endpoint anidado
    - _Requirements: 2.4, 3.4, 3.5_

  - [x] 8.3 Agregar endpoints de asignación profesor-curso
    - `POST /api/v1/courses/{course_id}/professor` → 200 (asignar/reemplazar profesor)
    - `GET /api/v1/courses/{course_id}/professor` → 200 UserRead | 404
    - `GET /api/v1/professors/{professor_id}/courses` → 200 list[CourseRead]
    - `GET /api/v1/courses/{course_id}/students` → 200 list[UserRead] | 403
    - Validar rol PROFESSOR en asignación (422), verificar existencia de curso (404)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.3_

  - [x] 8.4 Registrar router de universidades en `app/main.py`
    - Importar y registrar con `app.include_router(universities.router, prefix="/api/v1", tags=["Universidades"])`
    - _Requirements: 1.2_

  - [x] 8.5 Escribir test de propiedad: aislamiento de programas por universidad
    - **Property 6: Aislamiento de programas por universidad**
    - **Validates: Requirements 2.4, 6.1, 6.3**

  - [x] 8.6 Escribir test de propiedad: unicidad de program_code dentro de una universidad
    - **Property 7: Unicidad de program_code dentro de una universidad**
    - **Validates: Requirements 2.5**

  - [x] 8.7 Escribir test de propiedad: aislamiento de cursos por programa
    - **Property 8: Aislamiento de cursos por programa**
    - **Validates: Requirements 3.4, 6.3**

  - [x] 8.8 Escribir test de propiedad: validación jerárquica universidad→programa→cursos
    - **Property 9: Validación jerárquica universidad→programa→cursos**
    - **Validates: Requirements 3.5, 6.3**

- [x] 9. Checkpoint — Verificar endpoints y aislamiento de datos
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Implementar control de acceso de profesor y auditoría
  - [x] 10.1 Implementar lógica de asignación profesor-curso en servicio
    - Crear o extender servicio para manejar `POST /courses/{id}/professor` con lógica de reemplazo (upsert)
    - Verificar que el usuario tenga rol PROFESSOR (422)
    - Verificar existencia del curso (404)
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 10.2 Implementar control de acceso RB-04 en servicio
    - Verificar que el profesor está asignado al curso antes de permitir acceso a estudiantes (403)
    - Verificar que el profesor está asignado al curso antes de permitir escritura de notas (403)
    - Registrar en audit_log cada operación de escritura de notas
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 10.3 Escribir test de propiedad: un curso tiene exactamente un profesor asignado
    - **Property 10: Un curso tiene exactamente un profesor asignado (idempotencia de asignación)**
    - **Validates: Requirements 4.1, 4.2**

  - [x] 10.4 Escribir test de propiedad: round-trip de asignación profesor-curso
    - **Property 11: Round-trip de asignación profesor-curso**
    - **Validates: Requirements 4.5, 4.6**

  - [x] 10.5 Escribir test de propiedad: RB-04 profesor solo ve estudiantes de sus cursos
    - **Property 12: RB-04 — Profesor solo ve estudiantes de sus cursos asignados**
    - **Validates: Requirements 5.1, 5.3, 5.4**

  - [x] 10.6 Escribir test de propiedad: escritura de notas en curso no asignado retorna 403
    - **Property 13: Escritura de notas en curso no asignado retorna 403**
    - **Validates: Requirements 5.2**

  - [x] 10.7 Escribir test de propiedad: toda escritura de notas genera entrada en audit_log
    - **Property 14: Toda escritura de notas genera entrada en audit_log**
    - **Validates: Requirements 5.5**

- [x] 11. Checkpoint — Verificar control de acceso y auditoría
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Integración final y tests de confluencia/migración
  - [x] 12.1 Verificar wiring completo de componentes
    - Asegurar que todos los routers están registrados en `app/main.py`
    - Asegurar que todos los imports en `__init__.py` están actualizados
    - Verificar que la inyección de dependencias funciona correctamente en todos los endpoints
    - _Requirements: 1.2, 2.4, 3.4, 4.2, 4.5, 4.6, 5.3_

  - [x] 12.2 Escribir test de propiedad: confluencia del filtro por universidad
    - **Property 15: Confluencia del filtro por universidad**
    - **Validates: Requirements 6.4**

  - [x] 12.3 Escribir test de propiedad: reversibilidad de la migración
    - **Property 16: Reversibilidad de la migración**
    - **Validates: Requirements 7.4**

  - [x] 12.4 Escribir tests unitarios para servicios de universidad
    - Test: `create()` lanza 409 cuando code duplicado
    - Test: `create()` lanza 403 para roles no-ADMIN
    - Test: `get()` lanza 404 cuando no existe
    - Test: `update()` lanza 403 para roles no-ADMIN
    - _Requirements: 1.2, 1.3, 1.5, 1.6, 1.7_

  - [x] 12.5 Escribir tests de integración para migración 0004
    - Test: migración sobre DB vacía completa sin errores
    - Test: migración sobre DB con datos asigna `DEFAULT_UNIVERSITY_ID`
    - Test: migración falla con mensaje descriptivo si `DEFAULT_UNIVERSITY_ID` no configurado
    - Test: `upgrade()` + `downgrade()` restaura esquema sin pérdida de datos
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 13. Final checkpoint — Verificar integración completa
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate the 16 universal correctness properties defined in the design document using Hypothesis
- Unit tests validate specific examples and edge cases
- All property tests should use `@h_settings(max_examples=100)` following the existing project pattern
- Test files should be organized under `tests/property/`, `tests/unit/`, and `tests/integration/` following the existing structure
