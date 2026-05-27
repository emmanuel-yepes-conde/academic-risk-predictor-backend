"""
Módulo de infraestructura de base de datos.
Gestiona el motor SQLAlchemy asíncrono y las sesiones de DB.
"""

from typing import AsyncGenerator

from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

_engine_kwargs = {
    "echo": settings.DB_ECHO,
    "pool_pre_ping": True,
}

if settings.HOST in {"localhost", "127.0.0.1", "::1"}:
    # En desarrollo local, uvicorn/reload puede recrear event loops. asyncpg no
    # permite reutilizar conexiones creadas en otro loop, así que no las pooleamos.
    _engine_kwargs["poolclass"] = NullPool
else:
    _engine_kwargs.update(
        {
            "pool_size": settings.DB_POOL_MIN,
            "max_overflow": settings.DB_POOL_MAX - settings.DB_POOL_MIN,
            "pool_recycle": 1800,  # recicla conexiones cada 30 min, evita conexiones stale
        }
    )

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

AsyncSessionFactory = async_sessionmaker(engine, expire_on_commit=False)

# Engine dedicado para background tasks: siempre NullPool para evitar el error
# "Task got Future attached to a different loop" que ocurre cuando asyncpg
# intenta reciclar conexiones del pool desde un contexto asyncio diferente.
_bg_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    poolclass=NullPool,
)
BackgroundSessionFactory = async_sessionmaker(_bg_engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Generador asíncrono de sesiones de DB compatible con FastAPI Depends.

    Abre una sesión por request. Si el endpoint termina bien hace commit; si
    lanza una excepción hace rollback y propaga el error original.
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
