# Documento de Requisitos — Vista "Mi Progreso" del Estudiante (Backend)

## Introducción

Este documento define los requisitos backend necesarios para soportar la vista "Mi Progreso" en el frontend del estudiante. Actualmente, el endpoint `GET /api/v1/students/{student_id}/enrollments` solo permite acceso a roles ADMIN y PROFESSOR, el enum `EnrollmentStatusEnum` no incluye los estados COMPLETED ni PENDING para distinguir cursos aprobados y materias pendientes por cursar, y no existe un endpoint GET para obtener un programa individual por ID. Estos cambios son necesarios para que el frontend pueda mostrar al estudiante sus inscripciones activas, cursos completados, materias pendientes, progreso académico y el nombre de su programa.

## Glosario

- **Sistema_Inscripciones**: Módulo del backend MPRA responsable de gestionar las inscripciones de estudiantes en cursos (tabla `enrollments`).
- **Sistema_Programas**: Módulo del backend MPRA responsable de gestionar los programas académicos (tabla `programs`).
- **Dependencia_Auth**: Módulo de dependencias de autenticación y autorización de FastAPI (`app/api/v1/dependencies/auth.py`) que provee `require_roles`, `require_self_or_roles` y `get_current_user`.
- **Enrollment**: Registro que vincula un estudiante (`student_id`) con un curso (`course_id`), con campo `status` que indica PENDING, ACTIVE, COMPLETED o CANCELLED.
- **EnrollmentStatusEnum**: Enumeración de dominio que define los estados válidos de una inscripción.
- **ProgramRead**: Schema Pydantic de respuesta que contiene los datos de un programa académico.
- **JWT**: Token de autenticación que contiene `sub` (ID del usuario) y `role` (rol del usuario).
- **Auto-acceso**: Patrón de autorización donde un usuario con rol STUDENT puede acceder a sus propios datos cuando el `student_id` del path coincide con el `sub` del JWT.
- **RB-04**: Regla de negocio que restringe a los profesores a ver únicamente datos de estudiantes inscritos en sus cursos asignados.

## Requisitos

### Requisito 1: Permitir al estudiante consultar sus propias inscripciones (auto-acceso)

**User Story:** Como estudiante, quiero consultar mis propias inscripciones en cursos, para poder ver mi progreso académico en la vista "Mi Progreso".

#### Criterios de Aceptación

1. WHEN una solicitud GET a `/students/{student_id}/enrollments` es recibida con un JWT de rol STUDENT cuyo `sub` coincide con el `student_id` del path, THE Sistema_Inscripciones SHALL retornar la lista de inscripciones del estudiante con código HTTP 200.
2. IF una solicitud GET a `/students/{student_id}/enrollments` es recibida con un JWT de rol STUDENT cuyo `sub` no coincide con el `student_id` del path, THEN THE Sistema_Inscripciones SHALL retornar código HTTP 403 con el mensaje "No tiene permisos para esta acción".
3. WHILE el usuario autenticado tiene rol ADMIN, THE Sistema_Inscripciones SHALL permitir acceso a las inscripciones de cualquier `student_id`.
4. WHILE el usuario autenticado tiene rol PROFESSOR, THE Sistema_Inscripciones SHALL retornar únicamente las inscripciones en cursos asignados al profesor solicitante (RB-04).
5. WHEN un estudiante consulta sus propias inscripciones, THE Sistema_Inscripciones SHALL retornar inscripciones en todos los estados (PENDING, ACTIVE, COMPLETED, CANCELLED) a menos que se aplique un filtro de estado.
6. THE Dependencia_Auth SHALL proveer una dependencia reutilizable que valide auto-acceso por `student_id` del path, aceptando también roles ADMIN y PROFESSOR con sus reglas existentes.

### Requisito 2: Agregar estados COMPLETED y PENDING al enum de estado de inscripción

**User Story:** Como administrador, quiero gestionar los estados de inscripción incluyendo PENDING para materias que faltan por cursar y COMPLETED para materias aprobadas, para reflejar el progreso académico real del estudiante.

#### Criterios de Aceptación

1. THE EnrollmentStatusEnum SHALL incluir los valores PENDING, ACTIVE, COMPLETED y CANCELLED.
2. WHEN una solicitud PATCH a `/enrollments/{enrollment_id}/status` es recibida con estado COMPLETED, THE Sistema_Inscripciones SHALL actualizar el campo `status` del registro Enrollment a COMPLETED y retornar los datos actualizados con código HTTP 200.
3. WHEN una solicitud PATCH a `/enrollments/{enrollment_id}/status` es recibida con estado PENDING, THE Sistema_Inscripciones SHALL actualizar el campo `status` del registro Enrollment a PENDING y retornar los datos actualizados con código HTTP 200.
4. WHEN una inscripción cambia de estado, THE Sistema_Inscripciones SHALL registrar un Log_Auditoría con operación UPDATE, tabla "enrollments", el estado anterior y el nuevo estado.
5. THE Sistema_Inscripciones SHALL generar una migración Alembic que agregue los valores COMPLETED y PENDING al tipo enum `enrollmentstatusenum` en PostgreSQL.
6. WHEN los valores COMPLETED y PENDING son agregados al enum de base de datos, THE migración SHALL preservar los registros existentes con estados ACTIVE y CANCELLED sin modificarlos.

### Requisito 3: Filtrar inscripciones por estado

**User Story:** Como consumidor de la API (frontend o administrador), quiero filtrar las inscripciones de un estudiante por estado, para poder obtener solo las inscripciones pendientes, activas, completadas o canceladas según necesite.

#### Criterios de Aceptación

1. WHEN una solicitud GET a `/students/{student_id}/enrollments` incluye el query param `status` con un valor válido del EnrollmentStatusEnum, THE Sistema_Inscripciones SHALL retornar únicamente las inscripciones que coincidan con el estado indicado.
2. WHEN una solicitud GET a `/students/{student_id}/enrollments` no incluye el query param `status`, THE Sistema_Inscripciones SHALL retornar las inscripciones según la lógica de rol existente (ADMIN: todas las ACTIVE; PROFESSOR: filtradas por cursos del profesor; STUDENT: todas sin filtro de estado).
3. IF el query param `status` contiene un valor que no pertenece al EnrollmentStatusEnum, THEN THE Sistema_Inscripciones SHALL retornar código HTTP 422 con los detalles de validación.
4. WHEN el query param `status` es proporcionado junto con el rol PROFESSOR, THE Sistema_Inscripciones SHALL aplicar tanto el filtro de estado como el filtro de cursos del profesor (RB-04).

### Requisito 4: Obtener un programa académico por ID

**User Story:** Como estudiante, quiero obtener los datos de mi programa académico por su ID, para que la vista "Mi Progreso" muestre el nombre del programa.

#### Criterios de Aceptación

1. WHEN una solicitud GET a `/programs/{program_id}` es recibida con un `program_id` válido, THE Sistema_Programas SHALL retornar los datos del programa con el schema ProgramRead y código HTTP 200.
2. IF el `program_id` no corresponde a un programa existente, THEN THE Sistema_Programas SHALL retornar código HTTP 404 con el mensaje "Programa no encontrado".
3. THE Sistema_Programas SHALL permitir acceso al endpoint GET `/programs/{program_id}` a cualquier usuario autenticado (roles STUDENT, PROFESSOR y ADMIN).

### Requisito 5: Validación de datos de entrada para los nuevos comportamientos

**User Story:** Como sistema, quiero validar los datos de entrada en las operaciones nuevas y modificadas, para garantizar la integridad de los datos.

#### Criterios de Aceptación

1. THE Sistema_Inscripciones SHALL validar que el query param `status` es un valor válido del EnrollmentStatusEnum cuando es proporcionado en la solicitud GET de inscripciones.
2. THE Sistema_Inscripciones SHALL aceptar COMPLETED y PENDING como valores válidos en el schema EnrollmentStatusUpdate para solicitudes PATCH de cambio de estado.
3. THE Sistema_Programas SHALL validar que `program_id` es un UUID válido en la solicitud GET de programa por ID.
4. IF algún parámetro tiene formato inválido, THEN THE Sistema_Inscripciones SHALL retornar código HTTP 422 con los detalles de validación de Pydantic.
