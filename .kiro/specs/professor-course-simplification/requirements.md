# Documento de Requerimientos — Simplificación Profesor-Curso: Eliminar tabla intermedia

## Introducción

El sistema MPRA actualmente gestiona la relación profesor-curso mediante una tabla intermedia `professor_courses` con columnas `(id, professor_id, course_id)` y una restricción `UNIQUE(course_id)`. Dado que la relación es estrictamente 1:1 (un profesor por curso), esta tabla intermedia agrega complejidad innecesaria: JOINs adicionales en consultas, un modelo ORM dedicado, y lógica de upsert que podría ser una simple actualización de columna.

Este feature simplifica el modelo de datos agregando una columna `professor_id` (FK nullable → `users.id`) directamente en la tabla `courses`, migrando los datos existentes desde `professor_courses`, y eliminando la tabla intermedia junto con toda su infraestructura asociada (modelo ORM `ProfessorCourse`, schema Pydantic `ProfessorCourseRead`, y queries con JOINs a `professor_courses`). La regla de negocio RB-04 (profesores solo operan sobre estudiantes de sus cursos asignados) y la trazabilidad de auditoría se mantienen intactas.

## Glosario

- **Sistema**: El backend MPRA (FastAPI + PostgreSQL).
- **Curso**: Entidad que representa una asignatura (tabla `courses`). Pertenece a un Programa mediante `program_id` (FK).
- **Profesor**: Usuario con rol `PROFESSOR` en la tabla `users`.
- **Tabla_Intermedia**: La tabla `professor_courses` que actualmente vincula profesores con cursos mediante `(id, professor_id, course_id)`.
- **Migración_Alembic**: Script de migración de base de datos gestionado por Alembic que modifica el esquema de PostgreSQL.
- **Modelo_ORM**: Clase SQLModel que mapea una tabla de la base de datos a un objeto Python.
- **Schema_Pydantic**: Clase Pydantic que define la estructura de datos para validación de entrada/salida en la API.
- **Repositorio**: Clase de la capa de infraestructura que encapsula las operaciones de persistencia (CRUD) contra la base de datos.
- **Servicio**: Clase de la capa de aplicación que implementa la lógica de negocio.
- **Endpoint**: Ruta HTTP expuesta por la API REST de FastAPI.
- **RB-04**: Regla de negocio que establece que los profesores solo pueden visualizar y operar sobre los datos de estudiantes inscritos en sus cursos asignados.
- **Audit_Log**: Registro de auditoría que almacena cada operación de escritura en la base de datos para trazabilidad.

## Requerimientos

### Requerimiento 1: Agregar columna professor_id a la tabla courses

**User Story:** Como desarrollador del MVP, quiero que la tabla `courses` contenga directamente la referencia al profesor asignado, para que la relación profesor-curso no requiera una tabla intermedia.

#### Criterios de Aceptación

1. WHEN el Sistema ejecute la Migración_Alembic 0007, THE Sistema SHALL agregar una columna `professor_id` de tipo UUID nullable a la tabla `courses`.
2. WHEN el Sistema ejecute la Migración_Alembic 0007, THE Sistema SHALL crear una restricción de clave foránea desde `courses.professor_id` hacia `users.id`.
3. WHEN el Sistema ejecute la Migración_Alembic 0007, THE Sistema SHALL crear un índice sobre `courses.professor_id` para optimizar consultas por profesor.
4. THE Modelo_ORM `Course` SHALL contener el campo `professor_id` como clave foránea opcional (nullable) apuntando a `users.id`.

### Requerimiento 2: Migrar datos existentes de professor_courses a courses

**User Story:** Como desarrollador del MVP, quiero que los datos de asignación profesor-curso existentes se transfieran a la nueva columna, para que no se pierda información durante la simplificación.

#### Criterios de Aceptación

1. WHEN el Sistema ejecute la Migración_Alembic 0007, THE Sistema SHALL copiar el valor de `professor_courses.professor_id` a `courses.professor_id` para cada registro en la Tabla_Intermedia.
2. WHEN el Sistema ejecute la Migración_Alembic 0007, THE Sistema SHALL preservar todas las asignaciones profesor-curso existentes sin pérdida de datos.
3. WHEN el Sistema ejecute la Migración_Alembic 0007 y la migración de datos se complete, THE Sistema SHALL eliminar la Tabla_Intermedia `professor_courses`.

### Requerimiento 3: Eliminar la infraestructura de la tabla intermedia

**User Story:** Como desarrollador del MVP, quiero eliminar todo el código asociado a la tabla `professor_courses`, para que el sistema no contenga artefactos de un modelo de datos obsoleto.

#### Criterios de Aceptación

1. THE Sistema SHALL eliminar el Modelo_ORM `ProfessorCourse` del módulo `app/infrastructure/models/professor_course.py`.
2. THE Sistema SHALL eliminar el archivo `app/infrastructure/models/professor_course.py`.
3. THE Sistema SHALL eliminar el Schema_Pydantic `ProfessorCourseRead` del módulo `app/application/schemas/professor_course.py`.
4. THE Sistema SHALL eliminar todas las importaciones y referencias al Modelo_ORM `ProfessorCourse` en el Repositorio `CourseRepository`.
5. THE Sistema SHALL eliminar todas las importaciones y referencias al Modelo_ORM `ProfessorCourse` en el Servicio `ProfessorCourseService`.

### Requerimiento 4: Refactorizar la asignación profesor-curso para usar Course.professor_id

**User Story:** Como desarrollador del MVP, quiero que la asignación de un profesor a un curso se realice actualizando directamente `courses.professor_id`, para que la operación sea más simple y no requiera una tabla intermedia.

#### Criterios de Aceptación

1. WHEN se asigne un Profesor a un Curso, THE Servicio SHALL actualizar el campo `professor_id` del Curso directamente en la tabla `courses`.
2. WHEN se asigne un Profesor a un Curso y el Curso ya tenga un Profesor asignado, THE Servicio SHALL reemplazar el `professor_id` existente con el nuevo valor.
3. WHEN se asigne un Profesor a un Curso, THE Servicio SHALL verificar que el usuario indicado existe y tiene rol `PROFESSOR`, retornando código de estado 422 si no cumple la condición.
4. WHEN se asigne un Profesor a un Curso y el Curso no exista, THE Servicio SHALL retornar un error con código de estado 404 y el mensaje "Curso no encontrado".
5. WHEN se asigne un Profesor a un Curso, THE Servicio SHALL registrar la operación en el Audit_Log con la tabla de referencia `courses`, incluyendo el valor anterior y el nuevo valor de `professor_id`.

### Requerimiento 5: Refactorizar las consultas de profesor-curso para usar Course.professor_id

**User Story:** Como desarrollador del MVP, quiero que las consultas de profesor asignado y cursos por profesor se realicen directamente sobre la tabla `courses`, para que no se requieran JOINs con la tabla intermedia.

#### Criterios de Aceptación

1. WHEN se consulte el Profesor asignado a un Curso, THE Repositorio SHALL obtener el `professor_id` directamente desde la tabla `courses` y realizar un JOIN con `users` para retornar los datos del Profesor.
2. WHEN se consulte el Profesor asignado a un Curso y el Curso no tenga Profesor asignado (`professor_id` es NULL), THE Servicio SHALL retornar un error con código de estado 404 y el mensaje "El curso no tiene profesor asignado".
3. WHEN se listen los Cursos asignados a un Profesor, THE Repositorio SHALL filtrar la tabla `courses` por `professor_id` igual al ID del Profesor, sin realizar JOINs con la Tabla_Intermedia.
4. THE Repositorio `CourseRepository` SHALL implementar el método `listar_por_docente` filtrando directamente por `Course.professor_id`.

### Requerimiento 6: Mantener el control de acceso RB-04 funcional

**User Story:** Como desarrollador del MVP, quiero que la regla de negocio RB-04 siga funcionando correctamente después de la simplificación, para que los profesores solo puedan operar sobre estudiantes de sus cursos asignados.

#### Criterios de Aceptación

1. WHEN un Profesor solicite la lista de estudiantes de un Curso, THE Servicio SHALL verificar que `Course.professor_id` coincida con el ID del Profesor solicitante.
2. IF el Profesor no está asignado al Curso (el `professor_id` del Curso no coincide con el ID del Profesor), THEN THE Servicio SHALL retornar un error con código de estado 403 y el mensaje "No tiene permiso para operar en este curso".
3. WHEN un Profesor solicite registrar una nota para un estudiante, THE Servicio SHALL verificar que `Course.professor_id` coincida con el ID del Profesor antes de permitir la operación.
4. WHEN un Profesor solicite registrar una nota y el estudiante no esté inscrito en el Curso, THE Servicio SHALL retornar un error con código de estado 403 y el mensaje "Acceso denegado: el estudiante no está inscrito en sus cursos".

### Requerimiento 7: Mantener el contrato de la API sin cambios externos

**User Story:** Como desarrollador del MVP, quiero que los endpoints de la API mantengan las mismas rutas y comportamiento externo, para que los clientes del API no se vean afectados por la refactorización interna.

#### Criterios de Aceptación

1. THE Endpoint `POST /courses/{course_id}/professor` SHALL mantener la misma ruta, método HTTP y código de estado 200 de respuesta exitosa.
2. THE Endpoint `GET /courses/{course_id}/professor` SHALL mantener la misma ruta, método HTTP y modelo de respuesta `UserRead`.
3. THE Endpoint `GET /professors/{professor_id}/courses` SHALL mantener la misma ruta, método HTTP y modelo de respuesta `list[CourseRead]`.
4. THE Endpoint `GET /courses/{course_id}/students` SHALL mantener la misma ruta, método HTTP y modelo de respuesta `list[UserRead]`.
5. WHEN se asigne un Profesor a un Curso mediante `POST /courses/{course_id}/professor`, THE Endpoint SHALL aceptar el mismo body `ProfessorAssign` con el campo `professor_id`.
6. WHEN se asigne un Profesor a un Curso mediante `POST /courses/{course_id}/professor`, THE Endpoint SHALL retornar un objeto con los campos `id`, `professor_id` y `course_id` para mantener compatibilidad con el contrato actual.

### Requerimiento 8: Mantener la trazabilidad de auditoría

**User Story:** Como desarrollador del MVP, quiero que todas las operaciones de asignación y cambio de profesor queden registradas en el log de auditoría, para que se mantenga la trazabilidad completa de cambios.

#### Criterios de Aceptación

1. WHEN se asigne un Profesor a un Curso que no tenía Profesor asignado, THE Servicio SHALL registrar una operación `INSERT` en el Audit_Log con `table_name` igual a `courses` y `new_data` conteniendo el `professor_id` asignado.
2. WHEN se reemplace el Profesor de un Curso, THE Servicio SHALL registrar una operación `UPDATE` en el Audit_Log con `table_name` igual a `courses`, `previous_data` conteniendo el `professor_id` anterior, y `new_data` conteniendo el nuevo `professor_id`.
3. THE Servicio SHALL incluir el `course_id` en los datos registrados en el Audit_Log para cada operación de asignación de profesor.

### Requerimiento 9: Crear migración Alembic 0007

**User Story:** Como desarrollador del MVP, quiero una migración Alembic que transforme el esquema de base de datos para eliminar la tabla intermedia, para que la base de datos refleje la relación directa curso-profesor.

#### Criterios de Aceptación

1. THE Migración_Alembic SHALL tener como revisión padre la migración `0006` (simplify program course model).
2. WHEN se ejecute la función `upgrade()`, THE Migración_Alembic SHALL agregar la columna `professor_id` (UUID, nullable) a la tabla `courses`.
3. WHEN se ejecute la función `upgrade()`, THE Migración_Alembic SHALL crear la restricción de clave foránea `fk_courses_professor_id` desde `courses.professor_id` hacia `users.id`.
4. WHEN se ejecute la función `upgrade()`, THE Migración_Alembic SHALL crear el índice `ix_courses_professor_id` sobre la columna `courses.professor_id`.
5. WHEN se ejecute la función `upgrade()`, THE Migración_Alembic SHALL ejecutar una sentencia SQL que copie `professor_courses.professor_id` a `courses.professor_id` para cada par `(course_id, professor_id)` existente en la Tabla_Intermedia.
6. WHEN se ejecute la función `upgrade()`, THE Migración_Alembic SHALL eliminar la tabla `professor_courses` después de completar la migración de datos.
7. THE Migración_Alembic SHALL incluir una función `downgrade()` que revierta todos los cambios: recrear la tabla `professor_courses`, migrar los datos de vuelta desde `courses.professor_id`, y eliminar la columna `professor_id` de `courses`.

### Requerimiento 10: Actualizar los schemas Pydantic del curso

**User Story:** Como desarrollador del MVP, quiero que los schemas Pydantic del curso reflejen la nueva columna `professor_id`, para que la API pueda exponer la información del profesor asignado cuando sea necesario.

#### Criterios de Aceptación

1. THE Schema_Pydantic `CourseRead` SHALL incluir el campo `professor_id` como `UUID | None` para reflejar la columna nullable en la tabla `courses`.
2. THE Schema_Pydantic `CourseCreate` SHALL mantener su estructura actual sin incluir `professor_id`, ya que la asignación de profesor se realiza mediante un endpoint dedicado.
3. THE Schema_Pydantic `ProfessorAssign` SHALL mantenerse sin cambios en el módulo `app/application/schemas/professor_course.py` para preservar el contrato del endpoint de asignación.

### Requerimiento 11: Actualizar tests existentes

**User Story:** Como desarrollador del MVP, quiero que todos los tests que referencian `ProfessorCourse` se actualicen para usar `Course.professor_id`, para que la suite de tests refleje el modelo de datos simplificado.

#### Criterios de Aceptación

1. THE Sistema SHALL actualizar todos los tests que importen o referencien el Modelo_ORM `ProfessorCourse` para usar `Course.professor_id` directamente.
2. THE Sistema SHALL actualizar todos los tests que verifiquen la asignación profesor-curso para validar que `Course.professor_id` contiene el valor correcto.
3. THE Sistema SHALL actualizar todos los tests que verifiquen el control de acceso RB-04 para usar la verificación directa sobre `Course.professor_id`.
4. WHEN se ejecute la suite completa de tests, THE Sistema SHALL pasar todos los tests sin errores.
