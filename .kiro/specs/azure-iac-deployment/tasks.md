# Plan de Implementación: Despliegue IaC en Azure

## Visión General

Implementación de la infraestructura como código para desplegar la aplicación MPRA en Azure. Se crean tres archivos en el directorio `infra/`: una plantilla Bicep (`main.bicep`) con todos los recursos de Azure, un script Bash (`deploy.sh`) que orquesta el despliegue completo, y documentación (`README.md`). Cada tarea construye incrementalmente sobre la anterior, terminando con la integración completa del flujo de despliegue y destrucción.

## Tareas

- [x] 1. Crear la plantilla Bicep con todos los recursos de Azure
  - [x] 1.1 Crear `infra/main.bicep` con parámetros, variables y recursos base
    - Definir parámetros de entrada: `environmentName` (string), `location` (string, default `resourceGroup().location`), `dbAdminPassword` (@secure string), `jwtSecretKey` (@secure string), `dbName` (string, default `mpra_db`), `dbAdminUser` (string, default `mpraadmin`)
    - Definir variables derivadas con la convención de nombres: `acrName` = `acrmpra${environmentName}`, `containerAppEnvName` = `cae-mpra-${environmentName}`, `containerAppName` = `ca-mpra-${environmentName}`, `postgresServerName` = `pg-mpra-${environmentName}`
    - Definir variable `databaseUrl` construida como `postgresql+asyncpg://{user}:{pass}@{host}:5432/{db}?sslmode=require`
    - Crear recurso Azure Container Registry con SKU Basic y admin user deshabilitado
    - Crear recurso Container App Environment con Log Analytics workspace integrado
    - Crear recurso PostgreSQL Flexible Server v16, SKU Burstable B1ms, backup 7 días, autenticación por contraseña
    - Crear recurso PostgreSQL Database `mpra_db` con charset UTF-8
    - Crear regla de firewall PostgreSQL para permitir acceso desde servicios de Azure (startIpAddress: `0.0.0.0`, endIpAddress: `0.0.0.0`)
    - Crear recurso Container App con imagen placeholder (`mcr.microsoft.com/azuredocs/containerapps-helloworld:latest`), ingress externo en puerto 8000, recursos 0.5 vCPU y 1Gi memoria
    - Configurar secretos del Container App: `database-url` y `jwt-secret-key`
    - Configurar variables de entorno del Container App: `HOST=0.0.0.0`, `PORT=8000`, `LOG_LEVEL=info`, `CORS_ORIGINS=*`, `MODEL_PATH=ml_models/modelo_logistico.joblib`, `SCALER_PATH=ml_models/scaler.joblib`, `DATASET_PATH=datasets/dataset_estudiantes_decimal.csv`
    - Configurar health probe (liveness) apuntando a `/health`
    - Crear Role Assignment AcrPull para la identidad del Container App sobre el ACR
    - Definir outputs: `containerAppFqdn`, `acrLoginServer`, `acrName`, `postgresHost`, `containerAppName`, `containerAppEnvironmentName`
    - _Requisitos: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.4, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 1.2 Validar la plantilla Bicep con `az bicep build`
    - Ejecutar `az bicep build --file infra/main.bicep` para verificar sintaxis y referencias válidas
    - Ejecutar `shellcheck` o revisión manual de la estructura del archivo
    - _Requisitos: 1.3_

- [x] 2. Crear el script de despliegue automatizado
  - [x] 2.1 Crear `infra/deploy.sh` con parseo de argumentos y validación de prerrequisitos
    - Crear archivo con shebang `#!/usr/bin/env bash` y `set -euo pipefail`
    - Implementar función `usage()` que muestre instrucciones de uso con todos los parámetros disponibles
    - Implementar parseo de argumentos con `getopts` o `while/case`: `-e|--env`, `-r|--region`, `-p|--db-password`, `-j|--jwt-secret`, `--destroy`
    - Validar que Azure CLI está instalado (`command -v az`)
    - Validar que hay sesión activa (`az account show`)
    - Validar que los parámetros requeridos están presentes según el modo (deploy vs destroy)
    - Mostrar uso cuando se ejecuta sin argumentos
    - _Requisitos: 5.1, 5.2, 5.3, 5.7_

  - [x] 2.2 Implementar el flujo de despliegue completo en `deploy.sh`
    - Crear Resource Group con `az group create --name rg-mpra-{env} --location {region}`
    - Desplegar Bicep con `az deployment group create` pasando los parámetros (`environmentName`, `dbAdminPassword`, `jwtSecretKey`)
    - Capturar outputs del despliegue (ACR name, FQDN, postgres host, container app name) usando `--query` o `jq`
    - Construir imagen Docker con `az acr build --registry {acrName} --image mpra-backend:latest .`
    - Actualizar Container App con la imagen nueva usando `az containerapp update --name {caName} --resource-group {rgName} --image {acrLoginServer}/mpra-backend:latest`
    - Ejecutar migraciones Alembic con `az containerapp exec --name {caName} --resource-group {rgName} --command "alembic upgrade head"`, capturando errores como advertencia (no exit)
    - Mostrar resumen final: URL pública (`https://{fqdn}`), cadena de conexión (sin contraseña)
    - Implementar manejo de errores descriptivo en cada paso con `set -euo pipefail`
    - _Requisitos: 2.2, 2.3, 4.6, 5.4, 5.5, 5.6, 6.1, 6.2, 6.3_

  - [x] 2.3 Implementar el flujo de destrucción (`--destroy`) en `deploy.sh`
    - Solicitar confirmación interactiva antes de eliminar (`read -p`)
    - Ejecutar `az group delete --name rg-mpra-{env} --yes --no-wait` si se confirma
    - Manejar caso donde el Resource Group no existe (mensaje informativo, exit 0)
    - Confirmar eliminación exitosa al usuario
    - _Requisitos: 8.1, 8.2, 8.3_

- [x] 3. Checkpoint — Verificar plantilla Bicep y script de despliegue
  - Verificar que `infra/main.bicep` compila sin errores con `az bicep build` (si está disponible) o revisión de sintaxis
  - Verificar que `infra/deploy.sh` pasa `shellcheck` (si está disponible) o revisión de sintaxis bash
  - Verificar que el script tiene permisos de ejecución (`chmod +x`)
  - Asegurar que todos los tests pasan, preguntar al usuario si surgen dudas.

- [x] 4. Crear la documentación del despliegue
  - [x] 4.1 Crear `infra/README.md` con documentación completa
    - Sección de prerrequisitos: Azure CLI ≥ 2.50, suscripción activa de Azure, Docker (para desarrollo local)
    - Instrucciones paso a paso para despliegue desde cero (login, ejecución del script, verificación)
    - Tabla de variables de entorno configurables con sus valores por defecto (HOST, PORT, LOG_LEVEL, CORS_ORIGINS, MODEL_PATH, SCALER_PATH, DATASET_PATH, DATABASE_URL, JWT_SECRET_KEY)
    - Instrucciones de limpieza/cleanup con el flag `--destroy`
    - Sección de estimación de costos mensuales para la configuración base (Container Apps consumo, PostgreSQL Burstable B1ms, ACR Basic)
    - _Requisitos: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 5. Integración final y verificación
  - [x] 5.1 Verificar coherencia entre Bicep, script y documentación
    - Confirmar que los nombres de parámetros en `main.bicep` coinciden con los que pasa `deploy.sh`
    - Confirmar que los outputs de Bicep son consumidos correctamente por el script
    - Confirmar que las variables de entorno del Container App coinciden con las de `app/core/config.py`
    - Confirmar que la DATABASE_URL usa el formato `postgresql+asyncpg://` requerido por la app
    - Confirmar que el README documenta correctamente los flags del script y las variables de entorno
    - _Requisitos: 1.2, 3.3, 3.4, 4.6, 5.4_

- [x] 6. Checkpoint final — Validación completa
  - Asegurar que todos los archivos están creados: `infra/main.bicep`, `infra/deploy.sh`, `infra/README.md`
  - Asegurar que `deploy.sh` tiene permisos de ejecución
  - Asegurar que todos los tests pasan, preguntar al usuario si surgen dudas.

## Notas

- Las tareas marcadas con `*` son opcionales y pueden omitirse para un MVP más rápido
- Cada tarea referencia requisitos específicos para trazabilidad
- Los checkpoints aseguran validación incremental
- Este feature es IaC (Bicep + Bash), por lo que no se incluyen property-based tests — la validación se hace con `az bicep build`, `shellcheck` y smoke tests post-despliegue
- La ejecución real contra Azure requiere una suscripción activa y no se automatiza en CI local
