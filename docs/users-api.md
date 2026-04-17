# Users API — Flujos y Ejemplos

Base URL: `/api/v1`

---

## POST /users — Crear usuario

Crea un nuevo usuario en el sistema. El `email` debe ser único.

### Campos del body

| Campo | Tipo | Requerido | Descripción |
|---|---|---|---|
| `email` | string (email) | ✅ | Correo institucional único |
| `full_name` | string | ✅ | Nombre completo |
| `role` | `STUDENT` \| `PROFESSOR` \| `ADMIN` | ✅ | Rol del usuario |
| `password_hash` | string \| null | ❌ | Hash de contraseña (auth local) |
| `microsoft_oid` | string \| null | ❌ | OID de Microsoft Entra (SSO) |
| `google_oid` | string \| null | ❌ | OID de Google (SSO) |
| `ml_consent` | boolean | ❌ | Consentimiento ML (default: `false`) |

---

### Flujo 1 — Crear estudiante (auth local)

```http
POST /api/v1/users
Content-Type: application/json
```

```json
{
  "email": "estudiante@universidad.edu.co",
  "full_name": "María García López",
  "role": "STUDENT",
  "password_hash": "$2b$12$hashed_password_here",
  "ml_consent": false
}
```

**Respuesta 201:**
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "email": "estudiante@universidad.edu.co",
  "full_name": "María García López",
  "role": "STUDENT",
  "status": "ACTIVE",
  "ml_consent": false,
  "created_at": "2026-04-04T19:00:00",
  "updated_at": "2026-04-04T19:00:00"
}
```

---

### Flujo 2 — Crear docente (auth local)

```json
{
  "email": "docente@universidad.edu.co",
  "full_name": "Carlos Rodríguez Pérez",
  "role": "PROFESSOR",
  "password_hash": "$2b$12$hashed_password_here"
}
```

---

### Flujo 3 — Crear administrador

```json
{
  "email": "admin@universidad.edu.co",
  "full_name": "Ana Martínez Torres",
  "role": "ADMIN",
  "password_hash": "$2b$12$hashed_password_here"
}
```

---

### Flujo 4 — Crear usuario con SSO Microsoft

Para usuarios que se autentican vía Microsoft Entra ID. No requiere `password_hash`.

```json
{
  "email": "usuario@universidad.edu.co",
  "full_name": "Juan Pérez Gómez",
  "role": "STUDENT",
  "microsoft_oid": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
}
```

---

### Flujo 5 — Crear usuario con SSO Google

```json
{
  "email": "usuario@universidad.edu.co",
  "full_name": "Laura Sánchez Díaz",
  "role": "STUDENT",
  "google_oid": "1234567890abcdef"
}
```

---

## PATCH /users/{user_id} — Actualizar usuario

Actualización parcial. Solo se envían los campos a modificar.

```http
PATCH /api/v1/users/3fa85f64-5717-4562-b3fc-2c963f66afa6
Content-Type: application/json
```

```json
{
  "full_name": "María García López (actualizado)",
  "ml_consent": true
}
```

---

## PATCH /users/{user_id}/status — Cambiar estado

Soft delete (desactivar) o reactivar un usuario.

**Desactivar:**
```json
{
  "status": "INACTIVE"
}
```

**Reactivar:**
```json
{
  "status": "ACTIVE"
}
```

---

## GET /users — Listar usuarios

Soporta filtros opcionales y paginación.

```http
GET /api/v1/users?role=STUDENT&status=ACTIVE&skip=0&limit=20
```

| Query param | Tipo | Descripción |
|---|---|---|
| `role` | `STUDENT` \| `PROFESSOR` \| `ADMIN` | Filtrar por rol |
| `status` | `ACTIVE` \| `INACTIVE` | Filtrar por estado |
| `professor_id` | UUID | Estudiantes de un docente específico |
| `skip` | int (default: 0) | Offset de paginación |
| `limit` | int (default: 20, max: 100) | Tamaño de página |

**Respuesta 200:**
```json
{
  "data": [
    {
      "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "email": "estudiante@universidad.edu.co",
      "full_name": "María García López",
      "role": "STUDENT",
      "status": "ACTIVE",
      "ml_consent": false,
      "created_at": "2026-04-04T19:00:00",
      "updated_at": "2026-04-04T19:00:00"
    }
  ],
  "total": 1,
  "skip": 0,
  "limit": 20
}
```

---

## GET /users/{user_id} — Obtener usuario por ID

```http
GET /api/v1/users/3fa85f64-5717-4562-b3fc-2c963f66afa6
```

**Respuesta 200:** mismo schema que `UserRead` arriba.

**Respuesta 404:**
```json
{
  "detail": "User not found"
}
```

---

## Códigos de error comunes

| Código | Causa |
|---|---|
| `400` | Body inválido o falta campo requerido |
| `404` | Usuario no encontrado |
| `409` | Email ya registrado |
| `422` | Validación Pydantic fallida (ej. email mal formado, rol inválido) |
