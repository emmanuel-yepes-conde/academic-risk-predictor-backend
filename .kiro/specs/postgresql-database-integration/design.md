# Documento de Diseño Técnico
## Feature: `postgresql-database-integration`
### MPRA — Modelo Predictivo de Riesgo Académico

---

## Visión General

Este documento describe el diseño técnico para integrar PostgreSQL 16 como capa de persistencia del backend FastAPI del MPRA. La integración introduce gestión de usuarios (roles `STUDENT`, `PROFESSOR`, `ADMIN`), asignaturas, inscripciones, auditoría atómica y consentimiento ML, siguiendo **Clean Architecture** (Dominio / Aplicación / Infraestructura) y principios **SOLID**.

**Stack de persistencia elegido:**
- ORM: **SQLModel** (SQLAlchemy 2.x + Pydantic v2)
- Driver async: **asyncpg**
- Migraciones: **Alembic**
- Entorno local: **Docker Compose** con `postgres:16-alpine`

**Decisiones de diseño clave:**

| Decisión | Alternativa descartada | Justificación |
|---|---|---|
| SQLModel sobre SQLAlchemy puro | SQLAlchemy Core | SQLModel unifica ORM model y Pydantic schema en una sola clase, eliminando duplicación. Compatible con Pydantic v2. |
| `asyncpg` como driver | `psycopg2` / `psycopg3` | Driver nativo async de alto rendimiento; requerido por `create_async_engine`. |
| Alembic con `--autogenerate` | Migraciones manuales | Detecta automáticamente cambios en los modelos ORM y genera scripts versionados. |
| UUID como PK | Integer autoincrement | Evita colisiones en entornos distribuidos y no expone secuencias internas. |
| `AuditLog` solo-inserción a nivel repositorio | Triggers de DB | Mantiene la lógica de auditoría en Python (testeable, portable, sin dependencia de extensiones PG). |
| Pool 5–20 conexiones | Pool fijo | Permite escalar bajo carga sin agotar conexiones disponibles en PostgreSQL. |

---

## Arquitectura

### Diagrama de capas

```mermaid
graph TD
    subgraph API["Capa API (FastAPI)"]
        EP[Endpoints / Routers]
        DEP[Dependencias: get_session]
    end

    subgraph APP["Capa Aplicación"]
        SVC[Services: AuthService, MLService, ConsentService]
        UC[Use Cases]
    end

    subgraph DOMAIN["Capa Dominio"]
        ENT[Entidades: User, Course, Enrollment...]
        REPO_IF[Interfaces de Repositorio]
        ENUM[Enums: RoleEnum, OperationEnum]
    end

    subgraph INFRA["Capa Infraestructura"]
        REPO_IMPL[Repositorios: UserRepository, CourseRepository...]
        ORM[Modelos ORM SQLModel]
        DB[Database Engine + Session Factory]
        ALEMBIC[Alembic Migrations]
    end

    EP --> DEP
    DEP --> SVC
    SVC --> REPO_IF
    REPO_IF --> REPO_IMPL
    REPO_IMPL --> ORM
    ORM --> DB
    DB --> PG[(PostgreSQL 16)]
    ALEMBIC --> PG
```

### Flujo de una petición típica

```mermaid
sequenceDiagram
    participant Client
    participant Router as FastAPI Router
    participant Service as ApplicationService
    participant Repo as Repository
    participant DB as PostgreSQL

    Client->>Router: HTTP Request
    Router->>Router: Validar JWT / sesión
    Router->>Service: Llamar use case (session inyectada)
    Service->>Repo: Operación de datos
    Repo->>DB: SQL async (asyncpg)
    DB-->>Repo: Resultado
    Repo->>Repo: Registrar AuditLog (misma sesión)
    Repo-->>Service: Entidad de dominio
    Service-->>Router: DTO de respuesta
    Router-->>Client: HTTP Response
```

### Flujo de autenticación dual

```mermaid
flowchart TD
    LOGIN[POST /auth/login] --> TIPO{¿Tipo de auth?}

    TIPO -->|SSO Microsoft| MS[Microsoft Entra ID\nOIDC callback]
    TIPO -->|SSO Google| GG[Google OAuth2\ncallback]
    TIPO -->|Local| LOCAL[Verificar email +\nbcrypt password_hash]

    MS --> OID_MS[Extraer microsoft_oid\ndel id_token]
    GG --> OID_GG[Extraer google_oid\ndel id_token]
    LOCAL --> HASH[bcrypt.checkpw\npassword vs hash]

    OID_MS --> UPSERT[UserRepository.get_by_microsoft_oid\n→ crear si no existe]
    OID_GG --> UPSERT2[UserRepository.get_by_google_oid\n→ crear si no existe]
    HASH --> GET[UserRepository.get_by_email]

    UPSERT --> JWT[Emitir JWT interno]
    UPSERT2 --> JWT
    GET --> JWT

    JWT --> RESP[HTTP 200 + access_token]
```

---

## Componentes e Interfaces

### Estructura de directorios propuesta

```
app/
├── core/
│   ├── config.py              # Settings (ampliado con DB vars)
│   └── security.py            # bcrypt helpers, JWT utils
├── domain/
│   ├── enums.py               # RoleEnum, OperationEnum
│   └── interfaces/
│       ├── user_repository.py
│       ├── course_repository.py
│       ├── audit_log_repository.py
│       └── consent_repository.py
├── infrastructure/
│   ├── database.py            # engine, AsyncSession, get_session
│   ├── models/
│   │   ├── user.py            # ORM: User
│   │   ├── course.py          # ORM: Course
│   │   ├── enrollment.py      # ORM: Enrollment
│   │   ├── professor_course.py
│   │   ├── audit_log.py       # ORM: AuditLog
│   │   └── consent.py         # ORM: Consent
│   └── repositories/
│       ├── user_repository.py
│       ├── course_repository.py
│       ├── audit_log_repository.py
│       └── consent_repository.py
├── application/
│   ├── schemas/               # Pydantic DTOs (entrada/salida API)
│   │   ├── user.py
│   │   ├── course.py
│   │   └── consent.py
│   └── services/
│       ├── auth_service.py
│       ├── ml_service.py      # Ampliado con verificación de consentimiento
│       └── consent_service.py
└── api/
    └── v1/
        └── endpoints/
            ├── auth.py
            ├── users.py
            ├── courses.py
            ├── health.py      # Ampliado con DB check
            └── prediction.py  # Ampliado con consent gate
alembic/
├── env.py
├── script.py.mako
└── versions/
    └── 0001_initial_schema.py
```

### Interfaces de repositorio (Dominio)

```python
# app/domain/interfaces/user_repository.py
from abc import ABC, abstractmethod
from uuid import UUID
from app.domain.enums import RoleEnum

class IUserRepository(ABC):
    @abstractmethod
    async def create(self, user: UserCreate) -> User: ...
    @abstractmethod
    async def get_by_id(self, id: UUID) -> User | None: ...
    @abstractmethod
    async def get_by_email(self, email: str) -> User | None: ...
    @abstractmethod
    async def get_by_microsoft_oid(self, oid: str) -> User | None: ...
    @abstractmethod
    async def get_by_google_oid(self, oid: str) -> User | None: ...
    @abstractmethod
    async def list(self, role: RoleEnum | None, professor_id: UUID | None,
                   skip: int, limit: int) -> list[User]: ...
    @abstractmethod
    async def update(self, id: UUID, data: UserUpdate) -> User | None: ...
```

### Módulo de base de datos (`infrastructure/database.py`)

```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_MIN,       # default 5
    max_overflow=settings.DB_POOL_MAX - settings.DB_POOL_MIN,  # default 15
    echo=settings.DB_ECHO,                # False en producción
)

AsyncSessionFactory = async_sessionmaker(engine, expire_on_commit=False)

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

---

## Modelos de Datos

### Diagrama ERD

```mermaid
erDiagram
    USER {
        uuid id PK
        string email UK
        string full_name
        string role
        string microsoft_oid UK
        string google_oid UK
        string password_hash
        bool ml_consent
        datetime created_at
        datetime updated_at
    }

    COURSE {
        uuid id PK
        string code UK
        string name
        int credits
        string academic_period
        datetime created_at
    }

    ENROLLMENT {
        uuid id PK
        uuid student_id FK
        uuid course_id FK
        datetime enrollment_date
    }

    PROFESSOR_COURSE {
        uuid id PK
        uuid professor_id FK
        uuid course_id FK
    }

    AUDIT_LOG {
        uuid id PK
        string table_name
        string operation
        uuid record_id
        uuid user_id FK
        json previous_data
        json new_data
        datetime timestamp
    }

    CONSENT {
        uuid id PK
        uuid student_id FK UK
        bool accepted
        string terms_version
        datetime accepted_at
    }

    USER ||--o{ ENROLLMENT : "student_id"
    COURSE ||--o{ ENROLLMENT : "course_id"
    USER ||--o{ PROFESSOR_COURSE : "professor_id"
    COURSE ||--o{ PROFESSOR_COURSE : "course_id"
    USER ||--o{ AUDIT_LOG : "user_id"
    USER ||--o| CONSENT : "student_id"
```

### Modelos ORM SQLModel

```python
# app/infrastructure/models/user.py
import uuid
from datetime import datetime, timezone
from sqlmodel import SQLModel, Field
from app.domain.enums import RoleEnum

class User(SQLModel, table=True):
    __tablename__ = "users"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    email: str = Field(unique=True, nullable=False, index=True)
    full_name: str = Field(nullable=False)
    role: RoleEnum = Field(nullable=False)
    microsoft_oid: str | None = Field(default=None, unique=True, nullable=True)
    google_oid: str | None = Field(default=None, unique=True, nullable=True)
    password_hash: str | None = Field(default=None, nullable=True)
    ml_consent: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

```python
# app/infrastructure/models/audit_log.py
import uuid
from datetime import datetime, timezone
from typing import Any
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import JSON
from app.domain.enums import OperationEnum

class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    table_name: str = Field(nullable=False)
    operation: OperationEnum = Field(nullable=False)
    record_id: uuid.UUID = Field(nullable=False)
    user_id: uuid.UUID | None = Field(default=None, foreign_key="users.id", nullable=True)
    previous_data: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    new_data: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        index=True
    )
```

### Enums de dominio

```python
# app/domain/enums.py
from enum import Enum

class RoleEnum(str, Enum):
    STUDENT = "STUDENT"
    PROFESSOR = "PROFESSOR"
    ADMIN = "ADMIN"

class OperationEnum(str, Enum):
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
```

### Estrategia de auditoría atómica

Cada repositorio que realiza escrituras (`UserRepository`, `CourseRepository`, `ConsentRepository`) invoca `AuditLogRepository.register` **dentro de la misma `AsyncSession`** antes del `commit`. Esto garantiza que si la operación principal falla, el log de auditoría también se revierte (atomicidad por transacción).

```mermaid
sequenceDiagram
    participant Repo as UserRepository
    participant AuditRepo as AuditLogRepository
    participant DB as PostgreSQL

    Repo->>DB: INSERT INTO users (...)
    Repo->>AuditRepo: register(AuditLogCreate(...))
    AuditRepo->>DB: INSERT INTO audit_logs (...)
    Note over Repo,DB: Ambos INSERTs en la misma sesión
    Repo->>DB: COMMIT
    DB-->>Repo: OK (ambos registros persistidos)
```

### Variables de entorno nuevas (`.env`)

```dotenv
# Base de datos
DB_USER=mpra_user
DB_PASSWORD=mpra_secret
DB_HOST=localhost
DB_PORT=5432
DB_NAME=mpra_db
# DATABASE_URL se construye automáticamente si no se define:
# postgresql+asyncpg://mpra_user:mpra_secret@localhost:5432/mpra_db

# Pool de conexiones
DB_POOL_MIN=5
DB_POOL_MAX=20
DB_ECHO=false
```

---

## Manejo de Errores

| Escenario | Comportamiento esperado | Código HTTP |
|---|---|---|
| DB no disponible en `/health` | `{"status": "unhealthy", "database": "unreachable"}` | 503 |
| Timeout de verificación DB (> 2s) | `{"database": "timeout"}` | 503 |
| Email duplicado en `UserRepository.create` | `IntegrityError` → `HTTP 409 Conflict` | 409 |
| Inscripción duplicada (`UNIQUE` violation) | `IntegrityError` → `HTTP 409 Conflict` | 409 |
| Estudiante sin consentimiento ML | `HTTP 403 Forbidden` con mensaje específico | 403 |
| Docente accede a estudiante no inscrito | Retorna `None` / lista vacía (sin 403) | 200 |
| Excepción en sesión DB | `rollback()` automático antes de propagar | 500 |
| `AuditLog` UPDATE/DELETE intentado | `NotImplementedError` en repositorio | 405 |

---

## Estrategia de Testing

### Enfoque dual

Se combinan **tests unitarios** (ejemplos concretos y casos borde) con **tests de propiedades** (cobertura exhaustiva mediante entradas generadas aleatoriamente).

**Tests unitarios** — cubren:
- Ejemplos de integración entre repositorios y la sesión de DB (usando una DB de test en memoria o PostgreSQL de test)
- Casos borde: email duplicado, inscripción duplicada, consentimiento inexistente
- Verificación del health check con DB disponible e indisponible

**Tests de propiedades** — cubren:
- Invariantes que deben cumplirse para cualquier entrada válida
- Round trips de serialización/deserialización de modelos
- Comportamiento de filtros de privacidad (RB-04) con datos generados

**Librería PBT elegida:** [`hypothesis`](https://hypothesis.readthedocs.io/) (estándar de facto para Python)

**Configuración mínima:**
```python
from hypothesis import given, settings as h_settings
from hypothesis import strategies as st

@h_settings(max_examples=100)
@given(st.emails())
def test_user_email_roundtrip(email: str):
    ...
```

**Convención de etiquetado:**
Cada test de propiedad incluye un comentario con el formato:
`# Feature: postgresql-database-integration, Property N: <texto de la propiedad>`


---

## Propiedades de Corrección

*Una propiedad es una característica o comportamiento que debe cumplirse en todas las ejecuciones válidas del sistema — esencialmente, un enunciado formal sobre lo que el sistema debe hacer. Las propiedades sirven como puente entre las especificaciones legibles por humanos y las garantías de corrección verificables por máquina.*

---

### Propiedad 1: Construcción automática de DATABASE_URL

*Para cualquier* combinación válida de valores `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` y `DB_NAME`, la `DATABASE_URL` construida automáticamente por `Settings` debe tener el formato `postgresql+asyncpg://{user}:{password}@{host}:{port}/{dbname}` y contener exactamente esos valores.

**Validates: Requirements 2.1, 2.4**

---

### Propiedad 2: Rollback automático ante excepción en sesión

*Para cualquier* operación de escritura que lance una excepción dentro de una `AsyncSession`, el estado de la base de datos debe permanecer idéntico al estado previo a la operación (la transacción debe revertirse completamente).

**Validates: Requirements 3.3**

---

### Propiedad 3: Unicidad de relaciones (Enrollment, ProfessorCourse, Consent)

*Para cualquier* par `(student_id, course_id)`, intentar crear dos registros `Enrollment` con los mismos valores debe resultar en un error de integridad y dejar exactamente un registro en la tabla. Lo mismo aplica para `(professor_id, course_id)` en `ProfessorCourse` y para `student_id` en `Consent`.

**Validates: Requirements 4.3, 4.4, 4.6**

---

### Propiedad 4: AuditLog es de solo inserción

*Para cualquier* registro `AuditLog` existente en la base de datos, invocar cualquier método de actualización o eliminación sobre `AuditLogRepository` debe lanzar un error (`NotImplementedError` o similar) y dejar el registro sin modificaciones.

**Validates: Requirements 4.7, 9.4**

---

### Propiedad 5: Round trip de migraciones (upgrade / downgrade)

*Para cualquier* estado de esquema de base de datos al que se llegue mediante `alembic upgrade head`, aplicar `alembic downgrade -1` seguido de `alembic upgrade head` debe producir un esquema idéntico al estado previo al downgrade.

**Validates: Requirements 5.4**

---

### Propiedad 6: Round trip de repositorios (create → get)

*Para cualquier* entidad válida (`User`, `Course`, `Consent`) creada mediante el método `create` / `register_consent` del repositorio correspondiente, consultarla inmediatamente por su identificador único (`get_by_id`, `get_by_email`, `get_consent`) debe retornar una entidad con los mismos valores que la entidad creada.

**Validates: Requirements 6.1, 6.2, 6.4**

---

### Propiedad 7: Auditoría atómica con contenido correcto

*Para cualquier* operación de escritura (`INSERT`, `UPDATE`, `DELETE`) sobre las tablas auditadas (`users`, `courses`, `enrollments`, `consents`), debe existir exactamente un registro nuevo en `audit_logs` dentro de la misma transacción, con `table_name`, `operation`, `record_id` y `new_data` / `previous_data` que correspondan fielmente a la operación ejecutada.

**Validates: Requirements 6.5, 9.1, 9.2**

---

### Propiedad 8: Filtro de privacidad RB-04

*Para cualquier* docente y cualquier llamada a `UserRepository.list(professor_id=<id>)` o `CourseRepository.listar_estudiantes_inscritos`, todos los usuarios retornados deben tener al menos una `Enrollment` activa en alguna asignatura asignada a ese docente. Ningún estudiante sin inscripción en las asignaturas del docente debe aparecer en los resultados.

**Validates: Requirements 7.1, 7.2, 7.3**

---

### Propiedad 9: Consentimiento ML como prerequisito de predicción

*Para cualquier* estudiante cuyo registro `Consent` tenga `accepted = False` o no exista, invocar el servicio ML debe retornar un error HTTP 403 sin ejecutar la predicción. Solo cuando `Consent.accepted == True` debe permitirse la ejecución del modelo.

**Validates: Requirements 8.2, 8.3**

---

### Propiedad 10: Inmutabilidad del registro de consentimiento

*Para cualquier* registro `Consent` ya persistido, no debe existir ningún método en `ConsentRepository` que permita modificar sus campos directamente. La revocación del consentimiento debe crear un nuevo registro con `accepted = False`, dejando el registro original intacto.

**Validates: Requirements 8.4**

---

### Propiedad 11: Health check reporta estado real de la DB

*Para cualquier* estado de la base de datos (disponible, no disponible, timeout), el endpoint `GET /health` debe retornar un campo `database` cuyo valor refleje fielmente ese estado (`"connected"`, `"unreachable"` o `"timeout"`), con el código HTTP correspondiente (200 o 503).

**Validates: Requirements 10.1, 10.2, 10.3, 10.4**

---

## Estrategia de Testing (detalle)

### Tests unitarios

Se enfocan en ejemplos concretos, casos borde e integración entre componentes:

- Verificar que `Settings` construye `DATABASE_URL` con el formato correcto
- Verificar que `get_session` hace rollback ante excepción (mock de DB)
- Verificar que `AuditLogRepository` no expone métodos `update` ni `delete`
- Verificar que el health check retorna 503 cuando la DB no responde (mock)
- Verificar que la migración inicial crea todas las tablas esperadas (DB de test)
- Casos borde: email duplicado → 409, inscripción duplicada → 409, consentimiento inexistente → 403

### Tests de propiedades (Hypothesis)

Cada propiedad del diseño se implementa como un test de Hypothesis con mínimo 100 ejemplos generados:

```python
# Feature: postgresql-database-integration, Property 1: DATABASE_URL construction
@given(
    user=st.text(min_size=1, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"))),
    password=st.text(min_size=1),
    host=st.just("localhost"),
    port=st.integers(min_value=1024, max_value=65535),
    dbname=st.text(min_size=1, alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")))
)
@h_settings(max_examples=100)
def test_database_url_construction(user, password, host, port, dbname):
    url = build_database_url(user, password, host, port, dbname)
    assert url.startswith("postgresql+asyncpg://")
    assert f"{user}:" in url
    assert f"@{host}:{port}/{dbname}" in url
```

```python
# Feature: postgresql-database-integration, Property 3: Unicidad de relaciones
@given(student_id=st.uuids(), course_id=st.uuids())
@h_settings(max_examples=100)
async def test_enrollment_uniqueness(student_id, course_id):
    # Primer insert debe tener éxito
    # Segundo insert con mismos IDs debe lanzar IntegrityError
    ...
```

```python
# Feature: postgresql-database-integration, Property 6: Repository round trip
@given(email=st.emails(), full_name=st.text(min_size=1, max_size=100))
@h_settings(max_examples=100)
async def test_user_create_get_roundtrip(email, full_name):
    created = await user_repo.create(UserCreate(email=email, full_name=full_name, role=RoleEnum.STUDENT))
    fetched = await user_repo.get_by_id(created.id)
    assert fetched is not None
    assert fetched.email == created.email
    assert fetched.full_name == created.full_name
```

```python
# Feature: postgresql-database-integration, Property 8: Filtro de privacidad RB-04
@given(
    n_students=st.integers(min_value=1, max_value=10),
    n_enrolled=st.integers(min_value=0, max_value=5)
)
@h_settings(max_examples=100)
async def test_professor_only_sees_enrolled_students(n_students, n_enrolled):
    # Crear n_students estudiantes, inscribir n_enrolled en asignatura del docente
    # Verificar que list(professor_id=...) retorna exactamente n_enrolled estudiantes
    ...
```

```python
# Feature: postgresql-database-integration, Property 9: Consent gate para ML
@given(accepted=st.booleans())
@h_settings(max_examples=100)
async def test_ml_consent_gate(accepted):
    # Crear estudiante con Consent.accepted = accepted
    # Si accepted=False → predict debe retornar 403
    # Si accepted=True → predict debe ejecutarse normalmente
    ...
```

### Configuración de pytest

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.hypothesis]
max_examples = 100
deriving = "auto"
```

### Estructura de tests

```
tests/
├── unit/
│   ├── test_config.py          # Settings y DATABASE_URL
│   ├── test_database.py        # get_session, rollback
│   └── test_health.py          # health check con DB mock
├── integration/
│   ├── test_user_repository.py
│   ├── test_course_repository.py
│   ├── test_audit_log_repository.py
│   └── test_consent_repository.py
└── property/
    ├── test_url_construction.py    # Propiedad 1
    ├── test_session_rollback.py    # Propiedad 2
    ├── test_uniqueness.py          # Propiedad 3
    ├── test_audit_immutability.py  # Propiedad 4
    ├── test_migration_roundtrip.py # Propiedad 5
    ├── test_repo_roundtrip.py      # Propiedad 6
    ├── test_audit_atomicity.py     # Propiedad 7
    ├── test_privacy_filter.py      # Propiedad 8
    ├── test_consent_gate.py        # Propiedad 9
    ├── test_consent_immutability.py # Propiedad 10
    └── test_health_check.py        # Propiedad 11
```
