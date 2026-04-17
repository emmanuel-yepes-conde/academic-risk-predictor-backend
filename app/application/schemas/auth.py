"""Pydantic DTOs for authentication operations."""

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """Schema for user login via email and password."""

    email: EmailStr = Field(..., description="Correo electrónico del usuario")
    password: str = Field(..., min_length=1, description="Contraseña del usuario")


class RefreshRequest(BaseModel):
    """Schema for refreshing an access token."""

    refresh_token: str = Field(..., description="Refresh token JWT")


class TokenResponse(BaseModel):
    """Schema for the token pair returned after login or refresh."""

    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Tipo de token")
    expires_in: int = Field(..., description="Tiempo de vida del access token en segundos")


class LogoutResponse(BaseModel):
    """Schema for the logout confirmation response."""

    message: str = Field(default="Sesión cerrada exitosamente", description="Mensaje de confirmación")
