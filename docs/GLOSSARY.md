# Glosario — Academic Risk Predictor Backend

> **Mantenimiento:** Este archivo debe actualizarse cada vez que se agregue o modifique un modelo, endpoint, servicio, enum o concepto de negocio. Ver instrucción en `CLAUDE.md`.

---

## Índice

1. [Arquitectura y Capas](#arquitectura-y-capas)
2. [Entidades del Dominio](#entidades-del-dominio)
3. [Enumeraciones](#enumeraciones)
4. [Schemas / DTOs](#schemas--dtos)
5. [Servicios de Aplicación](#servicios-de-aplicación)
6. [Repositorios e Interfaces](#repositorios-e-interfaces)
7. [Autenticación y Autorización](#autenticación-y-autorización)
8. [Endpoints de la API](#endpoints-de-la-api)
9. [Conceptos Académicos](#conceptos-académicos)
10. [Predicción de Riesgo (ML)](#predicción-de-riesgo-ml)
11. [Privacidad y Consentimiento](#privacidad-y-consentimiento)
12. [Infraestructura y Configuración](#infraestructura-y-configuración)
13. [Terminología del Sistema Educativo Colombiano](#terminología-del-sistema-educativo-colombiano)

---

## Arquitectura y Capas

| Término | Definición |
|---|---|
| **Domain Layer** | Capa de reglas de negocio puras. Contiene enums, excepciones, interfaces de repositorio y value objects. No depende de infraestructura. |
| **Application Layer** | Capa de orquestación. Contiene services y schemas (DTOs). Coordina dominio e infraestructura. |
| **Infrastructure Layer** | Capa de persistencia y detalles técnicos. Contiene modelos SQLModel, repositorios concretos, proveedor de auth y configuración de base de datos. |
| **API Layer** | Capa de presentación. Endpoints FastAPI, dependencias de auth y routers. Ubicada en `app/api/v1/`. |
| **Repository Pattern** | Patrón que abstrae el acceso a datos. Las interfaces (`IXRepository`) viven en el dominio; las implementaciones concretas, en infraestructura. |
| **Dependency Injection** | FastAPI resuelve dependencias (session, servicios, usuario actual) mediante `Depends()`. |
| **SQLModel** | ORM/schema unificado usado para definir tanto tablas de BD como validación Pydantic. |
| **AsyncSession** | Sesión de SQLAlchemy en modo asíncrono (`asyncpg`). Se inyecta mediante `get_session()`. |
| **Alembic** | Herramienta de migraciones de BD. Las versiones están en `alembic/versions/`. |

---

## Entidades del Dominio

### `User`
Representa cualquier usuario del sistema (estudiante, profesor, administrador).

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | UUID (PK) | Identificador único |
| `email` | str (unique) | Correo de acceso al sistema |
| `institutional_email` | str \| None (unique) | Correo institucional (ej: `PIPE@TAU.USBMED.EDU.CO`) |
| `full_name` | str | Nombre completo |
| `role` | `RoleEnum` | Rol del usuario |
| `microsoft_oid` | str \| None | OID de Microsoft para SSO |
| `google_oid` | str \| None | OID de Google para SSO |
| `password_hash` | str \| None | Hash bcrypt de la contraseña |
| `ml_consent` | bool | Si el usuario aceptó el uso de ML |
| `status` | `UserStatusEnum` | Estado de la cuenta |
| `created_at` | datetime | Fecha de creación |
| `updated_at` | datetime | Última actualización |

### `StudentProfile`
Perfil académico extendido, solo para usuarios con rol `STUDENT`.

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | UUID (PK) | Identificador único |
| `user_id` | UUID (FK→User) | Relación 1:1 con User |
| `student_institutional_id` | str (unique) | ID institucional del estudiante (ej: `30000032391`) |
| `document_type` | str | Tipo de documento (`CC`, `TI`, `CE`, `PP`) |
| `document_number` | str | Número de documento |
| `birth_date` | date \| None | Fecha de nacimiento |
| `gender` | str \| None | Género (`M` / `F`) |
| `phone` | str \| None | Teléfono de contacto |
| `socioeconomic_stratum` | int \| None | Estrato socioeconómico (1–6) |
| `academic_cycle` | int \| None | Ciclo lectivo |
| `academic_year` | int \| None | Año académico |
| `semester` | int \| None | Semestre actual |
| `program_action` | str \| None | Código de acción del programa (ej: `RLOA`) |
| `enrollment_status` | str \| None | Estado de matrícula (ej: `AC` = activo) |
| `enrolled_credits` | Decimal \| None | Créditos matriculados |
| `other_credits` | Decimal \| None | Créditos en otros cursos |
| `academic_level` | int \| None | Nivel académico |
| `cohort` | str \| None | Cohorte de ingreso (ej: `2023-I`) |
| `action_reason` | str \| None | Motivo de la acción del programa |
| `program_id` | UUID \| None (FK→Program) | Programa al que pertenece |

### `Program`
Programa académico de la institución (ej: Ingeniería de Sistemas).

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | UUID (PK) | Identificador único |
| `institution` | str | Código de institución (ej: `USBCO`) |
| `degree_type` | str | Tipo de título (ej: `PREG` = pregrado) |
| `program_code` | str (unique) | Código interno del programa (ej: `M0200`) |
| `program_name` | str | Nombre completo del programa |
| `location` | str | Sede (ej: `SAN BENITO`) |
| `snies_code` | int (unique) | Código SNIES del Ministerio de Educación |
| `created_at` | datetime | Fecha de creación |

### `Subject`
Definición de una materia (curso como concepto académico, independiente del período).

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | UUID (PK) | Identificador único |
| `code` | str | Código de la materia (ej: `MAT-101`). Único **por programa** (`unique(code, program_id)`). El mismo código puede existir en distintos programas. |
| `name` | str | Nombre de la materia |
| `credits` | int | Número de créditos académicos (puede diferir entre programas para la misma materia) |
| `program_id` | UUID (FK→Program) | Programa al que pertenece |
| `status` | `CourseStatusEnum` | Estado de la materia |
| `created_at` | datetime | Fecha de creación |
| — | Constraint | `uq_subject_code_program`: único en `(code, program_id)` |

### `Course`
Oferta concreta de una `Subject` en un período y grupo específicos (sección).

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | UUID (PK) | Identificador único |
| `subject_id` | UUID (FK→Subject) | Materia que se ofrece |
| `section` | str | Identificador de grupo/sección (ej: `A`, `B`, `1`) |
| `academic_period` | str | Período académico (ej: `2025-I`) |
| `professor_id` | UUID \| None (FK→User) | Profesor asignado |
| `status` | `CourseStatusEnum` | Estado de la oferta |
| `created_at` | datetime | Fecha de creación |
| — | Constraint | Único: `(subject_id, section, academic_period)` |

### `Enrollment`
Matrícula de un estudiante en un `Course`. Contiene notas.

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | UUID (PK) | Identificador único |
| `student_id` | UUID (FK→User) | Estudiante matriculado |
| `course_id` | UUID (FK→Course) | Curso en el que está matriculado |
| `status` | `EnrollmentStatusEnum` | Estado de la matrícula |
| `enrollment_date` | datetime | Fecha de matrícula |
| `updated_at` | datetime | Última actualización |
| `grades` | JSONB \| None | Notas detalladas por corte (ver estructura abajo) |
| `first_cohort_grade` | Decimal(3,2) \| None | Nota del primer corte |
| `second_cohort_grade` | Decimal(3,2) \| None | Nota del segundo corte |
| `third_cohort_grade` | Decimal(3,2) \| None | Nota del tercer corte |
| `final_grade` | Decimal(3,2) \| None | Nota definitiva |
| — | Constraint | Único: `(student_id, course_id)` |

**Estructura del campo `grades` (JSONB):**
```json
{
  "first_cohort": {
    "weight": "30%",
    "parcial": { "note": 4.0, "weight": "20%" },
    "seguimiento": {
      "act1": { "note": 3.5, "weight": "10%" },
      "act2": { "note": 3.2, "weight": "10%" }
    }
  },
  "second_cohort": { "..." },
  "third_cohort": { "..." }
}
```

### `Consent`
Registro del consentimiento informado del estudiante para uso de ML.

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | UUID (PK) | Identificador único |
| `student_id` | UUID (FK→User, unique) | Estudiante que dio el consentimiento |
| `accepted` | bool | Si aceptó o rechazó |
| `terms_version` | str | Versión del documento de términos aceptado |
| `accepted_at` | datetime | Momento del consentimiento |

### `AuditLog`
Registro de auditoría de operaciones sobre cualquier tabla.

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | UUID (PK) | Identificador único |
| `table_name` | str | Tabla afectada |
| `operation` | `OperationEnum` | Tipo de operación |
| `record_id` | UUID | ID del registro afectado |
| `user_id` | UUID \| None (FK→User) | Usuario que realizó la operación |
| `previous_data` | JSON \| None | Estado anterior del registro |
| `new_data` | JSON \| None | Estado nuevo del registro |
| `timestamp` | datetime (indexed) | Momento de la operación |

---

## Enumeraciones

| Enum | Valores | Descripción |
|---|---|---|
| `RoleEnum` | `STUDENT`, `PROFESSOR`, `ADMIN` | Rol del usuario en el sistema |
| `UserStatusEnum` | `ACTIVE`, `INACTIVE` | Estado de la cuenta de usuario |
| `CourseStatusEnum` | `ACTIVE`, `INACTIVE` | Estado de una materia o sección de curso |
| `EnrollmentStatusEnum` | `PENDING`, `ACTIVE`, `COMPLETED`, `CANCELLED` | Ciclo de vida de una matrícula |
| `OperationEnum` | `INSERT`, `UPDATE`, `DELETE` | Tipo de operación en el log de auditoría |

---

## Schemas / DTOs

Los schemas Pydantic viven en `app/application/schemas/`. Son los contratos de entrada/salida de la API.

### Autenticación (`auth.py`)

| Schema | Campos | Uso |
|---|---|---|
| `LoginRequest` | `email`, `password` | Cuerpo del POST `/auth/login` |
| `RefreshRequest` | `refresh_token` | Cuerpo del POST `/auth/refresh` |
| `TokenResponse` | `access_token`, `refresh_token`, `token_type`, `expires_in` | Respuesta de login/refresh |
| `LogoutResponse` | `message` | Respuesta de logout |

### Usuarios (`user.py`)

| Schema | Campos | Uso |
|---|---|---|
| `UserCreate` | `email`, `full_name`, `role`, `microsoft_oid?`, `google_oid?`, `password?`, `ml_consent?`, `institutional_email?` | Crear usuario |
| `UserUpdate` | Todos opcionales de `UserCreate` | Actualizar usuario |
| `UserRead` | `id`, `email`, `institutional_email?`, `full_name`, `role`, `status`, `ml_consent`, `created_at`, `updated_at` | Leer usuario |
| `UserStatusUpdate` | `status: UserStatusEnum` | Cambiar estado de cuenta |
| `PaginatedResponse[T]` | `data`, `total`, `skip`, `limit` | Respuesta paginada genérica |

### Programas (`program.py`)

| Schema | Campos clave | Uso |
|---|---|---|
| `ProgramCreate` | `institution`, `degree_type`, `program_code`, `program_name`, `location`, `snies_code` | Crear programa |
| `ProgramUpdate` | Todos opcionales | Actualizar programa |
| `ProgramRead` | Todos los campos + `id`, `created_at` | Leer programa |

### Materias (`subject.py`)

| Schema | Campos clave | Uso |
|---|---|---|
| `SubjectCreate` | `code`, `name`, `credits`, `program_id` | Crear materia |
| `SubjectUpdate` | `code?`, `name?`, `credits?` | Actualizar materia |
| `SubjectStatusUpdate` | `status: CourseStatusEnum` | Cambiar estado |
| `SubjectRead` | Todos los campos + `id`, `created_at` | Leer materia |
| `SubjectBulkUploadResponse` | `total_rows`, `created`, `failed`, `results` | Resultado de carga masiva por CSV |
| `SubjectBulkRowResult` | `row`, `code`, `status`, `detail`, `subject?` | Resultado por fila en carga masiva |

### Cursos / Secciones (`course.py`)

| Schema | Campos clave | Uso |
|---|---|---|
| `CourseCreate` | `subject_id`, `section`, `academic_period`, `professor_id?` | Crear sección |
| `CourseUpdate` | `section?`, `academic_period?`, `professor_id?` | Actualizar sección |
| `CourseStatusUpdate` | `status: CourseStatusEnum` | Cambiar estado |
| `CourseRead` | Campos del Course + campos desnormalizados de Subject (`code`, `name`, `credits`, `program_id`) | Leer sección |

### Matrículas y Notas (`enrollment.py`)

| Schema | Campos clave | Uso |
|---|---|---|
| `EnrollmentCreate` | `student_id`, `course_id` | Matricular estudiante |
| `EnrollmentUpdate` | `course_id` | Cambiar curso |
| `EnrollmentStatusUpdate` | `status: EnrollmentStatusEnum` | Cambiar estado |
| `EnrollmentRead` | `id`, `student_id`, `course_id`, `status`, `enrollment_date`, `updated_at` | Leer matrícula |
| `GradesRead` | `id`, `student_id`, `course_id`, `grades`, `first_cohort_grade`, `second_cohort_grade`, `third_cohort_grade`, `final_grade` | Leer notas |
| `GradesUpdate` | `grades: dict` | Registrar/actualizar notas |
| `RiskFromEnrollmentRequest` | `promedio_asistencia`, `inicios_sesion_plataforma`, `uso_tutorias` | Predicción desde contexto de matrícula |

### Estudiante / Predicción (`student.py`)

| Schema | Campos | Uso |
|---|---|---|
| `StudentInput` | `promedio_asistencia` (0–100), `promedio_seguimiento` (0–5), `nota_parcial_1` (0–5), `inicios_sesion_plataforma` (≥0), `uso_tutorias` (0–10) | Entrada del modelo ML |
| `PredictionOutput` | `probabilidad_riesgo`, `porcentaje_riesgo`, `nivel_riesgo`, `analisis_ia`, `datos_radar`, `detalles_matematicos` | Salida de predicción |
| `ChatInput` | `pregunta`, `datos_estudiante`, `prediccion_actual?` | Pregunta al asistente IA |
| `ChatOutput` | `respuesta` | Respuesta del asistente IA |

### Consentimiento (`consent.py`)

| Schema | Campos | Uso |
|---|---|---|
| `ConsentRead` | `id`, `student_id`, `accepted`, `terms_version`, `accepted_at` | Leer registro de consentimiento |

### Auditoría (`audit_log.py`)

| Schema | Campos | Uso |
|---|---|---|
| `AuditLogCreate` | `table_name`, `operation`, `record_id`, `user_id?`, `previous_data?`, `new_data?` | Registrar evento |

### Asignación Profesor-Curso (`professor_course.py`)

| Schema | Campos | Uso |
|---|---|---|
| `ProfessorAssign` | `professor_id: UUID` | Asignar profesor a un curso |
| `ProfessorAssignmentRead` | `id`, `professor_id`, `course_id` | Leer asignación |

---

## Servicios de Aplicación

Ubicados en `app/application/services/`. Orquestan lógica de negocio, no acceden directamente a la BD.

| Servicio | Responsabilidad principal |
|---|---|
| `AuthService` | Login con credenciales, refresh de tokens |
| `UserService` | CRUD de usuarios con paginación y filtros |
| `TokenService` | Crear y decodificar JWT (access + refresh) |
| `CourseService` | CRUD de secciones de cursos |
| `EnrollmentService` | Matricular/desmatricular estudiantes; lógica de reactivación |
| `GradeService` | Leer y registrar notas; cálculo por corte y final |
| `ProgramService` | CRUD de programas académicos con cascada |
| `SubjectService` | CRUD de materias; carga masiva por CSV |
| `ConsentService` | Verificar consentimiento de ML (lanza 403 si no hay) |
| `MLApplicationService` | Puerta de entrada al ML: verifica consentimiento y delega a `AcademicRiskService` |
| `ProfessorCourseService` | Asignar profesores; listar estudiantes del profesor (RB-04) |
| `AcademicRiskService` | Lógica ML pura: carga modelo, escala features, predice, genera análisis IA |

---

## Repositorios e Interfaces

Las interfaces viven en `app/domain/interfaces/`; las implementaciones en `app/infrastructure/repositories/`.

| Interfaz | Métodos clave |
|---|---|
| `IUserRepository` | `create`, `get_by_id`, `get_by_email`, `get_by_microsoft_oid`, `list`, `count`, `update`, `update_status` |
| `IEnrollmentRepository` | `create`, `get_by_id`, `get_by_student_and_course`, `update_course`, `update_status`, `list_by_student`, `update_grades` |
| `ICourseRepository` | `create`, `get_by_id`, `list_by_subject`, `list_by_professor`, `list_by_program`, `list_all`, `update`, `update_status`, `list_enrolled_students` |
| `IProgramRepository` | `get_by_id`, `list_all`, `create`, `update`, `get_by_program_code`, `get_by_snies_code`, `delete` |
| `ISubjectRepository` | `create`, `get_by_id`, `get_by_code(code, program_id)`, `list_by_program`, `list_all`, `update`, `update_status` |
| `IConsentRepository` | `register_consent`, `get_consent` |
| `IAuditLogRepository` | `register` |
| `IAuthProvider` | `authenticate(**kwargs)` → `User` |

---

## Autenticación y Autorización

### Tokens JWT

| Concepto | Descripción |
|---|---|
| **Access Token** | Token de corta duración (30 min por defecto). Se envía en el header `Authorization: Bearer <token>`. |
| **Refresh Token** | Token de larga duración (7 días por defecto). Permite obtener un nuevo access token sin re-autenticarse. |
| **Token Claims** | `sub` (user_id), `role`, `type` (`access`\|`refresh`), `exp`, `iat` |
| **JWT_SECRET_KEY** | Clave secreta para firmar tokens. Requerida en variables de entorno. |
| **JWT_ALGORITHM** | Algoritmo de firma. Por defecto: `HS256`. |

### Control de Acceso (RBAC)

| Función | Descripción |
|---|---|
| `require_roles(*roles)` | Guard de endpoint: permite solo los roles indicados |
| `require_self_or_roles(*roles)` | Permite acceso propio o si tiene alguno de los roles |
| `require_student_self_or_roles(*roles)` | Estudiante ve sus propios datos; ADMIN y PROFESSOR ven con restricciones |
| **RB-04** | Regla de negocio: un PROFESSOR solo puede ver estudiantes y matrículas de sus propios cursos asignados |

### Roles y Permisos

| Rol | Permisos |
|---|---|
| `STUDENT` | Ver sus matrículas y notas; dar consentimiento ML |
| `PROFESSOR` | Crear cursos, registrar notas, ver estudiantes de sus cursos (RB-04) |
| `ADMIN` | CRUD completo sobre todas las entidades; gestión de usuarios y programas; auditoría |

### Excepciones de Auth

| Excepción | HTTP Status | Descripción |
|---|---|---|
| `AuthenticationError` | 401 | Credenciales inválidas |
| `TokenExpiredError` | 401 | Token expirado |
| `InvalidTokenError` | 401 | Token malformado o inválido |
| `AuthorizationError` | 403 | Sin permisos para la operación |

---

## Endpoints de la API

Base path: `/api/v1`

### Autenticación (`/auth`)

| Método | Path | Auth | Descripción |
|---|---|---|---|
| POST | `/auth/login` | Pública | Login con email y contraseña |
| POST | `/auth/refresh` | Pública | Renovar access token |
| POST | `/auth/logout` | JWT | Cerrar sesión |

### Usuarios (`/users`)

| Método | Path | Roles | Descripción |
|---|---|---|---|
| GET | `/users` | ADMIN, PROFESSOR | Listar con paginación y filtros |
| POST | `/users` | ADMIN | Crear usuario |
| GET | `/users/{user_id}` | ADMIN, self, PROFESSOR (RB-04) | Obtener por ID |
| PATCH | `/users/{user_id}` | ADMIN | Actualizar datos |
| PATCH | `/users/{user_id}/status` | ADMIN | Cambiar estado de cuenta |

### Programas (`/programs`)

| Método | Path | Roles | Descripción |
|---|---|---|---|
| GET | `/programs` | Autenticado | Listar programas |
| POST | `/programs` | ADMIN | Crear programa |
| GET | `/programs/{program_id}` | Autenticado | Obtener por ID |
| PATCH | `/programs/{program_id}` | ADMIN | Actualizar |
| DELETE | `/programs/{program_id}` | ADMIN | Eliminar (con cascada) |
| GET | `/programs/{program_id}/subjects` | Autenticado | Materias del programa |
| GET | `/programs/{program_id}/courses` | Autenticado | Cursos del programa |

### Materias (`/subjects`)

| Método | Path | Roles | Descripción |
|---|---|---|---|
| GET | `/subjects` | Autenticado | Listar con paginación |
| POST | `/subjects` | ADMIN | Crear materia |
| GET | `/subjects/{subject_id}` | Autenticado | Obtener por ID |
| PATCH | `/subjects/{subject_id}` | ADMIN | Actualizar |
| PATCH | `/subjects/{subject_id}/status` | ADMIN | Cambiar estado |
| POST | `/subjects/bulk-create` | ADMIN | Carga masiva desde CSV |

### Cursos / Secciones (`/courses`)

| Método | Path | Roles | Descripción |
|---|---|---|---|
| GET | `/courses` | Autenticado | Listar con paginación |
| POST | `/courses` | ADMIN | Crear sección |
| GET | `/courses/{course_id}` | Autenticado | Obtener por ID |
| PATCH | `/courses/{course_id}` | ADMIN | Actualizar |
| PATCH | `/courses/{course_id}/status` | ADMIN | Cambiar estado |
| POST | `/courses/{course_id}/professor` | ADMIN | Asignar profesor |
| GET | `/courses/{course_id}/students` | ADMIN, PROFESSOR | Listar estudiantes matriculados |

### Matrículas (`/enrollments`)

| Método | Path | Roles | Descripción |
|---|---|---|---|
| POST | `/enrollments` | ADMIN | Matricular estudiante |
| GET | `/enrollments/{enrollment_id}` | ADMIN, PROFESSOR, STUDENT(self) | Obtener matrícula |
| PATCH | `/enrollments/{enrollment_id}/course` | ADMIN | Cambiar curso |
| PATCH | `/enrollments/{enrollment_id}/status` | ADMIN | Cambiar estado |
| GET | `/enrollments/{enrollment_id}/grades` | ADMIN, PROFESSOR, STUDENT(self) | Ver notas |
| POST | `/enrollments/{enrollment_id}/grades` | ADMIN, PROFESSOR | Registrar notas |
| GET | `/enrollments?student_id={id}` | ADMIN, PROFESSOR, STUDENT(self) | Matrículas por estudiante |

### Predicción de Riesgo (`/predict`)

| Método | Path | Auth | Descripción |
|---|---|---|---|
| POST | `/predict` | Opcional (JWT) | Predecir riesgo académico. Si se pasa `student_id`, verifica consentimiento ML. |

### Health Check

| Método | Path | Auth | Descripción |
|---|---|---|---|
| GET | `/health` | Pública | Estado del servicio |

---

## Conceptos Académicos

| Término | Definición |
|---|---|
| **Program** | Programa de grado (ej: Ingeniería de Sistemas). Entidad raíz del catálogo académico. |
| **Subject** | Materia o asignatura definida: tiene código, nombre y créditos. Es el "qué se enseña". |
| **Course / Section** | Oferta concreta de una materia en un período + grupo + profesor. Es el "cuándo y quién". |
| **Enrollment** | Matrícula de un estudiante en un curso. Contiene estado y notas. |
| **Academic Period** | Identificador del semestre (ej: `2025-I`, `2025-II`). |
| **Section** | Letra o número que distingue grupos paralelos de la misma materia en el mismo período (ej: `A`, `B`, `1`). |
| **Credit** | Unidad de peso académico de una materia. |
| **Grade Scale** | Escala de 0.0 a 5.0. La nota mínima aprobatoria es **3.0**. |
| **Cohort (corte)** | Período de evaluación: `first_cohort`, `second_cohort`, `third_cohort`. Cada uno tiene peso porcentual. |
| **Parcial** | Examen principal de un corte. Campo `grades.first_cohort.parcial`. |
| **Seguimiento** | Actividades de seguimiento (tareas, quizzes) dentro de un corte. Campo `grades.first_cohort.seguimiento`. |
| **Weight** | Porcentaje que pondera la nota de un componente sobre el total del corte o del curso. |
| **SNIES** | Sistema Nacional de Información de la Educación Superior. El `snies_code` es el código oficial del programa ante el Ministerio de Educación de Colombia. |

---

## Predicción de Riesgo (ML)

### Features de entrada

| Variable | Rango | Descripción |
|---|---|---|
| `promedio_asistencia` | 0–100 | Porcentaje de asistencia a clases |
| `promedio_seguimiento` | 0–5 | Promedio de actividades de seguimiento |
| `nota_parcial_1` | 0–5 | Nota del primer examen parcial |
| `inicios_sesion_plataforma` | ≥0 | Número de inicios de sesión en el LMS |
| `uso_tutorias` | 0–10 | Número de tutorías utilizadas |

### Salida del modelo

| Campo | Tipo | Descripción |
|---|---|---|
| `probabilidad_riesgo` | float (0–1) | Probabilidad de riesgo calculada por el modelo |
| `porcentaje_riesgo` | float (0–100) | Misma probabilidad en escala porcentual |
| `nivel_riesgo` | `ALTO` \| `MEDIO` \| `BAJO` | Clasificación según umbrales configurables |
| `analisis_ia` | str | Análisis narrativo generado por IA |
| `datos_radar` | dict | Datos para gráfico radar (comparación con estudiantes aprobados) |
| `detalles_matematicos` | dict | Detalles del cálculo (pesos de features, probabilidad logística) |

### Umbrales de riesgo (configurables en `.env`)

| Nivel | Condición | Default |
|---|---|---|
| `ALTO` | `probabilidad_riesgo >= UMBRAL_RIESGO_ALTO` | ≥ 0.70 |
| `MEDIO` | `UMBRAL_RIESGO_MEDIO <= probabilidad_riesgo < UMBRAL_RIESGO_ALTO` | 0.40–0.70 |
| `BAJO` | `probabilidad_riesgo < UMBRAL_RIESGO_MEDIO` | < 0.40 |

### Modelo ML

| Concepto | Detalle |
|---|---|
| **Algoritmo** | Regresión Logística (`LogisticRegression` de scikit-learn) |
| **Scaler** | `StandardScaler` — estandariza features antes de la predicción |
| **Archivo modelo** | `ml_models/modelo_logistico.joblib` |
| **Archivo scaler** | `ml_models/scaler.joblib` |
| **Dataset de entrenamiento** | `datasets/dataset_estudiantes_decimal.csv` |
| **Carga** | Singleton — se carga una vez al iniciar el servicio |
| **Fallback** | Si no existe el `.joblib`, entrena desde el CSV |

---

## Privacidad y Consentimiento

| Término | Descripción |
|---|---|
| **ML Consent** | Permiso explícito del estudiante para que sus datos sean usados en predicciones de riesgo. Se registra en `Consent` y también como flag en `User.ml_consent`. |
| **Terms Version** | Versión del documento de términos aceptado. Permite rastrear si el estudiante necesita re-aceptar términos actualizados. |
| **Consent Gate** | Lógica en `ConsentService.verify_ml_consent()` que bloquea (403) cualquier predicción para un estudiante que no haya dado consentimiento. |
| **Privacy by Design** | Las predicciones ML solo se ejecutan si hay consentimiento explícito y registrado. |

---

## Infraestructura y Configuración

### Variables de entorno clave

| Variable | Descripción | Default |
|---|---|---|
| `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME` | Conexión a PostgreSQL | — |
| `JWT_SECRET_KEY` | Clave para firmar JWT. **Requerida.** | — |
| `JWT_ALGORITHM` | Algoritmo JWT | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Duración del access token | `30` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Duración del refresh token | `7` |
| `MODEL_PATH` | Ruta del modelo ML | `ml_models/modelo_logistico.joblib` |
| `SCALER_PATH` | Ruta del scaler | `ml_models/scaler.joblib` |
| `DATASET_PATH` | Ruta del dataset de entrenamiento | `datasets/dataset_estudiantes_decimal.csv` |
| `UMBRAL_RIESGO_ALTO` | Umbral de riesgo alto | `0.7` |
| `UMBRAL_RIESGO_MEDIO` | Umbral de riesgo medio | `0.4` |
| `CORS_ORIGINS` | Orígenes permitidos en CORS | — |

### Stack tecnológico

| Componente | Tecnología |
|---|---|
| **Framework web** | FastAPI |
| **ORM** | SQLModel + SQLAlchemy (async) |
| **Base de datos** | PostgreSQL (driver: `asyncpg`) |
| **Migraciones** | Alembic |
| **ML** | scikit-learn (`LogisticRegression`, `StandardScaler`) |
| **Serialización** | Pydantic v2 |
| **Auth** | JWT (`python-jose`) + bcrypt |
| **Contenedores** | Docker + Docker Compose |
| **CI/CD** | GitHub Actions + Azure Container Apps |

---

## Terminología del Sistema Educativo Colombiano

Campos heredados del dataset institucional. Se usan principalmente en `StudentProfile`.

| Término / Campo | Significado |
|---|---|
| `ID_Estud` | Identificador institucional del estudiante |
| `Tp_Doc_ID` | Tipo de documento de identidad (`CC`=Cédula Ciudadanía, `TI`=Tarjeta Identidad, `CE`=Cédula Extranjería, `PP`=Pasaporte) |
| `Estrato_SocEcon` | Estrato socioeconómico (1 más bajo, 6 más alto). Usado en Colombia para clasificación social y subsidios. |
| `Ciclo_Lvo` | Ciclo lectivo / académico |
| `Año_Acad` | Año académico |
| `Acc_Prog` | Acción sobre el programa (ej: `RLOA` = renovación de matrícula) |
| `Estado` (`AC`) | Estado de matrícula activa |
| `Cred_Matric` | Créditos matriculados en el período |
| `Cred_Otro_Curso` | Créditos en otros cursos fuera del programa principal |
| `Nivel` | Nivel académico dentro de la carrera |
| `Cohorte` | Período de primera matrícula del estudiante (ej: `2023-I`) |
| `Mvo_Acción` | Motivo de la acción sobre el programa |
| `PREG` | Pregrado (tipo de título) |
| `USBCO` | Código de la institución (Universidad de San Buenaventura Colombia) |
| `SNIES` | Sistema Nacional de Información de la Educación Superior — identificador oficial del MEN |
| `LMS` | Learning Management System — plataforma digital de gestión del aprendizaje |
