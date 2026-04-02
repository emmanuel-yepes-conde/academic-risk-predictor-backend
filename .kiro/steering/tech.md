# Tech Stack

## Stack Tecnológico
- Backend: Python 3.12+ con FastAPI (Async REST API) + uvicorn (ASGI)
- Base de datos: PostgreSQL 16 (persistencia relacional)
- Autenticación: Inicio de sesión seguro, con posibilidad de escalar a SSO con microsoft y google
- Seguridad en tránsito: TLS 1.3; anonimización de identificadores en capa de inferencia
- Pydantic v2 + pydantic-settings para validación y configuración

## Machine Learning
- scikit-learn — LogisticRegression con StandardScaler
- joblib — serialización de modelo/scaler (cargado en memoria al iniciar)
- pandas + numpy — carga de datos y procesamiento de features

## Librerías Python Clave
- `python-dotenv` — carga de .env
- `python-multipart` — soporte CORS/middleware

## Configuración
- Centralizada en `app/core/config.py` vía `pydantic-settings` `BaseSettings`
- Variables de entorno desde `.env` (ver `env.example`)
- Vars clave: `HOST`, `PORT`, `CORS_ORIGINS`, `MODEL_PATH`, `SCALER_PATH`, `DATASET_PATH`, `UMBRAL_RIESGO_ALTO`, `UMBRAL_RIESGO_MEDIO`

## Ciclo de Vida del Modelo ML
- Artefactos en `ml_models/` (`.joblib`)
- Al iniciar: si existen se cargan; si no, se entrena desde `datasets/dataset_estudiantes_decimal.csv` y se persisten
- Orden de features estricto (debe coincidir con el entrenamiento):
  1. `promedio_asistencia` — porcentaje de asistencia (0–100)
  2. `promedio_seguimiento` — promedio quizzes/tareas (0–5)
  3. `nota_parcial_1` — nota primer parcial (0–5)

## Diccionario de Datos (Variables Mínimas Obligatorias — RB-01)
| Campo | Tipo | Rango | Descripción |
|---|---|---|---|
| Asistencia | Decimal | 0.00 – 100.00 | Porcentaje de asistencia a la fecha |
| Seguimiento | Decimal | 0.0 – 5.0 | Promedio de notas de actividades tempranas |
| Parcial 1 | Decimal | 0.0 – 5.0 | Calificación del primer examen parcial |

## Requerimientos No Funcionales
- RNF-01: TLS 1.3 en tránsito; anonimización de IDs en capa de inferencia
- RNF-02: Tiempo de respuesta API para cálculo de riesgo < 300ms
- RNF-03: Principios SOLID y Clean Architecture (capas Dominio / Aplicación / Infraestructura)
- RNF-04: Interfaz responsive validada para 1920×1080 y móviles
- RNF-05: Modelo cargado en memoria al iniciar el servicio (sin I/O por petición)

## Infraestructura y Despliegue
- Modelo cliente-servidor desacoplado (escalabilidad horizontal del backend)
- Auditoría: logs de cada transacción de escritura en BD (trazabilidad de notas y asistencias)
- Despliegue soportado: Docker, Railway, Render, Heroku (ver `Procfile`, `railway.json`, `render.yaml`)

## Comandos Comunes

```bash
# Instalar dependencias
pip install -r requirements.txt

# Servidor de desarrollo
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Via wrapper raíz
python main.py

# Producción (multi-worker)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

# Docker
docker build -t academic-risk-predictor .
docker run -p 8000:8000 academic-risk-predictor

# Tests
pytest tests/ -v --cov=app
```

## Documentación API (servidor corriendo)
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
