# Documento de Requerimientos — Simplificación del Modelo de Datos: Programa → Curso

## Introducción

El sistema MPRA (Modelo Predictivo de Riesgo Académico) actualmente implementa una jerarquía de datos de cuatro niveles: **Universidad → Campus → Programa → Curso**. Para el MVP, esta complejidad es innecesaria y agrega carga de mantenimiento, endpoints redundantes y migraciones frágiles.

Este feature simplifica el modelo de datos a una relación directa **Programa → Curso**, eliminando las entidades `University` y `Campus` junto con toda su infraestructura asociada (modelos ORM, repositorios, interfaces de dominio, servicios, schemas Pydantic, endpoints API y migraciones). El modelo `Program` se simplifica para ser autónomo, sin dependencias a tablas externas de jerarquía institucional.

## Glosario

- **Sistema**: El backend MPRA (FastAPI + PostgreSQL).
- **Programa**: Entidad que representa un programa académico (tabla `programs`). Contiene código, nombre, tipo de grado y metadatos académicos.
- **Curso**: Entidad que representa una asignatura (tabla `courses`). Pertenece a un Programa mediante `program_id` (FK).
- **Migración_Alembic**: Script de migración de base de datos gestionado por Alembic que modifica el esquema de PostgreSQL.
- **Modelo_ORM**: Clase SQLModel que mapea una tabla de la base de datos a un objeto Python.
- **Schema_Pydantic**: Clase Pydantic que define la estructura de datos para validación de entrada/salida en la API.
- **Repositorio**: Clase de la capa de infraestructura que encapsula las operaciones de persistencia (CRUD) contra la base de datos.
- **Interfaz_Dominio**: Clase abstracta (ABC) en la capa de dominio que define el contrato de un Repositorio.
- **Endpoint**: Ruta HTTP expuesta por la API REST de FastAPI.
- **Perfil_Estudiante**: Entidad que almacena datos académicos del estudiante (tabla `student_profiles`), vinculada a un Programa mediante `program_id`.

## Requerimientos

### Requerimiento 1: Eliminar la entidad University del sistema

**User Story:** Como desarrollador del MVP, quiero eliminar la entidad University y toda su infraestructura asociada, para que el modelo de datos sea más simple y no requiera gestión de universidades.

#### Criterios de Aceptación

1. WHEN el Sistema ejecute la Migración_Alembic de simplificación, THE Sistema SHALL eliminar la columna `university_id` de la tabla `programs`.
2. WHEN el Sistema ejecute la Migración_Alembic de simplificación, THE Sistema SHALL eliminar la tabla `universities` de la base de datos.
3. THE Sistema SHALL eliminar el Modelo_ORM `University` del módulo `app/infrastructure/models/university.py`.
4. THE Sistema SHALL eliminar el Repositorio `UniversityRepository` del módulo `app/infrastructure/repositories/university_repository.py`.
5. THE Sistema SHALL eliminar la Interfaz_Dominio `IUniversityRepository` del módulo `app/domain/interfaces/university_repository.py`.
6. THE Sistema SHALL eliminar el servicio `UniversityService` del módulo `app/application/services/university_service.py`.
7. THE Sistema SHALL eliminar los Schema_Pydantic `UniversityCreate`, `UniversityUpdate` y `UniversityRead` del módulo `app/application/schemas/university.py`.
8. THE Sistema SHALL eliminar todos los Endpoint de universidades del módulo `app/api/v1/endpoints/universities.py`.
9. THE Sistema SHALL eliminar el registro del router de universidades en `app/main.py`.
10. THE Sistema SHALL eliminar las referencias a `University` y `Campus` del módulo `app/infrastructure/models/__init__.py`.

### Requerimiento 2: Eliminar la entidad Campus del sistema

**User Story:** Como desarrollador del MVP, quiero eliminar la entidad Campus y toda su infraestructura asociada, para que no exista una capa intermedia entre programa y la organización.

#### Criterios de Aceptación

1. WHEN el Sistema ejecute la Migración_Alembic de simplificación, THE Sistema SHALL eliminar la columna `campus_id` de la tabla `programs`.
2. WHEN el Sistema ejecute la Migración_Alembic de simplificación, THE Sistema SHALL eliminar la tabla `campuses` de la base de datos.
3. THE Sistema SHALL eliminar el Modelo_ORM `Campus` del módulo `app/infrastructure/models/campus.py`.
4. THE Sistema SHALL eliminar el Repositorio `CampusRepository` del módulo `app/infrastructure/repositories/campus_repository.py`.
5. THE Sistema SHALL eliminar la Interfaz_Dominio `ICampusRepository` del módulo `app/domain/interfaces/campus_repository.py`.
6. THE Sistema SHALL eliminar el servicio `CampusService` del módulo `app/application/services/campus_service.py`.
7. THE Sistema SHALL eliminar los Schema_Pydantic `CampusCreate`, `CampusUpdate` y `CampusRead` del módulo `app/application/schemas/campus.py`.
8. THE Sistema SHALL eliminar todos los Endpoint de campus del módulo `app/api/v1/endpoints/campuses.py`.
9. THE Sistema SHALL eliminar el registro del router de campus en `app/main.py`.

### Requerimiento 3: Simplificar el modelo Program

**User Story:** Como desarrollador del MVP, quiero que el modelo Program sea autónomo sin dependencias a University ni Campus, para que la relación Programa → Curso sea directa y simple.

#### Criterios de Aceptación

1. THE Modelo_ORM `Program` SHALL contener únicamente los campos: `id`, `institution`, `degree_type`, `program_code`, `program_name`, `pensum`, `academic_group`, `location`, `snies_code` y `created_at`.
2. THE Modelo_ORM `Program` SHALL definir una restricción de unicidad sobre el campo `program_code`.
3. THE Modelo_ORM `Program` SHALL definir una restricción de unicidad sobre el campo `snies_code`.
4. WHEN el Sistema ejecute la Migración_Alembic de simplificación, THE Sistema SHALL restaurar la restricción de unicidad global de `program_code` (sin scope por universidad ni campus).
5. THE Schema_Pydantic `ProgramRead` SHALL excluir los campos `university_id` y `campus_id` de su definición.

### Requerimiento 4: Mantener la relación Programa → Curso intacta

**User Story:** Como desarrollador del MVP, quiero que la relación entre Programa y Curso se mantenga funcional, para que los cursos sigan perteneciendo a un programa académico.

#### Criterios de Aceptación

1. THE Modelo_ORM `Course` SHALL mantener el campo `program_id` como clave foránea obligatoria (NOT NULL) apuntando a `programs.id`.
2. WHEN se consulte un Programa por su ID, THE Sistema SHALL retornar los datos del Programa sin campos de universidad ni campus.
3. WHEN se listen los Cursos de un Programa, THE Sistema SHALL retornar todos los Cursos cuyo `program_id` coincida con el Programa solicitado.
4. THE Endpoint `GET /programs/{program_id}/courses` SHALL permanecer funcional y retornar la lista de Cursos del Programa indicado.

### Requerimiento 5: Simplificar los endpoints de la API

**User Story:** Como desarrollador del MVP, quiero que la API exponga endpoints simples para programas y cursos, para que el frontend no necesite navegar una jerarquía de universidad → campus → programa.

#### Criterios de Aceptación

1. THE Sistema SHALL eliminar todos los Endpoint que contengan `/universities/` en su ruta.
2. THE Sistema SHALL eliminar todos los Endpoint que contengan `/campuses/` en su ruta.
3. THE Endpoint `GET /programs/{program_id}/courses` SHALL retornar la lista de Cursos del Programa con código de estado 200.
4. IF el `program_id` proporcionado no existe en la base de datos, THEN THE Sistema SHALL retornar un error con código de estado 404 y el mensaje "Programa no encontrado".

### Requerimiento 6: Simplificar repositorios e interfaces de dominio

**User Story:** Como desarrollador del MVP, quiero que los repositorios y sus interfaces reflejen el modelo simplificado, para que no existan métodos que dependan de university_id o campus_id.

#### Criterios de Aceptación

1. THE Interfaz_Dominio `IProgramRepository` SHALL exponer los métodos `get_by_id`, `list_all` y `count_all` sin parámetros de `university_id` ni `campus_id`.
2. THE Repositorio `ProgramRepository` SHALL implementar los métodos `get_by_id`, `list_all` y `count_all` sin filtros por universidad ni campus.
3. THE Interfaz_Dominio `ICourseRepository` SHALL eliminar los métodos `listar_por_universidad_y_programa` y `listar_por_campus_y_programa`.
4. THE Repositorio `CourseRepository` SHALL eliminar los métodos `listar_por_universidad_y_programa` y `listar_por_campus_y_programa`.
5. THE Repositorio `CourseRepository` SHALL mantener el método `listar_por_programa` funcional para la relación Programa → Curso.

### Requerimiento 7: Crear migración Alembic de simplificación

**User Story:** Como desarrollador del MVP, quiero una migración Alembic que transforme el esquema de base de datos al modelo simplificado, para que la base de datos refleje la relación directa Programa → Curso.

#### Criterios de Aceptación

1. THE Migración_Alembic SHALL tener como revisión padre la migración `0005` (campus hierarchy).
2. WHEN se ejecute la función `upgrade()`, THE Migración_Alembic SHALL eliminar la columna `campus_id` de la tabla `programs`.
3. WHEN se ejecute la función `upgrade()`, THE Migración_Alembic SHALL eliminar la columna `university_id` de la tabla `programs`.
4. WHEN se ejecute la función `upgrade()`, THE Migración_Alembic SHALL eliminar la tabla `campuses`.
5. WHEN se ejecute la función `upgrade()`, THE Migración_Alembic SHALL eliminar la tabla `universities`.
6. WHEN se ejecute la función `upgrade()`, THE Migración_Alembic SHALL restaurar la restricción de unicidad global sobre `program_code` en la tabla `programs`.
7. WHEN se ejecute la función `upgrade()`, THE Migración_Alembic SHALL eliminar las restricciones de clave foránea `fk_programs_campus_id` y `fk_programs_university_id` antes de eliminar las columnas.
8. WHEN se ejecute la función `upgrade()`, THE Migración_Alembic SHALL eliminar los índices `ix_programs_campus_id` y `ix_programs_university_id` antes de eliminar las columnas.
9. THE Migración_Alembic SHALL incluir una función `downgrade()` que revierta todos los cambios del `upgrade()`.

### Requerimiento 8: Mantener la integridad del Perfil_Estudiante

**User Story:** Como desarrollador del MVP, quiero que el perfil del estudiante siga vinculado a un programa, para que la relación estudiante → programa no se rompa con la simplificación.

#### Criterios de Aceptación

1. THE Modelo_ORM `StudentProfile` SHALL mantener el campo `program_id` como clave foránea opcional (nullable) apuntando a `programs.id`.
2. WHEN se consulte un Perfil_Estudiante, THE Sistema SHALL retornar el `program_id` asociado sin campos de universidad ni campus.

### Requerimiento 9: Actualizar la documentación del proyecto

**User Story:** Como desarrollador del MVP, quiero que la documentación refleje el modelo simplificado, para que cualquier desarrollador entienda la estructura actual del sistema.

#### Criterios de Aceptación

1. THE Sistema SHALL actualizar el archivo `README.md` para reflejar el modelo de datos simplificado Programa → Curso.
2. THE Sistema SHALL actualizar el diagrama ER en formato Mermaid para mostrar únicamente las relaciones vigentes sin University ni Campus.
3. THE Sistema SHALL actualizar la sección de endpoints de la API en el `README.md` para excluir los endpoints eliminados de universidades y campus.
