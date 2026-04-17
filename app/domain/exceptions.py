"""Custom domain exceptions for authentication and authorization."""


class AuthenticationError(Exception):
    """Raised when authentication fails (wrong credentials, inactive user, etc.)."""

    def __init__(self, message: str = "Credenciales inválidas", status_code: int = 401):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class TokenExpiredError(Exception):
    """Raised when a JWT token has expired."""

    def __init__(self, message: str = "Token expirado"):
        self.message = message
        super().__init__(self.message)


class InvalidTokenError(Exception):
    """Raised when a JWT token is malformed, tampered, or has wrong type."""

    def __init__(self, message: str = "Token inválido"):
        self.message = message
        super().__init__(self.message)


class AuthorizationError(Exception):
    """Raised when an authenticated user lacks permission for an action."""

    def __init__(self, message: str = "No tiene permisos para esta acción"):
        self.message = message
        super().__init__(self.message)
