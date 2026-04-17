# Documento de Requisitos

## Introducción

Esta feature integra una base de datos PostgreSQL 16 al backend FastAPI del MPRA (Modelo Predictivo de Riesgo Académico). La integración gestiona la persistencia de usuarios (docentes, estudiantes y administradores) y asignaturas, siguiendo los principios de Clean Architecture (capas Dominio / Aplicación / Infraestructura) y SOLID. El ORM elegido es **SQLModel** (construido sobre SQLAlchemy + Pydantic v2), que ofrece una experiencia similar a Prisma para TypeScript. Las migraciones se gestionan con **Alembic**. El entorno de desarrollo local levanta PostgreSQL mediante Docker Compose.

---

## Glosario

- **DB**: Base de datos PostgreSQL 16.
- **ORM**: SQLModel (capa de mapeo objeto-relacional sobre SQLAlchemy 2.x).
- **Alembic**: Herramienta de migraciones de esquema para SQLAlchemy/SQLModel.
- **Migration**: Script versionado que aplica o revierte cambios en el esquema de la DB.
- **Session**: Unidad de trabajo de SQLModel/SQLAlchemy que encapsula una transacción.
- **Repository**: Clase de la capa de Infraestructura que abstrae el acceso a la DB.
- **Domain_Model**: Clase Python que representa una entidad de negocio (sin dependencias de infraestructura).
- **ORM_Model**: Clase SQLModel que mapea una entidad a una tabla de la DB.
- **Usuario**: Persona registrada en el sistema; puede tener rol `STUDENT`, `PROFESSOR` o `ADMIN`.
- **Asignatura**: Materia académica que puede tener docentes asignados y estudiantes inscritos.
- **Inscripcion**: Relación entre un Estudiante y una Asignatura en un período académico.
- **ProfessorCourse**: Relación entre un Docente y una Asignatura que le ha sido asignada.
- **AuditLog**: Registro inmutable de cada operación de escritura (`INSERT`/`UPDATE`/`DELETE`) en la DB.
- **Consent**: Registro del consentimiento explícito de un estudiante para el procesamiento de sus datos en el motor ML.
- **Docker_Compose**: Herramienta para orquestar servicios en entorno de desarrollo local.
- **Connection_Pool**: Conjunto de conexiones reutilizables a la DB gestionado por SQLAlchemy.
- **Health_Check**: Endpoint que verifica la disponibilidad y conectividad del servicio.

---

## Requisitos

### Requisito 1: Servicio PostgreSQL en entorno de desarrollo local

**User Story:** Como desarrollador, quiero levantar PostgreSQL 16 desde Docker Compose, para tener un entorno de desarrollo local reproducible sin instalar la DB en el sistema operativo.

#### Criterios de Aceptación

1. THE Docker_Compose SHALL incluir un servicio `db` basado en la imagen oficial `postgres:16-alpine` con variables de entorno `POSTGRES_USER`, `POSTGRES_PASSWORD` y `POSTGRES_DB` configurables desde un archivo `.env`.
2. THE Docker_Compose SHALL definir un volumen nombrado `postgres_data` para persistir los datos entre reinicios del contenedor.
3. THE Docker_Compose SHALL exponer el puerto `5432` del contenedor al puerto `5432` del host en entorno de desarrollo.
4. THE Docker_Compose SHALL incluir un `healthcheck` para el servicio `db` que use `pg_isready` con un intervalo de 10 segundos, timeout de 5 segundos y 5 reintentos antes de marcar el servicio como no saludable.
5. WHEN el servicio `backend` se inicia en Docker Compose, THE Docker_Compose SHALL declarar `depends_on` con condición `service_healthy` sobre el servicio `db`, garantizando que el backend no arranque hasta que la DB esté lista.

---

### Requisito 2: Configuración de la conexión a la base de datos

**User Story:** Como desarrollador, quiero centralizar la configuración de la conexión a PostgreSQL en `app/core/config.py`, para gestionar las credenciales mediante variables de entorno sin hardcodear valores sensibles.

#### Criterios de Aceptación

1. THE Settings_Class SHALL incluir un campo `DATABASE_URL` de tipo `str` con valor por defecto construido a partir de las variables `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` y `DB_NAME`, siguiendo el formato `postgresql+asyncpg://user:password@host:port/dbname`.
2. THE Settings_Class SHALL exponer los campos individuales `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` y `DB_NAME` como variables de entorno independientes para facilitar el despliegue en plataformas como Railway o Render.
3. THE env_example_file SHALL documentar todas las variables de entorno nuevas relacionadas con la DB con valores de ejemplo para entorno local.
4. IF la variable `DATABASE_URL` no está definida en el entorno, THEN THE Settings_Class SHALL construirla automáticamente a partir de los campos individuales `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` y `DB_NAME`.

---

### Requisito 3: Inicialización del motor de base de datos y gestión de sesiones

**User Story:** Como desarrollador, quiero un módulo de infraestructura que gestione el motor SQLAlchemy y las sesiones de DB, para que los repositorios y servicios puedan obtener sesiones de forma segura y eficiente.

#### Criterios de Aceptación

1. THE Database_Module SHALL crear un motor SQLAlchemy asíncrono (`create_async_engine`) usando `asyncpg` como driver, con un `Connection_Pool` de mínimo 5 y máximo 20 conexiones configurables desde `Settings`.
2. THE Database_Module SHALL exponer una función generadora asíncrona `get_session` compatible con el sistema de inyección de dependencias de FastAPI (`Depends`), que abra una `Session`, la ceda al llamador y la cierre al finalizar la petición.
3. WHEN una excepción ocurre dentro de una `Session`, THE Database_Module SHALL hacer rollback de la transacción activa antes de propagar la excepción.
4. THE Application_Lifespan SHALL inicializar el `Connection_Pool` al arrancar el servicio FastAPI y cerrarlo al apagar el servicio.
5. WHILE el servicio está en ejecución, THE Database_Module SHALL mantener el `Connection_Pool` activo y reutilizar conexiones entre peticiones.

---

### Requisito 4: Modelos ORM de dominio

**User Story:** Como desarrollador, quiero definir los modelos ORM de las entidades principales usando SQLModel, para tener una única fuente de verdad que sirva tanto como modelo de DB como esquema Pydantic.

#### Criterios de Aceptación

1. THE ORM_Model `User` SHALL definir los campos: `id` (UUID, PK, generado automáticamente), `email` (str, único, no nulo), `full_name` (str, no nulo), `role` (Enum: `STUDENT`, `PROFESSOR`, `ADMIN`), `microsoft_oid` (str, único, nullable — identificador de Microsoft Entra ID), `google_oid` (str, único, nullable — identificador de Google), `password_hash` (str, nullable), `ml_consent` (bool, default `False`), `created_at` (datetime, default UTC now) y `updated_at` (datetime, actualizado automáticamente en cada UPDATE).
2. THE ORM_Model `Asignatura` SHALL definir los campos: `id` (UUID, PK, generado automáticamente), `codigo` (str, único, no nulo), `nombre` (str, no nulo), `creditos` (int, no nulo), `periodo_academico` (str, no nulo) y `fecha_creacion` (datetime, default UTC now).
3. THE ORM_Model `Inscripcion` SHALL definir los campos: `id` (UUID, PK), `estudiante_id` (UUID, FK → `Usuario.id`), `course_id` (UUID, FK → `Asignatura.id`), `fecha_inscripcion` (datetime, default UTC now) y una restricción `UNIQUE` compuesta sobre (`estudiante_id`, `course_id`).
4. THE ORM_Model `ProfessorCourse` SHALL definir los campos: `id` (UUID, PK), `docente_id` (UUID, FK → `Usuario.id`), `course_id` (UUID, FK → `Asignatura.id`) y una restricción `UNIQUE` compuesta sobre (`docente_id`, `course_id`).
5. THE ORM_Model `AuditLog` SHALL definir los campos: `id` (UUID, PK), `table_name` (str, no nulo), `operation` (Enum: `INSERT`, `UPDATE`, `DELETE`), `record_id` (UUID, no nulo), `user_id` (UUID, nullable — FK → `User.id`), `previous_data` (JSON, nullable), `new_data` (JSON, nullable) y `timestamp` (datetime, default UTC now, no actualizable).
6. THE ORM_Model `Consent` SHALL definir los campos: `id` (UUID, PK), `student_id` (UUID, FK → `User.id`, único), `accepted` (bool, no nulo), `terms_version` (str, no nulo) y `accepted_at` (datetime, default UTC now).
7. THE ORM_Model `AuditLog` SHALL ser de solo inserción: el sistema no permitirá operaciones UPDATE ni DELETE sobre registros de `AuditLog`.

---

### Requisito 5: Migraciones de esquema con Alembic

**User Story:** Como desarrollador, quiero gestionar los cambios de esquema de la DB mediante migraciones versionadas con Alembic, para aplicar y revertir cambios de forma controlada en todos los entornos.

#### Criterios de Aceptación

1. THE Alembic_Config SHALL estar inicializado en el directorio `alembic/` con un `env.py` que importe los `ORM_Model` del proyecto y use la `DATABASE_URL` de `Settings` para conectarse.
2. WHEN el desarrollador ejecuta `alembic revision --autogenerate -m "<descripcion>"`, THE Alembic SHALL generar un script de migración en `alembic/versions/` que refleje los cambios en los `ORM_Model` respecto al estado actual de la DB.
3. WHEN el desarrollador ejecuta `alembic upgrade head`, THE Alembic SHALL aplicar todas las migraciones pendientes a la DB en orden cronológico.
4. WHEN el desarrollador ejecuta `alembic downgrade -1`, THE Alembic SHALL revertir la última migración aplicada sin afectar las migraciones anteriores.
5. THE initial_migration SHALL crear todas las tablas definidas en los `ORM_Model` del Requisito 4, incluyendo índices sobre `Usuario.email`, `Usuario.microsoft_oid`, `Asignatura.codigo` y `AuditLog.timestamp`. Las tablas `Inscripcion` y `ProfessorCourse` deberán crearse con sus respectivas claves foráneas y restricciones `UNIQUE`.

---

### Requisito 6: Repositorios de acceso a datos

**User Story:** Como desarrollador, quiero repositorios que encapsulen las operaciones CRUD sobre cada entidad, para que la capa de Aplicación no tenga dependencias directas de SQLModel ni de SQL.

#### Criterios de Aceptación

1. THE `UserRepository` SHALL implementar los métodos: `create(user: UserCreate) → User`, `get_by_id(id: UUID) → User | None`, `get_by_email(email: str) → User | None`, `get_by_microsoft_oid(oid: str) → User | None`, `list(role: RoleEnum | None, skip: int, limit: int) → list[User]` y `update(id: UUID, data: UserUpdate) → User | None`.
2. THE `CourseRepository` SHALL implementar los métodos: `crear(asignatura: CourseCreate) → Asignatura`, `obtener_por_id(id: UUID) → Asignatura | None`, `listar_por_docente(docente_id: UUID) → list[Asignatura]` y `listar_estudiantes_inscritos(course_id: UUID) → list[Usuario]`.
3. THE `AuditLogRepository` SHALL implementar el método `register(log: AuditLogCreate) → AuditLog` y no expondrá métodos de actualización ni eliminación.
4. THE `ConsentRepository` SHALL implementar los métodos: `register_consent(student_id: UUID, version: str) → Consent` y `get_consent(student_id: UUID) → Consent | None`.
5. WHEN un repositorio ejecuta una operación de escritura (INSERT, UPDATE), THE Repository SHALL invocar `AuditLogRepository.register` dentro de la misma `Session` para garantizar atomicidad.
6. THE Repository_Layer SHALL recibir la `Session` como dependencia inyectada (no la creará internamente), siguiendo el principio de inversión de dependencias (DIP).

---

### Requisito 7: Aplicación de la regla de privacidad RB-04

**User Story:** Como docente, quiero que el sistema solo me permita ver los datos de los estudiantes inscritos en mis asignaturas, para garantizar la privacidad de los estudiantes según la regla de negocio RB-04.

#### Criterios de Aceptación

1. WHEN un usuario con rol `DOCENTE` consulta la lista de estudiantes, THE `CourseRepository` SHALL filtrar los resultados retornando únicamente los estudiantes con una `Inscripcion` activa en alguna `Asignatura` asignada al docente solicitante.
2. IF un usuario con rol `DOCENTE` intenta acceder a datos de un estudiante no inscrito en ninguna de sus asignaturas, THEN THE Repository_Layer SHALL retornar `None` o una lista vacía, sin lanzar un error de autorización (la restricción se aplica en la capa de datos, no solo en la capa de API).
3. THE `UserRepository.list` SHALL aceptar un parámetro opcional `professor_id: UUID | None`; WHEN `professor_id` está presente, THE Repository SHALL aplicar el filtro de RB-04 automáticamente.

---

### Requisito 8: Gestión del consentimiento ML (RB-02)

**User Story:** Como estudiante, quiero que el sistema registre mi consentimiento explícito antes de procesar mis datos en el motor ML, para tener control sobre el uso de mi información académica.

#### Criterios de Aceptación

1. THE `ConsentRepository` SHALL persistir el consentimiento del estudiante con la versión de los términos aceptados y la fecha exacta de aceptación en UTC.
2. WHEN el motor ML intenta procesar datos de un estudiante, THE ML_Service SHALL consultar `ConsentRepository.get_consent` y verificar que `Consent.accepted == True` antes de ejecutar la predicción.
3. IF `Consent.accepted == False` o no existe un registro de `Consent` para el estudiante, THEN THE ML_Service SHALL retornar un error con código HTTP 403 y el mensaje `"El estudiante no ha otorgado consentimiento para el procesamiento de datos ML"`.
4. THE `Consent` record SHALL ser inmutable una vez creado; para revocar el consentimiento, THE System SHALL crear un nuevo registro `Consent` con `accepted = False`.

---

### Requisito 9: Auditoría de escrituras en base de datos

**User Story:** Como administrador del sistema, quiero que cada operación de escritura en la DB quede registrada en un log de auditoría, para garantizar la trazabilidad de cambios en datos sensibles.

#### Criterios de Aceptación

1. WHEN se ejecuta una operación INSERT, UPDATE o DELETE sobre las tablas `Usuario`, `Asignatura`, `Inscripcion` o `Consent`, THE Audit_Service SHALL crear un registro en `AuditLog` con la tabla afectada, el tipo de operación, el `id` del registro modificado, el `usuario_id` del actor (si está disponible en el contexto), los datos anteriores (para UPDATE/DELETE) y los datos nuevos (para INSERT/UPDATE).` (para INSERT/UPDATE).
2. THE `AuditLog` records SHALL ser persistidos en la misma transacción de DB que la operación que los originó, garantizando consistencia.
3. THE `AuditLog` table SHALL tener un índice sobre el campo `timestamp` para permitir consultas eficientes por rango de fechas.
4. THE `AuditLog` records SHALL ser de solo inserción: THE System SHALL rechazar cualquier intento de UPDATE o DELETE sobre la tabla `AuditLog` a nivel de repositorio.

---

### Requisito 10: Health check de conectividad con la base de datos

**User Story:** Como operador del sistema, quiero que el endpoint `/health` reporte el estado de la conexión a la DB, para detectar problemas de conectividad sin necesidad de revisar los logs del servidor.

#### Criterios de Aceptación

1. WHEN se realiza una petición `GET /health`, THE Health_Endpoint SHALL ejecutar una consulta de verificación (`SELECT 1`) contra la DB y reportar el estado de la conexión en el campo `database` de la respuesta.
2. IF la DB no está disponible o la consulta falla, THEN THE Health_Endpoint SHALL retornar HTTP 503 con `{"status": "unhealthy", "database": "unreachable"}` en lugar de HTTP 200.
3. WHEN la DB está disponible, THE Health_Endpoint SHALL retornar HTTP 200 con `{"status": "healthy", "database": "connected"}` junto con los campos existentes del health check actual.
4. THE Health_Endpoint SHALL completar la verificación de conectividad con la DB en menos de 2 segundos; IF supera ese tiempo, THEN THE Health_Endpoint SHALL reportar `"database": "timeout"` y retornar HTTP 503.
