# API RESTful Best Practices

## Naming Conventions
- Use **plural nouns** for resource collections: `/users`, `/courses`, `/consents`
- Use **kebab-case** for multi-word resources: `/audit-logs`
- Nest sub-resources logically: `/users/{user_id}/consents`
- Never use verbs in URLs — the HTTP method conveys the action

## HTTP Methods
| Method | Usage |
|--------|-------|
| GET | Retrieve resource(s) — idempotent, no side effects |
| POST | Create a new resource |
| PUT | Full replacement of a resource |
| PATCH | Partial update of a resource |
| DELETE | Remove a resource |

## Status Codes
| Code | Meaning |
|------|---------|
| 200 | OK — successful GET, PUT, PATCH |
| 201 | Created — successful POST |
| 204 | No Content — successful DELETE |
| 400 | Bad Request — validation error |
| 401 | Unauthorized — missing/invalid auth |
| 403 | Forbidden — authenticated but not authorized |
| 404 | Not Found — resource doesn't exist |
| 409 | Conflict — duplicate resource |
| 422 | Unprocessable Entity — Pydantic validation failure |
| 500 | Internal Server Error |

## Request & Response
- Always return JSON (`application/json`)
- Use Pydantic v2 schemas for request validation and response serialization
- Separate schemas: `UserCreate`, `UserUpdate`, `UserResponse` — never expose ORM models directly
- Use `model_config = ConfigDict(from_attributes=True)` for ORM compatibility

## Versioning
- All endpoints live under `/api/v1/`
- New breaking changes → new version prefix `/api/v2/`

## Pagination
- Use `skip` / `limit` query params for list endpoints
- Default: `skip=0`, `limit=20`, max `limit=100`
- Response includes the list directly (can wrap in `{"data": [], "total": n}` for paginated endpoints)

## Error Responses
Standardized error body:
```json
{
  "detail": "Human-readable error message"
}
```
Use FastAPI's `HTTPException` for all error responses.

## Security
- Validate ownership/authorization at the service layer, not just the router
- Never expose internal IDs or sensitive fields (passwords, tokens) in responses
- Apply RB-04: docentes only see students enrolled in their assigned courses

## Router Organization
- One router file per resource in `app/api/v1/endpoints/`
- Register routers in `app/api/v1/__init__.py` with appropriate prefix and tags
- Use dependency injection (`Depends`) for DB sessions and auth

## FastAPI-Specific
- Use `response_model` on every endpoint to enforce output schema
- Use `status_code` parameter to set correct HTTP status on success
- Prefer async handlers (`async def`) for all endpoints
