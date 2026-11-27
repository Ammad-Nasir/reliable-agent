import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.config import settings
from app.db.models import Base

# Determine database engine URL
def get_db_url() -> str:
    # If SQLite fallback is forced or default Postgres is not running, use SQLite
    if settings.USE_SQLITE_FALLBACK:
        return settings.SQLITE_FALLBACK_URL
    return settings.DATABASE_URL

db_url = get_db_url()

engine = create_async_engine(
    db_url,
    echo=False,
    future=True,
    # SQLite connection arguments
    connect_args={"check_same_thread": False} if "sqlite" in db_url else {}
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

async def init_db():
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for obtaining async DB sessions."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
