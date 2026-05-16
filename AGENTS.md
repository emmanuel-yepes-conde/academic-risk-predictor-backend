# AGENTS.md — Academic Risk Predictor Backend

Instrucciones permanentes para el agente de IA en este proyecto.

---

## Glosario — Regla de actualización

El archivo [`docs/GLOSSARY.md`](docs/GLOSSARY.md) es la fuente canónica de terminología del proyecto.

**Debes actualizarlo automáticamente cada vez que realices cualquiera de los siguientes cambios:**

- Agregar o modificar un modelo ORM (`app/infrastructure/models/`)
- Agregar o modificar un schema / DTO (`app/application/schemas/`)
- Agregar o modificar un enum (`app/domain/enums.py`)
- Agregar o modificar un endpoint de la API (`app/api/v1/endpoints/`)
- Agregar o modificar un servicio (`app/application/services/` o `app/services/`)
- Agregar o modificar una interfaz de repositorio (`app/domain/interfaces/`)
- Agregar variables de entorno nuevas a la configuración (`app/core/config.py`)
- Agregar una migración de base de datos (`alembic/versions/`)
- Cambiar reglas de negocio, umbrales, o lógica de acceso (RBAC)

**Cómo actualizar el glosario:**

1. Identifica la sección correspondiente en `docs/GLOSSARY.md`.
2. Agrega, modifica o elimina la entrada relevante.
3. Si introduces un concepto que no encaja en ninguna sección existente, crea una nueva sección al final.
4. Mantén el formato de tablas Markdown existente.
5. No borres entradas de términos que sigan siendo válidos aunque cambien de ubicación en el código.

**Cuándo NO actualizar el glosario:**

- Cambios de formato, linting o estilo sin impacto semántico.
- Refactors internos que no cambian la interfaz ni la terminología visible.
- Cambios solo en tests.

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
|------|----------|
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
