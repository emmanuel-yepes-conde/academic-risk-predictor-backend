# Plan de Implementación: Campus Hierarchy

## Visión General

Este plan implementa la entidad `Campus` como nivel intermedio en la jerarquía académica, transformándola de `University → Program → Course` a `University → Campus → Program → Course`. Incluye el modelo de datos, CRUD completo, migración Alembic con data migration reversible, endpoints jerárquicos anidados y actualización del modelo `Program`. Sigue la Clean Architecture existente (Domain → Application → Infrastructure → API) y el stack Python 3.12 + FastAPI + SQLModel + PostgreSQL.

## Tasks

- [x] 1. Crear modelo de datos Campus y migración Alembic
  - [x] 1.1 Crear modelo SQLModel `Campus` en `app/infrastructure/models/campus.py`
    - Campos: `id` (UUID PK), `university_id` (FK → universities.id, NOT NULL, indexed), `campus_code` (str, NOT NULL, indexed), `name` (str, NOT NULL), `city` (str, NOT NULL), `active` (bool, default True), `created_at` (datetime con timezone)
    - UniqueConstraint `("university_id", "campus_code", name="uq_university_campus_code")`
    - Seguir el patrón de `app/infrastructure/models/university.py`
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 1.2 Modificar modelo `Program` en `app/infrastructure/models/program.py`
    - Agregar `campus_id: uuid.UUID = Field(foreign_key="campuses.id", nullable=False, index=True)`
    - Mantener `university_id` como campo denormalizado de solo lectura
    - Eliminar campo de texto `campus`
    - Cambiar UniqueConstraint de `("program_code", "university_id")` a `("program_code", "campus_id", name="uq_program_code_campus")`
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [x] 1.3 Crear migración Alembic `alembic/versions/0005_add_campus_hierarchy.py`
    - `upgrade()`: crear tabla `campuses` con esquema completo → agregar `campus_id` nullable a `programs` → data migration (SELECT DISTINCT university_id, campus; INSERT INTO campuses; UPDATE programs SET campus_id) → ALTER campus_id a NOT NULL → eliminar UniqueConstraint `uq_program_code_university` → crear UniqueConstraint `uq_program_code_campus` → eliminar columna `campus` texto → crear índice en `programs.campus_id`
    - `downgrade()`: agregar columna `campus` texto nullable → repoblar desde campuses → ALTER a NOT NULL → eliminar UniqueConstraint `uq_program_code_campus` → crear UniqueConstraint `uq_program_code_university` → eliminar columna `campus_id` → eliminar tabla `campuses`
    - Manejar caso de BD vacía sin errores
    - Seguir patrón de `alembic/versions/0004_add_university_and_multi_university_support.py`
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8_

- [x] 2. Checkpoint — Verificar modelos y migración
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Implementar capa de dominio e interfaz de repositorio de campus
  - [x] 3.1 Crear interfaz `ICampusRepository` en `app/domain/interfaces/campus_repository.py`
    - Métodos abstractos: `create(university_id, data)`, `get_by_id(campus_id)`, `get_by_university_and_code(university_id, campus_code)`, `list_by_university(university_id, skip, limit)`, `count_by_university(university_id)`, `update(campus_id, data)`
    - Seguir patrón de `app/domain/interfaces/university_repository.py`
    - _Requirements: 2.1, 2.4, 2.5, 2.6_

  - [x] 3.2 Extender interfaz `ICourseRepository` en `app/domain/interfaces/course_repository.py`
    - Agregar método abstracto: `listar_por_campus_y_programa(campus_id, program_id) -> list[Course]`
    - _Requirements: 4.2_

- [x] 4. Implementar schemas Pydantic para campus
  - [x] 4.1 Crear schemas en `app/application/schemas/campus.py`
    - `CampusCreate`: campus_code (str, required), name (str, required), city (str, required), active (bool, default True) — todos con `Field(description=...)`
    - `CampusUpdate`: name, city, active (todos opcionales)
    - `CampusRead`: id, university_id, campus_code, name, city, active, created_at — con `model_config = {"from_attributes": True}`
    - _Requirements: 6.1, 6.2, 6.3, 6.5_

  - [x] 4.2 Modificar `ProgramRead` en `app/application/schemas/program.py`
    - Agregar campo `campus_id: UUID`
    - Eliminar campo `campus: str`
    - _Requirements: 6.4_

- [x] 5. Implementar repositorio de campus y extender repositorio de cursos
  - [x] 5.1 Crear `CampusRepository` en `app/infrastructure/repositories/campus_repository.py`
    - Implementar todos los métodos de `ICampusRepository`
    - Incluir registro de audit_log en `create` y `update`
    - Seguir patrón de `app/infrastructure/repositories/university_repository.py`
    - _Requirements: 2.1, 2.3, 2.4, 2.5, 2.6_

  - [x] 5.2 Extender `CourseRepository` en `app/infrastructure/repositories/course_repository.py`
    - Implementar `listar_por_campus_y_programa(campus_id, program_id)` con JOIN a Program para validar `Program.campus_id == campus_id`
    - _Requirements: 4.2, 5.2_

  - [x] 5.3 Escribir tests unitarios para `CampusRepository`
    - Test: `create()` inserta registro y registra audit_log
    - Test: `get_by_id()` retorna None si no existe
    - Test: `get_by_university_and_code()` busca por combinación correcta
    - Test: `list_by_university()` filtra por university_id
    - Test: `update()` modifica solo campos provistos
    - _Requirements: 2.1, 2.4, 2.5, 2.6_

- [x] 6. Checkpoint — Verificar repositorios y schemas
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implementar servicio de campus
  - [x] 7.1 Crear `CampusService` en `app/application/services/campus_service.py`
    - `create(university_id, data, actor_role)`: verificar rol ADMIN (403), verificar universidad existe (404), verificar unicidad university_id+campus_code (409), delegar a repo
    - `list_by_university(university_id, skip, limit)`: retornar `PaginatedResponse[CampusRead]`
    - `get(university_id, campus_id)`: verificar existencia + pertenencia a universidad (404)
    - `update(university_id, campus_id, data, actor_role)`: verificar ADMIN (403), existencia + pertenencia (404), actualizar
    - `list_programs_by_campus(university_id, campus_id, skip, limit)`: validar campus pertenece a universidad (404), retornar programas paginados
    - `list_courses_by_campus_and_program(university_id, campus_id, program_id)`: validar cadena completa universidad → campus → programa (404 en cada nivel)
    - Inyectar `ICampusRepository` e `IUniversityRepository` como dependencias
    - Seguir patrón de `app/application/services/university_service.py`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 4.1, 4.2, 4.3, 4.4, 5.1, 5.2, 5.3_

  - [x] 7.2 Escribir tests unitarios para `CampusService`
    - Test: `create()` lanza 403 para roles no-ADMIN
    - Test: `create()` lanza 404 si universidad no existe
    - Test: `create()` lanza 409 si combinación university_id+campus_code ya existe
    - Test: `create()` con datos válidos retorna CampusRead
    - Test: `get()` lanza 404 si campus no existe o no pertenece a universidad
    - Test: `update()` lanza 403 para roles no-ADMIN
    - Test: `update()` lanza 404 si campus no existe
    - Test: `list_programs_by_campus()` lanza 404 si campus no pertenece a universidad
    - Test: `list_courses_by_campus_and_program()` lanza 404 si programa no pertenece al campus
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6, 2.7, 4.3, 4.4_

- [x] 8. Checkpoint — Verificar servicio de campus
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implementar endpoints de campus y jerarquía
  - [x] 9.1 Crear router `app/api/v1/endpoints/campuses.py`
    - `POST /api/v1/universities/{university_id}/campuses` → 201 CampusRead
    - `GET /api/v1/universities/{university_id}/campuses` → 200 PaginatedResponse[CampusRead]
    - `GET /api/v1/universities/{university_id}/campuses/{campus_id}` → 200 CampusRead | 404
    - `PATCH /api/v1/universities/{university_id}/campuses/{campus_id}` → 200 CampusRead | 403 | 404
    - Cada endpoint con `summary`, `description`, `response_model`, `status_code`, `tags`
    - Dependency injection para CampusService con sesión de BD
    - Seguir patrón de `app/api/v1/endpoints/universities.py`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [x] 9.2 Agregar endpoints jerárquicos al router de campuses
    - `GET /api/v1/universities/{university_id}/campuses/{campus_id}/programs` → 200 PaginatedResponse[ProgramRead]
    - `GET /api/v1/universities/{university_id}/campuses/{campus_id}/programs/{program_id}/courses` → 200 list[CourseRead] | 404
    - Validar pertenencia completa de la cadena universidad → campus → programa
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 9.3 Actualizar endpoint legacy en `app/api/v1/endpoints/universities.py`
    - Mantener `GET /api/v1/universities/{university_id}/programs` como endpoint de compatibilidad
    - Actualizar la query para funcionar con la nueva estructura (programas a través de campus vía university_id denormalizado)
    - _Requirements: 4.5_

  - [x] 9.4 Registrar router de campus en `app/main.py`
    - Importar `campuses` desde `app/api/v1/endpoints`
    - Registrar con `app.include_router(campuses.router, prefix="/api/v1", tags=["Campus"])`
    - _Requirements: 2.1_

  - [x] 9.5 Escribir tests de integración para endpoints de campus
    - Test: POST campus retorna 201 con datos válidos
    - Test: POST campus retorna 404 si universidad no existe
    - Test: POST campus retorna 409 si combinación duplicada
    - Test: POST campus retorna 403 si no es ADMIN
    - Test: GET lista campus retorna lista paginada
    - Test: GET campus por ID retorna 200 o 404
    - Test: PATCH campus retorna 200 con campos actualizados
    - Test: GET programas por campus retorna lista filtrada
    - Test: GET cursos jerárquico retorna 404 si cadena inválida
    - Test: GET legacy `/universities/{id}/programs` sigue funcionando
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 10. Checkpoint — Verificar endpoints y aislamiento de datos
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Integración final, migración y validación
  - [x] 11.1 Verificar wiring completo de componentes
    - Asegurar que el router de campus está registrado en `app/main.py`
    - Asegurar que todos los imports en `__init__.py` están actualizados
    - Verificar que la inyección de dependencias funciona correctamente en todos los endpoints
    - Verificar que el endpoint legacy de programas por universidad sigue operativo
    - _Requirements: 2.1, 4.1, 4.5_

  - [x] 11.2 Escribir tests de integración para migración 0005
    - Test: migración sobre BD vacía completa sin errores
    - Test: migración sobre BD con programas existentes crea registros en campuses y asigna campus_id
    - Test: `upgrade()` + `downgrade()` restaura esquema sin pérdida de datos
    - Test: post-migración el UniqueConstraint `uq_program_code_campus` está activo
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8_

  - [x] 11.3 Escribir tests unitarios para aislamiento de datos por campus
    - Test: consulta filtrada por campus_id retorna solo programas de ese campus
    - Test: consulta jerárquica universidad → campus → programa → cursos respeta aislamiento
    - Test: dos campus de la misma universidad pueden tener programas con el mismo program_code
    - _Requirements: 5.1, 5.2, 5.3_

- [x] 12. Final checkpoint — Verificar integración completa
  - Ensure all tests pass, ask the user if questions arise.

## Notas

- Las tareas marcadas con `*` son opcionales y pueden omitirse para un MVP más rápido
- Cada tarea referencia requisitos específicos para trazabilidad
- Los checkpoints garantizan validación incremental
- Los tests unitarios usan `unittest.mock` / `AsyncMock` siguiendo el patrón existente del proyecto
- Los tests de integración usan `AsyncClient` con `ASGITransport` del `conftest.py` compartido
- Los archivos de test se organizan bajo `tests/unit/`, `tests/integration/` siguiendo la estructura existente
