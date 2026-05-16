from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.config import settings


def _async_url(url: str) -> str:
    """Convert any postgres:// / postgresql:// URL to postgresql+asyncpg://"""
    return (
        url.replace("postgres://", "postgresql+asyncpg://")
           .replace("postgresql://", "postgresql+asyncpg://")
    )


engine = create_async_engine(
    _async_url(settings.database_url),
    echo=False,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
    class_=AsyncSession,
)


class Base(DeclarativeBase):
    pass


# FastAPI dependency
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
