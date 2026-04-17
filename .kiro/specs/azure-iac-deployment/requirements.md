# Documento de Requisitos — Despliegue IaC en Azure

## Introducción

Este documento define los requisitos para implementar Infraestructura como Código (IaC) que permita desplegar la aplicación MPRA (Modelo Predictivo de Riesgo Académico) en Microsoft Azure sin necesidad de configuración manual desde el portal web de Azure. El despliegue incluye un contenedor para el backend FastAPI y una base de datos PostgreSQL gestionada, todo provisionable desde el repositorio mediante Azure CLI y Bicep.

## Glosario

- **Azure_CLI**: Herramienta de línea de comandos de Microsoft Azure (`az`) utilizada para crear y gestionar recursos en la nube
- **Bicep**: Lenguaje declarativo de IaC nativo de Azure que compila a plantillas ARM; alternativa más legible a ARM JSON
- **Resource_Group**: Contenedor lógico de Azure que agrupa recursos relacionados para su gestión conjunta
- **Azure_Container_App**: Servicio serverless de Azure para ejecutar contenedores sin gestionar infraestructura de servidores
- **Container_App_Environment**: Entorno compartido de Azure Container Apps que proporciona red, logging y escalado
- **Azure_Container_Registry (ACR)**: Registro privado de imágenes Docker en Azure para almacenar la imagen del backend
- **Azure_Database_for_PostgreSQL_Flexible_Server**: Servicio gestionado de PostgreSQL en Azure con alta disponibilidad y backups automáticos
- **Backend_Container**: Contenedor Docker que ejecuta la aplicación FastAPI con uvicorn en el puerto 8000
- **Script_de_Despliegue**: Script Bash que orquesta el aprovisionamiento completo usando Azure CLI y Bicep
- **Variables_de_Entorno**: Configuraciones inyectadas al contenedor en tiempo de ejecución (DATABASE_URL, JWT_SECRET_KEY, etc.)
- **Alembic**: Herramienta de migraciones de base de datos utilizada por el proyecto para gestionar el esquema de PostgreSQL

## Requisitos

### Requisito 1: Definición de infraestructura con Bicep

**Historia de Usuario:** Como desarrollador, quiero definir toda la infraestructura de Azure en archivos Bicep versionados en el repositorio, para que el despliegue sea reproducible y no dependa de configuración manual en el portal.

#### Criterios de Aceptación

1. THE Bicep_Template SHALL definir todos los recursos de Azure necesarios en un único archivo principal con módulos opcionales
2. THE Bicep_Template SHALL aceptar parámetros para el nombre del entorno, la región de Azure, las credenciales de la base de datos y la clave JWT
3. WHEN el Bicep_Template se despliega en una región de Azure válida, THE Azure_CLI SHALL crear todos los recursos sin errores
4. THE Bicep_Template SHALL incluir los siguientes recursos: Resource_Group, Azure_Container_Registry, Container_App_Environment, Azure_Container_App y Azure_Database_for_PostgreSQL_Flexible_Server
5. THE Bicep_Template SHALL residir en el directorio `infra/` del repositorio

### Requisito 2: Registro de contenedores y construcción de imagen Docker

**Historia de Usuario:** Como desarrollador, quiero que la imagen Docker del backend se construya y publique automáticamente en un registro privado de Azure, para que Azure Container Apps pueda desplegarla.

#### Criterios de Aceptación

1. THE Bicep_Template SHALL provisionar un Azure_Container_Registry con SKU Basic
2. WHEN el Script_de_Despliegue se ejecuta, THE Azure_CLI SHALL construir la imagen Docker del backend usando el Dockerfile existente del repositorio
3. WHEN la imagen se construye exitosamente, THE Azure_CLI SHALL publicar la imagen en el Azure_Container_Registry provisionado
4. THE Azure_Container_App SHALL tener permisos de lectura (AcrPull) sobre el Azure_Container_Registry para descargar la imagen

### Requisito 3: Contenedor del backend FastAPI

**Historia de Usuario:** Como desarrollador, quiero que el backend FastAPI se ejecute en Azure Container Apps con la configuración correcta, para que la API esté disponible públicamente.

#### Criterios de Aceptación

1. THE Azure_Container_App SHALL ejecutar la imagen del Backend_Container desde el Azure_Container_Registry
2. THE Azure_Container_App SHALL exponer el puerto 8000 con ingress externo habilitado para tráfico HTTPS
3. THE Azure_Container_App SHALL recibir las siguientes Variables_de_Entorno como secretos: DATABASE_URL, JWT_SECRET_KEY
4. THE Azure_Container_App SHALL recibir las siguientes Variables_de_Entorno como configuración: HOST, PORT, LOG_LEVEL, CORS_ORIGINS, MODEL_PATH, SCALER_PATH, DATASET_PATH
5. THE Azure_Container_App SHALL configurar recursos mínimos de 0.5 vCPU y 1Gi de memoria
6. WHEN el Azure_Container_App se despliega, THE Backend_Container SHALL responder con estado HTTP 200 en el endpoint `/health`
7. THE Azure_Container_App SHALL configurar un health probe (liveness) apuntando al endpoint `/health`

### Requisito 4: Base de datos PostgreSQL gestionada

**Historia de Usuario:** Como desarrollador, quiero una instancia de PostgreSQL gestionada en Azure, para que la base de datos tenga backups automáticos y alta disponibilidad sin administración manual.

#### Criterios de Aceptación

1. THE Bicep_Template SHALL provisionar un Azure_Database_for_PostgreSQL_Flexible_Server con versión 16
2. THE Azure_Database_for_PostgreSQL_Flexible_Server SHALL usar el SKU Burstable B1ms (1 vCore, 2 GiB RAM) como configuración inicial
3. THE Azure_Database_for_PostgreSQL_Flexible_Server SHALL crear una base de datos con el nombre especificado en los parámetros del despliegue
4. THE Azure_Database_for_PostgreSQL_Flexible_Server SHALL tener backups automáticos habilitados con retención de 7 días
5. THE Azure_Database_for_PostgreSQL_Flexible_Server SHALL permitir conexiones desde el Azure_Container_App mediante reglas de firewall o integración de red virtual
6. THE Script_de_Despliegue SHALL construir la DATABASE_URL en formato `postgresql+asyncpg://` a partir de las credenciales y el host del servidor PostgreSQL provisionado

### Requisito 5: Script de despliegue automatizado

**Historia de Usuario:** Como desarrollador, quiero un único script que ejecute todo el proceso de despliegue desde cero, para que no necesite interactuar con el portal de Azure.

#### Criterios de Aceptación

1. THE Script_de_Despliegue SHALL ser un archivo Bash ejecutable ubicado en `infra/deploy.sh`
2. WHEN el Script_de_Despliegue se ejecuta sin argumentos, THE Script_de_Despliegue SHALL mostrar las instrucciones de uso con los parámetros requeridos
3. THE Script_de_Despliegue SHALL aceptar parámetros para: nombre del entorno, región de Azure, contraseña de la base de datos y clave JWT
4. WHEN el Script_de_Despliegue se ejecuta con parámetros válidos, THE Script_de_Despliegue SHALL ejecutar los siguientes pasos en orden: crear el Resource_Group, desplegar el Bicep_Template, construir y publicar la imagen Docker, y actualizar el Azure_Container_App con la imagen
5. IF un paso del despliegue falla, THEN THE Script_de_Despliegue SHALL mostrar un mensaje de error descriptivo y detener la ejecución
6. WHEN el despliegue se completa exitosamente, THE Script_de_Despliegue SHALL mostrar la URL pública de la API y la cadena de conexión de la base de datos (sin la contraseña)
7. THE Script_de_Despliegue SHALL validar que Azure_CLI está instalado y que el usuario tiene una sesión activa antes de iniciar el despliegue

### Requisito 6: Ejecución de migraciones de base de datos

**Historia de Usuario:** Como desarrollador, quiero que las migraciones de Alembic se ejecuten como parte del proceso de despliegue, para que el esquema de la base de datos esté actualizado al desplegar.

#### Criterios de Aceptación

1. WHEN el despliegue se completa y la base de datos está accesible, THE Script_de_Despliegue SHALL ejecutar las migraciones de Alembic (`alembic upgrade head`) contra la base de datos provisionada
2. IF las migraciones de Alembic fallan, THEN THE Script_de_Despliegue SHALL mostrar el error y advertir que la aplicación puede no funcionar correctamente
3. THE Script_de_Despliegue SHALL configurar la variable DATABASE_URL antes de ejecutar las migraciones para que Alembic se conecte a la base de datos correcta

### Requisito 7: Documentación del despliegue

**Historia de Usuario:** Como desarrollador, quiero documentación clara sobre cómo desplegar en Azure, para que cualquier miembro del equipo pueda ejecutar el despliegue sin conocimiento previo de Azure.

#### Criterios de Aceptación

1. THE Documentación SHALL incluir un archivo `infra/README.md` con los prerrequisitos (Azure CLI, suscripción activa, Docker)
2. THE Documentación SHALL incluir instrucciones paso a paso para ejecutar el despliegue desde cero
3. THE Documentación SHALL listar todas las variables de entorno configurables y sus valores por defecto
4. THE Documentación SHALL incluir instrucciones para eliminar todos los recursos de Azure creados (cleanup)
5. THE Documentación SHALL incluir una sección de estimación de costos mensuales para la configuración base (SKU Burstable + Container Apps)

### Requisito 8: Script de limpieza de recursos

**Historia de Usuario:** Como desarrollador, quiero poder eliminar todos los recursos de Azure creados con un solo comando, para evitar costos innecesarios cuando el entorno no está en uso.

#### Criterios de Aceptación

1. THE Script_de_Despliegue SHALL incluir una opción `--destroy` que elimine el Resource_Group completo y todos los recursos contenidos
2. WHEN se ejecuta con `--destroy`, THE Script_de_Despliegue SHALL solicitar confirmación antes de proceder con la eliminación
3. WHEN la eliminación se completa, THE Script_de_Despliegue SHALL confirmar que todos los recursos fueron eliminados exitosamente
