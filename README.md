# 🏗️ Academic Risk Predictor Backend - Arquitectura Refactorizada

## 📋 Tabla de Contenidos
- [Descripción](#descripción)
- [Arquitectura](#arquitectura)
- [Estructura del Proyecto](#estructura-del-proyecto)
- [Instalación](#instalación)
- [Ejecución](#ejecución)
- [Endpoints Disponibles](#endpoints-disponibles)
- [Desarrollo](#desarrollo)

---

## 📖 Descripción

Sistema de predicción de riesgo académico basado en Machine Learning (Regresión Logística) que ha sido refactorizado siguiendo **Clean Architecture** (Arquitectura en Capas).

**Tecnologías:**
- FastAPI (Framework Web)
- Scikit-learn (Machine Learning)
- Pydantic (Validación de Datos)
- Pandas & Numpy (Análisis de Datos)

**Proyecto Final - Semestre 2025-II**

---

## 🏛️ Arquitectura

El proyecto sigue una **Arquitectura en Capas (Clean Architecture)** similar a NestJS o Express bien estructurado:

```
┌─────────────────────────────────────────┐
│         Capa de Presentación           │
│      (Endpoints/Controladores)         │
│    ✓ Manejo de HTTP Requests           │
│    ✓ Validación de entrada (Pydantic)  │
│    ✓ Serialización de respuesta        │
└─────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────┐
│       Capa de Lógica de Negocio        │
│            (Servicios)                  │
│    ✓ Predicciones ML                    │
│    ✓ Análisis personalizado             │
│    ✓ Cálculos matemáticos               │
└─────────────────────────────────────────┘
                   ↓
┌─────────────────────────────────────────┐
│         Capa de Datos                   │
│      (Modelos ML + Dataset)             │
│    ✓ Modelo entrenado (.joblib)         │
│    ✓ Scaler (.joblib)                   │
│    ✓ Dataset de entrenamiento (.csv)    │
└─────────────────────────────────────────┘
```

### Principios Aplicados

1. **Separación de Responsabilidades**: Cada capa tiene una responsabilidad específica
2. **Inyección de Dependencias**: Los servicios se inyectan en los controladores
3. **DTOs (Data Transfer Objects)**: Contratos claros de entrada/salida con Pydantic
4. **Singleton Pattern**: El modelo ML se carga una sola vez al inicio
5. **Configuración Centralizada**: Todas las configuraciones en un solo lugar

---

## 📁 Estructura del Proyecto

```
academic-risk-predictor-backend/
│
├── app/                                    # 📦 Paquete principal de la aplicación
│   ├── __init__.py
│   ├── main.py                            # 🚀 Entry Point de FastAPI
│   │
│   ├── api/                               # 🌐 Capa de API (Controladores)
│   │   └── v1/                           # Versión 1 del API
│   │       └── endpoints/
│   │           ├── __init__.py
│   │           └── prediction.py         # Endpoints de predicción y chat
│   │
│   ├── core/                              # ⚙️ Configuración Core
│   │   ├── __init__.py
│   │   └── config.py                     # Settings y variables de entorno
│   │
│   ├── schemas/                           # 📋 DTOs (Pydantic Models)
│   │   ├── __init__.py
│   │   └── student.py                    # Schemas de estudiante
│   │
│   └── services/                          # 🧠 Lógica de Negocio
│       ├── __init__.py
│       └── ml_service.py                 # Servicio de Machine Learning
│
├── main.py                                # 🔧 Wrapper para compatibilidad
├── requirements.txt                       # 📦 Dependencias Python
├── env.example                            # ⚙️ Ejemplo de configuración
│
├── modelo_logistico.joblib               # 🤖 Modelo entrenado (generado)
├── scaler.joblib                          # 📊 Scaler entrenado (generado)
└── dataset_estudiantes_decimal.csv       # 📈 Dataset de entrenamiento
```

### Descripción de Componentes

#### 📦 `app/main.py` - Entry Point
- Configura la aplicación FastAPI
- Registra middleware CORS
- Incluye los routers
- Define endpoints generales (`/`, `/health`)

#### 🌐 `app/api/v1/endpoints/prediction.py` - Controladores
- **POST /api/v1/predict**: Predicción de riesgo
- **POST /api/v1/chat**: Chat con consejero virtual
- Solo orquestación, sin lógica de negocio

#### 📋 `app/schemas/student.py` - DTOs
- `StudentInput`: Datos de entrada del estudiante
- `PredictionOutput`: Respuesta de la predicción
- `ChatInput/ChatOutput`: Datos del chat
- Validación automática con Pydantic

#### 🧠 `app/services/ml_service.py` - Servicio ML
- Carga/entrenamiento del modelo
- Predicciones
- Análisis personalizado con IA
- Cálculos matemáticos detallados
- **Patrón Singleton**: Una sola instancia global

#### ⚙️ `app/core/config.py` - Configuración
- Manejo centralizado de configuraciones
- Variables de entorno
- Valores por defecto
- Basado en Pydantic Settings

---

## 🚀 Instalación

### 1. Clonar el Repositorio
```bash
git clone <repository-url>
cd academic-risk-predictor-backend
```

### 2. Crear Entorno Virtual
```bash
python3 -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

### 3. Instalar Dependencias
```bash
pip install -r requirements.txt
```

### 4. Configurar Variables de Entorno (Opcional)
```bash
cp env.example .env
# Editar .env según necesidades
```

---

## ▶️ Ejecución

### Desarrollo
```bash
# Opción 1: Usando el archivo main.py de la raíz
python main.py

# Opción 2: Usando uvicorn directamente
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Producción
```bash
# Sin reload para mejor rendimiento
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Docker (si aplica)
```bash
docker build -t academic-risk-predictor .
docker run -p 8000:8000 academic-risk-predictor
```

---

## 🔌 Endpoints Disponibles

### 📍 General

#### `GET /`
Información del API y endpoints disponibles.

#### `GET /health`
Health check - Estado del servicio y modelo ML.

```json
{
  "status": "healthy",
  "modelo_cargado": true,
  "scaler_cargado": true,
  "version": "1.0.0"
}
```

---

### 📍 Predicción

#### `POST /api/v1/predict`
Realiza una predicción de riesgo académico.

**Request Body:**
```json
{
  "promedio_asistencia": 78.5,
  "promedio_seguimiento": 3.1,
  "nota_parcial_1": 2.8,
  "inicios_sesion_plataforma": 45,
  "uso_tutorias": 2
}
```

**Response:**
```json
{
  "probabilidad_riesgo": 0.65,
  "porcentaje_riesgo": 65.0,
  "nivel_riesgo": "MEDIO",
  "analisis_ia": "⚠️ **SITUACIÓN DE RIESGO MODERADO**...",
  "datos_radar": {
    "labels": ["Asistencia (%)", "Seguimiento", "Parcial 1", "Logins", "Tutorías"],
    "estudiante": [78.5, 3.1, 2.8, 45, 2],
    "promedio_aprobado": [82.76, 3.40, 3.39, 39.06, 1.51]
  },
  "detalles_matematicos": {
    "formula_logit": "z = β₀ + Σ(βᵢ × xᵢ)",
    "valor_z": 0.619,
    "coeficientes": [-0.35, 0.28, 0.52, 0.15, -0.22]
  }
}
```

---

#### `POST /api/v1/chat`
Chat con el consejero académico virtual.

**Request Body:**
```json
{
  "pregunta": "¿Cómo puedo mejorar mi nota?",
  "datos_estudiante": {
    "promedio_asistencia": 78.5,
    "promedio_seguimiento": 3.1,
    "nota_parcial_1": 2.8,
    "inicios_sesion_plataforma": 45,
    "uso_tutorias": 2
  },
  "prediccion_actual": {
    "porcentaje_riesgo": 65.0
  }
}
```

**Response:**
```json
{
  "respuesta": "**💡 Cómo Mejorar Tu Rendimiento:**\n\n..."
}
```

---

## 📚 Documentación Interactiva

Una vez iniciado el servidor, visita:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## 🛠️ Desarrollo

### Agregar un Nuevo Endpoint

1. **Crear el schema en `app/schemas/`** (si es necesario)
```python
# app/schemas/new_feature.py
from pydantic import BaseModel

class NewFeatureInput(BaseModel):
    field1: str
    field2: int
```

2. **Agregar lógica en `app/services/`** (si es necesario)
```python
# app/services/new_service.py
class NewService:
    def process(self, data):
        # Lógica de negocio
        return result
```

3. **Crear el endpoint en `app/api/v1/endpoints/`**
```python
# app/api/v1/endpoints/new_endpoint.py
from fastapi import APIRouter
router = APIRouter()

@router.post("/new-feature")
async def new_feature(data: NewFeatureInput):
    # Orquestación
    return result
```

4. **Registrar el router en `app/main.py`**
```python
from app.api.v1.endpoints import new_endpoint

app.include_router(
    new_endpoint.router,
    prefix="/api/v1",
    tags=["New Feature"]
)
```

### Testing
```bash
# Instalar dependencias de testing
pip install pytest pytest-cov httpx

# Ejecutar tests
pytest tests/ -v --cov=app
```

---

## 🌍 Despliegue

### Railway / Render / Heroku

1. Asegurarse de tener `Procfile`:
```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

2. Configurar variables de entorno en el panel del servicio

3. Push al repositorio:
```bash
git push railway main  # o render/heroku
```

---

## 📝 Notas Técnicas

### ⚠️ Puntos Críticos

1. **El Scaler**: Las variables están escaladas con `StandardScaler`. El modelo espera datos escalados.

2. **Orden de Features**: El array de entrada debe mantener exactamente este orden:
   - promedio_asistencia
   - promedio_seguimiento
   - nota_parcial_1
   - inicios_sesion_plataforma
   - uso_tutorias

3. **Modelo Singleton**: El modelo se carga UNA SOLA VEZ al iniciar la app (patrón Singleton).

4. **Entrenamiento Automático**: Si los archivos `.joblib` no existen, el sistema entrena el modelo automáticamente desde el CSV.

---

## 🤝 Contribución

Para contribuir al proyecto:

1. Fork el repositorio
2. Crear una rama feature (`git checkout -b feature/AmazingFeature`)
3. Commit cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la rama (`git push origin feature/AmazingFeature`)
5. Abrir un Pull Request

---

## 📄 Licencia

Proyecto Final - Semestre 2025-II

---

## 👨‍💻 Autor

Desarrollado como proyecto final académico.

---

## 🔗 Enlaces Relacionados

- [Documentación de FastAPI](https://fastapi.tiangolo.com/)
- [Pydantic Documentation](https://docs.pydantic.dev/)
- [Scikit-learn User Guide](https://scikit-learn.org/stable/user_guide.html)

