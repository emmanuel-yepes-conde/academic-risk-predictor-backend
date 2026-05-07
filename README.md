# Academic Risk Predictor — Backend

API REST construida con **FastAPI + Python 3.13** que expone predicción de riesgo académico con ML, gestión de usuarios, cursos, programas universitarios y notificaciones por correo electrónico.

---

## Requisitos previos

| Herramienta | Versión mínima | Notas |
|---|---|---|
| Python | 3.13 | Usar pyenv si hay conflictos de versión |
| Docker Desktop | cualquiera | Para levantar PostgreSQL |
| Git | cualquiera | |

---

## 1. Clonar el proyecto

```bash
git clone <repository-url>
cd academic-risk-predictor-backend
```

---

## 2. Configurar variables de entorno

```bash
cp env.example .env
```

Edita `.env` con los siguientes valores. **Solo cambia lo marcado con ⚠️** si ejecutas en local:

```env
# Servidor
HOST=0.0.0.0
PORT=8001                          # ⚠️ El frontend espera puerto 8001

# Base de datos — Docker (no cambiar si usas docker-compose)
POSTGRES_USER=mpra_user
POSTGRES_PASSWORD=mpra_password
POSTGRES_DB=mpra_db

# Conexión desde la app al contenedor
DB_USER=mpra_user
DB_PASSWORD=mpra_password
DB_HOST=localhost
DB_PORT=5433                       # ⚠️ Puerto externo del contenedor (ver docker-compose)
DB_NAME=mpra_db
DB_POOL_MIN=5
DB_POOL_MAX=20
DB_ECHO=false

# JWT — ⚠️ Generar uno nuevo con: python3 -c "import secrets; print(secrets.token_urlsafe(32))"
JWT_SECRET_KEY=REEMPLAZAR_CON_CLAVE_SEGURA
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# ML
MODEL_PATH=ml_models/modelo_logistico.joblib
SCALER_PATH=ml_models/scaler.joblib
DATASET_PATH=datasets/dataset_estudiantes_decimal.csv
UMBRAL_RIESGO_ALTO=0.7
UMBRAL_RIESGO_MEDIO=0.4

# SMTP — credenciales reales en .env local, NUNCA en el repo
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=TU_CORREO@gmail.com
SMTP_PASSWORD=TU_APP_PASSWORD_DE_GMAIL
FROM_EMAIL=TU_CORREO@gmail.com
FROM_NAME=Academic Risk Notifications

# Logging
LOG_LEVEL=info
```

> **Generar un JWT_SECRET_KEY nuevo:**
> ```bash
> python3 -c "import secrets; print(secrets.token_urlsafe(32))"
> ```

---

## 3. Levantar la base de datos con Docker

```bash
docker-compose up -d db
```

Esto levanta **PostgreSQL 16** en `localhost:5433` (puerto externo 5433 para no colisionar con instalaciones locales de Postgres).

Verifica que esté corriendo:
```bash
docker ps
# Debe aparecer: mpra_db   ->  0.0.0.0:5433->5432/tcp
```

---

## 4. Crear entorno virtual e instalar dependencias

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

---

## 5. Ejecutar migraciones de base de datos

```bash
source venv/bin/activate
alembic upgrade head
```

Esto crea todas las tablas:
- `users` — usuarios con roles (STUDENT, PROFESSOR, ADMIN)
- `universities`, `campuses`, `programs`, `courses`
- `enrollments`, `professor_courses`, `student_profiles`
- `audit_logs`

Verifica que se aplicaron las 5 migraciones:
```bash
alembic history
# Debes ver: 0001 → 0002 → 0003 → 0004 → 0005 (head)
```

---

## 6. Crear el usuario administrador inicial

```bash
source venv/bin/activate
python3 scripts/seed_admin.py
```

Crea el usuario:
| Email | Contraseña | Rol |
|---|---|---|
| `admin@universidad.edu` | `Admin123!` | ADMIN |

> Ejecutar **una sola vez**. Si ya existe, el script no hace nada.

---

## 7. (Opcional) Poblar datos para reentrenamiento ML

```bash
python3 -m scripts.seed_training_program
```

Genera un programa completo (1º a 5º semestre), estudiantes, matrículas y `grades` en JSONB.
Además, exporta/regenera `datasets/dataset_estudiantes_decimal.csv` para reentrenar el modelo.

---

## 8. Iniciar el servidor

```bash
source venv/bin/activate
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

El servidor quedará disponible en:
- API: http://localhost:8001
- Swagger UI: http://localhost:8001/docs
- ReDoc: http://localhost:8001/redoc
- Health check: http://localhost:8001/health

---

## Estructura del proyecto

```
academic-risk-predictor-backend/
├── app/
│   ├── main.py                        # Entry point FastAPI
│   ├── core/
│   │   ├── config.py                  # Settings (pydantic-settings)
│   │   └── security.py                # bcrypt hash/verify
│   ├── api/v1/endpoints/
│   │   ├── auth.py                    # POST /auth/login, /auth/refresh, /auth/logout
│   │   ├── users.py                   # CRUD /users
│   │   ├── universities.py            # CRUD /universities
│   │   ├── programs.py                # CRUD /programs
│   │   ├── courses.py                 # CRUD /courses
│   │   ├── prediction.py              # POST /predict, /chat
│   │   ├── notifications.py           # POST /notifications/risk-alert, /predictor-reminder
│   │   └── health.py                  # GET /health
│   ├── application/
│   │   ├── schemas/                   # DTOs Pydantic
│   │   └── services/                  # Lógica de negocio
│   ├── domain/
│   │   ├── enums.py                   # RoleEnum, UserStatusEnum
│   │   ├── exceptions.py
│   │   ├── interfaces/                # Contratos de repositorios
│   │   └── value_objects/
│   │       └── token.py               # TokenPayload (incluye full_name)
│   ├── infrastructure/
│   │   ├── database.py                # Engine async + get_session
│   │   ├── models/                    # ORM SQLModel
│   │   ├── repositories/              # Implementaciones de repos
│   │   └── auth/                      # credential_provider.py
│   └── services/
│       └── email_service.py           # SMTP con templates HTML
├── alembic/versions/
│   ├── 0001_initial_schema.py
│   ├── 0002_add_user_status.py
│   ├── 0003_add_programs_and_student_profiles.py
│   ├── 0004_add_university_and_multi_university_support.py
│   └── 0005_add_campus_hierarchy.py
├── datasets/
│   └── dataset_estudiantes_decimal.csv
├── ml_models/
│   ├── modelo_logistico.joblib        # Generado automáticamente al iniciar
│   └── scaler.joblib
├── scripts/
│   ├── seed_admin.py                  # Crea admin@universidad.edu
│   ├── seed_training_program.py       # Seed masivo + export dataset de entrenamiento
│   └── update_student_grades.py       # Ajuste manual de grades para un estudiante específico
├── docker-compose.yml
├── requirements.txt
├── alembic.ini
└── env.example
```

---

## Endpoints principales

### Autenticación
| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/v1/auth/login` | Login con email + password → JWT |
| POST | `/api/v1/auth/refresh` | Renovar access token con refresh token |
| POST | `/api/v1/auth/logout` | Logout (stateless) |

### Usuarios
| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/api/v1/users` | ADMIN, PROFESSOR | Listar usuarios (filtros + paginación, max 100) |
| POST | `/api/v1/users` | ADMIN | Crear usuario |
| GET | `/api/v1/users/{id}` | ADMIN, self, PROFESSOR | Ver usuario |
| PATCH | `/api/v1/users/{id}` | ADMIN | Actualizar usuario |
| PATCH | `/api/v1/users/{id}/status` | ADMIN | Activar/desactivar |

### Predicción ML
| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/v1/predict` | Predicción de riesgo con notas por cohorte y total |
| POST | `/api/v1/predict/cohort` | Predicción de riesgo de un cohorte (parcial + seguimiento + asistencia) |
| POST | `/api/v1/chat` | Chat con consejero académico IA |

### Notificaciones (email)
| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/v1/notifications/risk-alert` | Alerta de riesgo ALTO al profesor |
| POST | `/api/v1/notifications/predictor-reminder` | Recordatorio motivacional al estudiante |

---

## Modelo ML

- Algoritmo: **Regresión Logística** (scikit-learn)
- Entrenado con ~99.000 registros
- Precisión: ~90%
- Variables de entrada (orden estricto):
  1. `nota_corte_1` — nota del corte 1 (0-5)
  2. `nota_corte_2` — nota del corte 2 (0-5)
  3. `nota_corte_final` — nota del corte final (0-5)
  4. `nota_total` — nota total ponderada (0-5)
- Si los archivos `.joblib` no existen, se entrenan automáticamente al iniciar

---

## Solución de problemas frecuentes

### Error: `connection refused` al conectar con la DB
- Verifica que el contenedor Docker esté corriendo: `docker ps`
- El puerto externo es **5433**, no 5432
- Asegúrate de que `DB_PORT=5433` en `.env`

### Error: `IllegalStateChangeError` de SQLAlchemy
- Ya resuelto en `database.py` con `async with session.begin()`
- Si aparece, verifica que estés usando Python 3.13 y la versión de SQLAlchemy en `requirements.txt`

### El modelo ML no carga
- Verifica que existan `ml_models/modelo_logistico.joblib` y `ml_models/scaler.joblib`
- Si no existen, el sistema los genera al arrancar desde el CSV en `datasets/`
- Verifica las rutas en `.env`: `MODEL_PATH`, `SCALER_PATH`, `DATASET_PATH`

### Los correos no llegan
- El SMTP usa Gmail App Password — funciona correctamente
- Correos a dominios con **Microsoft Exchange** (universidades) pueden ir a spam
- Para pruebas, usar una cuenta Gmail personal
- Verificar carpeta de correo no deseado
