"""
Seed script — crea el usuario ADMIN inicial.

Uso:
    python3 -m scripts.seed_admin

Solo crea el admin si no existe un usuario con ese email.
"""

import asyncio
import sys

from sqlalchemy import select

from app.core.security import hash_password
from app.infrastructure.database import AsyncSessionFactory, engine
from app.infrastructure.models.user import User
from app.domain.enums import RoleEnum, UserStatusEnum

# ── Configuración del admin inicial ──────────────────────────────────────
ADMIN_EMAIL = "admin@universidad.edu"
ADMIN_PASSWORD = "Admin123!"
ADMIN_FULL_NAME = "Administrador del Sistema"


async def seed() -> None:
    async with AsyncSessionFactory() as session:
        result = await session.execute(
            select(User).where(User.email == ADMIN_EMAIL)
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            print(f"⚠️  Ya existe un usuario con email {ADMIN_EMAIL}. No se creó nada.")
            return

        admin = User(
            email=ADMIN_EMAIL,
            full_name=ADMIN_FULL_NAME,
            role=RoleEnum.ADMIN,
            status=UserStatusEnum.ACTIVE,
            password_hash=hash_password(ADMIN_PASSWORD),
        )
        session.add(admin)
        await session.commit()
        print(f"✅ Admin creado exitosamente:")
        print(f"   Email:    {ADMIN_EMAIL}")
        print(f"   Password: {ADMIN_PASSWORD}")
        print(f"   Rol:      ADMIN")


async def main() -> None:
    try:
        await seed()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
