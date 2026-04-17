"""Value object representing the JWT payload claims."""

from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import RoleEnum


@dataclass(frozen=True)
class TokenPayload:
    """Immutable value object for decoded JWT token claims.

    Attributes:
        sub: User UUID as string.
        role: User role from RoleEnum.
        type: Token type — ``"access"`` or ``"refresh"``.
        exp: Expiration timestamp.
        iat: Issued-at timestamp.
    """

    sub: str
    role: RoleEnum
    type: str
    exp: datetime
    iat: datetime
