"""
Módulo de infraestructura de base de datos.
Gestiona el motor SQLAlchemy asíncrono y las sesiones de DB.
"""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_MIN,
    max_overflow=settings.DB_POOL_MAX - settings.DB_POOL_MIN,
    echo=settings.DB_ECHO,
    pool_recycle=1800,  # recicla conexiones cada 30 min, evita conexiones stale
)

AsyncSessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Generador asíncrono de sesiones de DB compatible con FastAPI Depends.

    Usa el patrón oficial de SQLAlchemy 2.x para Python 3.13:
    - `async with AsyncSessionFactory()` garantiza que close() se llame
      solo cuando no haya operaciones en vuelo (evita IllegalStateChangeError).
    - `async with session.begin()` hace commit automático al salir con éxito
      y rollback automático ante cualquier excepción, sin llamadas manuales.
    """
    async with AsyncSessionFactory() as session:
        async with session.begin():
            yield session
