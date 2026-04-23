# Documento de Requisitos — GitHub Actions CI/CD para MPRA

## Introducción

Este documento define los requisitos para implementar pipelines de Integración Continua (CI) y Despliegue Continuo (CD) mediante GitHub Actions para la aplicación MPRA (Modelo Predictivo de Riesgo Académico). El proyecto ya cuenta con infraestructura Azure definida en Bicep (`infra/main.bicep`) y un script de despliegue (`infra/deploy.sh`). El objetivo es automatizar la validación de código, ejecución de tests y despliegue a Azure Container Apps en entornos separados (dev y prod) según la rama de destino, reemplazando el workflow existente (`azure-deploy.yml`) que está desactualizado y no cubre CI ni entornos múltiples.

## Glosario

- **GitHub_Actions**: Plataforma de automatización de CI/CD integrada en GitHub que ejecuta workflows definidos en archivos YAML dentro del directorio `.github/workflows/`
- **Workflow_CI**: Workflow de GitHub Actions que valida el código fuente, ejecuta tests y verifica la plantilla Bicep en cada Pull Request
- **Workflow_CD**: Workflow de GitHub Actions que despliega automáticamente la aplicación a Azure Container Apps cuando se fusiona código a una rama protegida
- **GitHub_Secrets**: Almacén seguro de GitHub para credenciales y valores sensibles que se inyectan como variables de entorno en los workflows
- **Bicep_Template**: Archivo de infraestructura como código ubicado en `infra/main.bicep` que define los recursos de Azure
- **Deploy_Script**: Script Bash ubicado en `infra/deploy.sh` que orquesta el despliegue completo en Azure
- **Azure_Credentials**: Credenciales de un Service Principal de Azure en formato JSON, utilizadas para autenticar GitHub Actions contra Azure
- **Entorno_Dev**: Entorno de desarrollo desplegado cuando se fusiona código a la rama `develop`
- **Entorno_Prod**: Entorno de producción desplegado cuando se fusiona código a la rama `main`
- **Test_Suite**: Conjunto de tests del proyecto ejecutados con `python3 -m pytest tests/ -v --cov=app`
- **Container_App**: Instancia de Azure Container Apps donde se ejecuta el backend FastAPI de MPRA

## Requisitos

### Requisito 1: Workflow de Integración Continua (CI)

**Historia de Usuario:** Como desarrollador, quiero que cada Pull Request ejecute automáticamente validaciones de código y tests, para detectar errores antes de fusionar cambios a las ramas protegidas.

#### Criterios de Aceptación

1. WHEN un Pull Request se abre o actualiza contra las ramas `main` o `develop`, THE Workflow_CI SHALL ejecutarse automáticamente
2. THE Workflow_CI SHALL instalar las dependencias de Python definidas en `requirements.txt` usando Python 3.12
3. THE Workflow_CI SHALL ejecutar la Test_Suite completa con el comando `python3 -m pytest tests/ -v --cov=app`
4. IF la Test_Suite falla con uno o más tests en estado de error, THEN THE Workflow_CI SHALL marcar el Pull Request como fallido
5. THE Workflow_CI SHALL validar la sintaxis de la Bicep_Template ejecutando `az bicep build --file infra/main.bicep`
6. IF la validación de la Bicep_Template falla, THEN THE Workflow_CI SHALL marcar el Pull Request como fallido
7. THE Workflow_CI SHALL residir en el archivo `.github/workflows/ci.yml`

### Requisito 2: Workflow de Despliegue Continuo (CD) a Entorno Dev

**Historia de Usuario:** Como desarrollador, quiero que al fusionar código a la rama `develop` se despliegue automáticamente al entorno de desarrollo, para validar los cambios en un entorno real antes de promoverlos a producción.

#### Criterios de Aceptación

1. WHEN se fusiona código a la rama `develop`, THE Workflow_CD SHALL ejecutarse automáticamente para el Entorno_Dev
2. THE Workflow_CD SHALL autenticarse en Azure usando las Azure_Credentials almacenadas en GitHub_Secrets
3. THE Workflow_CD SHALL ejecutar el Deploy_Script con el parámetro de entorno `dev` y la región configurada en GitHub_Secrets
4. THE Workflow_CD SHALL pasar la contraseña de la base de datos y la clave JWT desde GitHub_Secrets al Deploy_Script mediante los flags `-p` y `-j`
5. WHEN el despliegue se completa exitosamente, THE Workflow_CD SHALL verificar que el endpoint `/health` del Container_App del Entorno_Dev responde con estado HTTP 200
6. IF el despliegue falla en cualquier paso, THEN THE Workflow_CD SHALL marcar la ejecución como fallida y mostrar los logs del error
7. THE Workflow_CD SHALL residir en el archivo `.github/workflows/cd.yml`

### Requisito 3: Workflow de Despliegue Continuo (CD) a Entorno Prod

**Historia de Usuario:** Como desarrollador, quiero que al fusionar código a la rama `main` se despliegue automáticamente al entorno de producción, para que los cambios validados estén disponibles para los usuarios finales.

#### Criterios de Aceptación

1. WHEN se fusiona código a la rama `main`, THE Workflow_CD SHALL ejecutarse automáticamente para el Entorno_Prod
2. THE Workflow_CD SHALL autenticarse en Azure usando las Azure_Credentials almacenadas en GitHub_Secrets
3. THE Workflow_CD SHALL ejecutar el Deploy_Script con el parámetro de entorno `prod` y la región configurada en GitHub_Secrets
4. THE Workflow_CD SHALL pasar la contraseña de la base de datos y la clave JWT desde GitHub_Secrets al Deploy_Script mediante los flags `-p` y `-j`
5. WHEN el despliegue se completa exitosamente, THE Workflow_CD SHALL verificar que el endpoint `/health` del Container_App del Entorno_Prod responde con estado HTTP 200
6. IF el despliegue falla en cualquier paso, THEN THE Workflow_CD SHALL marcar la ejecución como fallida y mostrar los logs del error
7. THE Workflow_CD SHALL ejecutar la Test_Suite como paso previo al despliegue para garantizar que el código es válido antes de desplegarlo a producción

### Requisito 4: Gestión de Secretos con GitHub Secrets

**Historia de Usuario:** Como desarrollador, quiero que las credenciales y valores sensibles se gestionen de forma segura mediante GitHub Secrets, para que no se expongan en el código fuente ni en los logs de los workflows.

#### Criterios de Aceptación

1. THE Workflow_CD SHALL utilizar los siguientes GitHub_Secrets: `AZURE_CREDENTIALS`, `DB_PASSWORD_DEV`, `DB_PASSWORD_PROD`, `JWT_SECRET_DEV`, `JWT_SECRET_PROD`, `AZURE_REGION`
2. THE Workflow_CI SHALL utilizar el GitHub_Secret `AZURE_CREDENTIALS` para autenticarse al validar la Bicep_Template
3. THE Workflow_CD SHALL referenciar los secretos específicos del entorno según la rama que activó el despliegue (secretos con sufijo `_DEV` para la rama `develop`, secretos con sufijo `_PROD` para la rama `main`)
4. THE GitHub_Actions workflows SHALL enmascarar los valores de los secretos en los logs de ejecución utilizando el mecanismo nativo de GitHub Actions
5. THE documentación del proyecto SHALL incluir una lista de todos los GitHub_Secrets requeridos con su descripción y formato esperado, sin incluir valores reales

### Requisito 5: Ejecución de Tests en el Pipeline CI

**Historia de Usuario:** Como desarrollador, quiero que los tests unitarios, de integración y de propiedades se ejecuten automáticamente en el pipeline CI, para garantizar la calidad del código antes de fusionar cambios.

#### Criterios de Aceptación

1. THE Workflow_CI SHALL configurar un servicio de PostgreSQL como contenedor auxiliar para los tests de integración
2. THE Workflow_CI SHALL configurar las variables de entorno necesarias para que la Test_Suite se conecte al servicio de PostgreSQL del pipeline (DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, JWT_SECRET_KEY)
3. THE Workflow_CI SHALL ejecutar las migraciones de Alembic (`alembic upgrade head`) contra la base de datos del pipeline antes de ejecutar la Test_Suite
4. THE Workflow_CI SHALL generar un reporte de cobertura de código y publicarlo como artefacto del workflow
5. IF la cobertura de código cae por debajo del umbral configurado, THEN THE Workflow_CI SHALL emitir una advertencia en el resumen del workflow

### Requisito 6: Validación de Infraestructura en CI

**Historia de Usuario:** Como desarrollador, quiero que los cambios en la plantilla Bicep se validen automáticamente en cada Pull Request, para detectar errores de sintaxis o configuración antes de intentar un despliegue.

#### Criterios de Aceptación

1. WHEN un Pull Request contiene cambios en archivos dentro del directorio `infra/`, THE Workflow_CI SHALL ejecutar la validación de la Bicep_Template
2. THE Workflow_CI SHALL instalar Azure CLI y la extensión Bicep en el runner para ejecutar la validación
3. THE Workflow_CI SHALL ejecutar `az bicep build --file infra/main.bicep` para verificar que la plantilla compila sin errores
4. IF la compilación de la Bicep_Template produce errores, THEN THE Workflow_CI SHALL mostrar los errores detallados en el log del workflow

### Requisito 7: Reemplazo del Workflow Existente

**Historia de Usuario:** Como desarrollador, quiero que el workflow existente `azure-deploy.yml` sea reemplazado por los nuevos workflows de CI/CD, para evitar conflictos y mantener una única fuente de verdad para la automatización.

#### Criterios de Aceptación

1. WHEN los nuevos workflows de CI y CD estén implementados, THE archivo `.github/workflows/azure-deploy.yml` SHALL ser eliminado del repositorio
2. THE Workflow_CD SHALL replicar la funcionalidad de despliegue del workflow existente utilizando el Deploy_Script en lugar de comandos Docker manuales
3. THE documentación del proyecto SHALL actualizarse para reflejar los nuevos workflows y eliminar referencias al workflow anterior

### Requisito 8: Documentación de los Workflows CI/CD

**Historia de Usuario:** Como desarrollador, quiero documentación clara sobre los workflows de CI/CD, para que cualquier miembro del equipo pueda entender el proceso de automatización y configurar los secretos necesarios.

#### Criterios de Aceptación

1. THE documentación SHALL incluir un diagrama de flujo que muestre el proceso completo de CI/CD desde el Pull Request hasta el despliegue en producción
2. THE documentación SHALL listar todos los GitHub_Secrets requeridos con su nombre, descripción y formato esperado
3. THE documentación SHALL incluir instrucciones para crear el Service Principal de Azure y configurar las Azure_Credentials en GitHub
4. THE documentación SHALL describir la estrategia de ramas: `develop` para despliegues a dev y `main` para despliegues a producción
5. THE documentación SHALL incluir instrucciones para ejecutar los workflows manualmente mediante `workflow_dispatch`
