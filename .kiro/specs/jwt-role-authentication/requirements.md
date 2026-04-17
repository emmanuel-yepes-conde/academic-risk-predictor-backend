# Requirements Document

## Introduction

Este documento define los requisitos para implementar autenticación basada en JWT (JSON Web Tokens) con control de acceso por roles en el sistema MPRA (Modelo Predictivo de Riesgo Académico). El sistema debe emitir tokens JWT tras una autenticación exitosa, validar dichos tokens en cada petición protegida, y aplicar políticas de autorización según los roles existentes (STUDENT, PROFESSOR, ADMIN). La implementación debe ser compatible con la futura integración de SSO con Microsoft y Google, y respetar la regla de negocio RB-04 (los profesores solo pueden ver estudiantes inscritos en sus cursos asignados).

## Glossary

- **Auth_Service**: Servicio de la capa de aplicación responsable de autenticar usuarios y emitir tokens JWT.
- **Token_Service**: Servicio responsable de crear, firmar y decodificar tokens JWT.
- **Auth_Middleware**: Dependencia de FastAPI que intercepta peticiones, extrae el token JWT del header `Authorization` y valida su autenticidad.
- **Role_Guard**: Dependencia de FastAPI que verifica si el rol del usuario autenticado tiene permiso para acceder a un endpoint específico.
- **Access_Token**: Token JWT de corta duración que contiene el identificador del usuario, su rol y tiempo de expiración.
- **Refresh_Token**: Token JWT de mayor duración utilizado exclusivamente para obtener un nuevo Access_Token sin requerir credenciales.
- **JWT_Payload**: Estructura de datos contenida en el token JWT, incluyendo `sub` (user ID), `role`, `exp` (expiración) e `iat` (emisión).
- **Login_Endpoint**: Endpoint POST `/api/v1/auth/login` que recibe credenciales y retorna tokens.
- **MPRA**: Modelo Predictivo de Riesgo Académico — el sistema completo.
- **RoleEnum**: Enumeración del dominio con valores STUDENT, PROFESSOR, ADMIN.
- **UserStatusEnum**: Enumeración del dominio con valores ACTIVE, INACTIVE.

## Requirements

### Requirement 1: Autenticación por Credenciales

**User Story:** Como usuario del MPRA, quiero autenticarme con mi correo electrónico y contraseña, para obtener un token de acceso que me permita usar los endpoints protegidos.

#### Acceptance Criteria

1. WHEN a user submits valid email and password to the Login_Endpoint, THE Auth_Service SHALL verify the credentials against the stored password_hash and return an Access_Token and a Refresh_Token.
2. WHEN a user submits an email that does not exist in the system, THE Auth_Service SHALL return HTTP 401 with a generic error message "Credenciales inválidas".
3. WHEN a user submits a valid email with an incorrect password, THE Auth_Service SHALL return HTTP 401 with the same generic error message "Credenciales inválidas".
4. WHEN a user with status INACTIVE attempts to authenticate, THE Auth_Service SHALL return HTTP 403 with the message "Cuenta desactivada".
5. WHEN a user without a password_hash (SSO-only user) attempts to authenticate via the Login_Endpoint, THE Auth_Service SHALL return HTTP 401 with the message "Credenciales inválidas".

### Requirement 2: Generación de Tokens JWT

**User Story:** Como sistema MPRA, quiero generar tokens JWT firmados con información del usuario, para que los endpoints protegidos puedan verificar la identidad y el rol del solicitante.

#### Acceptance Criteria

1. THE Token_Service SHALL generate Access_Tokens containing the fields: `sub` (user UUID), `role` (RoleEnum value), `exp` (expiration timestamp), and `iat` (issued-at timestamp).
2. THE Token_Service SHALL sign all tokens using the HS256 algorithm with a secret key configured via the environment variable `JWT_SECRET_KEY`.
3. THE Token_Service SHALL set the Access_Token expiration to the value configured in the environment variable `ACCESS_TOKEN_EXPIRE_MINUTES` with a default of 30 minutes.
4. THE Token_Service SHALL set the Refresh_Token expiration to the value configured in the environment variable `REFRESH_TOKEN_EXPIRE_DAYS` with a default of 7 days.
5. THE Token_Service SHALL include a `type` claim in each token to distinguish between "access" and "refresh" tokens.
6. FOR ALL valid JWT_Payload objects, encoding then decoding SHALL produce an equivalent payload (round-trip property).

### Requirement 3: Validación de Tokens y Protección de Endpoints

**User Story:** Como sistema MPRA, quiero validar el token JWT en cada petición a endpoints protegidos, para garantizar que solo usuarios autenticados accedan a los recursos.

#### Acceptance Criteria

1. WHEN a request includes a valid Access_Token in the `Authorization: Bearer <token>` header, THE Auth_Middleware SHALL extract the JWT_Payload and make the authenticated user available to the endpoint handler.
2. WHEN a request does not include an `Authorization` header, THE Auth_Middleware SHALL return HTTP 401 with the message "Token no proporcionado".
3. WHEN a request includes an expired Access_Token, THE Auth_Middleware SHALL return HTTP 401 with the message "Token expirado".
4. WHEN a request includes a malformed or tampered token, THE Auth_Middleware SHALL return HTTP 401 with the message "Token inválido".
5. WHEN a request includes a Refresh_Token instead of an Access_Token in a protected endpoint, THE Auth_Middleware SHALL return HTTP 401 with the message "Token inválido".
6. THE Auth_Middleware SHALL reject tokens signed with a different secret key by returning HTTP 401.

### Requirement 4: Renovación de Tokens

**User Story:** Como usuario del MPRA, quiero renovar mi token de acceso usando un refresh token, para mantener mi sesión activa sin tener que ingresar mis credenciales nuevamente.

#### Acceptance Criteria

1. WHEN a valid Refresh_Token is submitted to the refresh endpoint `POST /api/v1/auth/refresh`, THE Token_Service SHALL issue a new Access_Token and a new Refresh_Token.
2. WHEN an expired Refresh_Token is submitted to the refresh endpoint, THE Token_Service SHALL return HTTP 401 with the message "Refresh token expirado".
3. WHEN an Access_Token is submitted to the refresh endpoint instead of a Refresh_Token, THE Token_Service SHALL return HTTP 401 with the message "Token inválido".
4. WHEN a Refresh_Token with an invalid signature is submitted, THE Token_Service SHALL return HTTP 401 with the message "Token inválido".

### Requirement 5: Autorización por Roles

**User Story:** Como administrador del MPRA, quiero que cada endpoint tenga restricciones de acceso según el rol del usuario, para que cada actor solo pueda realizar las operaciones que le corresponden.

#### Acceptance Criteria

1. WHEN an authenticated user with an authorized role accesses a protected endpoint, THE Role_Guard SHALL allow the request to proceed.
2. WHEN an authenticated user with an unauthorized role accesses a protected endpoint, THE Role_Guard SHALL return HTTP 403 with the message "No tiene permisos para esta acción".
3. THE Role_Guard SHALL support specifying a list of allowed roles per endpoint via a dependency parameter.
4. WHEN a user with role ADMIN accesses any endpoint, THE Role_Guard SHALL allow the request (ADMIN has full access).
5. WHEN a user with role PROFESSOR accesses student data, THE Role_Guard SHALL allow the request only for students enrolled in courses assigned to the Professor via the professor_courses table.
6. WHEN a user with role STUDENT accesses data, THE Role_Guard SHALL restrict access to the Student's own data only.

### Requirement 6: Protección de Endpoints Existentes

**User Story:** Como equipo de desarrollo del MPRA, quiero aplicar autenticación y autorización a los endpoints existentes, para que los recursos del sistema estén protegidos adecuadamente.

#### Acceptance Criteria

1. THE MPRA SHALL require a valid Access_Token for all endpoints under `/api/v1/users`.
2. THE MPRA SHALL restrict user creation (`POST /api/v1/users`) to users with role ADMIN.
3. THE MPRA SHALL restrict user listing (`GET /api/v1/users`) to users with role ADMIN or PROFESSOR.
4. THE MPRA SHALL restrict user status changes (`PATCH /api/v1/users/{user_id}/status`) to users with role ADMIN.
5. THE MPRA SHALL allow user profile retrieval (`GET /api/v1/users/{user_id}`) for ADMIN, for the user themselves, or for a PROFESSOR viewing a student enrolled in their courses.
6. THE MPRA SHALL keep the `GET /health` endpoint and the root endpoint `/` publicly accessible without authentication.
7. THE MPRA SHALL keep the authentication endpoints (`POST /api/v1/auth/login` and `POST /api/v1/auth/refresh`) publicly accessible.

### Requirement 7: Configuración de Seguridad JWT

**User Story:** Como equipo de operaciones, quiero que los parámetros de seguridad JWT sean configurables mediante variables de entorno, para poder ajustarlos según el entorno de despliegue.

#### Acceptance Criteria

1. THE MPRA SHALL load the JWT signing secret from the environment variable `JWT_SECRET_KEY`.
2. THE MPRA SHALL load the access token expiration from the environment variable `ACCESS_TOKEN_EXPIRE_MINUTES` with a default value of 30.
3. THE MPRA SHALL load the refresh token expiration from the environment variable `REFRESH_TOKEN_EXPIRE_DAYS` with a default value of 7.
4. THE MPRA SHALL load the JWT algorithm from the environment variable `JWT_ALGORITHM` with a default value of "HS256".
5. IF the `JWT_SECRET_KEY` environment variable is not set, THEN THE MPRA SHALL fail to start and log an error message indicating the missing configuration.

### Requirement 8: Compatibilidad con Futura Integración SSO

**User Story:** Como arquitecto del MPRA, quiero que la implementación JWT sea compatible con la futura integración de SSO con Microsoft y Google, para evitar refactorizaciones mayores cuando se implemente SSO.

#### Acceptance Criteria

1. THE Token_Service SHALL generate tokens using the same JWT_Payload structure regardless of the authentication method (credentials or future SSO).
2. THE Auth_Middleware SHALL validate tokens based solely on signature and claims, without depending on the authentication method used to obtain the token.
3. THE User model SHALL retain the `microsoft_oid` and `google_oid` fields for future SSO provider linking.
4. THE Auth_Service SHALL use an authentication strategy pattern that allows adding new authentication providers without modifying existing authentication logic.

### Requirement 9: Logout y Seguridad de Sesión

**User Story:** Como usuario del MPRA, quiero poder cerrar mi sesión de forma segura, para proteger mi cuenta cuando dejo de usar el sistema.

#### Acceptance Criteria

1. WHEN a user sends a POST request to `/api/v1/auth/logout`, THE Auth_Service SHALL respond with HTTP 200 and a confirmation message.
2. THE MPRA SHALL implement stateless logout by relying on short-lived Access_Tokens and client-side token removal.
3. THE Auth_Service SHALL provide the token expiration time in the login and refresh responses so the client can manage token lifecycle.
