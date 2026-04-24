# Documento de Requisitos — Endpoints CRUD de Cursos (Materias)

## Introducción

Este documento define los requisitos para agregar los endpoints CRUD faltantes al recurso de cursos (materias): listado con paginación (`GET /courses`), obtención por ID (`GET /courses/{course_id}`), creación (`POST /courses`), actualización parcial (`PATCH /courses/{course_id}`) y desactivación por soft delete (`PATCH /courses/{course_id}/status`). Actualmente el sistema solo expone endpoints de asignación profesor-curso y listado de estudiantes, pero carece de operaciones CRUD básicas. Los nuevos endpoints seguirán la arquitectura limpia del proyecto (Dominio → Aplicación → Infraestructura → API) y el patrón establecido por el CRUD de programas (`program-crud-endpoints`) y el soft delete de usuarios (`PATCH /users/{user_id}/status`).

## Glosario

- **API**: Interfaz de programación de aplicaciones REST expuesta por el backend FastAPI.
- **Course**: Entidad que representa un curso (materia) con campos: `id`, `code`, `name`, `credits`, `academic_period`, `program_id`, `professor_id`, `status`, `created_at`.
- **CourseCreate**: Schema Pydantic de entrada para la creación de un curso.
- **CourseUpdate**: Schema Pydantic de entrada para la actualización parcial de un curso.
- **CourseStatusUpdate**: Schema Pydantic de entrada para cambiar el estado de un curso (soft delete / reactivación).
- **CourseRead**: Schema Pydantic de salida que representa un curso.
- **CourseStatusEnum**: Enumeración con valores `ACTIVE` e `INACTIVE` para el campo `status` del curso.
- **CourseService**: Servicio de aplicación que encapsula la lógica de negocio de cursos.
- **CourseRepository**: Implementación del repositorio que persiste cursos en PostgreSQL.
- **ICourseRepository**: Interfaz abstracta del repositorio de cursos en la capa de dominio.
- **Admin**: Usuario autenticado con rol `ADMIN`.
- **AuditLog**: Registro de auditoría que se crea por cada operación de escritura en la base de datos.
- **code**: Código único del curso (ej. `MAT101`).
- **program_id**: Identificador UUID del programa académico al que pertenece el curso (FK → `programs.id`).
- **professor_id**: Identificador UUID del profesor asignado al curso (FK → `users.id`). Gestionado por el flujo de asignación profesor-curso, no por el CRUD de cursos.

## Requisitos

### Requisito 1: Schema de Creación de Curso

**Historia de Usuario:** Como administrador, quiero enviar los datos de un curso en formato validado, para que el sistema garantice la integridad de los datos antes de persistirlos.

#### Criterios de Aceptación

1. THE CourseCreate schema SHALL require the fields: `code` (str), `name` (str), `credits` (int), `academic_period` (str), and `program_id` (UUID).
2. WHEN a request body is missing any required field, THE API SHALL return a 422 status code with a descriptive validation error.
3. THE CourseCreate schema SHALL exclude the fields `id`, `professor_id`, and `created_at` from the input.
4. THE CourseCreate schema SHALL include `Field(description=...)` on each field for OpenAPI documentation.

### Requisito 2: Schema de Actualización Parcial de Curso

**Historia de Usuario:** Como administrador, quiero enviar solo los campos que deseo modificar de un curso, para que el sistema actualice únicamente esos campos sin alterar los demás.

#### Criterios de Aceptación

1. THE CourseUpdate schema SHALL define all fields as optional: `code` (str | None), `name` (str | None), `credits` (int | None), `academic_period` (str | None), and `program_id` (UUID | None).
2. WHEN a PATCH request body contains only a subset of fields, THE CourseService SHALL update only the provided fields and preserve the existing values for omitted fields.
3. THE CourseUpdate schema SHALL exclude the fields `id`, `professor_id`, and `created_at` from the input.

### Requisito 3: Schema de Lectura de Curso

**Historia de Usuario:** Como consumidor de la API, quiero que la respuesta de un curso incluya los campos `program_id` y `status`, para que pueda identificar a qué programa pertenece el curso y si está activo o inactivo.

#### Criterios de Aceptación

1. THE CourseRead schema SHALL include the field `program_id` (UUID) in the response.
2. THE CourseRead schema SHALL include the field `status` (CourseStatusEnum) in the response.
3. THE CourseRead schema SHALL include the fields: `id` (UUID), `code` (str), `name` (str), `credits` (int), `academic_period` (str), `program_id` (UUID), `professor_id` (UUID | None), `status` (CourseStatusEnum), and `created_at` (datetime).

### Requisito 3b: Schema de Cambio de Estado de Curso

**Historia de Usuario:** Como administrador, quiero enviar el nuevo estado de un curso, para que el sistema permita desactivar o reactivar cursos sin eliminarlos.

#### Criterios de Aceptación

1. THE CourseStatusUpdate schema SHALL require the field `status` (CourseStatusEnum).
2. THE CourseStatusEnum SHALL define two values: `ACTIVE` and `INACTIVE`.
3. THE CourseStatusEnum SHALL be added to `app/domain/enums.py` following the pattern of `UserStatusEnum`.

### Requisito 3c: Campo `status` en el Modelo Course

**Historia de Usuario:** Como desarrollador, quiero que el modelo Course tenga un campo `status` con valor por defecto `ACTIVE`, para soportar soft delete sin eliminar registros de la base de datos.

#### Criterios de Aceptación

1. THE Course model SHALL include a `status` field of type `CourseStatusEnum` with default value `ACTIVE`.
2. THE `status` field SHALL be non-nullable with a server default of `"ACTIVE"`.
3. A new Alembic migration SHALL add the `status` column to the `courses` table and the `coursestatusenum` PostgreSQL enum type.

### Requisito 4: Interfaz del Repositorio de Cursos

**Historia de Usuario:** Como desarrollador, quiero que la interfaz del repositorio de cursos defina contratos para las operaciones CRUD completas, para que la capa de dominio permanezca desacoplada de la infraestructura.

#### Criterios de Aceptación

1. THE ICourseRepository SHALL define an abstract method `create(data: dict) -> Course` for persisting a new course.
2. THE ICourseRepository SHALL define an abstract method `update(course_id: UUID, data: CourseUpdate) -> Course | None` for updating an existing course.
3. THE ICourseRepository SHALL define an abstract method `get_by_code(code: str) -> Course | None` for looking up a course by its unique code.
4. THE ICourseRepository SHALL define an abstract method `list_all(skip: int, limit: int) -> list[Course]` for paginated listing of courses.
5. THE ICourseRepository SHALL define an abstract method `count_all() -> int` for counting the total number of courses.
6. THE ICourseRepository SHALL define an abstract method `update_status(course_id: UUID, status: CourseStatusEnum) -> Course | None` for changing the status of a course (soft delete / reactivation).

### Requisito 5: Implementación del Repositorio de Cursos

**Historia de Usuario:** Como desarrollador, quiero que el repositorio de cursos implemente las operaciones CRUD con auditoría, para que cada escritura quede registrada.

#### Criterios de Aceptación

1. WHEN the `create` method is called, THE CourseRepository SHALL persist a new Course record in the database and return the created Course entity.
2. WHEN the `create` method is called, THE CourseRepository SHALL register an AuditLog entry with operation `INSERT` and table name `courses`.
3. WHEN the `update` method is called with a valid course ID, THE CourseRepository SHALL apply only the provided fields to the existing record and return the updated Course entity.
4. WHEN the `update` method is called, THE CourseRepository SHALL register an AuditLog entry with operation `UPDATE`, the previous data, and the new data.
5. WHEN the `update` method is called with a non-existent course ID, THE CourseRepository SHALL return None.
6. WHEN the `get_by_code` method is called, THE CourseRepository SHALL return the matching Course or None if no match exists.
7. WHEN the `list_all` method is called with `skip` and `limit` parameters, THE CourseRepository SHALL return the corresponding page of Course records ordered consistently, filtering by `status` when provided.
8. WHEN the `count_all` method is called, THE CourseRepository SHALL return the total number of Course records in the database, filtering by `status` when provided.
9. WHEN the `update_status` method is called with a valid course ID, THE CourseRepository SHALL update the `status` field and return the updated Course entity.
10. WHEN the `update_status` method is called with a non-existent course ID, THE CourseRepository SHALL return None.
11. WHEN the `update_status` method is called, THE CourseRepository SHALL register an AuditLog entry with operation `UPDATE`, the previous status, and the new status.

### Requisito 6: Servicio de Aplicación de Cursos

**Historia de Usuario:** Como desarrollador, quiero un servicio de aplicación que encapsule la lógica de negocio de cursos, para que los endpoints deleguen la validación y orquestación al servicio.

#### Criterios de Aceptación

1. THE CourseService SHALL receive an ICourseRepository as a constructor dependency.
2. WHEN the `create_course` method is called, THE CourseService SHALL validate that no existing course has the same `code` and persist the new course.
3. WHEN a course with the same `code` already exists, THE CourseService SHALL raise an HTTPException with status code 409 and detail "El code ya está registrado".
4. WHEN the `update_course` method is called with a non-existent course ID, THE CourseService SHALL raise an HTTPException with status code 404 and detail "Curso no encontrado".
5. WHEN the `update_course` method is called with a `code` that belongs to a different course, THE CourseService SHALL raise an HTTPException with status code 409 and detail "El code ya está registrado".
6. WHEN the `update_course` method is called with a `code` that belongs to the same course being updated, THE CourseService SHALL allow the update without raising a conflict error.
7. WHEN the `get_course` method is called with a non-existent course ID, THE CourseService SHALL raise an HTTPException with status code 404 and detail "Curso no encontrado".
8. WHEN the `list_courses` method is called, THE CourseService SHALL return a paginated list of courses and the total count, applying `status=ACTIVE` as default filter when no status is specified.
9. WHEN the `update_course_status` method is called with a non-existent course ID, THE CourseService SHALL raise an HTTPException with status code 404 and detail "Curso no encontrado".

### Requisito 7: Endpoint GET /courses (Listado con Paginación)

**Historia de Usuario:** Como consumidor de la API, quiero listar todos los cursos con paginación, para que pueda navegar eficientemente por el catálogo de cursos.

#### Criterios de Aceptación

1. THE API SHALL expose a `GET /api/v1/courses` endpoint that returns a list of CourseRead objects.
2. THE API endpoint SHALL accept optional query parameters `skip` (int, default 0), `limit` (int, default 20), and `status` (CourseStatusEnum, optional).
3. WHEN the endpoint is called without a `status` parameter, THE API SHALL default to returning only `ACTIVE` courses.
4. WHEN the endpoint is called, THE API SHALL return a 200 status code with the paginated list of courses and a `total` count.
5. THE API endpoint SHALL require authentication via JWT Bearer token.
6. THE API endpoint SHALL include `summary`, `description`, `response_model`, `status_code`, and `tags` in its decorator following the project documentation standards.

### Requisito 8: Endpoint GET /courses/{course_id}

**Historia de Usuario:** Como consumidor de la API, quiero obtener los detalles de un curso específico por su ID, para que pueda consultar la información completa del curso.

#### Criterios de Aceptación

1. THE API SHALL expose a `GET /api/v1/courses/{course_id}` endpoint that returns a CourseRead response.
2. WHEN the `course_id` path parameter matches an existing course, THE API SHALL return a 200 status code with the course data.
3. WHEN the `course_id` path parameter does not match any existing course, THE API SHALL return a 404 status code with detail "Curso no encontrado".
4. THE API endpoint SHALL require authentication via JWT Bearer token.
5. THE API endpoint SHALL include `summary`, `description`, `response_model`, `status_code`, and `tags` in its decorator following the project documentation standards.

### Requisito 9: Endpoint POST /courses

**Historia de Usuario:** Como administrador, quiero crear un curso mediante una petición POST, para que el sistema registre nuevos cursos.

#### Criterios de Aceptación

1. THE API SHALL expose a `POST /api/v1/courses` endpoint that accepts a CourseCreate body and returns a CourseRead response.
2. WHEN a valid CourseCreate body is submitted, THE API SHALL return a 201 status code with the created course data.
3. THE API endpoint SHALL require authentication via JWT Bearer token.
4. THE API endpoint SHALL restrict access to users with the ADMIN role only.
5. WHEN an unauthenticated request is received, THE API SHALL return a 401 status code.
6. WHEN a non-ADMIN authenticated user sends a request, THE API SHALL return a 403 status code.
7. THE API endpoint SHALL include `summary`, `description`, `response_model`, `status_code`, and `tags` in its decorator following the project documentation standards.

### Requisito 10: Endpoint PATCH /courses/{course_id}

**Historia de Usuario:** Como administrador, quiero actualizar parcialmente un curso mediante una petición PATCH, para que el sistema permita modificar campos específicos sin reemplazar todo el recurso.

#### Criterios de Aceptación

1. THE API SHALL expose a `PATCH /api/v1/courses/{course_id}` endpoint that accepts a CourseUpdate body and returns a CourseRead response.
2. WHEN a valid CourseUpdate body is submitted for an existing course, THE API SHALL return a 200 status code with the updated course data.
3. WHEN the `course_id` path parameter does not match any existing course, THE API SHALL return a 404 status code with detail "Curso no encontrado".
4. THE API endpoint SHALL require authentication via JWT Bearer token.
5. THE API endpoint SHALL restrict access to users with the ADMIN role only.
6. WHEN an unauthenticated request is received, THE API SHALL return a 401 status code.
7. WHEN a non-ADMIN authenticated user sends a request, THE API SHALL return a 403 status code.
8. THE API endpoint SHALL include `summary`, `description`, `response_model`, `status_code`, and `tags` in its decorator following the project documentation standards.

### Requisito 11: Endpoint PATCH /courses/{course_id}/status (Soft Delete / Reactivación)

**Historia de Usuario:** Como administrador, quiero cambiar el estado de un curso a INACTIVE o ACTIVE, para que el sistema permita desactivar cursos sin perder datos ni romper relaciones existentes (inscripciones, asignaciones de profesor, audit logs).

#### Criterios de Aceptación

1. THE API SHALL expose a `PATCH /api/v1/courses/{course_id}/status` endpoint that accepts a CourseStatusUpdate body and returns a CourseRead response.
2. WHEN a valid CourseStatusUpdate body is submitted for an existing course, THE API SHALL update the course status and return a 200 status code with the updated course data.
3. WHEN the `course_id` path parameter does not match any existing course, THE API SHALL return a 404 status code with detail "Curso no encontrado".
4. THE API endpoint SHALL require authentication via JWT Bearer token.
5. THE API endpoint SHALL restrict access to users with the ADMIN role only.
6. WHEN an unauthenticated request is received, THE API SHALL return a 401 status code.
7. WHEN a non-ADMIN authenticated user sends a request, THE API SHALL return a 403 status code.
8. THE API endpoint SHALL include `summary`, `description`, `response_model`, `status_code`, and `tags` in its decorator following the project documentation standards.

### Requisito 12: Validación de Unicidad en Creación y Actualización

**Historia de Usuario:** Como administrador, quiero que el sistema rechace cursos con códigos duplicados, para que se mantenga la integridad de los datos.

#### Criterios de Aceptación

1. WHEN a POST request contains a `code` that already exists in the database, THE API SHALL return a 409 status code with detail "El code ya está registrado".
2. WHEN a PATCH request contains a `code` that belongs to a different course, THE API SHALL return a 409 status code with detail "El code ya está registrado".
3. WHEN a PATCH request contains a `code` identical to the current value of the course being updated, THE API SHALL process the update without conflict.
