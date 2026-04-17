"""
Módulo de Seguridad
Helpers para hashing y verificación de contraseñas usando bcrypt
"""

import bcrypt


def hash_password(plain: str) -> str:
    """Genera un hash bcrypt a partir de una contraseña en texto plano."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verifica si una contraseña en texto plano coincide con su hash bcrypt."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
