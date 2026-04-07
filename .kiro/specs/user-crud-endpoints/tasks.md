# Plan de Implementación: user-crud-endpoints

## Visión General

Implementación incremental de los endpoints CRUD para la entidad `User` siguiendo el orden de dependencias entre capas: Dominio → Infraestructura → Aplicación → API → Tests. Cada tarea construye sobre la anterior y termina con la integración completa en `main.py`.

## Tareas

- [x] 1. Agregar `UserStatusEnum` al módulo de enums del dominio
  - Agregar `class UserStatusEnum(str, Enum)` con valores `ACTIVE` e `INACTIVE` en `app/domain/enums.py`
  - _Requisitos: 6.1_

- [x] 2. Agregar campo `status` al modelo ORM `User`
  - Agregar campo `status: UserStatusEnum` con `default=UserStatusEnum.ACTIVE`, `nullable=False` y `sa_column_kwargs={"server_default": "ACTIVE"}` en `app/infrastructure/models/user.py`
  - Importar `UserStatusEnum` desde `app.domain.enums`
  - _Requisitos: 6.2_

- [x] 3. Crear migración Alembic `0002_add_user_status`
  - Crear `alembic/versions/0002_add_user_status.py` con `revision="0002"` y `down_revision="0001"`
  - `upgrade()`: ejecutar `CREATE TYPE userstatusenum AS ENUM ('ACTIVE', 'INACTIVE')`, luego `op.add_column("users", ...)` con `server_default="ACTIVE"` y `nullable=False`
  - `downgrade()`: `op.drop_column("users", "status")` y `op.execute("DROP TYPE IF EXISTS userstatusenum")`
  - _Requisitos: 6.3_

- [x] 4. Actualizar la interfaz `IUserRepository`
  - [x] 4.1 Actualizar firma de `list` para incluir el parámetro `status: UserStatusEnum | None` en `app/domain/interfaces/user_repository.py`
    - Agregar import de `UserStatusEnum` desde `app.domain.enums`
    - _Requisitos: 1.2, 1.3, 1.4, 1.5_

  - [x] 4.2 Agregar método abstracto `count(role, professor_id, status) -> int`
    - Declarar `@abstractmethod async def count(self, role: RoleEnum | None, professor_id: UUID | None, status: UserStatusEnum | None) -> int: ...`
    - _Requisitos: 1.8_

  - [x] 4.3 Agregar método abstracto `update_status(id, status) -> User | None`
    - Declarar `@abstractmethod async def update_status(self, id: UUID, status: UserStatusEnum) -> User | None: ...`
    - _Requisitos: 6.5_

- [x] 5. Actualizar `UserRepository` con los nuevos métodos
  - [x] 5.1 Extraer método privado `_build_filter_stmt` compartido entre `list` y `count`
    - El método recibe `role`, `professor_id`, `status` y retorna el `select(User)` con los filtros aplicados (incluyendo JOIN RB-04 cuando `professor_id` no es `None`)
    - _Requisitos: 1.2, 1.3, 1.4, 1.5_

  - [x] 5.2 Actualizar `list` para aceptar `status: UserStatusEnum | None` y usar `_build_filter_stmt`
    - Reemplazar la lógica de filtrado inline por una llamada a `_build_filter_stmt`
    - _Requisitos: 1.2, 1.3, 1.4, 1.5_

  - [x] 5.3 Implementar `count(role, professor_id, status) -> int`
    - Usar `select(func.count()).select_from(User)` aplicando los mismos filtros de `_build_filter_stmt` sin `OFFSET`/`LIMIT`
    - _Requisitos: 1.8_

  - [x] 5.4 Implementar `update_status(id, status) -> User | None`
    - Obtener usuario con `get_by_id`; si `None` retornar `None`
    - Actualizar `user.status` y `user.updated_at`, hacer `flush` y `refresh`
    - Registrar `AuditLogCreate` con `operation=OperationEnum.UPDATE`, `previous_data={"status": previous_status}`, `new_data={"status": status}`
    - _Requisitos: 5.5, 6.6_

- [x] 6. Actualizar schemas Pydantic en `app/application/schemas/user.py`
  - [x] 6.1 Agregar `status: UserStatusEnum` a `UserRead` e importar `UserStatusEnum`
    - _Requisitos: 1.9, 2.5, 3.4, 4.6, 5.6, 6.4_

  - [x] 6.2 Agregar `UserStatusUpdate(BaseModel)` con campo `status: UserStatusEnum`
    - _Requisitos: 5.1, 5.4_

  - [x] 6.3 Agregar `PaginatedResponse(BaseModel, Generic[T])` con campos `data: list[T]`, `total: int`, `skip: int`, `limit: int`
    - Agregar imports `from typing import Generic, TypeVar` y declarar `T = TypeVar("T")`
    - _Requisitos: 1.1, 1.6_

- [x] 7. Crear `UserService` en `app/application/services/user_service.py`
  - [x] 7.1 Implementar constructor y método `list_users(role, professor_id, status, skip, limit) -> PaginatedResponse[UserRead]`
    - Constructor recibe `repo: IUserRepository`
    - Aplicar `status = UserStatusEnum.ACTIVE` cuando `status is None` (regla de negocio)
    - Ejecutar `repo.list` y `repo.count` en paralelo con `asyncio.gather`
    - Retornar `PaginatedResponse[UserRead]` con `data`, `total`, `skip`, `limit`
    - _Requisitos: 1.1, 1.4, 1.6, 1.8_

  - [x] 7.2 Implementar `create_user(data: UserCreate) -> UserRead`
    - Verificar email duplicado con `repo.get_by_email`; si existe lanzar `HTTPException(409, "El email ya está registrado")`
    - Delegar a `repo.create` y retornar `UserRead.model_validate(user)`
    - _Requisitos: 2.1, 2.2, 2.4_

  - [x] 7.3 Implementar `get_user(id: UUID) -> UserRead`
    - Llamar a `repo.get_by_id`; si `None` lanzar `HTTPException(404, "Usuario no encontrado")`
    - _Requisitos: 3.1, 3.2_

  - [x] 7.4 Implementar `update_user(id: UUID, data: UserUpdate) -> UserRead`
    - Llamar a `repo.update`; si `None` lanzar `HTTPException(404, "Usuario no encontrado")`
    - _Requisitos: 4.1, 4.2, 4.4_

  - [x] 7.5 Implementar `update_user_status(id: UUID, status: UserStatusEnum) -> UserRead`
    - Llamar a `repo.update_status`; si `None` lanzar `HTTPException(404, "Usuario no encontrado")`
    - _Requisitos: 5.1, 5.2, 5.5_

- [x] 8. Crear `UserRouter` en `app/api/v1/endpoints/users.py`
  - [x] 8.1 Implementar `GET /users` con query params `role?`, `professor_id?`, `status?`, `skip=Query(0, ge=0)`, `limit=Query(20, ge=1, le=100)`
    - `response_model=PaginatedResponse[UserRead]`, `status_code=200`
    - Inyectar `session: AsyncSession = Depends(get_session)`, construir `UserService(UserRepository(session))`
    - _Requisitos: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [x] 8.2 Implementar `POST /users` con body `UserCreate`
    - `response_model=UserRead`, `status_code=201`
    - _Requisitos: 2.1, 2.2, 2.3_

  - [x] 8.3 Implementar `GET /users/{user_id}` con path param `user_id: UUID`
    - `response_model=UserRead`, `status_code=200`
    - _Requisitos: 3.1, 3.2, 3.3_

  - [x] 8.4 Implementar `PATCH /users/{user_id}` con body `UserUpdate`
    - `response_model=UserRead`, `status_code=200`
    - _Requisitos: 4.1, 4.2, 4.3, 4.5_

  - [x] 8.5 Implementar `PATCH /users/{user_id}/status` con body `UserStatusUpdate`
    - `response_model=UserRead`, `status_code=200`
    - _Requisitos: 5.1, 5.2, 5.3, 5.4_

- [x] 9. Registrar `UserRouter` en `app/main.py`
  - Importar `users` desde `app.api.v1.endpoints`
  - Agregar `app.include_router(users.router, prefix="/api/v1", tags=["Usuarios"])`
  - _Requisitos: 7.1, 7.2, 7.3_

- [x] 10. Checkpoint — Verificar integración completa
  - Asegurarse de que todos los tests pasen, consultar al usuario si surgen dudas.

- [x] 11. Crear tests unitarios en `tests/test_users.py`
  - [x] 11.1 Configurar fixture `client` con `app.dependency_overrides[get_session]` usando `pytest-asyncio` y `httpx.AsyncClient`
    - _Requisitos: 8.9_

  - [x] 11.2 Escribir tests concretos para `POST /users`
    - Crear usuario válido → HTTP 201, respuesta contiene `id`, `email`, `status=ACTIVE`, sin `password_hash`
    - Email duplicado → HTTP 409
    - Body inválido (campo requerido ausente) → HTTP 422
    - _Requisitos: 2.1, 2.2, 2.3, 2.5_

  - [x] 11.3 Escribir tests concretos para `GET /users/{user_id}`
    - Usuario existente → HTTP 200, campos correctos
    - UUID inexistente → HTTP 404
    - UUID con formato inválido → HTTP 422
    - _Requisitos: 3.1, 3.2, 3.3, 3.4_

  - [x] 11.4 Escribir tests concretos para `PATCH /users/{user_id}`
    - Actualización parcial → solo los campos enviados cambian, HTTP 200
    - UUID inexistente → HTTP 404
    - _Requisitos: 4.1, 4.2, 4.5, 4.6_

  - [x] 11.5 Escribir tests concretos para `PATCH /users/{user_id}/status`
    - Cambiar a `INACTIVE` → `status` en respuesta es `INACTIVE`, HTTP 200
    - Cambiar a `ACTIVE` → `status` en respuesta es `ACTIVE`, HTTP 200
    - UUID inexistente → HTTP 404
    - Valor de status inválido → HTTP 422
    - _Requisitos: 5.1, 5.2, 5.3, 5.4_

  - [x] 11.6 Escribir tests concretos para `GET /users`
    - Sin parámetros → solo retorna usuarios `ACTIVE`
    - `?status=INACTIVE` → retorna usuarios `INACTIVE`
    - `?role=STUDENT` → solo retorna estudiantes
    - `limit=101` → HTTP 422
    - `skip=-1` → HTTP 422
    - Respuesta nunca contiene `password_hash`
    - _Requisitos: 1.1, 1.2, 1.4, 1.5, 1.6, 1.7, 1.9_

- [x] 12. Crear tests de propiedades en `tests/test_users_properties.py`
  - [x] 12.1 Escribir test `test_create_get_roundtrip` — Propiedad 1
    - `@given(st.builds(UserCreate, email=st.emails(), full_name=st.text(min_size=1), role=st.sampled_from(RoleEnum)))`
    - `@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])`
    - Comentario: `# Feature: user-crud-endpoints, Propiedad 1: Round-trip crear → recuperar`
    - **Propiedad 1: Round-trip crear → recuperar**
    - **Valida: Requisitos 2.1, 3.1, 8.1**

  - [x] 12.2 Escribir test `test_get_idempotent` — Propiedad 2
    - Múltiples llamadas consecutivas a `GET /users/{user_id}` sin modificaciones intermedias deben retornar la misma respuesta
    - Comentario: `# Feature: user-crud-endpoints, Propiedad 2: Idempotencia de lectura`
    - **Propiedad 2: Idempotencia de lectura**
    - **Valida: Requisito 8.2**

  - [x] 12.3 Escribir test `test_filter_by_role_exhaustive` — Propiedad 3
    - `@given(st.lists(st.builds(UserCreate, ...), min_size=1), st.sampled_from(RoleEnum))`
    - Todos los elementos de `data` deben tener `role == r`; `total == len(data)` cuando `skip=0` y `limit >= total`
    - Comentario: `# Feature: user-crud-endpoints, Propiedad 3: Filtrado por rol es exhaustivo y exclusivo`
    - **Propiedad 3: Filtrado por rol es exhaustivo y exclusivo**
    - **Valida: Requisitos 1.2, 1.5**

  - [x] 12.4 Escribir test `test_inactive_excluded_from_default_list` — Propiedad 4
    - Usuario creado y desactivado no debe aparecer en `GET /users` sin parámetro `status`
    - Comentario: `# Feature: user-crud-endpoints, Propiedad 4: Soft delete — usuarios INACTIVE excluidos del listado por defecto`
    - **Propiedad 4: Soft delete — usuarios INACTIVE excluidos del listado por defecto**
    - **Valida: Requisitos 1.4, 5.1, 8.7**

  - [x] 12.5 Escribir test `test_reactivated_appears_in_default_list` — Propiedad 5
    - Usuario INACTIVE reactivado debe aparecer en `GET /users` sin parámetro `status`
    - Comentario: `# Feature: user-crud-endpoints, Propiedad 5: Reactivación — usuarios ACTIVE incluidos en listado por defecto`
    - **Propiedad 5: Reactivación — usuarios ACTIVE incluidos en listado por defecto**
    - **Valida: Requisitos 1.4, 1.5, 5.1, 8.8**

  - [x] 12.6 Escribir test `test_pagination_metamorphic` — Propiedad 6
    - `@given(st.lists(st.builds(UserCreate, ...), min_size=2, max_size=10), st.integers(min_value=1))`
    - Concatenación de todas las páginas con `limit=k` debe contener los mismos elementos que `limit=N, skip=0`
    - Comentario: `# Feature: user-crud-endpoints, Propiedad 6: Paginación metamórfica — unión de páginas equivale a consulta completa`
    - **Propiedad 6: Paginación metamórfica — unión de páginas equivale a consulta completa**
    - **Valida: Requisito 8.3**

  - [x] 12.7 Escribir test `test_pagination_total_consistent` — Propiedad 7
    - El campo `total` debe ser igual a N independientemente del valor de `skip`
    - Comentario: `# Feature: user-crud-endpoints, Propiedad 7: Consistencia del total paginado`
    - **Propiedad 7: Consistencia del total paginado**
    - **Valida: Requisito 8.4**

  - [x] 12.8 Escribir test `test_nonexistent_uuid_returns_404` — Propiedad 8
    - `@given(st.uuids())` filtrados para no existir en BD
    - `GET /users/{id}`, `PATCH /users/{id}` y `PATCH /users/{id}/status` deben retornar HTTP 404
    - Comentario: `# Feature: user-crud-endpoints, Propiedad 8: HTTP 404 para UUID inexistente`
    - **Propiedad 8: HTTP 404 para UUID inexistente**
    - **Valida: Requisitos 3.2, 4.2, 5.2, 8.5**

  - [x] 12.9 Escribir test `test_password_hash_never_in_response` — Propiedad 9
    - `@given(st.builds(UserCreate, ..., password_hash=st.text(min_size=1)))`
    - Ninguna respuesta de ningún endpoint debe contener el campo `password_hash`
    - Comentario: `# Feature: user-crud-endpoints, Propiedad 9: password_hash nunca aparece en ninguna respuesta`
    - **Propiedad 9: `password_hash` nunca aparece en ninguna respuesta**
    - **Valida: Requisitos 1.9, 2.5, 3.4, 4.6, 5.6, 8.6**

  - [x] 12.10 Escribir test `test_write_operations_create_audit_log` — Propiedad 10
    - Verificar que cada operación de escritura exitosa genera exactamente un registro en `audit_logs` con el `record_id` correcto y la `operation` correspondiente
    - Comentario: `# Feature: user-crud-endpoints, Propiedad 10: Audit log registrado en cada operación de escritura`
    - **Propiedad 10: Audit log registrado en cada operación de escritura**
    - **Valida: Requisitos 2.4, 4.4, 5.5**

  - [x] 12.11 Escribir test `test_duplicate_email_returns_409` — Propiedad 11
    - `@given(st.emails())`
    - Usar el mismo email dos veces en `POST /users`; el segundo intento debe retornar HTTP 409 sin crear registro nuevo
    - Comentario: `# Feature: user-crud-endpoints, Propiedad 11: Email duplicado retorna HTTP 409`
    - **Propiedad 11: Email duplicado retorna HTTP 409**
    - **Valida: Requisito 2.2**

- [x] 13. Checkpoint final — Asegurarse de que todos los tests pasen
  - Asegurarse de que todos los tests pasen, consultar al usuario si surgen dudas.

## Notas

- Las tareas marcadas con `*` son opcionales y pueden omitirse para un MVP más rápido
- Cada tarea referencia requisitos específicos para trazabilidad
- Los checkpoints (tareas 10 y 13) garantizan validación incremental
- Los tests de propiedades validan invariantes universales con Hypothesis (`max_examples=100`)
- Los tests unitarios validan ejemplos concretos y casos borde
