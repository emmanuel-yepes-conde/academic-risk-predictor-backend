# 🤖 Backend - Predictor de Riesgo Académico

API REST desarrollada con **FastAPI** y **Machine Learning (Regresión Logística)** para predecir el riesgo de reprobación académica.

## 🚀 Características

- ✅ Predicción de riesgo usando **Regresión Logística**
- ✅ Análisis personalizado con consejos específicos
- ✅ API REST con documentación automática (Swagger)
- ✅ CORS habilitado para acceso público
- ✅ Modelo entrenado automáticamente al iniciar

## 📋 Requisitos

- Python 3.12 o superior
- pip (gestor de paquetes de Python)

## ⚡ Instalación Rápida

### 1. Clonar el repositorio

```bash
git clone https://github.com/TU_USUARIO/academic-risk-predictor-backend.git
cd academic-risk-predictor-backend
```

### 2. Crear entorno virtual

```bash
python -m venv venv

# Activar en Mac/Linux:
source venv/bin/activate

# Activar en Windows:
venv\Scripts\activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Ejecutar el servidor

```bash
python main.py
```

El servidor estará disponible en: **http://localhost:8000**

## 📡 Endpoints

### `GET /`
Información general del API

### `GET /health`
Verificar estado del servicio

**Respuesta:**
```json
{
  "status": "healthy",
  "modelo_cargado": true,
  "scaler_cargado": true
}
```

### `POST /predict`
Realizar predicción de riesgo académico

**Body:**
```json
{
  "promedio_asistencia": 85.0,
  "promedio_seguimiento": 3.5,
  "nota_parcial_1": 3.2,
  "inicios_sesion_plataforma": 42,
  "uso_tutorias": 1
}
```

**Respuesta:**
```json
{
  "probabilidad_riesgo": 0.35,
  "porcentaje_riesgo": 35.0,
  "nivel_riesgo": "BAJO",
  "analisis_ia": "...",
  "datos_radar": {...},
  "detalles_matematicos": {...}
}
```

## 📚 Documentación Automática

Una vez iniciado el servidor, puedes acceder a:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 🧠 Modelo de Machine Learning

### Algoritmo
**Regresión Logística** con 5 variables predictoras:

1. Promedio de asistencia (0-100%)
2. Promedio de seguimiento (0-5)
3. Nota parcial 1 (0-5)
4. Inicios de sesión en plataforma
5. Uso de tutorías (0 o 1)

### Fórmulas

```
z = β₀ + Σ(βᵢ × xᵢ_scaled)
P(riesgo) = 1 / (1 + e^(-z))
```

### Entrenamiento

El modelo se entrena automáticamente la primera vez que ejecutas el servidor usando el dataset incluido (`dataset_estudiantes_decimal.csv`). Los archivos generados son:

- `modelo_logistico.joblib` - Modelo entrenado
- `scaler.joblib` - Escalador StandardScaler

## 🌐 Despliegue

### Render.com (Recomendado - Gratis)

1. Crea una cuenta en [Render.com](https://render.com)
2. Conecta tu repositorio de GitHub
3. Crea un nuevo **Web Service**
4. Configuración:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python main.py`
   - **Environment**: Python 3
   
### Railway.app

1. Crea una cuenta en [Railway.app](https://railway.app)
2. Conecta tu repositorio
3. Railway detectará automáticamente Python
4. Deploy automático

### Variables de Entorno (Opcional)

```bash
PORT=8000  # Puerto del servidor (por defecto 8000)
```

## 🛠️ Tecnologías

- **FastAPI** 0.121+ - Framework web moderno
- **scikit-learn** 1.7+ - Machine Learning
- **pandas** 2.3+ - Análisis de datos
- **numpy** 2.3+ - Computación numérica
- **uvicorn** 0.38+ - Servidor ASGI
- **pydantic** 2.12+ - Validación de datos

## 📦 Estructura del Proyecto

```
academic-risk-predictor-backend/
├── main.py                          # API FastAPI
├── requirements.txt                 # Dependencias
├── dataset_estudiantes_decimal.csv  # Dataset de entrenamiento
├── .gitignore                       # Archivos ignorados
└── README.md                        # Este archivo
```

## 🤝 Contribuir

1. Fork el proyecto
2. Crea una rama (`git checkout -b feature/NuevaCaracteristica`)
3. Commit tus cambios (`git commit -m 'Agrega nueva característica'`)
4. Push a la rama (`git push origin feature/NuevaCaracteristica`)
5. Abre un Pull Request

## 📄 Licencia

Este proyecto es de código abierto.

## 🆘 Soporte

¿Problemas? Abre un **Issue** en GitHub.

---

**Desarrollado con ❤️ usando Python y Machine Learning**

