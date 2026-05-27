#!/usr/bin/env python3
"""
Reset script — elimina TODOS los datos de la base de datos local.

⚠️  DESTRUCTIVO. Solo usar en desarrollo/pruebas, NUNCA en producción.

Uso:
    python3 -m scripts.reset_db
"""

import asyncio

from sqlalchemy import text

from app.infrastructure.database import AsyncSessionFactory, engine

# Orden respeta FK: tablas hijas primero.
TABLES = [
    "attendances",
    "class_sessions",
    "referrals",
    "notifications",
    "push_subscriptions",
    "audit_logs",
    "consents",
    "enrollments",
    "student_profiles",
    "courses",
    "subjects",
    "programs",
    "users",
    "job_configs",
]


async def reset() -> None:
    async with AsyncSessionFactory() as session:
        async with session.begin():
            for table in TABLES:
                await session.execute(
                    text(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE')
                )
                print(f"  ✓ {table}")
    print("\n✅ Base de datos reseteada.")


async def main() -> None:
    print("=" * 60)
    print("⚠️  ADVERTENCIA: Se eliminarán TODOS los datos.")
    print("=" * 60)
    confirm = input("Escribe 'CONFIRMAR' para continuar: ").strip()
    if confirm != "CONFIRMAR":
        print("Operación cancelada.")
        return
    try:
        await reset()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
