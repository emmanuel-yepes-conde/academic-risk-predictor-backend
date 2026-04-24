# Plan de Implementación: course-crud-endpoints

## Visión General

Implementación incremental de los endpoints CRUD completos para el recurso de cursos (materias): listado con paginación (`GET /courses`), obtención por ID (`GET /courses/{course_id}`), creación (`POST /courses`), actualización parcial (`PATCH /courses/{course_id}`) y cambio de estado vía soft delete (`PATCH /courses/{course_id}/status`). Se sigue el orden de dependencias entre capas de Clean Architecture: Dominio → Infraestructura → Aplicación → API. Cada tarea construye sobre la anterior, con tests TDD (Red → Green → Refactor) integrados como sub-tareas. Se reutilizan los patrones establecidos por el CRUD de programas (`ProgramService`, `ProgramRepository`, `programs.py`) y el soft delete de usuarios (`UserService`, `UserRepository`, `users.py`).

## Tareas

- [x] 1. Agregar `CourseStatusEnum` y actualizar schemas Pydantic
  - [x] 1.1 Agregar `CourseStatusEnum` en `app/domain/enums.py`
    - Agregar clase `CourseStatusEnum(str, Enum)` con valores `ACTIVE` e `INACTIVE`
    - Seguir el patrón exacto de `UserStatusEnum`
    - _Requisitos: 3b.2, 3b.3_

  - [x] 1.2 Actualizar `CourseCreate` en `app/application/schemas/course.py`
    - Agregar `Field(..., description="...")` a todos los campos existentes (`code`, `name`, `credits`, `academic_period`)
    - Verificar que `program_id` ya tiene `Field(..., description="...")`
    - _Requisitos: 1.1, 1.4_

  - [x] 1.3 Crear `CourseUpdate` en `app/application/schemas/course.py`
    - Campos opcionales: `code` (str | None = None), `name` (str | None = None), `credits` (int | None = None), `academic_period` (str | None = None), `program_id` (UUID | None = None)
    - Excluir `id`, `professor_id`, `created_at`
    - _Requisitos: 2.1, 2.3_

  - [x] 1.4 Crear `CourseStatusUpdate` en `app/application/schemas/course.py`
    - Campo requerido: `status: CourseStatusEnum = Field(..., description="Nuevo estado del curso (ACTIVE o INACTIVE)")`
    - Importar `CourseStatusEnum` desde `app.domain.enums`
    - _Requisitos: 3b.1_

  - [x] 1.5 Actualizar `CourseRead` en `app/application/schemas/course.py`
    - Agregar campo `program_id: UUID` (actualmente faltante)
    - Agregar campo `status: CourseStatusEnum`
    - Importar `CourseStatusEnum` desde `app.domain.enums`
    - _Requisitos: 3.1, 3.2, 3.3_

  - [x] 1.6 Escribir test de propiedad para validación de `CourseCreate`
    - **Propiedad 1: CourseCreate rechaza entrada incompleta**
    - Para cualquier subconjunto de campos requeridos al que le falte al menos uno, construir `CourseCreate` debe lanzar `ValidationError`
    - Archivo: `tests/property/test_course_crud_property.py`
    - **Valida: Requisitos 1.1, 1.2**

- [x] 2. Extender interfaz `ICourseRepository` con métodos CRUD
  - [x] 2.1 Agregar métodos abstractos en `app/domain/interfaces/course_repository.py`
    - `create(data: dict) -> Course`
    - `update(course_id: UUID, data: CourseUpdate) -> Course | None`
    - `get_by_code(code: str) -> Course | None`
    - `list_all(skip: int, limit: int, status: CourseStatusEnum | None = None) -> list[Course]`
    - `count_all(status: CourseStatusEnum | None = None) -> int`
    - `update_status(course_id: UUID, status: CourseStatusEnum) -> Course | None`
    - Agregar imports de `CourseUpdate` y `CourseStatusEnum` con `TYPE_CHECKING`
    - _Requisitos: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

- [x] 3. Agregar campo `status` al modelo Course y crear migración Alembic
  - [x] 3.1 Modificar modelo `Course` en `app/infrastructure/models/course.py`
    - Agregar campo `status: CourseStatusEnum = Field(default=CourseStatusEnum.ACTIVE, nullable=False, sa_column_kwargs={"server_default": "ACTIVE"})`
    - Importar `CourseStatusEnum` desde `app.domain.enums`
    - Seguir el patrón exacto del campo `status` en `User`
    - _Requisitos: 3c.1, 3c.2_

  - [x] 3.2 Crear migración Alembic `alembic/versions/0008_add_course_status.py`
    - `upgrade()`: crear tipo enum `coursestatusenum` con `CREATE TYPE`, agregar columna `status` con `server_default="ACTIVE"`
    - `downgrade()`: eliminar columna `status`, eliminar tipo enum `coursestatusenum`
    - Seguir el patrón exacto de `0002_add_user_status.py`
    - `revision = "0008"`, `down_revision = "0007"`
    - _Requisitos: 3c.3_

- [x] 4. Implementar métodos CRUD en `CourseRepository`
  - [x] 4.1 Implementar `create(data: dict) -> Course`
    - Crear `Course(**data)`, `session.add`, `flush`, `refresh`
    - Registrar `AuditLogCreate` con `operation=INSERT`, `table_name="courses"`, `record_id=course.id`, `new_data=data`
    - Seguir el patrón del método `crear` existente en `CourseRepository`
    - _Requisitos: 5.1, 5.2_

  - [x] 4.2 Implementar `update(course_id: UUID, data: CourseUpdate) -> Course | None`
    - Obtener curso con `obtener_por_id`; si `None` retornar `None`
    - Capturar snapshot de campos actuales como `previous_data`
    - Aplicar `data.model_dump(exclude_unset=True)` con `setattr`
    - `session.add`, `flush`, `refresh`
    - Registrar `AuditLogCreate` con `operation=UPDATE`, `previous_data`, `new_data=updates`
    - Seguir el patrón de `ProgramRepository.update`
    - _Requisitos: 5.3, 5.4, 5.5_

  - [x] 4.3 Implementar `get_by_code(code: str) -> Course | None`
    - `SELECT ... WHERE code = :code`
    - _Requisitos: 5.6_

  - [x] 4.4 Implementar `list_all(skip: int, limit: int, status: CourseStatusEnum | None = None) -> list[Course]`
    - `SELECT ... FROM courses [WHERE status = :status] OFFSET :skip LIMIT :limit`
    - Filtrar por status cuando se proporciona
    - _Requisitos: 5.7_

  - [x] 4.5 Implementar `count_all(status: CourseStatusEnum | None = None) -> int`
    - `SELECT COUNT(*) FROM courses [WHERE status = :status]`
    - Filtrar por status cuando se proporciona
    - _Requisitos: 5.8_

  - [x] 4.6 Implementar `update_status(course_id: UUID, status: CourseStatusEnum) -> Course | None`
    - Obtener curso con `obtener_por_id`; si `None` retornar `None`
    - Actualizar solo el campo `status`
    - Registrar `AuditLogCreate` con `operation=UPDATE`, `previous_data={"status": prev}`, `new_data={"status": new}`
    - Seguir el patrón de `UserRepository.update_status`
    - _Requisitos: 5.9, 5.10, 5.11_

  - [x] 4.7 Escribir test de propiedad para round-trip de creación y búsqueda por code
    - **Propiedad 3: Round-trip de creación y búsqueda por code**
    - Para cualquier dato de curso válido, `create` seguido de `get_by_code(course.code)` debe retornar un curso con el mismo `id` y los mismos valores en todos los campos
    - Archivo: `tests/property/test_course_crud_property.py`
    - **Valida: Requisitos 5.1, 5.6**

  - [x] 4.8 Escribir test de propiedad para audit log de operaciones de escritura
    - **Propiedad 4: Operaciones de escritura registran audit log correcto**
    - Para cualquier operación de escritura (create, update, update_status), el repositorio debe registrar un `AuditLog` con `table_name="courses"`, la operación correcta (`INSERT` o `UPDATE`), y los datos correspondientes
    - Archivo: `tests/property/test_course_crud_property.py`
    - **Valida: Requisitos 5.2, 5.4, 5.11**

  - [x] 4.9 Escribir test de propiedad para consistencia de list y count por status
    - **Propiedad 5: Listado y conteo filtran por status consistentemente**
    - Para cualquier conjunto de cursos con estados mixtos, `list_all(status=S)` y `count_all(status=S)` deben retornar solo cursos con status `S`, y `count_all(status=S)` debe ser igual a `len(list_all(status=S))` sin paginación
    - Archivo: `tests/property/test_course_crud_property.py`
    - **Valida: Requisitos 5.7, 5.8, 6.8, 7.3**

- [x] 5. Checkpoint — Verificar capa de dominio e infraestructura
  - Asegurarse de que todos los tests pasen, consultar al usuario si surgen dudas.

- [x] 6. Crear `CourseService` con validación de unicidad y paginación
  - [x] 6.1 Crear `CourseService` en `app/application/services/course_service.py`
    - Constructor recibe `repo: ICourseRepository` (DIP)
    - Seguir el patrón combinado de `ProgramService` (unicidad) y `UserService` (paginación con default de status)
    - _Requisitos: 6.1_

  - [x] 6.2 Implementar `create_course(data: CourseCreate) -> CourseRead`
    - Verificar unicidad de `code` con `repo.get_by_code`; si existe lanzar `HTTPException(409, "El code ya está registrado")`
    - Delegar a `repo.create(data.model_dump())` y retornar `CourseRead.model_validate(course)`
    - _Requisitos: 6.2, 6.3_

  - [x] 6.3 Implementar `get_course(course_id: UUID) -> CourseRead`
    - Obtener curso con `repo.obtener_por_id`; si `None` lanzar `HTTPException(404, "Curso no encontrado")`
    - Retornar `CourseRead.model_validate(course)`
    - _Requisitos: 6.7_

  - [x] 6.4 Implementar `list_courses(status, skip, limit) -> PaginatedResponse[CourseRead]`
    - Aplicar `status=ACTIVE` como default cuando `status is None`
    - Ejecutar `repo.list_all` y `repo.count_all` en paralelo con `asyncio.gather`
    - Retornar `PaginatedResponse[CourseRead]` reutilizando el genérico de `app/application/schemas/user.py`
    - _Requisitos: 6.8_

  - [x] 6.5 Implementar `update_course(course_id: UUID, data: CourseUpdate) -> CourseRead`
    - Si `data.code` está definido: verificar unicidad excluyendo el curso actual (`existing.id != course_id`); si conflicto lanzar `HTTPException(409, "El code ya está registrado")`
    - Delegar a `repo.update(course_id, data)`; si `None` lanzar `HTTPException(404, "Curso no encontrado")`
    - Retornar `CourseRead.model_validate(course)`
    - _Requisitos: 6.4, 6.5, 6.6_

  - [x] 6.6 Implementar `update_course_status(course_id: UUID, status: CourseStatusEnum) -> CourseRead`
    - Delegar a `repo.update_status(course_id, status)`; si `None` lanzar `HTTPException(404, "Curso no encontrado")`
    - Retornar `CourseRead.model_validate(course)`
    - _Requisitos: 6.9_

  - [x] 6.7 Escribir tests unitarios para `CourseService`
    - Archivo: `tests/unit/test_course_service.py`
    - `test_create_course_success` — camino feliz con datos válidos
    - `test_create_course_duplicate_code_returns_409` — verificación exacta del mensaje de error
    - `test_get_course_success` — obtención por ID existente
    - `test_get_course_not_found_returns_404` — ID inexistente
    - `test_update_course_success` — camino feliz de actualización parcial
    - `test_update_course_not_found_returns_404` — ID inexistente
    - `test_update_course_duplicate_code_different_course_returns_409` — code de otro curso
    - `test_update_course_same_code_no_conflict` — auto-actualización con mismo code
    - `test_update_course_status_success` — cambio de estado exitoso
    - `test_update_course_status_not_found_returns_404` — ID inexistente
    - `test_list_courses_default_status_active` — verifica que status=None se convierte en ACTIVE
    - Usar `unittest.mock.AsyncMock` para mockear `ICourseRepository`
    - _Requisitos: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9_

  - [x] 6.8 Escribir test de propiedad para rechazo de code duplicado en creación
    - **Propiedad 6: Creación rechaza code duplicado**
    - Para cualquier `code` que ya pertenezca a un curso existente, `create_course` debe lanzar `HTTPException` con código 409 y detalle "El code ya está registrado"
    - Archivo: `tests/property/test_course_crud_property.py`
    - **Valida: Requisitos 6.2, 6.3, 12.1**

  - [x] 6.9 Escribir test de propiedad para validación de unicidad en actualización
    - **Propiedad 7: Validación de unicidad en actualización**
    - Para cualesquiera dos cursos distintos A y B, `update_course(A.id, CourseUpdate(code=B.code))` debe lanzar `HTTPException` con código 409. Sin embargo, `update_course(A.id, CourseUpdate(code=A.code))` debe tener éxito sin error de conflicto
    - Archivo: `tests/property/test_course_crud_property.py`
    - **Valida: Requisitos 6.5, 6.6, 12.2, 12.3**

  - [x] 6.10 Escribir test de propiedad para preservación de campos omitidos
    - **Propiedad 2: Actualización parcial preserva campos omitidos**
    - Para cualquier curso existente y cualquier subconjunto no vacío de campos de `CourseUpdate`, `update_course` debe modificar solo los campos proporcionados y dejar los omitidos sin cambios
    - Archivo: `tests/property/test_course_crud_property.py`
    - **Valida: Requisitos 2.2, 5.3**

- [x] 7. Checkpoint — Verificar capa de servicio
  - Asegurarse de que todos los tests pasen, consultar al usuario si surgen dudas.

- [x] 8. Implementar endpoints CRUD en `courses.py`
  - [x] 8.1 Agregar helper `_get_course_service` en `app/api/v1/endpoints/courses.py`
    - `def _get_course_service(session: AsyncSession = Depends(get_session)) -> CourseService`
    - Retornar `CourseService(CourseRepository(session))`
    - Agregar imports necesarios: `CourseService`, `CourseCreate`, `CourseUpdate`, `CourseStatusUpdate`, `CourseRead`, `PaginatedResponse`, `CourseStatusEnum`, `CurrentUser`, `get_current_user`, `require_roles`, `RoleEnum`
    - _Requisitos: 7.1, 8.1, 9.1, 10.1, 11.1_

  - [x] 8.2 Implementar `GET /courses`
    - `response_model=PaginatedResponse[CourseRead]`, `status_code=200`
    - `summary="Listar cursos con paginación"`, `description="Retorna una lista paginada de cursos. Por defecto solo muestra cursos ACTIVE."`, `tags=["Cursos"]`
    - Parámetros: `status: CourseStatusEnum | None = None`, `skip: int = Query(0, ge=0)`, `limit: int = Query(20, ge=1, le=100)`, `current_user: CurrentUser = Depends(get_current_user)`, `service: CourseService = Depends(_get_course_service)`
    - Delegar a `service.list_courses(status, skip, limit)`
    - _Requisitos: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [x] 8.3 Implementar `GET /courses/{course_id}`
    - `response_model=CourseRead`, `status_code=200`
    - `summary="Obtener un curso por ID"`, `description="Retorna los datos de un curso específico, o 404 si no existe."`, `tags=["Cursos"]`
    - Parámetros: `course_id: UUID`, `current_user: CurrentUser = Depends(get_current_user)`, `service: CourseService = Depends(_get_course_service)`
    - Delegar a `service.get_course(course_id)`
    - _Requisitos: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 8.4 Implementar `POST /courses`
    - `response_model=CourseRead`, `status_code=201`
    - `summary="Crear un curso"`, `description="Crea un nuevo curso. Requiere rol ADMIN. Valida unicidad de code."`, `tags=["Cursos"]`
    - Parámetros: `body: CourseCreate`, `current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN))`, `service: CourseService = Depends(_get_course_service)`
    - Delegar a `service.create_course(body)`
    - _Requisitos: 9.1, 9.2, 9.3, 9.4, 9.7_

  - [x] 8.5 Implementar `PATCH /courses/{course_id}`
    - `response_model=CourseRead`, `status_code=200`
    - `summary="Actualizar parcialmente un curso"`, `description="Actualiza los campos proporcionados de un curso existente. Requiere rol ADMIN. Valida unicidad de code."`, `tags=["Cursos"]`
    - Parámetros: `course_id: UUID`, `body: CourseUpdate`, `current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN))`, `service: CourseService = Depends(_get_course_service)`
    - Delegar a `service.update_course(course_id, body)`
    - _Requisitos: 10.1, 10.2, 10.3, 10.4, 10.5, 10.8_

  - [x] 8.6 Implementar `PATCH /courses/{course_id}/status`
    - `response_model=CourseRead`, `status_code=200`
    - `summary="Cambiar estado de un curso (soft delete / reactivación)"`, `description="Cambia el estado de un curso a ACTIVE o INACTIVE. Requiere rol ADMIN."`, `tags=["Cursos"]`
    - Parámetros: `course_id: UUID`, `body: CourseStatusUpdate`, `current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN))`, `service: CourseService = Depends(_get_course_service)`
    - Delegar a `service.update_course_status(course_id, body.status)`
    - _Requisitos: 11.1, 11.2, 11.3, 11.4, 11.5, 11.8_

  - [x] 8.7 Escribir tests de integración para endpoints de cursos
    - Archivo: `tests/integration/test_course_endpoints.py`
    - `test_get_courses_returns_200` — listado con auth válida
    - `test_get_courses_default_active_filter` — solo cursos ACTIVE sin parámetro status
    - `test_get_course_by_id_returns_200` — obtención por ID con auth válida
    - `test_get_course_by_id_not_found_returns_404` — ID inexistente
    - `test_post_courses_returns_201` — creación válida con auth ADMIN
    - `test_post_courses_duplicate_code_returns_409` — code duplicado
    - `test_post_courses_missing_field_returns_422` — campo requerido faltante
    - `test_post_courses_no_auth_returns_401` — JWT faltante
    - `test_post_courses_non_admin_returns_403` — rol STUDENT/PROFESSOR
    - `test_patch_course_returns_200` — actualización válida con auth ADMIN
    - `test_patch_course_not_found_returns_404` — curso inexistente
    - `test_patch_course_status_returns_200` — cambio de estado exitoso
    - `test_patch_course_status_not_found_returns_404` — curso inexistente
    - `test_patch_course_status_no_auth_returns_401` — JWT faltante
    - `test_patch_course_status_non_admin_returns_403` — rol no-ADMIN
    - Usar `AsyncClient` con `ASGITransport` del `conftest.py` compartido
    - _Requisitos: 7.1–7.6, 8.1–8.5, 9.1–9.7, 10.1–10.8, 11.1–11.8, 12.1, 12.2, 12.3_

  - [x] 8.8 Escribir test de propiedad para rechazo de rol no-ADMIN
    - **Propiedad 8: Rechazo de rol no-ADMIN en endpoints de escritura**
    - Para cualquier usuario autenticado cuyo rol no sea `ADMIN`, `POST /courses`, `PATCH /courses/{id}` y `PATCH /courses/{id}/status` deben retornar código 403
    - Archivo: `tests/property/test_course_crud_property.py`
    - **Valida: Requisitos 9.4, 9.6, 10.5, 10.7, 11.5, 11.7**

- [x] 9. Checkpoint final — Verificar integración completa
  - Asegurarse de que todos los tests pasen, consultar al usuario si surgen dudas.

## Notas

- Las tareas marcadas con `*` son opcionales y pueden omitirse para un MVP más rápido
- Cada tarea referencia requisitos específicos para trazabilidad
- Los checkpoints garantizan validación incremental
- Los tests de propiedades validan invariantes universales con Hypothesis (archivo: `tests/property/test_course_crud_property.py`)
- Los tests unitarios validan ejemplos concretos y casos borde (archivo: `tests/unit/test_course_service.py`)
- Los tests de integración validan el flujo completo HTTP → servicio → repositorio (archivo: `tests/integration/test_course_endpoints.py`)
- Se requiere migración Alembic `0008_add_course_status.py` para agregar la columna `status` a la tabla `courses`
- El campo `professor_id` NO se gestiona por el CRUD — se mantiene exclusivamente en el flujo de asignación profesor-curso existente
