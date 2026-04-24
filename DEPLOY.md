# Despliegue

El proyecto utiliza **GitHub Actions** para CI/CD con despliegue automático en **Azure Container Apps**.

Para la guía completa de configuración (Service Principal, GitHub Secrets, workflows y ejecución manual) consulta [`infra/README.md`](infra/README.md).

## Resumen de workflows

| Workflow | Archivo | Propósito |
|----------|---------|-----------|
| **CI** | `.github/workflows/ci.yml` | Tests, cobertura y validación de plantilla Bicep en PRs contra `main` o `develop` |
| **CD** | `.github/workflows/cd.yml` | Despliegue automático a Azure al fusionar a `develop` (dev) o `main` (prod) |

## Estrategia de ramas

- Merge a `develop` → despliegue automático a **dev**
- Merge a `main` → despliegue automático a **prod** (previa ejecución de tests)
