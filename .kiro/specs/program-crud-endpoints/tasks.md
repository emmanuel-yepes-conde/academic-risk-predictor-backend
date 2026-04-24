# Plan de Implementación: program-crud-endpoints

## Visión General

Implementación incremental de los endpoints `POST /programs` y `PATCH /programs/{program_id}` para la entidad `Program`, siguiendo el orden de dependencias entre capas de Clean Architecture: Dominio → Infraestructura → Aplicación → API. Cada tarea construye sobre la anterior, con tests TDD (Red → Green → Refactor) integrados como sub-tareas. Se reutilizan los patrones establecidos por el CRUD de usuarios (`UserService`, `UserRepository`, `users.py`).

## Tareas

- [x] 1. Agregar schemas Pydantic `ProgramCreate` y `ProgramUpdate`
  - [x] 1.1 Crear `ProgramCreate` en `app/application/schemas/program.py`
    - Campos requeridos: `institution` (str), `degree_type` (str), `program_code` (str), `program_name` (str), `academic_group` (str), `location` (str), `snies_code` (int)
    - Todos con `Field(..., description="...")`
    - Excluir `id` y `created_at` del input
    - _Requisitos: 1.1, 1.2, 1.3_

  - [x] 1.2 Crear `ProgramUpdate` en `app/application/schemas/program.py`
    - Todos los campos opcionales: `institution` (str | None = None), `degree_type` (str | None = None), `program_code` (str | None = None), `program_name` (str | None = None), `academic_group` (str | None = None), `location` (str | None = None), `snies_code` (int | None = None)
    - _Requisitos: 2.1_

  - [x] 1.3 Escribir test de propiedad para validación de `ProgramCreate`
    - **Propiedad 1: ProgramCreate rechaza entrada incompleta**
    - Para cualquier subconjunto de campos requeridos al que le falte al menos uno, construir `ProgramCreate` debe lanzar `ValidationError`
    - Archivo: `tests/property/test_program_crud_property.py`
    - **Valida: Requisitos 1.1, 1.2**

- [x] 2. Extender interfaz `IProgramRepository` con métodos de escritura y búsqueda
  - [x] 2.1 Agregar métodos abstractos en `app/domain/interfaces/program_repository.py`
    - `create(data: dict) -> Program`
    - `update(program_id: UUID, data: ProgramUpdate) -> Program | None`
    - `get_by_program_code(program_code: str) -> Program | None`
    - `get_by_snies_code(snies_code: int) -> Program | None`
    - Agregar import de `ProgramUpdate` con `TYPE_CHECKING`
    - _Requisitos: 3.1, 3.2, 3.3, 3.4_

- [x] 3. Implementar métodos de escritura y búsqueda en `ProgramRepository`
  - [x] 3.1 Agregar soporte de auditoría al constructor de `ProgramRepository`
    - Instanciar `AuditLogRepository(session)` como `self._audit` en `app/infrastructure/repositories/program_repository.py`
    - Seguir el patrón de `UserRepository.__init__`
    - _Requisitos: 4.2, 4.4_

  - [x] 3.2 Implementar `create(data: dict) -> Program`
    - Crear `Program(**data)`, `session.add`, `flush`, `refresh`
    - Registrar `AuditLogCreate` con `operation=INSERT`, `table_name="programs"`, `record_id=program.id`, `new_data=data`
    - Seguir el patrón de `UserRepository.create_from_dict`
    - _Requisitos: 4.1, 4.2_

  - [x] 3.3 Implementar `update(program_id: UUID, data: ProgramUpdate) -> Program | None`
    - Obtener programa con `get_by_id`; si `None` retornar `None`
    - Capturar snapshot de campos actuales como `previous_data`
    - Aplicar `data.model_dump(exclude_unset=True)` con `setattr`
    - `session.add`, `flush`, `refresh`
    - Registrar `AuditLogCreate` con `operation=UPDATE`, `previous_data`, `new_data=updates`
    - Seguir el patrón de `UserRepository.update`
    - _Requisitos: 4.3, 4.4, 4.5_

  - [x] 3.4 Implementar `get_by_program_code(program_code: str) -> Program | None`
    - `SELECT ... WHERE program_code = :code`
    - _Requisitos: 4.6_

  - [x] 3.5 Implementar `get_by_snies_code(snies_code: int) -> Program | None`
    - `SELECT ... WHERE snies_code = :snies`
    - _Requisitos: 4.7_

  - [x] 3.6 Escribir test de propiedad para round-trip de búsqueda
    - **Propiedad 5: Round-trip de búsqueda por campos únicos**
    - Para cualquier programa persistido vía `create`, `get_by_program_code(program.program_code)` y `get_by_snies_code(program.snies_code)` deben retornar un programa con el mismo `id`
    - Archivo: `tests/property/test_program_crud_property.py`
    - **Valida: Requisitos 4.6, 4.7**

  - [x] 3.7 Escribir test de propiedad para audit log de creación
    - **Propiedad 3: Creación registra audit log INSERT**
    - Para cualquier dato válido, `ProgramRepository.create` debe registrar un `AuditLog` con `operation=INSERT`, `table_name="programs"`, y `new_data` coincidiendo con los datos de entrada
    - Archivo: `tests/property/test_program_crud_property.py`
    - **Valida: Requisitos 4.2**

  - [x] 3.8 Escribir test de propiedad para audit log de actualización
    - **Propiedad 4: Actualización registra audit log UPDATE con datos previos y nuevos**
    - Para cualquier programa existente y subconjunto no vacío de campos, `ProgramRepository.update` debe registrar un `AuditLog` con `operation=UPDATE`, `previous_data` con valores anteriores, y `new_data` con valores nuevos
    - Archivo: `tests/property/test_program_crud_property.py`
    - **Valida: Requisitos 4.4**

- [x] 4. Checkpoint — Verificar capa de dominio e infraestructura
  - Asegurarse de que todos los tests pasen, consultar al usuario si surgen dudas.

- [x] 5. Crear `ProgramService` con validación de unicidad
  - [x] 5.1 Crear `ProgramService` en `app/application/services/program_service.py`
    - Constructor recibe `repo: IProgramRepository` (DIP)
    - Seguir el patrón de `UserService`
    - _Requisitos: 5.1_

  - [x] 5.2 Implementar `create_program(data: ProgramCreate) -> ProgramRead`
    - Verificar unicidad de `program_code` con `repo.get_by_program_code`; si existe lanzar `HTTPException(409, "El program_code ya está registrado")`
    - Verificar unicidad de `snies_code` con `repo.get_by_snies_code`; si existe lanzar `HTTPException(409, "El snies_code ya está registrado")`
    - Delegar a `repo.create(data.model_dump())` y retornar `ProgramRead.model_validate(program)`
    - _Requisitos: 5.2, 5.3, 5.4, 5.5_

  - [x] 5.3 Implementar `update_program(program_id: UUID, data: ProgramUpdate) -> ProgramRead`
    - Si `data.program_code` está definido: verificar unicidad excluyendo el programa actual (`existing.id != program_id`); si conflicto lanzar `HTTPException(409, "El program_code ya está registrado")`
    - Si `data.snies_code` está definido: verificar unicidad excluyendo el programa actual; si conflicto lanzar `HTTPException(409, "El snies_code ya está registrado")`
    - Delegar a `repo.update(program_id, data)`; si `None` lanzar `HTTPException(404, "Programa no encontrado")`
    - Retornar `ProgramRead.model_validate(program)`
    - _Requisitos: 5.6, 5.7, 5.8, 5.9_

  - [x] 5.4 Escribir tests unitarios para `ProgramService`
    - Archivo: `tests/unit/test_program_service.py`
    - `test_create_program_success` — camino feliz con datos válidos
    - `test_create_program_duplicate_program_code_returns_409`
    - `test_create_program_duplicate_snies_code_returns_409`
    - `test_update_program_success` — camino feliz de actualización parcial
    - `test_update_program_not_found_returns_404`
    - `test_update_program_duplicate_program_code_different_program_returns_409`
    - `test_update_program_duplicate_snies_code_different_program_returns_409`
    - `test_update_program_same_codes_no_conflict` — auto-actualización
    - Usar `unittest.mock.AsyncMock` para mockear `IProgramRepository`
    - _Requisitos: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9_

  - [x] 5.5 Escribir test de propiedad para rechazo de duplicados en creación
    - **Propiedad 6: Creación rechaza campos únicos duplicados**
    - Para cualquier `program_code` o `snies_code` que ya pertenezca a un programa existente, `create_program` debe lanzar `HTTPException` con código 409
    - Archivo: `tests/property/test_program_crud_property.py`
    - **Valida: Requisitos 5.2, 5.3, 5.4, 5.5, 8.1, 8.2**

  - [x] 5.6 Escribir test de propiedad para rechazo de duplicados en actualización
    - **Propiedad 7: Actualización rechaza campos únicos pertenecientes a otro programa**
    - Para cualesquiera dos programas distintos A y B, `update_program(A.id, ProgramUpdate(program_code=B.program_code))` o con `snies_code` debe lanzar `HTTPException` con código 409
    - Archivo: `tests/property/test_program_crud_property.py`
    - **Valida: Requisitos 5.7, 5.8, 8.3, 8.4**

  - [x] 5.7 Escribir test de propiedad para auto-actualización sin conflicto
    - **Propiedad 8: Auto-actualización con campos únicos propios tiene éxito**
    - Para cualquier programa existente, `update_program(program.id, ProgramUpdate(program_code=program.program_code))` o con `snies_code` debe tener éxito sin error de conflicto
    - Archivo: `tests/property/test_program_crud_property.py`
    - **Valida: Requisitos 5.9, 8.5**

  - [x] 5.8 Escribir test de propiedad para preservación de campos omitidos
    - **Propiedad 2: Actualización parcial preserva campos omitidos**
    - Para cualquier programa existente y cualquier subconjunto no vacío de campos de `ProgramUpdate`, `update_program` debe modificar solo los campos proporcionados y dejar los omitidos sin cambios
    - Archivo: `tests/property/test_program_crud_property.py`
    - **Valida: Requisitos 2.2, 4.3**

- [x] 6. Checkpoint — Verificar capa de servicio
  - Asegurarse de que todos los tests pasen, consultar al usuario si surgen dudas.

- [x] 7. Implementar endpoints `POST /programs` y `PATCH /programs/{program_id}`
  - [x] 7.1 Agregar helper `_get_service` en `app/api/v1/endpoints/programs.py`
    - `def _get_service(session: AsyncSession = Depends(get_session)) -> ProgramService`
    - Retornar `ProgramService(ProgramRepository(session))`
    - Agregar imports necesarios: `ProgramService`, `ProgramCreate`, `ProgramUpdate`, `ProgramRead`, `CurrentUser`, `require_roles`, `RoleEnum`
    - _Requisitos: 6.1, 7.1_

  - [x] 7.2 Implementar `POST /programs`
    - `response_model=ProgramRead`, `status_code=201`
    - `summary="Crear un programa académico"`, `description="Crea un nuevo programa académico. Requiere rol ADMIN. Valida unicidad de program_code y snies_code."`, `tags=["Programas"]`
    - Parámetros: `body: ProgramCreate`, `current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN))`, `service: ProgramService = Depends(_get_service)`
    - Delegar a `service.create_program(body)`
    - _Requisitos: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

  - [x] 7.3 Implementar `PATCH /programs/{program_id}`
    - `response_model=ProgramRead`, `status_code=200`
    - `summary="Actualizar parcialmente un programa académico"`, `description="Actualiza los campos proporcionados de un programa existente. Requiere rol ADMIN. Valida unicidad de program_code y snies_code."`, `tags=["Programas"]`
    - Parámetros: `program_id: UUID`, `body: ProgramUpdate`, `current_user: CurrentUser = Depends(require_roles(RoleEnum.ADMIN))`, `service: ProgramService = Depends(_get_service)`
    - Delegar a `service.update_program(program_id, body)`
    - _Requisitos: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8_

  - [x] 7.4 Escribir tests de integración para endpoints de programas
    - Archivo: `tests/integration/test_program_endpoints.py`
    - `test_post_programs_returns_201` — creación válida con auth ADMIN
    - `test_patch_programs_returns_200` — actualización válida con auth ADMIN
    - `test_post_programs_no_auth_returns_401` — JWT faltante
    - `test_post_programs_non_admin_returns_403` — rol STUDENT/PROFESSOR
    - `test_patch_programs_not_found_returns_404` — programa inexistente
    - `test_post_programs_duplicate_program_code_returns_409`
    - `test_post_programs_missing_field_returns_422`
    - _Requisitos: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 7.5 Escribir test de propiedad para rechazo de rol no-ADMIN
    - **Propiedad 9: Rechazo de rol no-ADMIN**
    - Para cualquier usuario autenticado cuyo rol no sea `ADMIN`, `POST /programs` y `PATCH /programs/{id}` deben retornar código 403
    - Archivo: `tests/property/test_program_crud_property.py`
    - **Valida: Requisitos 6.4, 6.6, 7.5, 7.7**

- [x] 8. Checkpoint final — Verificar integración completa
  - Asegurarse de que todos los tests pasen, consultar al usuario si surgen dudas.

## Notas

- Las tareas marcadas con `*` son opcionales y pueden omitirse para un MVP más rápido
- Cada tarea referencia requisitos específicos para trazabilidad
- Los checkpoints garantizan validación incremental
- Los tests de propiedades validan invariantes universales con Hypothesis (archivo: `tests/property/test_program_crud_property.py`)
- Los tests unitarios validan ejemplos concretos y casos borde (archivo: `tests/unit/test_program_service.py`)
- Los tests de integración validan el flujo completo HTTP → servicio → repositorio (archivo: `tests/integration/test_program_endpoints.py`)
- No se requiere migración de base de datos — el esquema de la tabla `programs` no cambia
