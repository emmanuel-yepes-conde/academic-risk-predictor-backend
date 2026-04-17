# Plan de Implementación: GitHub Actions CI/CD para MPRA

## Resumen

Implementar dos workflows de GitHub Actions (`ci.yml` y `cd.yml`) que automatizan la integración continua y el despliegue continuo de la aplicación MPRA, reemplazando el workflow existente `azure-deploy.yml`. Incluye actualización de documentación en español.

## Tareas

- [x] 1. Crear el workflow de Integración Continua (CI)
  - [x] 1.1 Crear el archivo `.github/workflows/ci.yml` con la estructura base del workflow
    - Definir `name: CI`
    - Configurar trigger `pull_request` contra ramas `main` y `develop` (eventos `opened`, `synchronize`, `reopened`)
    - Configurar trigger `workflow_dispatch` para ejecución manual
    - _Requisitos: 1.1, 1.7_

  - [x] 1.2 Configurar el job `test` con servicio PostgreSQL 16 y ejecución de tests
    - Definir el job `test` con `runs-on: ubuntu-latest`
    - Configurar service container PostgreSQL 16 con usuario `mpra_test`, contraseña `mpra_test_pass`, base de datos `mpra_test_db`, health check con `pg_isready`
    - Configurar variables de entorno para la Test Suite: `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `JWT_SECRET_KEY`, `DATABASE_URL`
    - Agregar pasos: checkout (`actions/checkout@v4`), setup Python 3.12 (`actions/setup-python@v5`), cache de pip (`actions/cache@v4` con key basada en `requirements.txt`), instalar dependencias (`pip install -r requirements.txt`)
    - Agregar paso de espera a PostgreSQL con `pg_isready` en loop
    - Agregar paso de migraciones Alembic (`alembic upgrade head`)
    - Agregar paso de ejecución de tests: `python3 -m pytest tests/ -v --cov=app --cov-report=xml --cov-report=term-missing`
    - Agregar paso de publicación de cobertura como artefacto (`actions/upload-artifact@v4` con `coverage.xml`)
    - Agregar paso condicional que emite warning en el summary si la cobertura cae por debajo del 80%
    - _Requisitos: 1.2, 1.3, 1.4, 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 1.3 Configurar el job `validate-bicep` para validación de infraestructura
    - Definir el job `validate-bicep` con `runs-on: ubuntu-latest`
    - Agregar paso de checkout (`actions/checkout@v4`)
    - Agregar paso de Azure CLI Login (`azure/login@v2`) usando secreto `AZURE_CREDENTIALS`
    - Agregar paso de validación Bicep: `az bicep build --file infra/main.bicep`
    - _Requisitos: 1.5, 1.6, 4.2, 6.1, 6.2, 6.3, 6.4_

- [x] 2. Crear el workflow de Despliegue Continuo (CD)
  - [x] 2.1 Crear el archivo `.github/workflows/cd.yml` con la estructura base del workflow
    - Definir `name: CD`
    - Configurar trigger `push` a ramas `main` y `develop`
    - Configurar trigger `workflow_dispatch` con input `environment` (opciones `dev` y `prod`)
    - Definir variable de entorno `ENV_NAME` con expresión condicional que mapea rama → entorno (`develop`→`dev`, `main`→`prod`, o el input de `workflow_dispatch`)
    - _Requisitos: 2.1, 2.7, 3.1_

  - [x] 2.2 Configurar el job `deploy` con selección de secretos por entorno
    - Definir el job `deploy` con `runs-on: ubuntu-latest`
    - Agregar paso de checkout (`actions/checkout@v4`)
    - Agregar paso condicional de tests previos solo para producción (`env.ENV_NAME == 'prod'`): setup Python 3.12, instalar dependencias, configurar PostgreSQL service container, ejecutar migraciones y tests
    - Agregar paso de Azure Login (`azure/login@v2`) usando secreto `AZURE_CREDENTIALS`
    - Agregar paso de ejecución de `bash infra/deploy.sh` con flags `-e $ENV_NAME`, `-r $AZURE_REGION`, `-p` y `-j` usando selección condicional de secretos (`DB_PASSWORD_DEV`/`DB_PASSWORD_PROD`, `JWT_SECRET_DEV`/`JWT_SECRET_PROD`) según `ENV_NAME`
    - _Requisitos: 2.2, 2.3, 2.4, 2.6, 3.2, 3.3, 3.4, 3.6, 3.7, 4.1, 4.3, 4.4_

  - [x] 2.3 Agregar health check post-despliegue con reintentos
    - Agregar paso que obtiene el FQDN del Container App con `az containerapp show`
    - Implementar loop de 10 reintentos con 15 segundos de espera que verifica HTTP 200 en `/health`
    - Fallar el job si el health check no pasa después de 10 intentos
    - _Requisitos: 2.5, 3.5_

- [x] 3. Checkpoint — Verificar sintaxis de los workflows
  - Validar que los archivos YAML son sintácticamente correctos
  - Si `actionlint` está disponible, ejecutarlo contra ambos workflows
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Eliminar el workflow existente y limpiar referencias
  - [x] 4.1 Eliminar el archivo `.github/workflows/azure-deploy.yml`
    - Eliminar el workflow obsoleto que usa comandos Docker manuales y secretos antiguos (`ACR_NAME`, `ACR_USERNAME`, `ACR_PASSWORD`, `AZURE_WEBAPP_NAME`)
    - _Requisitos: 7.1, 7.2_

- [x] 5. Actualizar documentación del proyecto
  - [x] 5.1 Agregar sección de CI/CD en `infra/README.md`
    - Agregar sección "Integración Continua y Despliegue Continuo (CI/CD)" en español
    - Incluir diagrama de flujo Mermaid del proceso CI/CD completo (PR → CI → merge → CD → despliegue)
    - Documentar la tabla de GitHub Secrets requeridos con nombre, descripción y formato esperado (sin valores reales)
    - Incluir instrucciones para crear el Service Principal de Azure y configurar `AZURE_CREDENTIALS` en GitHub
    - Describir la estrategia de ramas: `develop` → dev, `main` → prod
    - Incluir instrucciones para ejecutar los workflows manualmente mediante `workflow_dispatch`
    - _Requisitos: 4.5, 7.3, 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 5.2 Actualizar la sección "Despliegue" del `README.md` principal
    - Agregar subsección sobre CI/CD con GitHub Actions en español
    - Mencionar los dos workflows (`ci.yml` y `cd.yml`) y su propósito
    - Eliminar cualquier referencia al workflow anterior `azure-deploy.yml`
    - Referenciar `infra/README.md` para documentación detallada de CI/CD y configuración de secretos
    - _Requisitos: 7.3, 8.1_

- [x] 6. Checkpoint final — Validación completa
  - Verificar que `.github/workflows/ci.yml` y `.github/workflows/cd.yml` existen y son YAML válido
  - Verificar que `.github/workflows/azure-deploy.yml` fue eliminado
  - Verificar que `infra/README.md` contiene la sección de CI/CD con todos los secretos documentados
  - Verificar que `README.md` fue actualizado con referencias a los nuevos workflows
  - Ensure all tests pass, ask the user if questions arise.

## Notas

- Esta feature consiste en archivos de configuración YAML declarativos, no código de aplicación ejecutable
- No aplica property-based testing — la validación se realiza mediante linting de YAML, `actionlint` y ejecución real en GitHub
- El script `infra/deploy.sh` ya está implementado y se reutiliza en el workflow CD
- La plantilla Bicep `infra/main.bicep` ya está implementada
- Los secretos de GitHub deben configurarse manualmente en el repositorio antes de ejecutar los workflows
- La documentación debe escribirse en español
- Cada tarea referencia requisitos específicos del documento de requisitos para trazabilidad
