# Documento de Requisitos — CRUD de Inscripciones de Estudiantes

## Introducción

Este documento define los requisitos para completar las operaciones CRUD de inscripciones (enrollments) de estudiantes en cursos. Actualmente el sistema cuenta con el modelo `Enrollment` y un endpoint GET para listar estudiantes inscritos en un curso. Faltan los endpoints para **crear** (inscribir un estudiante en un curso), **actualizar** (cambiar de curso) y **cancelar** (borrado lógico de inscripción). Todas las operaciones de escritura deben registrar logs de auditoría y respetar el control de acceso basado en roles (ADMIN). El sistema utiliza **borrado lógico** para todas las eliminaciones en base de datos, preservando los registros con un campo de estado.

## Glosario

- **Sistema_Inscripciones**: Módulo del backend MPRA responsable de gestionar las inscripciones de estudiantes en cursos (tabla `enrollments`).
- **Enrollment**: Registro que vincula un estudiante (`student_id`) con un curso (`course_id`), con restricción de unicidad sobre la combinación `(student_id, course_id)`. Incluye un campo `status` (ACTIVE o CANCELLED) para soportar borrado lógico.
- **Estudiante**: Usuario con rol `STUDENT` en el sistema.
- **Curso**: Asignatura registrada en la tabla `courses` con estado `ACTIVE` o `INACTIVE`.
- **ADMIN**: Rol de usuario con permisos completos de gestión sobre el sistema.
- **Log_Auditoría**: Registro inmutable en la tabla `audit_logs` que documenta cada operación de escritura (INSERT, UPDATE, DELETE).

## Requisitos

### Requisito 1: Inscribir un estudiante en un curso

**User Story:** Como administrador, quiero inscribir un estudiante en un curso, para que el estudiante quede registrado oficialmente en la asignatura.

#### Criterios de Aceptación

1. WHEN una solicitud POST es recibida con `student_id` y `course_id` válidos, THE Sistema_Inscripciones SHALL crear un registro Enrollment y retornar los datos de la inscripción con código HTTP 201.
2. WHEN una solicitud POST es recibida, THE Sistema_Inscripciones SHALL validar que el `student_id` corresponde a un usuario existente con rol STUDENT.
3. WHEN una solicitud POST es recibida, THE Sistema_Inscripciones SHALL validar que el `course_id` corresponde a un curso existente con estado ACTIVE.
4. IF el `student_id` no corresponde a un usuario existente con rol STUDENT, THEN THE Sistema_Inscripciones SHALL retornar código HTTP 422 con el mensaje "El usuario indicado no existe o no tiene rol de estudiante".
5. IF el `course_id` no corresponde a un curso existente, THEN THE Sistema_Inscripciones SHALL retornar código HTTP 404 con el mensaje "Curso no encontrado".
6. IF ya existe una inscripción ACTIVE con la misma combinación `(student_id, course_id)`, THEN THE Sistema_Inscripciones SHALL retornar código HTTP 409 con el mensaje "El estudiante ya está inscrito en este curso".
7. WHEN ya existe una inscripción CANCELLED con la misma combinación `(student_id, course_id)`, THE Sistema_Inscripciones SHALL reactivar el registro existente cambiando su estado a ACTIVE en lugar de crear uno nuevo.
8. WHEN una inscripción es creada exitosamente, THE Sistema_Inscripciones SHALL registrar un Log_Auditoría con operación INSERT, tabla "enrollments" y los datos de la nueva inscripción.
9. THE Sistema_Inscripciones SHALL requerir que el usuario autenticado tenga rol ADMIN para crear inscripciones.

### Requisito 2: Actualizar una inscripción (cambio de curso)

**User Story:** Como administrador, quiero actualizar la inscripción de un estudiante para cambiar el curso asignado, de modo que se refleje correctamente un cambio de asignatura.

#### Criterios de Aceptación

1. WHEN una solicitud PATCH es recibida con un `enrollment_id` válido y un nuevo `course_id`, THE Sistema_Inscripciones SHALL actualizar el curso de la inscripción y retornar los datos actualizados con código HTTP 200.
2. IF el `enrollment_id` no corresponde a una inscripción existente, THEN THE Sistema_Inscripciones SHALL retornar código HTTP 404 con el mensaje "Inscripción no encontrada".
3. WHEN una solicitud PATCH es recibida con un nuevo `course_id`, THE Sistema_Inscripciones SHALL validar que el curso destino existe y tiene estado ACTIVE.
4. IF el nuevo `course_id` no corresponde a un curso existente con estado ACTIVE, THEN THE Sistema_Inscripciones SHALL retornar código HTTP 404 con el mensaje "Curso no encontrado".
5. IF ya existe una inscripción ACTIVE con la combinación `(student_id, nuevo course_id)`, THEN THE Sistema_Inscripciones SHALL retornar código HTTP 409 con el mensaje "El estudiante ya está inscrito en el curso destino".
6. WHEN una inscripción es actualizada exitosamente, THE Sistema_Inscripciones SHALL registrar un Log_Auditoría con operación UPDATE, tabla "enrollments", los datos anteriores y los datos nuevos.
7. THE Sistema_Inscripciones SHALL requerir que el usuario autenticado tenga rol ADMIN para actualizar inscripciones.

### Requisito 3: Cancelar una inscripción (borrado lógico)

**User Story:** Como administrador, quiero cancelar la inscripción de un estudiante en un curso, para que el registro quede marcado como inactivo cuando el estudiante se retira de la asignatura.

#### Criterios de Aceptación

1. WHEN una solicitud PATCH es recibida para cambiar el estado de una inscripción a CANCELLED, THE Sistema_Inscripciones SHALL actualizar el campo `status` del registro Enrollment a CANCELLED y retornar los datos actualizados con código HTTP 200.
2. IF el `enrollment_id` no corresponde a una inscripción existente, THEN THE Sistema_Inscripciones SHALL retornar código HTTP 404 con el mensaje "Inscripción no encontrada".
3. WHEN una inscripción es cancelada exitosamente, THE Sistema_Inscripciones SHALL registrar un Log_Auditoría con operación UPDATE, tabla "enrollments", el estado anterior y el nuevo estado CANCELLED.
4. THE Sistema_Inscripciones SHALL requerir que el usuario autenticado tenga rol ADMIN para cancelar inscripciones.
5. THE Sistema_Inscripciones SHALL utilizar borrado lógico para todas las operaciones de cancelación, preservando el registro en la base de datos con un campo `status` que indique su estado (ACTIVE o CANCELLED).

### Requisito 4: Listar inscripciones de un estudiante

**User Story:** Como administrador o profesor, quiero consultar todas las inscripciones de un estudiante específico, para conocer en qué cursos está registrado.

#### Criterios de Aceptación

1. WHEN una solicitud GET es recibida con un `student_id` válido, THE Sistema_Inscripciones SHALL retornar la lista de inscripciones ACTIVE del estudiante con código HTTP 200.
2. WHEN no existen inscripciones para el `student_id` proporcionado, THE Sistema_Inscripciones SHALL retornar una lista vacía con código HTTP 200.
3. THE Sistema_Inscripciones SHALL requerir que el usuario autenticado tenga rol ADMIN o PROFESSOR para consultar inscripciones de un estudiante.
4. WHILE el usuario autenticado tiene rol PROFESSOR, THE Sistema_Inscripciones SHALL retornar únicamente las inscripciones en cursos asignados al profesor solicitante (RB-04).

### Requisito 5: Obtener detalle de una inscripción

**User Story:** Como administrador, quiero consultar el detalle de una inscripción específica, para verificar los datos de la relación estudiante-curso.

#### Criterios de Aceptación

1. WHEN una solicitud GET es recibida con un `enrollment_id` válido, THE Sistema_Inscripciones SHALL retornar los datos completos de la inscripción con código HTTP 200.
2. IF el `enrollment_id` no corresponde a una inscripción existente, THEN THE Sistema_Inscripciones SHALL retornar código HTTP 404 con el mensaje "Inscripción no encontrada".
3. THE Sistema_Inscripciones SHALL requerir que el usuario autenticado tenga rol ADMIN para consultar el detalle de una inscripción.

### Requisito 6: Validación de datos de entrada para inscripciones

**User Story:** Como sistema, quiero validar los datos de entrada en todas las operaciones de inscripción, para garantizar la integridad de los datos.

#### Criterios de Aceptación

1. THE Sistema_Inscripciones SHALL validar que `student_id` y `course_id` son UUIDs válidos en las solicitudes de creación.
2. THE Sistema_Inscripciones SHALL validar que `course_id` es un UUID válido en las solicitudes de actualización.
3. IF algún campo obligatorio no es proporcionado o tiene formato inválido, THEN THE Sistema_Inscripciones SHALL retornar código HTTP 422 con los detalles de validación de Pydantic.
4. THE Sistema_Inscripciones SHALL incluir la fecha de inscripción (`enrollment_date`) automáticamente al crear un registro, sin requerir que el cliente la proporcione.
