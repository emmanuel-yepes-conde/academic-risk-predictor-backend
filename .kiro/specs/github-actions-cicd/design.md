# Documento de Diseño — GitHub Actions CI/CD para MPRA

## Resumen

Este documento describe el diseño técnico para implementar dos workflows de GitHub Actions que automatizan la Integración Continua (CI) y el Despliegue Continuo (CD) de la aplicación MPRA. El diseño reemplaza el workflow existente `azure-deploy.yml` — que solo despliega a producción mediante comandos Docker manuales — por dos workflows separados y especializados que siguen la estrategia Gitflow del proyecto.

**Decisiones clave:**
- **Dos workflows separados** (`ci.yml` y `cd.yml`) en lugar de uno monolítico, para mantener responsabilidades claras y tiempos de ejecución independientes.
- **Reutilización del script `infra/deploy.sh`** existente en el CD, evitando duplicar lógica de despliegue en YAML.
- **PostgreSQL 16 como service container** en CI para ejecutar tests de integración con una base de datos real.
- **Selección de secretos por entorno** usando expresiones condicionales de GitHub Actions según la rama que dispara el CD.

## Arquitectura

### Diagrama de Flujo CI/CD

```mermaid
flowchart TD
    subgraph PR["Pull Request"]
        A["PR abierto/actualizado\ncontra main o develop"] --> CI
    end

    subgraph CI["Workflow CI (ci.yml)"]
        B["Checkout código"] --> C["Setup Python 3.12"]
        C --> D["Instalar dependencias"]
        D --> E["Iniciar PostgreSQL 16\n(service container)"]
        E --> F["Ejecutar migraciones\nAlembic"]
        F --> G["Ejecutar Test Suite\npytest + cobertura"]
        G --> H["Publicar reporte\nde cobertura"]
        H --> I["Validar Bicep\naz bicep build"]
    end

    subgraph MERGE["Merge a rama protegida"]
        J["Merge a develop"] --> CD_DEV
        K["Merge a main"] --> CD_PROD
    end

    subgraph CD_DEV["CD → Dev"]
        L1["Checkout"] --> L2["Azure Login"]
        L2 --> L3["deploy.sh -e dev"]
        L3 --> L4["Health check\n/health → 200"]
    end

    subgraph CD_PROD["CD → Prod"]
        M1["Checkout"] --> M2["Setup Python 3.12"]
        M2 --> M3["Tests previos"]
        M3 --> M4["Azure Login"]
        M4 --> M5["deploy.sh -e prod"]
        M5 --> M6["Health check\n/health → 200"]
    end

    CI -->|"✅ CI pasa"| MERGE
    CI -->|"❌ CI falla"| BLOCK["PR bloqueado"]
```

### Diagrama de Secretos por Entorno

```mermaid
flowchart LR
    subgraph SECRETS["GitHub Secrets"]
        S1["AZURE_CREDENTIALS"]
        S2["AZURE_REGION"]
        S3["DB_PASSWORD_DEV"]
        S4["DB_PASSWORD_PROD"]
        S5["JWT_SECRET_DEV"]
        S6["JWT_SECRET_PROD"]
    end

    subgraph CD_FLOW["Workflow CD"]
        DEV["develop → dev"]
        PROD["main → prod"]
    end

    S1 --> DEV
    S1 --> PROD
    S2 --> DEV
    S2 --> PROD
    S3 --> DEV
    S4 --> PROD
    S5 --> DEV
    S6 --> PROD
```

## Componentes e Interfaces

### 1. Workflow CI (`.github/workflows/ci.yml`)

**Responsabilidad:** Validar la calidad del código en cada Pull Request antes de permitir el merge.

**Trigger:**
- `pull_request` contra ramas `main` y `develop` (eventos `opened`, `synchronize`, `reopened`)
- `workflow_dispatch` para ejecución manual

**Job: `test`**

| Paso | Acción | Detalle |
|------|--------|---------|
| Checkout | `actions/checkout@v4` | Clona el repositorio |
| Setup Python | `actions/setup-python@v5` | Python 3.12 |
| Cache pip | `actions/cache@v4` | Cache de `~/.cache/pip` con key basada en `requirements.txt` |
| Instalar dependencias | `pip install -r requirements.txt` | Todas las dependencias incluyendo test |
| Esperar PostgreSQL | Script de espera | `pg_isready` en loop hasta que el service container esté listo |
| Migraciones | `alembic upgrade head` | Aplica migraciones contra la BD del pipeline |
| Tests + cobertura | `pytest tests/ -v --cov=app --cov-report=xml --cov-report=term-missing` | Ejecuta toda la suite |
| Publicar cobertura | `actions/upload-artifact@v4` | Sube `coverage.xml` como artefacto |
| Advertencia cobertura | Script condicional | Emite warning en el summary si cobertura < 80% |

**Service container PostgreSQL:**
```yaml
services:
  postgres:
    image: postgres:16
    env:
      POSTGRES_USER: mpra_test
      POSTGRES_PASSWORD: mpra_test_pass
      POSTGRES_DB: mpra_test_db
    ports:
      - 5432:5432
    options: >-
      --health-cmd="pg_isready -U mpra_test"
      --health-interval=10s
      --health-timeout=5s
      --health-retries=5
```

**Variables de entorno para tests:**
```yaml
env:
  DB_HOST: localhost
  DB_PORT: 5432
  DB_USER: mpra_test
  DB_PASSWORD: mpra_test_pass
  DB_NAME: mpra_test_db
  JWT_SECRET_KEY: test-jwt-secret-key-for-ci
  DATABASE_URL: postgresql+asyncpg://mpra_test:mpra_test_pass@localhost:5432/mpra_test_db
```

**Job: `validate-bicep`**

| Paso | Acción | Detalle |
|------|--------|---------|
| Checkout | `actions/checkout@v4` | Clona el repositorio |
| Azure CLI Login | `azure/login@v2` | Autenticación con `AZURE_CREDENTIALS` |
| Validar Bicep | `az bicep build --file infra/main.bicep` | Compila y valida sintaxis |

**Decisión de diseño:** La validación de Bicep se ejecuta siempre en el CI (no solo cuando cambian archivos en `infra/`). Esto simplifica la configuración y garantiza que la plantilla siempre sea válida, ya que el costo de ejecutar `az bicep build` es mínimo (< 10 segundos). Si en el futuro se desea optimizar, se puede agregar un filtro `paths` al trigger.

### 2. Workflow CD (`.github/workflows/cd.yml`)

**Responsabilidad:** Desplegar automáticamente a Azure Container Apps cuando se fusiona código a una rama protegida.

**Trigger:**
- `push` a ramas `main` y `develop`
- `workflow_dispatch` con input para seleccionar entorno (`dev` o `prod`)

**Job: `deploy`**

| Paso | Acción | Detalle |
|------|--------|---------|
| Determinar entorno | Script condicional | Mapea rama → entorno (`develop`→`dev`, `main`→`prod`) |
| Checkout | `actions/checkout@v4` | Clona el repositorio |
| Tests previos (solo prod) | Setup Python + pytest | Ejecuta tests antes de desplegar a producción |
| Azure Login | `azure/login@v2` | Autenticación con `AZURE_CREDENTIALS` |
| Ejecutar deploy.sh | `bash infra/deploy.sh` | Con flags `-e`, `-r`, `-p`, `-j` según entorno |
| Health check | `curl` con reintentos | Verifica `/health` responde HTTP 200 |

**Selección de secretos por entorno:**

La selección de secretos se realiza mediante expresiones condicionales de GitHub Actions. Se define una variable de entorno `ENV_NAME` al inicio del job basada en la rama o el input de `workflow_dispatch`:

```yaml
env:
  ENV_NAME: ${{ github.event_name == 'workflow_dispatch' && github.event.inputs.environment || (github.ref == 'refs/heads/main' && 'prod' || 'dev') }}
```

Luego, los secretos se seleccionan condicionalmente:
```yaml
- name: Ejecutar despliegue
  run: |
    bash infra/deploy.sh \
      -e ${{ env.ENV_NAME }} \
      -r ${{ secrets.AZURE_REGION }} \
      -p "${{ env.ENV_NAME == 'prod' && secrets.DB_PASSWORD_PROD || secrets.DB_PASSWORD_DEV }}" \
      -j "${{ env.ENV_NAME == 'prod' && secrets.JWT_SECRET_PROD || secrets.JWT_SECRET_DEV }}"
```

**Health check con reintentos:**

```yaml
- name: Verificar health check
  run: |
    FQDN=$(az containerapp show \
      --name "ca-mpra-${{ env.ENV_NAME }}" \
      --resource-group "rg-mpra-${{ env.ENV_NAME }}" \
      --query 'properties.configuration.ingress.fqdn' -o tsv)
    
    for i in $(seq 1 10); do
      STATUS=$(curl -s -o /dev/null -w "%{http_code}" "https://${FQDN}/health" || true)
      if [ "$STATUS" = "200" ]; then
        echo "✅ Health check exitoso (intento $i)"
        exit 0
      fi
      echo "⏳ Intento $i/10 — HTTP $STATUS, esperando 15s..."
      sleep 15
    done
    echo "❌ Health check falló después de 10 intentos"
    exit 1
```

**Decisión de diseño:** Se usan 10 reintentos con 15 segundos de espera (total ~2.5 minutos) porque Azure Container Apps con `minReplicas: 0` necesita tiempo para escalar desde cero (cold start) después de un despliegue.

### 3. Eliminación del Workflow Existente

El archivo `.github/workflows/azure-deploy.yml` será eliminado. El workflow actual:
- Solo despliega a producción (rama `main`)
- Usa comandos Docker manuales (`docker build`, `docker push`) en lugar del script `deploy.sh`
- No ejecuta tests
- No soporta múltiples entornos
- Usa secretos obsoletos (`ACR_NAME`, `ACR_USERNAME`, `ACR_PASSWORD`, `AZURE_WEBAPP_NAME`)

Los nuevos workflows cubren toda esta funcionalidad y la extienden significativamente.

## Modelos de Datos

### GitHub Secrets Requeridos

| Secreto | Descripción | Formato |
|---------|-------------|---------|
| `AZURE_CREDENTIALS` | Credenciales del Service Principal de Azure en formato JSON | `{"clientId":"...","clientSecret":"...","subscriptionId":"...","tenantId":"..."}` |
| `AZURE_REGION` | Región de Azure para los despliegues | String (ej: `eastus`, `westeurope`) |
| `DB_PASSWORD_DEV` | Contraseña del administrador PostgreSQL para entorno dev | String con requisitos de complejidad de Azure |
| `DB_PASSWORD_PROD` | Contraseña del administrador PostgreSQL para entorno prod | String con requisitos de complejidad de Azure |
| `JWT_SECRET_DEV` | Clave secreta JWT para entorno dev | String largo y aleatorio (≥ 32 caracteres) |
| `JWT_SECRET_PROD` | Clave secreta JWT para entorno prod | String largo y aleatorio (≥ 32 caracteres) |

### Mapeo Rama → Entorno → Secretos

| Rama | Entorno | Secreto DB | Secreto JWT |
|------|---------|------------|-------------|
| `develop` | `dev` | `DB_PASSWORD_DEV` | `JWT_SECRET_DEV` |
| `main` | `prod` | `DB_PASSWORD_PROD` | `JWT_SECRET_PROD` |

### Artefactos Generados

| Artefacto | Workflow | Contenido | Retención |
|-----------|----------|-----------|-----------|
| `coverage-report` | CI | `coverage.xml` con reporte de cobertura | 30 días (default) |

## Manejo de Errores

### Workflow CI

| Escenario de error | Comportamiento | Impacto |
|-------------------|----------------|---------|
| Fallo en instalación de dependencias | Job falla, PR marcado como fallido | PR no se puede fusionar |
| PostgreSQL service container no inicia | Job falla por timeout en health check | PR no se puede fusionar |
| Migraciones Alembic fallan | Job falla, logs muestran error de migración | PR no se puede fusionar |
| Uno o más tests fallan | Job falla, pytest muestra tests fallidos | PR no se puede fusionar |
| Validación Bicep falla | Job `validate-bicep` falla con errores detallados | PR no se puede fusionar |
| `AZURE_CREDENTIALS` no configurado | Job `validate-bicep` falla en login | PR no se puede fusionar |

### Workflow CD

| Escenario de error | Comportamiento | Impacto |
|-------------------|----------------|---------|
| `AZURE_CREDENTIALS` inválidas | Azure login falla, job se detiene | Despliegue no se ejecuta |
| `deploy.sh` falla en cualquier paso | Script retorna exit code ≠ 0, job falla | Despliegue incompleto, logs visibles |
| Health check falla después de 10 reintentos | Job falla con mensaje de error | Despliegue completó pero app no responde |
| Tests previos fallan (solo prod) | Job falla antes del despliegue | Código no se despliega a producción |
| Secreto de entorno faltante | Variable vacía, `deploy.sh` falla en validación | Despliegue no se ejecuta |

### Estrategia de Notificación

GitHub Actions notifica automáticamente por email al autor del commit cuando un workflow falla. Adicionalmente, el estado del workflow se refleja como check en el PR (para CI) o en el commit (para CD).

## Estrategia de Testing

### Evaluación de Property-Based Testing

Esta feature consiste en archivos de configuración YAML para GitHub Actions y documentación. **No hay lógica de aplicación, funciones puras ni transformaciones de datos** que se beneficien de property-based testing. Los workflows son declarativos — definen pipelines de CI/CD, no código ejecutable con inputs/outputs variables.

**PBT no aplica** para esta feature por las siguientes razones:
- Los workflows de GitHub Actions son **configuración declarativa**, no funciones con entradas/salidas
- La validación de los workflows se hace mediante **ejecución real en GitHub** o **linting estático**
- No existe un espacio de inputs significativo para generar variaciones

### Estrategia de Validación

En lugar de tests automatizados tradicionales, la validación de esta feature se realiza mediante:

1. **Validación de sintaxis YAML**: Verificar que los archivos YAML son válidos
2. **Linting de workflows**: Usar `actionlint` (opcional) para validar la estructura de los workflows
3. **Ejecución manual**: Usar `workflow_dispatch` para probar los workflows en un entorno real
4. **Revisión de código**: Code review del YAML para verificar lógica de condiciones y secretos
5. **Smoke test post-despliegue**: El health check integrado en el CD verifica que el despliegue fue exitoso

### Checklist de Validación Manual

- [ ] CI se ejecuta automáticamente al abrir un PR contra `develop`
- [ ] CI se ejecuta automáticamente al abrir un PR contra `main`
- [ ] CI falla correctamente cuando un test falla
- [ ] CI falla correctamente cuando la validación Bicep falla
- [ ] CD se ejecuta al fusionar a `develop` y despliega a dev
- [ ] CD se ejecuta al fusionar a `main` y despliega a prod
- [ ] CD ejecuta tests previos solo para despliegues a producción
- [ ] Health check verifica correctamente el endpoint `/health`
- [ ] `workflow_dispatch` permite ejecutar ambos workflows manualmente
- [ ] Los secretos no se exponen en los logs
- [ ] El workflow `azure-deploy.yml` fue eliminado
