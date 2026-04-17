# Requirements Document

## Introducción

El MPRA actualmente opera con programas y cursos sin una entidad universitaria explícita. Esta funcionalidad introduce la entidad `University` como raíz de la jerarquía académica (`University → Programs → Courses`), permitiendo que el sistema soporte múltiples universidades de forma aislada. Adicionalmente, se formaliza el rol de `Professor` como actor responsable de la carga de notas en los cursos que tiene asignados, reforzando la regla de negocio RB-04.

---

## Glosario

- **University**: Institución de educación superior registrada en el sistema. Raíz de la jerarquía académica.
- **Program**: Programa académico (carrera) que pertenece a exactamente una `University`.
- **Course**: Asignatura o materia que pertenece a exactamente un `Program`.
- **Professor**: Usuario con rol `PROFESSOR` que tiene uno o más cursos asignados y es el único autorizado a cargar notas en dichos cursos.
- **Student**: Usuario con rol `STUDENT` inscrito en uno o más cursos.
- **Enrollment**: Relación entre un `Student` y un `Course` para un período académico.
- **ProfessorCourse**: Relación de asignación entre un `Professor` y un `Course`. Un curso tiene exactamente un profesor asignado.
- **Grade**: Registro de nota académica (asistencia, seguimiento, parcial) cargado por el `Professor` asignado al curso.
- **Admin**: Usuario con rol `ADMIN` con acceso completo de gestión sobre todas las entidades.
- **MPRA**: Modelo Predictivo de Riesgo Académico — sistema backend en FastAPI + PostgreSQL.
- **SNIES**: Sistema Nacional de Información de la Educación Superior (Colombia). Código único por programa.

---

## Requisitos

### Requisito 1: Gestión de Universidades

**User Story:** Como administrador, quiero registrar y gestionar universidades en el sistema, para que los programas y cursos queden organizados bajo su institución correspondiente.

#### Criterios de Aceptación

1. THE MPRA SHALL almacenar cada universidad con los campos: `id` (UUID), `name` (nombre oficial), `code` (código único alfanumérico), `country`, `city`, `active` (booleano), `created_at`.
2. WHEN un administrador envía una solicitud `POST /api/v1/universities` con datos válidos, THE MPRA SHALL crear la universidad y retornar `201 Created` con la representación del recurso creado.
3. IF el campo `code` de una universidad ya existe en la base de datos, THEN THE MPRA SHALL retornar `409 Conflict` con un mensaje descriptivo.
4. WHEN un administrador envía una solicitud `GET /api/v1/universities`, THE MPRA SHALL retornar la lista paginada de universidades con parámetros `skip` y `limit`.
5. WHEN un administrador envía una solicitud `GET /api/v1/universities/{university_id}`, THE MPRA SHALL retornar los datos de la universidad correspondiente o `404 Not Found` si no existe.
6. WHEN un administrador envía una solicitud `PATCH /api/v1/universities/{university_id}` con campos válidos, THE MPRA SHALL actualizar únicamente los campos provistos y retornar `200 OK`.
7. IF un usuario con rol distinto a `ADMIN` intenta crear, actualizar o eliminar una universidad, THEN THE MPRA SHALL retornar `403 Forbidden`.

---

### Requisito 2: Asociación de Programas a Universidades

**User Story:** Como administrador, quiero que cada programa académico esté vinculado a una universidad, para que la jerarquía `University → Programs` sea explícita y consultable.

#### Criterios de Aceptación

1. THE MPRA SHALL agregar el campo `university_id` (FK → `universities.id`, `NOT NULL`) al modelo `Program`.
2. WHEN un administrador crea un programa mediante `POST /api/v1/programs`, THE MPRA SHALL requerir el campo `university_id` y validar que la universidad referenciada exista.
3. IF el `university_id` proporcionado no corresponde a una universidad existente, THEN THE MPRA SHALL retornar `422 Unprocessable Entity` con un mensaje descriptivo.
4. WHEN un cliente envía `GET /api/v1/universities/{university_id}/programs`, THE MPRA SHALL retornar únicamente los programas pertenecientes a esa universidad.
5. THE MPRA SHALL mantener la unicidad del campo `program_code` dentro del alcance de una misma universidad (dos universidades distintas pueden tener el mismo `program_code`).
6. WHILE la migración de datos existentes esté en curso, THE MPRA SHALL asignar los programas sin `university_id` a una universidad por defecto configurable mediante variable de entorno `DEFAULT_UNIVERSITY_ID`.

---

### Requisito 3: Asociación de Cursos a Programas

**User Story:** Como administrador, quiero que cada curso esté vinculado a un programa, para que la jerarquía `Program → Courses` sea explícita y la trazabilidad académica sea completa.

#### Criterios de Aceptación

1. THE MPRA SHALL garantizar que el campo `program_id` (FK → `programs.id`) en el modelo `Course` sea `NOT NULL` para todos los cursos nuevos.
2. WHEN un administrador crea un curso mediante `POST /api/v1/courses`, THE MPRA SHALL requerir el campo `program_id` y validar que el programa referenciado exista.
3. IF el `program_id` proporcionado no corresponde a un programa existente, THEN THE MPRA SHALL retornar `422 Unprocessable Entity` con un mensaje descriptivo.
4. WHEN un cliente envía `GET /api/v1/programs/{program_id}/courses`, THE MPRA SHALL retornar únicamente los cursos pertenecientes a ese programa.
5. WHEN un cliente envía `GET /api/v1/universities/{university_id}/programs/{program_id}/courses`, THE MPRA SHALL retornar los cursos del programa validando que el programa pertenezca a la universidad indicada.

---

### Requisito 4: Asignación de Profesor a Curso

**User Story:** Como administrador, quiero asignar exactamente un profesor a cada curso, para que quede claro quién es el responsable de cargar las notas de esa asignatura.

#### Criterios de Aceptación

1. THE MPRA SHALL garantizar que la tabla `professor_courses` soporte la restricción de que un curso tenga como máximo un profesor asignado activo a la vez (unicidad sobre `course_id`).
2. WHEN un administrador envía `POST /api/v1/courses/{course_id}/professor` con un `professor_id` válido, THE MPRA SHALL crear o reemplazar la asignación del profesor al curso y retornar `200 OK`.
3. IF el `professor_id` proporcionado no corresponde a un usuario con rol `PROFESSOR`, THEN THE MPRA SHALL retornar `422 Unprocessable Entity` con el mensaje "El usuario indicado no tiene rol de profesor".
4. IF el `course_id` no existe, THEN THE MPRA SHALL retornar `404 Not Found`.
5. WHEN un cliente envía `GET /api/v1/courses/{course_id}/professor`, THE MPRA SHALL retornar los datos del profesor asignado al curso o `404 Not Found` si el curso no tiene profesor asignado.
6. WHEN un administrador envía `GET /api/v1/professors/{professor_id}/courses`, THE MPRA SHALL retornar la lista de cursos asignados al profesor indicado.

---

### Requisito 5: Control de Acceso del Profesor para Carga de Notas

**User Story:** Como profesor, quiero poder cargar y actualizar las notas únicamente de los estudiantes inscritos en mis cursos asignados, para cumplir con la regla de privacidad RB-04.

#### Criterios de Aceptación

1. WHILE un usuario autenticado tiene rol `PROFESSOR`, THE MPRA SHALL restringir el acceso a los datos de estudiantes únicamente a aquellos inscritos en los cursos donde ese profesor está asignado.
2. WHEN un profesor envía una solicitud de escritura de notas sobre un curso que no le está asignado, THE MPRA SHALL retornar `403 Forbidden`.
3. WHEN un profesor envía `GET /api/v1/courses/{course_id}/students`, THE MPRA SHALL retornar únicamente los estudiantes inscritos en ese curso, siempre que el profesor esté asignado a él.
4. IF un profesor intenta acceder a datos de un estudiante no inscrito en ninguno de sus cursos asignados, THEN THE MPRA SHALL retornar `403 Forbidden`.
5. THE MPRA SHALL registrar en el log de auditoría cada operación de escritura de notas realizada por un profesor, incluyendo `professor_id`, `course_id`, `student_id`, `timestamp` y tipo de operación.

---

### Requisito 6: Aislamiento de Datos por Universidad

**User Story:** Como administrador de una universidad, quiero que los datos de mi institución estén aislados de los de otras universidades, para garantizar la privacidad y la integridad de la información.

#### Criterios de Aceptación

1. WHEN un usuario autenticado realiza una consulta de programas o cursos, THE MPRA SHALL retornar únicamente los recursos pertenecientes a la universidad asociada al contexto de la solicitud.
2. IF un administrador intenta modificar un programa o curso que pertenece a una universidad distinta a la suya, THEN THE MPRA SHALL retornar `403 Forbidden`.
3. THE MPRA SHALL propagar la restricción de universidad a través de toda la jerarquía: una consulta filtrada por `university_id` nunca retornará programas ni cursos de otra universidad.
4. FOR ALL consultas de recursos académicos, THE MPRA SHALL garantizar que el filtro por `university_id` produzca resultados equivalentes independientemente del orden en que se apliquen los filtros de jerarquía (propiedad de confluencia).

---

### Requisito 7: Migración de Datos Existentes

**User Story:** Como administrador del sistema, quiero que los datos existentes de programas y cursos sean migrados correctamente a la nueva estructura multi-universidad, para que no se pierda información al activar la funcionalidad.

#### Criterios de Aceptación

1. THE MPRA SHALL proveer una migración Alembic (`0004_add_university_and_multi_university_support`) que cree la tabla `universities` y agregue `university_id` a `programs`.
2. WHEN la migración se ejecuta sobre una base de datos con programas existentes, THE MPRA SHALL asignar esos programas a la universidad por defecto identificada por `DEFAULT_UNIVERSITY_ID`.
3. IF `DEFAULT_UNIVERSITY_ID` no está configurado al momento de ejecutar la migración, THEN la migración SHALL fallar con un mensaje de error descriptivo antes de realizar cambios.
4. THE MPRA SHALL garantizar que la migración sea reversible: el `downgrade()` SHALL restaurar el esquema al estado previo sin pérdida de datos de programas o cursos.
5. WHEN la migración se ejecuta en una base de datos vacía, THE MPRA SHALL completar sin errores y dejar el esquema en el estado esperado.
