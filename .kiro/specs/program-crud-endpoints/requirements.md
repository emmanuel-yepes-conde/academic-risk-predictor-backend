# Documento de Requisitos — Endpoints CRUD de Programas (CREATE y UPDATE)

## Introducción

Este documento define los requisitos para agregar los endpoints faltantes de creación (`POST /programs`) y actualización parcial (`PATCH /programs/{program_id}`) al recurso de programas académicos. Actualmente el sistema solo soporta operaciones de lectura (GET). Los nuevos endpoints seguirán la arquitectura limpia del proyecto (Dominio → Aplicación → Infraestructura → API) y el patrón establecido por el CRUD de usuarios.

## Glosario

- **API**: Interfaz de programación de aplicaciones REST expuesta por el backend FastAPI.
- **Program**: Entidad que representa un programa académico con campos: `id`, `institution`, `degree_type`, `program_code`, `program_name`, `academic_group`, `location`, `snies_code`, `created_at`.
- **ProgramCreate**: Schema Pydantic de entrada para la creación de un programa.
- **ProgramUpdate**: Schema Pydantic de entrada para la actualización parcial de un programa.
- **ProgramRead**: Schema Pydantic de salida que representa un programa.
- **ProgramService**: Servicio de aplicación que encapsula la lógica de negocio de programas.
- **ProgramRepository**: Implementación del repositorio que persiste programas en PostgreSQL.
- **IProgramRepository**: Interfaz abstracta del repositorio de programas en la capa de dominio.
- **Admin**: Usuario autenticado con rol `ADMIN`.
- **AuditLog**: Registro de auditoría que se crea por cada operación de escritura en la base de datos.
- **program_code**: Código único del programa académico (ej. `M0200`).
- **snies_code**: Código SNIES único asignado por el Ministerio de Educación Nacional de Colombia.

## Requisitos

### Requisito 1: Schema de Creación de Programa

**Historia de Usuario:** Como administrador, quiero enviar los datos de un programa académico en formato validado, para que el sistema garantice la integridad de los datos antes de persistirlos.

#### Criterios de Aceptación

1. THE ProgramCreate schema SHALL require the fields: `institution` (str), `degree_type` (str), `program_code` (str), `program_name` (str), `academic_group` (str), `location` (str), and `snies_code` (int).
2. WHEN a request body is missing any required field, THE API SHALL return a 422 status code with a descriptive validation error.
3. THE ProgramCreate schema SHALL exclude the fields `id` and `created_at` from the input.

### Requisito 2: Schema de Actualización Parcial de Programa

**Historia de Usuario:** Como administrador, quiero enviar solo los campos que deseo modificar de un programa, para que el sistema actualice únicamente esos campos sin alterar los demás.

#### Criterios de Aceptación

1. THE ProgramUpdate schema SHALL define all fields as optional: `institution` (str | None), `degree_type` (str | None), `program_code` (str | None), `program_name` (str | None), `academic_group` (str | None), `location` (str | None), and `snies_code` (int | None).
2. WHEN a PATCH request body contains only a subset of fields, THE ProgramService SHALL update only the provided fields and preserve the existing values for omitted fields.

### Requisito 3: Interfaz del Repositorio de Programas

**Historia de Usuario:** Como desarrollador, quiero que la interfaz del repositorio de programas defina contratos para crear y actualizar, para que la capa de dominio permanezca desacoplada de la infraestructura.

#### Criterios de Aceptación

1. THE IProgramRepository SHALL define an abstract method `create(data: dict) -> Program` for persisting a new program.
2. THE IProgramRepository SHALL define an abstract method `update(program_id: UUID, data: ProgramUpdate) -> Program | None` for updating an existing program.
3. THE IProgramRepository SHALL define an abstract method `get_by_program_code(program_code: str) -> Program | None` for looking up a program by its unique program code.
4. THE IProgramRepository SHALL define an abstract method `get_by_snies_code(snies_code: int) -> Program | None` for looking up a program by its unique SNIES code.

### Requisito 4: Implementación del Repositorio de Programas

**Historia de Usuario:** Como desarrollador, quiero que el repositorio de programas implemente las operaciones de creación y actualización con auditoría, para que cada escritura quede registrada.

#### Criterios de Aceptación

1. WHEN the `create` method is called, THE ProgramRepository SHALL persist a new Program record in the database and return the created Program entity.
2. WHEN the `create` method is called, THE ProgramRepository SHALL register an AuditLog entry with operation `INSERT` and table name `programs`.
3. WHEN the `update` method is called with a valid program ID, THE ProgramRepository SHALL apply only the provided fields to the existing record and return the updated Program entity.
4. WHEN the `update` method is called, THE ProgramRepository SHALL register an AuditLog entry with operation `UPDATE`, the previous data, and the new data.
5. WHEN the `update` method is called with a non-existent program ID, THE ProgramRepository SHALL return None.
6. WHEN the `get_by_program_code` method is called, THE ProgramRepository SHALL return the matching Program or None if no match exists.
7. WHEN the `get_by_snies_code` method is called, THE ProgramRepository SHALL return the matching Program or None if no match exists.

### Requisito 5: Servicio de Aplicación de Programas

**Historia de Usuario:** Como desarrollador, quiero un servicio de aplicación que encapsule la lógica de negocio de programas, para que los endpoints deleguen la validación y orquestación al servicio.

#### Criterios de Aceptación

1. THE ProgramService SHALL receive an IProgramRepository as a constructor dependency.
2. WHEN the `create_program` method is called, THE ProgramService SHALL validate that no existing program has the same `program_code` and persist the new program.
3. WHEN the `create_program` method is called, THE ProgramService SHALL validate that no existing program has the same `snies_code` and persist the new program.
4. WHEN a program with the same `program_code` already exists, THE ProgramService SHALL raise an HTTPException with status code 409 and detail "El program_code ya está registrado".
5. WHEN a program with the same `snies_code` already exists, THE ProgramService SHALL raise an HTTPException with status code 409 and detail "El snies_code ya está registrado".
6. WHEN the `update_program` method is called with a non-existent program ID, THE ProgramService SHALL raise an HTTPException with status code 404 and detail "Programa no encontrado".
7. WHEN the `update_program` method is called with a `program_code` that belongs to a different program, THE ProgramService SHALL raise an HTTPException with status code 409 and detail "El program_code ya está registrado".
8. WHEN the `update_program` method is called with a `snies_code` that belongs to a different program, THE ProgramService SHALL raise an HTTPException with status code 409 and detail "El snies_code ya está registrado".
9. WHEN the `update_program` method is called with a `program_code` or `snies_code` that belongs to the same program being updated, THE ProgramService SHALL allow the update without raising a conflict error.

### Requisito 6: Endpoint POST /programs

**Historia de Usuario:** Como administrador, quiero crear un programa académico mediante una petición POST, para que el sistema registre nuevos programas.

#### Criterios de Aceptación

1. THE API SHALL expose a `POST /api/v1/programs` endpoint that accepts a ProgramCreate body and returns a ProgramRead response.
2. WHEN a valid ProgramCreate body is submitted, THE API SHALL return a 201 status code with the created program data.
3. THE API endpoint SHALL require authentication via JWT Bearer token.
4. THE API endpoint SHALL restrict access to users with the ADMIN role only.
5. WHEN an unauthenticated request is received, THE API SHALL return a 401 status code.
6. WHEN a non-ADMIN authenticated user sends a request, THE API SHALL return a 403 status code.
7. THE API endpoint SHALL include `summary`, `description`, `response_model`, `status_code`, and `tags` in its decorator following the project documentation standards.

### Requisito 7: Endpoint PATCH /programs/{program_id}

**Historia de Usuario:** Como administrador, quiero actualizar parcialmente un programa académico mediante una petición PATCH, para que el sistema permita modificar campos específicos sin reemplazar todo el recurso.

#### Criterios de Aceptación

1. THE API SHALL expose a `PATCH /api/v1/programs/{program_id}` endpoint that accepts a ProgramUpdate body and returns a ProgramRead response.
2. WHEN a valid ProgramUpdate body is submitted for an existing program, THE API SHALL return a 200 status code with the updated program data.
3. WHEN the `program_id` path parameter does not match any existing program, THE API SHALL return a 404 status code with detail "Programa no encontrado".
4. THE API endpoint SHALL require authentication via JWT Bearer token.
5. THE API endpoint SHALL restrict access to users with the ADMIN role only.
6. WHEN an unauthenticated request is received, THE API SHALL return a 401 status code.
7. WHEN a non-ADMIN authenticated user sends a request, THE API SHALL return a 403 status code.
8. THE API endpoint SHALL include `summary`, `description`, `response_model`, `status_code`, and `tags` in its decorator following the project documentation standards.

### Requisito 8: Validación de Unicidad en Creación y Actualización

**Historia de Usuario:** Como administrador, quiero que el sistema rechace programas con códigos duplicados, para que se mantenga la integridad de los datos.

#### Criterios de Aceptación

1. WHEN a POST request contains a `program_code` that already exists in the database, THE API SHALL return a 409 status code with detail "El program_code ya está registrado".
2. WHEN a POST request contains a `snies_code` that already exists in the database, THE API SHALL return a 409 status code with detail "El snies_code ya está registrado".
3. WHEN a PATCH request contains a `program_code` that belongs to a different program, THE API SHALL return a 409 status code with detail "El program_code ya está registrado".
4. WHEN a PATCH request contains a `snies_code` that belongs to a different program, THE API SHALL return a 409 status code with detail "El snies_code ya está registrado".
5. WHEN a PATCH request contains a `program_code` or `snies_code` identical to the current values of the program being updated, THE API SHALL process the update without conflict.
