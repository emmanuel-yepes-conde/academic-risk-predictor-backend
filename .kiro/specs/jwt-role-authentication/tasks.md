# Implementation Plan: JWT Role-Based Authentication

## Overview

Implementación de autenticación JWT con autorización por roles para el sistema MPRA. El plan sigue TDD (Red → Green → Refactor) y la Clean Architecture existente, añadiendo componentes en las capas de Dominio, Aplicación e Infraestructura. Cada tarea construye sobre las anteriores de forma incremental, con tests escritos antes del código de producción.

## Tasks

- [x] 1. Add PyJWT dependency and extend JWT configuration
  - [x] 1.1 Add `PyJWT>=2.8.0` to `requirements.txt`
    - Add the PyJWT library to the project dependencies
    - _Requirements: 2.2, 7.1_

  - [x] 1.2 Extend `app/core/config.py` with JWT settings
    - Add `JWT_SECRET_KEY: str` (no default — app fails to start if missing), `JWT_ALGORITHM: str = "HS256"`, `ACCESS_TOKEN_EXPIRE_MINUTES: int = 30`, `REFRESH_TOKEN_EXPIRE_DAYS: int = 7` to the `Settings` class
    - Update `.env` and `env.example` with the new JWT variables
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 1.3 Write unit tests for JWT configuration
    - Test that default values are applied for `JWT_ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`
    - Test that missing `JWT_SECRET_KEY` raises a validation error
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [x] 2. Create domain layer: exceptions, interfaces, and value objects
  - [x] 2.1 Create custom exception classes in `app/domain/exceptions.py`
    - Implement `AuthenticationError(message, status_code=401)`, `TokenExpiredError`, `InvalidTokenError`, `AuthorizationError`
    - _Requirements: 1.2, 1.3, 1.4, 3.2, 3.3, 3.4, 5.2_

  - [x] 2.2 Create `IAuthProvider` interface in `app/domain/interfaces/auth_provider.py`
    - Define abstract `authenticate(**kwargs) -> User` method following the Strategy pattern
    - _Requirements: 8.4_

  - [x] 2.3 Create `TokenPayload` value object in `app/domain/value_objects/token.py`
    - Implement frozen dataclass with fields: `sub` (str), `role` (RoleEnum), `type` (str), `exp` (datetime), `iat` (datetime)
    - _Requirements: 2.1, 2.5_

- [x] 3. Implement TokenService with TDD
  - [x] 3.1 Implement `TokenService` in `app/application/services/token_service.py`
    - Implement `create_access_token(user_id, role) -> str` that encodes JWT with claims `sub`, `role`, `type="access"`, `exp`, `iat` using PyJWT and HS256
    - Implement `create_refresh_token(user_id, role) -> str` with `type="refresh"` and longer expiration
    - Implement `decode_token(token) -> TokenPayload` that validates signature, expiration, and token structure; raises `TokenExpiredError` or `InvalidTokenError` on failure
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [x] 3.2 Write property test: JWT Encode-Decode Round Trip
    - **Property 1: JWT Encode-Decode Round Trip**
    - Create `tests/property/test_jwt_roundtrip_property.py`
    - Use Hypothesis to generate random UUIDs, RoleEnum values, and verify that encoding then decoding produces equivalent payload
    - **Validates: Requirements 2.6**

  - [x] 3.3 Write property test: Token Claims Completeness
    - **Property 2: Token Claims Completeness**
    - In `tests/property/test_jwt_roundtrip_property.py`, verify that for any user (UUID, RoleEnum), created access tokens contain exactly `sub`, `role`, `type="access"`, `exp`, `iat`; refresh tokens have `type="refresh"`
    - **Validates: Requirements 2.1, 2.5**

  - [x] 3.4 Write property test: Token Expiration Matches Configuration
    - **Property 3: Token Expiration Matches Configuration**
    - Create `tests/property/test_token_expiration_property.py`
    - Use Hypothesis to generate positive integers for `access_expire_minutes` and `refresh_expire_days`, verify `exp - iat` matches the configured duration
    - **Validates: Requirements 2.3, 2.4**

  - [x] 3.5 Write property test: Invalid Tokens Are Always Rejected
    - **Property 4: Invalid Tokens Are Always Rejected**
    - Create `tests/property/test_token_validation_property.py`
    - Use Hypothesis to generate random strings, tokens signed with different keys, and malformed tokens; verify all raise `InvalidTokenError`
    - **Validates: Requirements 3.4, 3.6**

  - [x] 3.6 Write unit tests for TokenService edge cases
    - Create `tests/unit/test_token_service.py`
    - Test expired token handling, wrong token type detection, specific claim values
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.3, 3.4_

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement authentication schemas and CredentialAuthProvider
  - [x] 5.1 Create auth schemas in `app/application/schemas/auth.py`
    - Implement `LoginRequest(email: EmailStr, password: str)`, `RefreshRequest(refresh_token: str)`, `TokenResponse(access_token, refresh_token, token_type, expires_in)`, `LogoutResponse(message)`
    - Use `Field(description=...)` on all fields for Swagger documentation
    - _Requirements: 1.1, 4.1, 9.1, 9.3_

  - [x] 5.2 Implement `CredentialAuthProvider` in `app/infrastructure/auth/credential_provider.py`
    - Implement `authenticate(email, password) -> User` using `IUserRepository.get_by_email()` and `verify_password()` from `app/core/security.py`
    - Raise `AuthenticationError("Credenciales inválidas", 401)` for non-existent email, wrong password, or missing `password_hash`
    - _Requirements: 1.1, 1.2, 1.3, 1.5, 8.4_

  - [x] 5.3 Write unit tests for CredentialAuthProvider
    - Create `tests/unit/test_credential_provider.py`
    - Test: valid credentials return user, non-existent email raises error, wrong password raises error, SSO-only user (no password_hash) raises error
    - _Requirements: 1.1, 1.2, 1.3, 1.5_

- [x] 6. Implement AuthService with TDD
  - [x] 6.1 Implement `AuthService` in `app/application/services/auth_service.py`
    - Implement `login(email, password) -> TokenResponse`: delegates to `IAuthProvider`, checks `user.status == ACTIVE` (raises `AuthenticationError("Cuenta desactivada", 403)` if inactive), generates token pair via `TokenService`
    - Implement `refresh(refresh_token) -> TokenResponse`: decodes token, verifies `type == "refresh"`, issues new token pair
    - Implement `logout() -> dict`: returns confirmation message
    - _Requirements: 1.1, 1.4, 4.1, 4.2, 4.3, 4.4, 9.1, 9.2_

  - [x] 6.2 Write property test: Valid Credentials Produce Token Pair
    - **Property 8: Valid Credentials Produce Token Pair**
    - Create `tests/property/test_auth_login_property.py`
    - Use Hypothesis to generate active users with valid password hashes; verify login returns non-empty `access_token` and `refresh_token`, and decoded `sub` matches user UUID
    - **Validates: Requirements 1.1**

  - [x] 6.3 Write property test: Inactive Users Cannot Authenticate
    - **Property 9: Inactive Users Cannot Authenticate**
    - In `tests/property/test_auth_login_property.py`, verify that for any user with status INACTIVE, authentication always raises `AuthenticationError` with status_code 403
    - **Validates: Requirements 1.4**

  - [x] 6.4 Write property test: Valid Refresh Token Produces New Token Pair
    - **Property 10: Valid Refresh Token Produces New Token Pair**
    - Create `tests/property/test_token_refresh_property.py`
    - Use Hypothesis to generate valid refresh tokens; verify refresh produces new access_token and refresh_token with valid signatures and correct claims
    - **Validates: Requirements 4.1**

  - [x] 6.5 Write unit tests for AuthService
    - Create `tests/unit/test_auth_service.py`
    - Test: login with non-existent email, wrong password, inactive user, SSO-only user; refresh with expired token, access token used as refresh, invalid signature
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 4.1, 4.2, 4.3, 4.4_

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement FastAPI auth dependencies (middleware and guards)
  - [x] 8.1 Create `CurrentUser` model and `get_current_user` dependency in `app/api/v1/dependencies/auth.py`
    - Implement `CurrentUser(id: UUID, role: RoleEnum)` Pydantic model
    - Implement `get_current_user` dependency: extract `Authorization: Bearer <token>` header, decode via `TokenService`, assert `type == "access"`, return `CurrentUser`
    - Return HTTP 401 with appropriate messages: "Token no proporcionado" (missing header), "Token expirado" (expired), "Token inválido" (malformed/wrong type/wrong signature)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 8.2_

  - [x] 8.2 Implement `require_roles` dependency factory in `app/api/v1/dependencies/auth.py`
    - Create factory function that accepts a list of `RoleEnum` values and returns a dependency
    - ADMIN always has access regardless of the allowed roles list
    - Return HTTP 403 with "No tiene permisos para esta acción" if role is not authorized
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [x] 8.3 Implement `require_self_or_roles` dependency in `app/api/v1/dependencies/auth.py`
    - Allow access if user is accessing own data (user_id matches current_user.id)
    - Allow access if user has ADMIN role
    - Allow access if user is PROFESSOR and the target student is enrolled in one of their courses (query `professor_courses` + `enrollments` tables for RB-04)
    - Deny with HTTP 403 otherwise
    - _Requirements: 5.5, 5.6, 6.5_

  - [x] 8.4 Write property test: Role Guard Access
    - **Property 5: Role Guard Grants Access If and Only If Authorized**
    - Create `tests/property/test_role_guard_property.py`
    - Use Hypothesis to generate RoleEnum values and sets of allowed roles; verify access is granted iff role is in allowed set or role is ADMIN
    - **Validates: Requirements 5.1, 5.2, 5.4**

  - [x] 8.5 Write property test: RB-04 Professor Student Visibility
    - **Property 6: RB-04 Professor Student Visibility**
    - Create `tests/property/test_rb04_visibility_property.py`
    - Use Hypothesis to generate professor-course-student relationships; verify professor can access student data iff student is enrolled in a course assigned to the professor
    - **Validates: Requirements 5.5**

  - [x] 8.6 Write property test: Student Self-Access Restriction
    - **Property 7: Student Self-Access Restriction**
    - Create `tests/property/test_student_access_property.py`
    - Use Hypothesis to generate pairs of distinct UUIDs; verify STUDENT role can only access own data
    - **Validates: Requirements 5.6**

  - [x] 8.7 Write unit tests for auth dependencies
    - Create `tests/unit/test_auth_dependencies.py`
    - Test: missing Authorization header, malformed bearer format, refresh token used as access token, valid token extraction
    - _Requirements: 3.1, 3.2, 3.4, 3.5_

- [x] 9. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Create auth endpoints and register router
  - [x] 10.1 Create auth router in `app/api/v1/endpoints/auth.py`
    - Implement `POST /api/v1/auth/login` (public): accepts `LoginRequest`, returns `TokenResponse` with status 200
    - Implement `POST /api/v1/auth/refresh` (public): accepts `RefreshRequest`, returns `TokenResponse` with status 200
    - Implement `POST /api/v1/auth/logout` (authenticated): requires valid access token, returns `LogoutResponse` with status 200
    - Register exception handlers for `AuthenticationError`, `TokenExpiredError`, `InvalidTokenError` to return proper HTTP status codes and messages
    - Use `summary`, `description`, `response_model`, `status_code`, and `tags` on all endpoints per documentation standards
    - _Requirements: 1.1, 4.1, 6.7, 9.1, 9.2, 9.3_

  - [x] 10.2 Register auth router in `app/main.py`
    - Import and include the auth router with prefix `/api/v1` and tag `"Autenticación"`
    - Register exception handlers for custom auth exceptions
    - _Requirements: 6.7_

  - [x] 10.3 Write integration tests for auth endpoints
    - Create `tests/integration/test_auth_endpoints.py`
    - Test login success, login with invalid credentials, login with inactive user, refresh success, refresh with expired token, refresh with access token, logout with valid token, logout without token
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 4.1, 4.2, 4.3, 9.1_

- [x] 11. Protect existing endpoints with authentication and role guards
  - [x] 11.1 Add auth dependencies to user endpoints in `app/api/v1/endpoints/users.py`
    - `POST /api/v1/users` → require ADMIN role
    - `GET /api/v1/users` → require ADMIN or PROFESSOR role
    - `GET /api/v1/users/{user_id}` → use `require_self_or_roles` (ADMIN, self, or PROFESSOR with RB-04)
    - `PATCH /api/v1/users/{user_id}` → require ADMIN role
    - `PATCH /api/v1/users/{user_id}/status` → require ADMIN role
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 11.2 Ensure public endpoints remain unprotected
    - Verify `GET /health`, `GET /`, `POST /api/v1/auth/login`, `POST /api/v1/auth/refresh` do NOT require authentication
    - _Requirements: 6.6, 6.7_

  - [x] 11.3 Write integration tests for protected endpoints
    - Create `tests/integration/test_protected_endpoints.py`
    - Test that all `/api/v1/users` endpoints return 401 without a token
    - Test that public endpoints (`/health`, `/`, `/api/v1/auth/login`, `/api/v1/auth/refresh`) remain accessible without authentication
    - _Requirements: 6.1, 6.6, 6.7_

  - [x] 11.4 Write integration tests for role-based protection
    - Create `tests/integration/test_role_protection.py`
    - Test ADMIN can access all user endpoints
    - Test PROFESSOR can list users and view students in their courses but cannot create users or change status
    - Test STUDENT can only view own profile
    - _Requirements: 6.2, 6.3, 6.4, 6.5_

- [x] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The TDD methodology requires writing tests before production code (Red → Green → Refactor)
- All code follows the existing Clean Architecture pattern (Domain / Application / Infrastructure layers)
- `PyJWT` is the only new dependency; all test libraries are already in `requirements.txt`
