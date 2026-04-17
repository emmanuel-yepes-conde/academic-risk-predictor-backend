# Documento de Requisitos — Campus Hierarchy

## Introducción

El MPRA actualmente organiza la jerarquía académica como `University → Program → Course`. Sin embargo, una universidad puede tener múltiples sedes o campus (por ejemplo, "Medellín", "Bogotá", "Cali"), y cada campus administra sus propios programas y cursos de forma independiente. Esta funcionalidad introduce la entidad `Campus` como nivel intermedio en la jerarquía, transformándola en `University → Campus → Program → Course`. El campo `campus` que actualmente existe como texto plano en el modelo `Program` será reemplazado por una relación formal con la nueva tabla `campuses`. Cada campus se identifica de forma única mediante una llave compuesta natural entre el código de la universidad (`university_code`) y un código de campus (`campus_code`).

---

## Glosario

- **University**: Institución de educación superior registrada en el sistema. Raíz de la jerarquía académica. Identificada por un `code` único (ej. `USBCO`).
- **Campus**: Sede física o lógica de una universidad. Pertenece a exactamente una `University`. Identificado por la combinación única de `university_id` + `campus_code` (ej. `USBCO` + `MED`).
- **Program**: Programa académico (carrera) que pertenece a exactamente un `Campus`. Anteriormente vinculado directamente a `University`.
- **Course**: Asignatura o materia que pertenece a exactamente un `Program`.
- **Campus_Code**: Código alfanumérico corto que identifica una sede dentro de una universidad (ej. `MED`, `BOG`, `CAL`).
- **Admin**: Usuario con rol `ADMIN` con acceso completo de gestión sobre todas las entidades.
- **MPRA**: Modelo Predictivo de Riesgo Académico — sistema backend en FastAPI + PostgreSQL.

---

## Requisitos

### Requisito 1: Modelo de Datos de Campus

**User Story:** Como administrador, quiero que exista una entidad Campus en el sistema, para que cada sede de una universidad pueda gestionar sus propios programas y cursos de forma independiente.

#### Criterios de Aceptación

1. THE MPRA SHALL almacenar cada campus con los campos: `id` (UUID, PK), `university_id` (FK → `universities.id`, NOT NULL), `campus_code` (texto alfanumérico, NOT NULL), `name` (nombre descriptivo de la sede, NOT NULL), `city` (ciudad donde se ubica la sede, NOT NULL), `active` (booleano, default `true`), `created_at` (timestamp con zona horaria).
2. THE MPRA SHALL garantizar la unicidad de la combinación `university_id` + `campus_code` mediante un UniqueConstraint en la tabla `campuses`.
3. THE MPRA SHALL crear un índice sobre el campo `university_id` en la tabla `campuses` para optimizar consultas jerárquicas.
4. THE MPRA SHALL crear un índice sobre el campo `campus_code` en la tabla `campuses` para optimizar búsquedas por código.

---

### Requisito 2: CRUD de Campus

**User Story:** Como administrador, quiero crear, consultar, actualizar y listar los campus de una universidad, para gestionar las sedes de forma completa desde la API.

#### Criterios de Aceptación

1. WHEN un administrador envía una solicitud `POST /api/v1/universities/{university_id}/campuses` con datos válidos (`campus_code`, `name`, `city`, `active`), THE MPRA SHALL crear el campus asociado a la universidad y retornar `201 Created` con la representación del recurso creado.
2. IF el `university_id` proporcionado no corresponde a una universidad existente, THEN THE MPRA SHALL retornar `404 Not Found` con el mensaje "Universidad no encontrada".
3. IF la combinación de `university_id` y `campus_code` ya existe en la base de datos, THEN THE MPRA SHALL retornar `409 Conflict` con un mensaje descriptivo.
4. WHEN un cliente envía `GET /api/v1/universities/{university_id}/campuses`, THE MPRA SHALL retornar la lista paginada de campus pertenecientes a la universidad indicada, con parámetros `skip` y `limit`.
5. WHEN un cliente envía `GET /api/v1/universities/{university_id}/campuses/{campus_id}`, THE MPRA SHALL retornar los datos del campus correspondiente o `404 Not Found` si no existe o no pertenece a la universidad.
6. WHEN un administrador envía `PATCH /api/v1/universities/{university_id}/campuses/{campus_id}` con campos válidos, THE MPRA SHALL actualizar únicamente los campos provistos (`name`, `city`, `active`) y retornar `200 OK`.
7. IF un usuario con rol distinto a `ADMIN` intenta crear o actualizar un campus, THEN THE MPRA SHALL retornar `403 Forbidden`.

---

### Requisito 3: Reasociación de Programas a Campus

**User Story:** Como administrador, quiero que cada programa académico esté vinculado a un campus en lugar de directamente a una universidad, para que la jerarquía `University → Campus → Program` sea explícita.

#### Criterios de Aceptación

1. THE MPRA SHALL agregar el campo `campus_id` (FK → `campuses.id`, NOT NULL) al modelo `Program`.
2. THE MPRA SHALL eliminar el campo de texto plano `campus` del modelo `Program`, reemplazándolo por la relación formal con la tabla `campuses`.
3. THE MPRA SHALL mantener el campo `university_id` en el modelo `Program` como campo denormalizado de solo lectura, derivado de la relación `campus.university_id`, para preservar compatibilidad con consultas existentes.
4. THE MPRA SHALL actualizar la restricción de unicidad de `program_code` al alcance de un campus: `UniqueConstraint("program_code", "campus_id")`, permitiendo que dos campus de la misma universidad tengan programas con el mismo código.
5. WHEN un administrador crea un programa, THE MPRA SHALL requerir el campo `campus_id` y validar que el campus referenciado exista.
6. IF el `campus_id` proporcionado no corresponde a un campus existente, THEN THE MPRA SHALL retornar `422 Unprocessable Entity` con un mensaje descriptivo.

---

### Requisito 4: Endpoints Jerárquicos con Campus

**User Story:** Como cliente de la API, quiero consultar la jerarquía completa `University → Campus → Program → Course` a través de endpoints anidados, para navegar la estructura académica de forma intuitiva.

#### Criterios de Aceptación

1. WHEN un cliente envía `GET /api/v1/universities/{university_id}/campuses/{campus_id}/programs`, THE MPRA SHALL retornar la lista paginada de programas pertenecientes al campus indicado, validando que el campus pertenezca a la universidad.
2. WHEN un cliente envía `GET /api/v1/universities/{university_id}/campuses/{campus_id}/programs/{program_id}/courses`, THE MPRA SHALL retornar los cursos del programa, validando la pertenencia completa de la cadena universidad → campus → programa.
3. IF el campus no pertenece a la universidad indicada en la URL, THEN THE MPRA SHALL retornar `404 Not Found` con el mensaje "El campus no pertenece a la universidad indicada".
4. IF el programa no pertenece al campus indicado en la URL, THEN THE MPRA SHALL retornar `404 Not Found` con el mensaje "El programa no pertenece al campus indicado".
5. WHEN un cliente envía `GET /api/v1/universities/{university_id}/programs`, THE MPRA SHALL mantener compatibilidad con el endpoint existente, retornando todos los programas de todos los campus de la universidad.

---

### Requisito 5: Aislamiento de Datos por Campus

**User Story:** Como administrador de un campus, quiero que las consultas filtradas por campus retornen únicamente los recursos de ese campus, para garantizar el aislamiento lógico de datos entre sedes.

#### Criterios de Aceptación

1. WHEN un usuario autenticado realiza una consulta filtrada por `campus_id`, THE MPRA SHALL retornar únicamente los programas y cursos pertenecientes a ese campus.
2. THE MPRA SHALL propagar la restricción de campus a través de la jerarquía: una consulta filtrada por campus retornará solo programas de ese campus y solo cursos de esos programas.
3. FOR ALL consultas de recursos académicos filtradas por campus, THE MPRA SHALL garantizar que el filtro por `campus_id` produzca resultados equivalentes independientemente del orden en que se apliquen los filtros de jerarquía (propiedad de confluencia).

---

### Requisito 6: Schemas y Validación de Campus

**User Story:** Como desarrollador de la API, quiero schemas Pydantic bien definidos para las operaciones de Campus, para que la validación de entrada y la serialización de salida sean consistentes con el resto del sistema.

#### Criterios de Aceptación

1. THE MPRA SHALL definir un schema `CampusCreate` con los campos: `campus_code` (str, obligatorio), `name` (str, obligatorio), `city` (str, obligatorio), `active` (bool, default `true`).
2. THE MPRA SHALL definir un schema `CampusUpdate` con los campos opcionales: `name`, `city`, `active`.
3. THE MPRA SHALL definir un schema `CampusRead` con los campos: `id`, `university_id`, `campus_code`, `name`, `city`, `active`, `created_at`.
4. THE MPRA SHALL actualizar el schema `ProgramRead` para incluir el campo `campus_id` y retirar el campo de texto `campus`.
5. WHEN un campo requerido está ausente en el body de `CampusCreate`, THE MPRA SHALL retornar `422 Unprocessable Entity` con detalles de validación Pydantic.

---

### Requisito 7: Migración de Datos Existentes

**User Story:** Como administrador del sistema, quiero que los datos existentes de programas sean migrados correctamente a la nueva estructura con campus, para que no se pierda información al activar la funcionalidad.

#### Criterios de Aceptación

1. THE MPRA SHALL proveer una migración Alembic que cree la tabla `campuses` con su esquema completo (campos, índices, constraints).
2. WHEN la migración se ejecuta sobre una base de datos con programas existentes que tienen el campo `campus` como texto, THE MPRA SHALL crear registros en la tabla `campuses` a partir de los valores únicos de `campus` + `university_id` existentes en `programs`.
3. WHEN se crean los registros de campus durante la migración, THE MPRA SHALL derivar el `campus_code` del valor textual existente del campo `campus` en el modelo `Program`.
4. THE MPRA SHALL asignar el `campus_id` correspondiente a cada programa existente basándose en la combinación de su `university_id` y su valor de campo `campus` actual.
5. THE MPRA SHALL eliminar el campo de texto `campus` del modelo `Program` después de completar la migración de datos.
6. THE MPRA SHALL actualizar la restricción de unicidad de `program_code` de `("program_code", "university_id")` a `("program_code", "campus_id")`.
7. THE MPRA SHALL garantizar que la migración sea reversible: el `downgrade()` SHALL restaurar el campo `campus` como texto en `Program`, repoblar los valores desde la tabla `campuses` y eliminar la tabla `campuses`.
8. IF la migración se ejecuta en una base de datos vacía (sin programas), THE MPRA SHALL completar sin errores y dejar el esquema en el estado esperado.
