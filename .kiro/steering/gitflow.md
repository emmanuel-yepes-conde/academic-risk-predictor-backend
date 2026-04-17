# Estrategia de Ramas — Gitflow

## Modelo de Ramas

El proyecto sigue el modelo **Gitflow** para gestionar el ciclo de vida del código:

```
main ─────────────────────────────────────────── (producción)
  │
  └── develop ────────────────────────────────── (integración)
        │         │         │
        └── feature/xxx     └── feature/yyy ──── (funcionalidades)
        │
        └── bugfix/xxx ──────────────────────── (correcciones)
        │
        └── release/x.y.z ──────────────────── (preparación de release)
        │
        └── hotfix/x.y.z ───────────────────── (parches urgentes en prod)
```

## Ramas Principales

| Rama | Propósito | Protegida | Despliegue |
|------|-----------|-----------|------------|
| `main` | Código en producción, siempre estable | Sí | Automático a **prod** |
| `develop` | Rama de integración para el próximo release | Sí | Automático a **dev** |

## Ramas de Soporte

| Tipo | Prefijo | Se crea desde | Se fusiona a | Ejemplo |
|------|---------|---------------|--------------|---------|
| Feature | `feature/` | `develop` | `develop` | `feature/user-authentication` |
| Bugfix | `bugfix/` | `develop` | `develop` | `bugfix/login-validation` |
| Release | `release/` | `develop` | `main` + `develop` | `release/1.2.0` |
| Hotfix | `hotfix/` | `main` | `main` + `develop` | `hotfix/1.2.1` |

## Flujo de Trabajo

### Nueva funcionalidad (Feature)
1. Crear rama desde `develop`: `git checkout -b feature/mi-feature develop`
2. Desarrollar y hacer commits siguiendo TDD
3. Abrir Pull Request hacia `develop`
4. CI ejecuta tests y validaciones automáticamente
5. Code review + aprobación
6. Merge a `develop` → despliegue automático a **dev**

### Corrección de bug (Bugfix)
1. Crear rama desde `develop`: `git checkout -b bugfix/mi-fix develop`
2. Escribir test que reproduzca el bug (Red)
3. Corregir el bug (Green)
4. Abrir Pull Request hacia `develop`
5. Merge a `develop` → despliegue automático a **dev**

### Preparación de release
1. Crear rama desde `develop`: `git checkout -b release/1.2.0 develop`
2. Ajustes finales: versión, changelog, documentación
3. Abrir Pull Request hacia `main`
4. Merge a `main` → despliegue automático a **prod**
5. Merge de vuelta a `develop` para sincronizar
6. Crear tag de versión: `git tag -a v1.2.0 -m "Release 1.2.0"`

### Parche urgente (Hotfix)
1. Crear rama desde `main`: `git checkout -b hotfix/1.2.1 main`
2. Corregir el problema crítico
3. Abrir Pull Request hacia `main`
4. Merge a `main` → despliegue automático a **prod**
5. Merge de vuelta a `develop` para sincronizar
6. Crear tag de versión: `git tag -a v1.2.1 -m "Hotfix 1.2.1"`

## Convenciones de Commits

Usar [Conventional Commits](https://www.conventionalcommits.org/):

```
<tipo>(<alcance>): <descripción>

feat(auth): agregar endpoint de refresh token
fix(prediction): corregir cálculo de umbral de riesgo
docs(readme): actualizar instrucciones de despliegue
test(users): agregar tests de propiedad para creación de usuario
chore(deps): actualizar dependencias de seguridad
refactor(services): extraer lógica de validación a módulo compartido
ci(workflows): agregar validación de Bicep en CI
```

| Tipo | Uso |
|------|-----|
| `feat` | Nueva funcionalidad |
| `fix` | Corrección de bug |
| `docs` | Solo documentación |
| `test` | Agregar o modificar tests |
| `refactor` | Cambio de código sin cambiar comportamiento |
| `chore` | Tareas de mantenimiento (deps, config) |
| `ci` | Cambios en CI/CD |
| `style` | Formato, espacios, sin cambio de lógica |
| `perf` | Mejora de rendimiento |

## Reglas Obligatorias

- **No se hace push directo a `main` ni `develop`.** Todo cambio entra vía Pull Request.
- **Todo PR requiere al menos 1 aprobación** antes de fusionar.
- **CI debe pasar** (tests + validaciones) antes de permitir el merge.
- **Eliminar ramas de soporte** después de fusionar el PR.
- **No se hace rebase de ramas públicas** (`main`, `develop`). Usar merge commits.
- **Los tags de versión** solo se crean en `main` y siguen [SemVer](https://semver.org/).

## Integración con CI/CD

| Evento | Workflow | Acción |
|--------|----------|--------|
| PR abierto/actualizado contra `main` o `develop` | CI (`ci.yml`) | Tests + validación Bicep |
| Merge a `develop` | CD (`cd.yml`) | Despliegue a entorno **dev** |
| Merge a `main` | CD (`cd.yml`) | Despliegue a entorno **prod** |
