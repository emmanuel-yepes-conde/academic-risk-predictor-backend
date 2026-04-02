# Technical Specification: MPRA Infrastructure & Security

## 1. Stack Tecnológico
* **Backend:** Python 3.12 + FastAPI (Async REST API).
* **Base de Datos:** PostgreSQL 16 (Persistencia relacional).
* **Machine Learning:** Scikit-Learn (LogisticRegression) + Joblib (Persistencia del modelo).
* **Autenticación:** Microsoft Entra ID (OIDC/OAuth2).

## 2. Requerimientos No Funcionales (RNF)
* **RNF-01 (Seguridad):** Cifrado de datos en tránsito (TLS 1.3) y anonimización de identificadores en la capa de inferencia estadística.
* **RNF-02 (Desempeño):** El tiempo de respuesta de la API para el cálculo de riesgo debe ser inferior a 300ms.
* **RNF-03 (Mantenibilidad):** Aplicación de principios **SOLID** y **Clean Architecture** (Separación de capas de Dominio, Aplicación e Infraestructura).
* **RNF-04 (Usabilidad):** Interfaz 100% *Responsive* validada para resoluciones de escritorio (1920x1080) y dispositivos móviles.
* **RNF-05 (ML Ops):** El modelo entrenado debe cargarse en memoria al iniciar el servicio para evitar latencia de I/O por cada petición.

## 3. Infraestructura y Despliegue
* **Modelo Cliente-Servidor:** Desacoplado para permitir escalabilidad horizontal del backend.
* **Auditoría:** Logs detallados de cada transacción de escritura en base de datos para trazabilidad de cambios en notas y asistencias.