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
