# Metodología TDD (Test-Driven Development)

## Principio Fundamental
Todo código nuevo o modificado debe seguir el ciclo **Red → Green → Refactor**:

1. **Red:** Escribir un test que falle porque la funcionalidad aún no existe.
2. **Green:** Escribir el código mínimo necesario para que el test pase.
3. **Refactor:** Mejorar el código (eliminar duplicación, mejorar nombres, simplificar) sin romper los tests.

No se escribe código de producción sin un test que lo justifique.

## Estructura de Tests del Proyecto

```
tests/
├── conftest.py                  # Fixtures compartidos (client, stubs de BD y ML)
├── unit/                        # Tests unitarios (sin I/O, sin BD)
│   ├── test_config.py
│   ├── test_security.py
│   └── test_<service>.py
├── integration/                 # Tests de integración (con BD real o mock de sesión)
│   ├── conftest.py
│   └── test_<repository>.py
└── property/                    # Tests basados en propiedades (Hypothesis)
    └── test_<feature>_property.py
```

## Niveles de Test

### Tests Unitarios (`tests/unit/`)
- Prueban una sola unidad (función, método, clase) de forma aislada.
- **Sin I/O:** no tocan base de datos, red ni sistema de archivos.
- Usan `unittest.mock` / `AsyncMock` para dependencias externas.
- Deben ejecutarse en milisegundos.

```python
# Ejemplo: test unitario de un servicio
from unittest.mock import AsyncMock
import pytest

@pytest.mark.anyio
async def test_create_user_hashes_password():
    mock_repo = AsyncMock()
    mock_repo.get_by_email.return_value = None
    service = UserService(mock_repo)

    result = await service.create_user(UserCreate(email="a@b.com", password="secret", role="student"))

    assert result.password != "secret"
```

### Tests de Integración (`tests/integration/`)
- Validan la interacción entre capas (repositorio ↔ BD, endpoint ↔ servicio).
- Usan el `AsyncClient` con `ASGITransport` del `conftest.py` compartido.
- Pueden usar una sesión mock o una BD de test según el caso.

```python
# Ejemplo: test de integración de endpoint
@pytest.mark.anyio
async def test_create_user_returns_201(client):
    response = await client.post("/api/v1/users", json={
        "email": "nuevo@uni.edu",
        "password": "segura123",
        "role": "student"
    })
    assert response.status_code == 201
```

### Tests de Propiedades (`tests/property/`)
- Usan **Hypothesis** para generar datos aleatorios y verificar invariantes.
- Ideales para validar reglas de negocio que deben cumplirse para cualquier entrada válida.
- Nombrar archivos como `test_<feature>_property.py`.

```python
# Ejemplo: propiedad de umbrales de riesgo
from hypothesis import given, strategies as st

@given(probabilidad=st.floats(min_value=0.0, max_value=1.0))
def test_clasificacion_riesgo_siempre_valida(probabilidad):
    nivel = clasificar_riesgo(probabilidad)
    assert nivel in ("bajo", "medio", "alto")
```

## Flujo TDD Paso a Paso

### Para un nuevo endpoint:
1. **Red:** Crear test en `tests/integration/` o `tests/unit/` que haga la petición HTTP y verifique status code + response body esperado. Ejecutar → debe fallar.
2. **Green:** Crear schema Pydantic → crear método en servicio → crear endpoint en router → registrar router. Ejecutar test → debe pasar.
3. **Refactor:** Extraer lógica duplicada, mejorar nombres, agregar validaciones de negocio con sus tests correspondientes.

### Para una nueva regla de negocio:
1. **Red:** Escribir test que valide la regla (ej: "un profesor solo ve estudiantes de sus cursos"). Ejecutar → debe fallar.
2. **Green:** Implementar la validación en la capa de servicio. Ejecutar → debe pasar.
3. **Refactor:** Verificar que no se rompieron otros tests. Agregar test de propiedad si aplica.

### Para un bug fix:
1. **Red:** Escribir un test que reproduzca el bug exacto. Ejecutar → debe fallar (confirmando el bug).
2. **Green:** Corregir el código. Ejecutar → debe pasar.
3. **Refactor:** Verificar que la corrección no introdujo regresiones.

## Convenciones de Naming

| Tipo | Patrón de nombre | Ejemplo |
|------|-------------------|---------|
| Archivo unit | `test_<modulo>.py` | `test_user_service.py` |
| Archivo integration | `test_<recurso>_repository.py` | `test_consent_repository.py` |
| Archivo property | `test_<feature>_property.py` | `test_consent_gate.py` |
| Función test | `test_<accion>_<resultado_esperado>` | `test_create_user_returns_201` |
| Función test negativo | `test_<accion>_<condicion>_<error>` | `test_create_user_duplicate_email_returns_409` |

## Comandos

```bash
# Ejecutar todos los tests con cobertura
python3 -m pytest tests/ -v --cov=app

# Solo tests unitarios
python3 -m pytest tests/unit/ -v

# Solo tests de integración
python3 -m pytest tests/integration/ -v

# Solo tests de propiedades
python3 -m pytest tests/property/ -v

# Un test específico
python3 -m pytest tests/unit/test_user_service.py::test_create_user_hashes_password -v

# Con reporte de cobertura HTML
python3 -m pytest tests/ --cov=app --cov-report=html
```

## Reglas Obligatorias

- **No se hace merge de código sin tests.** Todo PR debe incluir tests que cubran la funcionalidad nueva o modificada.
- **Cobertura mínima:** apuntar a ≥ 80% de cobertura en la capa de servicios y endpoints.
- **Tests independientes:** cada test debe poder ejecutarse de forma aislada, sin depender del orden de ejecución.
- **Fixtures compartidos:** usar `conftest.py` para fixtures reutilizables (client, mock_session, etc.). No duplicar setup entre archivos.
- **Mocks explícitos:** mockear solo las dependencias directas de la unidad bajo test. No mockear la unidad misma.
- **Assertions claros:** un test debe tener un propósito claro. Preferir múltiples tests pequeños sobre un test gigante con muchos asserts.

## Checklist TDD al completar una tarea
- [ ] ¿Se escribieron los tests antes del código de producción?
- [ ] ¿Todos los tests pasan (`pytest` verde)?
- [ ] ¿Se cubrieron los casos positivos y negativos?
- [ ] ¿Se agregaron tests de propiedad para reglas de negocio críticas?
- [ ] ¿Los tests son independientes y reproducibles?
- [ ] ¿La cobertura de la funcionalidad nueva es ≥ 80%?
