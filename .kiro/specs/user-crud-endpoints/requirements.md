# Documento de Requisitos

## Introducción

Esta feature habilita los endpoints CRUD completos para la entidad `User` en el backend FastAPI del MPRA (Modelo Predictivo de Riesgo Académico). Se exponen cuatro operaciones REST bajo `/api/v1/users` más un endpoint de cambio de estado, respetando la Clean Architecture ya establecida (capas Dominio / Aplicación / Infraestructura / API), las prácticas RESTful del proyecto y las reglas de negocio vigentes (RB-04, RNF-02, RNF-03). La eliminación de usuarios es lógica (soft delete) mediante el campo `status` en la base de datos. Se registra el nuevo router en `main.py`.

---

## Glosario

- **User**: Entidad del sistema que representa a un actor (estudiante, docente o administrador) identificado por un UUID.
- **UserCreate**: Schema Pydantic v2 con los campos requeridos para crear un usuario.
- **UserUpdate**: Schema Pydantic v2 con todos los campos opcionales para actualizar parcialmente un usuario.
- **UserRead**: Schema Pydantic v2 de respuesta pública; nunca expone `password_hash`; incluye el campo `status` de tipo `UserStatusEnum`.
- **PaginatedResponse**: Schema Pydantic v2 genérico de respuesta paginada que envuelve una lista de resultados con metadatos de paginación (`data`, `total`, `skip`, `limit`).
- **UserRouter**: Router FastAPI que agrupa los endpoints CRUD de la entidad User más el endpoint de cambio de estado.
- **UserRepository**: Implementación concreta de `IUserRepository` con acceso a PostgreSQL vía SQLModel/SQLAlchemy async.
- **IUserRepository**: Interfaz abstracta (dominio) que define el contrato de persistencia para User.
- **UserService**: Capa de aplicación que orquesta la lógica de negocio entre el router y el repositorio.
- **AuditLog**: Registro inmutable de cada operación de escritura (INSERT, UPDATE) sobre la tabla `users`.
- **UserStatusEnum**: Enum definido en `app/domain/enums.py` con los valores `ACTIVE` e `INACTIVE` que representa el estado lógico de un usuario.
- **Soft Delete / Eliminación Lógica**: Desactivación de un usuario mediante el cambio del campo `status` a `INACTIVE`, sin eliminar físicamente el registro de la base de datos.
- **RB-04**: Regla de negocio de privacidad: los docentes solo pueden visualizar estudiantes inscritos en sus asignaturas asignadas.
- **RNF-02**: Requisito no funcional de desempeño: tiempo de respuesta de la API < 300 ms.
- **RNF-03**: Requisito no funcional de mantenibilidad: Clean Architecture con separación estricta de capas.
- **Session**: Sesión asíncrona de SQLAlchemy inyectada vía `Depends(get_session)`.

---

## Requisitos

### Requisito 1: Listar usuarios

**User Story:** Como administrador del sistema, quiero obtener una lista paginada de usuarios con filtros opcionales por rol, identificador de docente y estado, para poder gestionar los actores del sistema de forma eficiente.

#### Criterios de Aceptación

1. WHEN una petición `GET /api/v1/users` es recibida, THE UserRouter SHALL retornar una respuesta con el schema `PaginatedResponse[UserRead]` y el código HTTP 200, incluyendo los campos `data` (lista de `UserRead`), `total` (total de registros que coinciden con los filtros aplicados), `skip` (offset actual) y `limit` (tamaño de página actual).
2. WHEN el parámetro de consulta `role` es proporcionado, THE UserRepository SHALL filtrar los usuarios cuyo campo `role` coincida exactamente con el valor indicado, y THE UserRepository SHALL calcular el `total` aplicando el mismo filtro.
3. WHEN el parámetro de consulta `professor_id` es proporcionado, THE UserRepository SHALL aplicar el filtro RB-04 y retornar únicamente los estudiantes inscritos en asignaturas asignadas a ese docente, y THE UserRepository SHALL calcular el `total` aplicando el mismo filtro RB-04.
4. WHEN el parámetro de consulta `status` no es proporcionado, THE UserRepository SHALL retornar únicamente los usuarios cuyo campo `status` sea `ACTIVE`.
5. WHEN el parámetro de consulta `status` es proporcionado con un valor válido de `UserStatusEnum`, THE UserRepository SHALL filtrar los usuarios cuyo campo `status` coincida exactamente con el valor indicado.
6. THE UserRouter SHALL aceptar los parámetros de paginación `skip` (entero ≥ 0, por defecto 0) y `limit` (entero entre 1 y 100, por defecto 20).
7. IF el valor de `limit` supera 100, THEN THE UserRouter SHALL retornar HTTP 422 con un mensaje de error descriptivo.
8. THE IUserRepository SHALL declarar el método `count(role, professor_id, status) -> int` que retorna el número total de registros que coinciden con los mismos filtros aplicados en `list`, sin cargar los registros completos en memoria.
9. THE UserRead SHALL nunca incluir el campo `password_hash` en la respuesta.
10. WHILE la base de datos está disponible, THE UserRouter SHALL responder en menos de 300 ms (RNF-02).

---

### Requisito 2: Crear usuario

**User Story:** Como administrador del sistema, quiero crear un nuevo usuario proporcionando sus datos básicos, para registrar actores en el sistema MPRA.

#### Criterios de Aceptación

1. WHEN una petición `POST /api/v1/users` con un cuerpo `UserCreate` válido es recibida, THE UserRouter SHALL persistir el usuario y retornar el recurso creado serializado con `UserRead` y el código HTTP 201.
2. WHEN el campo `email` del cuerpo de la petición ya existe en la base de datos, THE UserRouter SHALL retornar HTTP 409 con el mensaje `"El email ya está registrado"`.
3. IF el cuerpo de la petición no cumple la validación Pydantic de `UserCreate`, THEN THE UserRouter SHALL retornar HTTP 422 con los detalles de validación.
4. WHEN un usuario es creado exitosamente, THE UserRepository SHALL registrar una entrada en `AuditLog` con `operation=INSERT` en la misma transacción de base de datos.
5. THE UserRead retornado en la respuesta SHALL nunca incluir el campo `password_hash`.

---

### Requisito 3: Obtener usuario por ID

**User Story:** Como administrador del sistema, quiero obtener los datos de un usuario específico por su UUID, para consultar su información de perfil.

#### Criterios de Aceptación

1. WHEN una petición `GET /api/v1/users/{user_id}` con un UUID válido es recibida, THE UserRouter SHALL retornar el usuario serializado con `UserRead` y el código HTTP 200.
2. IF el `user_id` proporcionado no corresponde a ningún usuario existente, THEN THE UserRouter SHALL retornar HTTP 404 con el mensaje `"Usuario no encontrado"`.
3. IF el `user_id` proporcionado no tiene formato UUID válido, THEN THE UserRouter SHALL retornar HTTP 422.
4. THE UserRead retornado SHALL nunca incluir el campo `password_hash`.

---

### Requisito 4: Actualizar usuario parcialmente

**User Story:** Como administrador del sistema, quiero actualizar uno o más campos de un usuario existente sin necesidad de enviar todos sus datos, para mantener la información del sistema actualizada.

#### Criterios de Aceptación

1. WHEN una petición `PATCH /api/v1/users/{user_id}` con un cuerpo `UserUpdate` válido es recibida, THE UserRouter SHALL aplicar únicamente los campos presentes en el cuerpo y retornar el usuario actualizado con `UserRead` y el código HTTP 200.
2. IF el `user_id` proporcionado no corresponde a ningún usuario existente, THEN THE UserRouter SHALL retornar HTTP 404 con el mensaje `"Usuario no encontrado"`.
3. WHEN el campo `email` no forma parte de `UserUpdate`, THE UserRouter SHALL rechazar cualquier intento de modificar el email de un usuario existente.
4. WHEN un usuario es actualizado exitosamente, THE UserRepository SHALL registrar una entrada en `AuditLog` con `operation=UPDATE`, incluyendo los valores anteriores y los nuevos valores modificados, en la misma transacción.
5. IF el cuerpo de la petición no cumple la validación Pydantic de `UserUpdate`, THEN THE UserRouter SHALL retornar HTTP 422 con los detalles de validación.
6. THE UserRead retornado SHALL nunca incluir el campo `password_hash`.

---

### Requisito 5: Cambiar estado de usuario (soft delete / reactivación)

**User Story:** Como administrador del sistema, quiero cambiar el estado de un usuario a `INACTIVE` o `ACTIVE` mediante un endpoint dedicado, para realizar eliminaciones lógicas sin perder el registro histórico en la base de datos.

#### Criterios de Aceptación

1. WHEN una petición `PATCH /api/v1/users/{user_id}/status` con un cuerpo `{"status": "INACTIVE"}` o `{"status": "ACTIVE"}` es recibida, THE UserRouter SHALL actualizar el campo `status` del usuario y retornar el usuario actualizado serializado con `UserRead` y el código HTTP 200.
2. IF el `user_id` proporcionado no corresponde a ningún usuario existente, THEN THE UserRouter SHALL retornar HTTP 404 con el mensaje `"Usuario no encontrado"`.
3. IF el `user_id` proporcionado no tiene formato UUID válido, THEN THE UserRouter SHALL retornar HTTP 422.
4. IF el cuerpo de la petición contiene un valor de `status` que no pertenece a `UserStatusEnum`, THEN THE UserRouter SHALL retornar HTTP 422 con los detalles de validación.
5. WHEN el estado de un usuario es actualizado exitosamente, THE UserRepository SHALL registrar una entrada en `AuditLog` con `operation=UPDATE`, incluyendo el valor anterior y el nuevo valor del campo `status`, en la misma transacción.
6. THE UserRead retornado SHALL nunca incluir el campo `password_hash`.
7. THE User SHALL tener un campo `status` de tipo `UserStatusEnum` con valor por defecto `ACTIVE`, respaldado por una migración de Alembic.

---

### Requisito 6: Modelo de dominio — campo `status` y `UserStatusEnum`

**User Story:** Como desarrollador del sistema, quiero que el modelo `User` incluya un campo `status` de tipo `UserStatusEnum`, para soportar la eliminación lógica de usuarios sin eliminar registros físicamente de la base de datos.

#### Criterios de Aceptación

1. THE UserStatusEnum SHALL estar definido en `app/domain/enums.py` con los valores `ACTIVE` e `INACTIVE`.
2. THE User SHALL incluir el campo `status` de tipo `UserStatusEnum` con valor por defecto `ACTIVE` y restricción `NOT NULL` en la base de datos.
3. THE Alembic_Migration SHALL agregar la columna `status` a la tabla `users` con valor por defecto `'ACTIVE'` para los registros existentes.
4. THE UserRead SHALL incluir el campo `status` de tipo `UserStatusEnum` en su schema de respuesta.
5. THE IUserRepository SHALL declarar el método abstracto `update_status(id: UUID, status: UserStatusEnum) -> User | None` que retorna el usuario actualizado o `None` si no existe.
6. THE UserRepository SHALL implementar el método `update_status(id: UUID, status: UserStatusEnum) -> User | None` actualizando únicamente el campo `status` del registro correspondiente.

---

### Requisito 7: Registro del router en la aplicación

**User Story:** Como desarrollador del sistema, quiero que el `UserRouter` quede registrado en `main.py` bajo el prefijo `/api/v1`, para que los endpoints sean accesibles desde el servidor.

#### Criterios de Aceptación

1. THE UserRouter SHALL estar registrado en `app.main` con el prefijo `/api/v1` y el tag `"Usuarios"`.
2. THE UserRouter SHALL ser importado desde `app.api.v1.endpoints.users` siguiendo la convención de organización de routers del proyecto.
3. WHEN la aplicación inicia, THE UserRouter SHALL estar disponible en la documentación automática de FastAPI (`/docs` y `/redoc`).

---

### Requisito 8: Propiedades de correctness con property-based testing

**User Story:** Como desarrollador del sistema, quiero contar con tests de propiedades (Hypothesis) que verifiquen invariantes clave de los endpoints CRUD, para detectar regresiones y casos borde de forma automatizada.

#### Criterios de Aceptación

1. THE Test_Suite SHALL verificar la propiedad de round-trip: un usuario creado vía `POST /api/v1/users` y luego recuperado vía `GET /api/v1/users/{user_id}` SHALL retornar los mismos valores de `email`, `full_name` y `role`.
2. THE Test_Suite SHALL verificar la propiedad de idempotencia de lectura: múltiples llamadas consecutivas a `GET /api/v1/users/{user_id}` con el mismo UUID SHALL retornar siempre la misma respuesta mientras el recurso no sea modificado.
3. THE Test_Suite SHALL verificar la propiedad metamórfica de paginación: para cualquier conjunto de N usuarios, la concatenación de los campos `data` de todas las páginas obtenidas con `limit=k` (donde k < N) SHALL contener exactamente los mismos elementos que el campo `data` de una consulta con `limit=N` y `skip=0`.
4. THE Test_Suite SHALL verificar la propiedad de consistencia del total paginado: para cualquier conjunto de N usuarios y cualquier valor de `limit=k`, la suma de `len(page.data)` sobre todas las páginas SHALL ser igual al campo `total` reportado en cualquiera de las respuestas de esa misma consulta.
5. THE Test_Suite SHALL verificar la propiedad de condición de error: invocar `GET /api/v1/users/{user_id}` con un UUID que no existe en la base de datos SHALL retornar siempre HTTP 404.
6. THE Test_Suite SHALL verificar que el campo `password_hash` nunca aparece en ninguna respuesta de los endpoints CRUD, para cualquier combinación de datos de entrada válidos generados por Hypothesis.
7. THE Test_Suite SHALL verificar la propiedad de soft delete: un usuario desactivado vía `PATCH /api/v1/users/{user_id}/status` con `{"status": "INACTIVE"}` NO SHALL aparecer en el campo `data` de la respuesta de `GET /api/v1/users` cuando el parámetro `status` no es proporcionado.
8. THE Test_Suite SHALL verificar la propiedad de reactivación: un usuario reactivado vía `PATCH /api/v1/users/{user_id}/status` con `{"status": "ACTIVE"}` SHALL aparecer en el campo `data` de la respuesta de `GET /api/v1/users` cuando el parámetro `status` no es proporcionado.
9. WHEN los tests de propiedades son ejecutados, THE Test_Suite SHALL completar sin errores en el entorno de CI del proyecto.
