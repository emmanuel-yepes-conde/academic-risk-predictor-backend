# Plan de Implementación: `postgresql-database-integration`

## Visión General

Integración de PostgreSQL 16 como capa de persistencia del backend FastAPI del MPRA, siguiendo Clean Architecture (Dominio / Aplicación / Infraestructura). El stack de persistencia usa SQLModel + asyncpg + Alembic. Los tests combinan pytest + hypothesis (PBT).

**Lenguaje de implementación:** Python 3.12

---

## Tareas

- [x] 1. Actualizar dependencias Python
  - Agregar al `requirements.txt`: `sqlmodel>=0.0.21`, `asyncpg>=0.29.0`, `alembic>=1.13.0`, `bcrypt>=4.1.0`, `hypothesis>=6.100.0`, `pytest-asyncio>=0.23.0`, `pytest>=8.0.0`, `pytest-cov>=5.0.0`
  - Verificar compatibilidad con `pydantic>=2.10.0` ya existente
  - _Requisitos: 3.1, 5.1_

- [x] 2. Configurar servicio PostgreSQL en Docker Compose
  - Agregar servicio `db` con imagen `postgres:16-alpine` al `docker-compose.yml` existente
  - Definir variables de entorno `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` desde `.env`
  - Agregar volumen nombrado `postgres_data` para persistencia
  - Exponer puerto `5432:5432`
  - Agregar `healthcheck` con `pg_isready`, intervalo 10s, timeout 5s, 5 reintentos
  - Agregar `depends_on` con condición `service_healthy` al servicio `backend`
  - _Requisitos: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 3. Ampliar Settings con variables de base de datos
  - Modificar `app/core/config.py` para agregar campos: `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DATABASE_URL` (construida automáticamente con `model_validator`), `DB_POOL_MIN` (default 5), `DB_POOL_MAX` (default 20), `DB_ECHO` (default False)
  - Usar `model_validator(mode='before')` para construir `DATABASE_URL` si no está definida en el entorno
  - Formato: `postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}`
  - _Requisitos: 2.1, 2.2, 2.4_

  - [x] 3.1 Test de propiedad: construcción automática de DATABASE_URL
    - **Propiedad 1: Construcción automática de DATABASE_URL**
    - Crear `tests/property/test_url_construction.py`
    - Usar `@given` con `st.text` para user/password/dbname y `st.integers` para port
    - Verificar que la URL resultante contiene exactamente los valores de entrada y tiene el prefijo `postgresql+asyncpg://`
    - `# Feature: postgresql-database-integration, Property 1: DATABASE_URL construction`
    - **Valida: Requisitos 2.1, 2.4**

- [x] 4. Crear módulo de infraestructura de base de datos
  - Crear `app/infrastructure/__init__.py`
  - Crear `app/infrastructure/database.py` con:
    - `create_async_engine` usando `settings.DATABASE_URL`, `pool_size=settings.DB_POOL_MIN`, `max_overflow=settings.DB_POOL_MAX - settings.DB_POOL_MIN`, `echo=settings.DB_ECHO`
    - `AsyncSessionFactory = async_sessionmaker(engine, expire_on_commit=False)`
    - Función generadora `get_session() -> AsyncGenerator[AsyncSession, None]` con commit en éxito y rollback ante excepción
  - _Requisitos: 3.1, 3.2, 3.3, 3.5_

  - [x] 4.1 Test unitario: rollback automático ante excepción en sesión
    - Crear `tests/unit/test_database.py`
    - Mockear la sesión para lanzar excepción y verificar que `rollback()` es invocado
    - _Requisitos: 3.3_

  - [x] 4.2 Test de propiedad: rollback automático ante excepción
    - **Propiedad 2: Rollback automático ante excepción en sesión**
    - Crear `tests/property/test_session_rollback.py`
    - Usar `@given` con operaciones de escritura generadas aleatoriamente que lanzan excepción
    - Verificar que el estado de la DB permanece idéntico al estado previo
    - `# Feature: postgresql-database-integration, Property 2: Session rollback`
    - **Valida: Requisitos 3.3**

- [x] 5. Definir enums de dominio
  - Crear `app/domain/__init__.py`
  - Crear `app/domain/enums.py` con `RoleEnum(str, Enum)`: `STUDENT`, `PROFESSOR`, `ADMIN` y `OperationEnum(str, Enum)`: `INSERT`, `UPDATE`, `DELETE`
  - _Requisitos: 4.1_

- [x] 6. Definir interfaces de repositorio (ABCs)
  - Crear `app/domain/interfaces/__init__.py`
  - Crear `app/domain/interfaces/user_repository.py` con `IUserRepository(ABC)`: métodos `create`, `get_by_id`, `get_by_email`, `get_by_microsoft_oid`, `get_by_google_oid`, `list`, `update`
  - Crear `app/domain/interfaces/course_repository.py` con `ICourseRepository(ABC)`: métodos `crear`, `obtener_por_id`, `listar_por_docente`, `listar_estudiantes_inscritos`
  - Crear `app/domain/interfaces/audit_log_repository.py` con `IAuditLogRepository(ABC)`: solo método `register`
  - Crear `app/domain/interfaces/consent_repository.py` con `IConsentRepository(ABC)`: métodos `register_consent`, `get_consent`
  - _Requisitos: 6.1, 6.2, 6.3, 6.4_

- [x] 7. Implementar modelos ORM SQLModel
  - Crear `app/infrastructure/models/__init__.py`
  - Crear `app/infrastructure/models/user.py`: modelo `User` con campos `id` (UUID PK), `email` (unique, index), `full_name`, `role` (RoleEnum), `microsoft_oid` (unique, nullable), `google_oid` (unique, nullable), `password_hash` (nullable), `ml_consent` (default False), `created_at`, `updated_at`
  - Crear `app/infrastructure/models/course.py`: modelo `Course` con campos `id`, `code` (unique, index), `name`, `credits`, `academic_period`, `created_at`
  - Crear `app/infrastructure/models/enrollment.py`: modelo `Enrollment` con campos `id`, `student_id` (FK users), `course_id` (FK courses), `enrollment_date`; restricción `UniqueConstraint('student_id', 'course_id')`
  - Crear `app/infrastructure/models/professor_course.py`: modelo `ProfessorCourse` con campos `id`, `professor_id` (FK users), `course_id` (FK courses); restricción `UniqueConstraint('professor_id', 'course_id')`
  - Crear `app/infrastructure/models/audit_log.py`: modelo `AuditLog` con campos `id`, `table_name`, `operation` (OperationEnum), `record_id`, `user_id` (FK nullable), `previous_data` (JSON), `new_data` (JSON), `timestamp` (index)
  - Crear `app/infrastructure/models/consent.py`: modelo `Consent` con campos `id`, `student_id` (FK users, unique), `accepted`, `terms_version`, `accepted_at`
  - _Requisitos: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

- [x] 8. Configurar Alembic y crear migración inicial
  - Ejecutar `alembic init alembic` en la raíz del proyecto
  - Modificar `alembic/env.py` para importar todos los modelos ORM y usar `settings.DATABASE_URL` con soporte async (`run_async_migrations`)
  - Generar migración inicial: `alembic revision --autogenerate -m "initial_schema"`
  - Verificar que el script generado en `alembic/versions/` crea las tablas: `users`, `courses`, `enrollments`, `professor_courses`, `audit_logs`, `consents` con sus índices y restricciones UNIQUE
  - _Requisitos: 5.1, 5.2, 5.3, 5.5_

  - [x] 8.1 Test de propiedad: round trip de migraciones upgrade/downgrade
    - **Propiedad 5: Round trip de migraciones (upgrade / downgrade)**
    - Crear `tests/property/test_migration_roundtrip.py`
    - Verificar que `upgrade head` → `downgrade -1` → `upgrade head` produce un esquema idéntico
    - `# Feature: postgresql-database-integration, Property 5: Migration round trip`
    - **Valida: Requisitos 5.4**

- [x] 9. Implementar repositorios de infraestructura
  - Crear `app/infrastructure/repositories/__init__.py`
  - Crear `app/infrastructure/repositories/audit_log_repository.py`: implementar `IAuditLogRepository` con método `register`; los métodos `update` y `delete` deben lanzar `NotImplementedError`
  - Crear `app/infrastructure/repositories/user_repository.py`: implementar `IUserRepository` con todos los métodos; cada escritura invoca `AuditLogRepository.register` en la misma sesión; `list` acepta `professor_id` opcional para aplicar filtro RB-04 (JOIN con `Enrollment` y `ProfessorCourse`)
  - Crear `app/infrastructure/repositories/course_repository.py`: implementar `ICourseRepository`; `listar_estudiantes_inscritos` filtra por inscripciones activas del docente (RB-04)
  - Crear `app/infrastructure/repositories/consent_repository.py`: implementar `IConsentRepository`; `register_consent` crea nuevo registro (inmutable); no exponer métodos de modificación directa
  - Todos los repositorios reciben `AsyncSession` como dependencia inyectada (DIP)
  - _Requisitos: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.1, 7.2, 7.3, 8.1, 8.4, 9.4_

  - [x] 9.1 Test de propiedad: AuditLog es de solo inserción
    - **Propiedad 4: AuditLog es de solo inserción**
    - Crear `tests/property/test_audit_immutability.py`
    - Usar `@given` con registros AuditLog generados aleatoriamente
    - Verificar que `update` y `delete` lanzan `NotImplementedError` y el registro permanece sin cambios
    - `# Feature: postgresql-database-integration, Property 4: AuditLog insert-only`
    - **Valida: Requisitos 4.7, 9.4**

  - [x] 9.2 Test de propiedad: unicidad de relaciones
    - **Propiedad 3: Unicidad de relaciones (Enrollment, ProfessorCourse, Consent)**
    - Crear `tests/property/test_uniqueness.py`
    - Usar `@given(st.uuids(), st.uuids())` para generar pares de IDs
    - Verificar que el segundo INSERT con los mismos IDs lanza `IntegrityError` y deja exactamente un registro
    - `# Feature: postgresql-database-integration, Property 3: Relationship uniqueness`
    - **Valida: Requisitos 4.3, 4.4, 4.6**

  - [x] 9.3 Test de propiedad: round trip de repositorios (create → get)
    - **Propiedad 6: Round trip de repositorios (create → get)**
    - Crear `tests/property/test_repo_roundtrip.py`
    - Usar `@given(st.emails(), st.text(min_size=1, max_size=100))` para User; estrategias similares para Course y Consent
    - Verificar que `get_by_id` / `get_by_email` retorna exactamente los mismos valores que se pasaron a `create`
    - `# Feature: postgresql-database-integration, Property 6: Repository round trip`
    - **Valida: Requisitos 6.1, 6.2, 6.4**

  - [x] 9.4 Test de propiedad: auditoría atómica con contenido correcto
    - **Propiedad 7: Auditoría atómica con contenido correcto**
    - Crear `tests/property/test_audit_atomicity.py`
    - Usar `@given` con operaciones INSERT/UPDATE/DELETE generadas aleatoriamente sobre tablas auditadas
    - Verificar que existe exactamente un registro nuevo en `audit_logs` con `table_name`, `operation`, `record_id` y `new_data`/`previous_data` correctos
    - `# Feature: postgresql-database-integration, Property 7: Atomic audit`
    - **Valida: Requisitos 6.5, 9.1, 9.2**

  - [x] 9.5 Test de propiedad: filtro de privacidad RB-04
    - **Propiedad 8: Filtro de privacidad RB-04**
    - Crear `tests/property/test_privacy_filter.py`
    - Usar `@given(st.integers(min_value=1, max_value=10), st.integers(min_value=0, max_value=5))` para n_students y n_enrolled
    - Verificar que `UserRepository.list(professor_id=...)` retorna exactamente los estudiantes inscritos en asignaturas del docente
    - `# Feature: postgresql-database-integration, Property 8: Privacy filter RB-04`
    - **Valida: Requisitos 7.1, 7.2, 7.3**

  - [x] 9.6 Test de propiedad: inmutabilidad del registro de consentimiento
    - **Propiedad 10: Inmutabilidad del registro de consentimiento**
    - Crear `tests/property/test_consent_immutability.py`
    - Verificar que no existe ningún método en `ConsentRepository` que modifique campos directamente; la revocación crea un nuevo registro
    - `# Feature: postgresql-database-integration, Property 10: Consent immutability`
    - **Valida: Requisitos 8.4**

  - [x] 9.7 Tests de integración de repositorios
    - Crear `tests/integration/test_user_repository.py`, `test_course_repository.py`, `test_audit_log_repository.py`, `test_consent_repository.py`
    - Cubrir casos borde: email duplicado → `IntegrityError`, inscripción duplicada → `IntegrityError`, consentimiento inexistente → `None`
    - _Requisitos: 6.1, 6.2, 6.3, 6.4_

- [x] 10. Checkpoint — Verificar que todos los tests de repositorios pasan
  - Asegurarse de que todos los tests pasan. Consultar al usuario si surgen dudas.

- [x] 11. Integrar pool de DB con lifespan de FastAPI
  - Modificar `app/main.py`: en el bloque `startup` del `lifespan`, llamar a `engine.connect()` para inicializar el pool; en el bloque `shutdown`, llamar a `await engine.dispose()` para cerrar todas las conexiones
  - Importar `engine` desde `app/infrastructure/database`
  - _Requisitos: 3.4_

- [x] 12. Ampliar endpoint `/health` con verificación de DB
  - Crear `app/api/v1/endpoints/health.py` con lógica de health check
  - Ejecutar `SELECT 1` contra la DB con timeout de 2 segundos usando `asyncio.wait_for`
  - Retornar `{"status": "healthy", "database": "connected", ...}` con HTTP 200 si la DB responde
  - Retornar `{"status": "unhealthy", "database": "unreachable"}` con HTTP 503 si la DB no responde
  - Retornar `{"status": "unhealthy", "database": "timeout"}` con HTTP 503 si supera 2 segundos
  - Registrar el router en `app/main.py` y eliminar el endpoint `/health` inline actual
  - _Requisitos: 10.1, 10.2, 10.3, 10.4_

  - [x] 12.1 Test unitario: health check con DB disponible e indisponible
    - Crear `tests/unit/test_health.py`
    - Mockear la sesión de DB para simular disponible, no disponible y timeout
    - Verificar códigos HTTP y campos `database` en la respuesta
    - _Requisitos: 10.1, 10.2, 10.3, 10.4_

  - [x] 12.2 Test de propiedad: health check reporta estado real de la DB
    - **Propiedad 11: Health check reporta estado real de la DB**
    - Crear `tests/property/test_health_check.py`
    - Usar `@given(st.sampled_from(["connected", "unreachable", "timeout"]))` para simular estados
    - Verificar que el campo `database` y el código HTTP corresponden fielmente al estado simulado
    - `# Feature: postgresql-database-integration, Property 11: Health check DB state`
    - **Valida: Requisitos 10.1, 10.2, 10.3, 10.4**

- [x] 13. Implementar consent gate en MLService
  - Crear `app/application/services/__init__.py` y `app/application/services/consent_service.py` con lógica de verificación de consentimiento
  - Modificar `app/services/ml_service.py` (o crear `app/application/services/ml_service.py`) para inyectar `ConsentRepository` y verificar `Consent.accepted == True` antes de ejecutar la predicción
  - Si `accepted == False` o no existe registro, lanzar `HTTPException(status_code=403, detail="El estudiante no ha otorgado consentimiento para el procesamiento de datos ML")`
  - _Requisitos: 8.2, 8.3_

  - [x] 13.1 Test de propiedad: consentimiento ML como prerequisito de predicción
    - **Propiedad 9: Consentimiento ML como prerequisito de predicción**
    - Crear `tests/property/test_consent_gate.py`
    - Usar `@given(st.booleans())` para el campo `accepted`
    - Verificar que `accepted=False` o ausencia de registro → HTTP 403 sin ejecutar predicción; `accepted=True` → predicción ejecutada
    - `# Feature: postgresql-database-integration, Property 9: ML consent gate`
    - **Valida: Requisitos 8.2, 8.3**

- [x] 14. Crear schemas Pydantic de aplicación (DTOs)
  - Crear `app/application/schemas/__init__.py`
  - Crear `app/application/schemas/user.py`: `UserCreate`, `UserUpdate`, `UserRead`
  - Crear `app/application/schemas/course.py`: `CourseCreate`, `CourseRead`
  - Crear `app/application/schemas/consent.py`: `ConsentRead`
  - Crear `app/application/schemas/audit_log.py`: `AuditLogCreate`
  - _Requisitos: 6.1, 6.2, 6.3, 6.4_

- [x] 15. Crear módulo de seguridad
  - Crear `app/core/security.py` con helpers bcrypt: `hash_password(plain: str) -> str` usando `bcrypt.hashpw` y `verify_password(plain: str, hashed: str) -> bool` usando `bcrypt.checkpw`
  - _Requisitos: 4.1 (campo `password_hash`)_

  - [x] 15.1 Test unitario: helpers de seguridad
    - Crear `tests/unit/test_security.py`
    - Verificar que `hash_password` produce un hash diferente al texto plano y que `verify_password` retorna `True` para el par correcto y `False` para uno incorrecto
    - _Requisitos: 4.1_

- [x] 16. Actualizar `env.example` y configurar pytest
  - Agregar al `env.example` todas las variables nuevas de DB con valores de ejemplo: `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DATABASE_URL` (comentada), `DB_POOL_MIN`, `DB_POOL_MAX`, `DB_ECHO`
  - Crear `pyproject.toml` (o `pytest.ini`) con configuración: `asyncio_mode = "auto"`, `testpaths = ["tests"]`
  - Crear estructura de directorios de tests: `tests/__init__.py`, `tests/unit/__init__.py`, `tests/integration/__init__.py`, `tests/property/__init__.py`
  - _Requisitos: 2.3_

  - [x] 16.1 Test unitario: Settings construye DATABASE_URL correctamente
    - Crear `tests/unit/test_config.py`
    - Verificar que `Settings` con variables individuales construye `DATABASE_URL` con el formato correcto
    - Verificar que si `DATABASE_URL` está definida en el entorno, se usa directamente sin reconstruir
    - _Requisitos: 2.1, 2.4_

- [x] 17. Checkpoint final — Verificar que todos los tests pasan
  - Ejecutar `pytest tests/ -v --cov=app` y asegurarse de que todos los tests pasan. Consultar al usuario si surgen dudas.

---

## Notas

- Las tareas marcadas con `*` son opcionales y pueden omitirse para un MVP más rápido
- Cada tarea referencia requisitos específicos para trazabilidad
- Los tests de propiedad usan `@h_settings(max_examples=100)` como mínimo
- Los repositorios reciben `AsyncSession` por inyección de dependencias (nunca la crean internamente)
- La auditoría es atómica: `AuditLogRepository.register` se invoca dentro de la misma sesión que la operación principal
- El filtro RB-04 se aplica en la capa de datos (repositorio), no solo en la capa API
