from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from config import settings

# Configure asynchronous engine with connection pool parameters for high load
engine = create_async_engine(
    settings.database_url,
    pool_size=20,           # Max connections kept in pool
    max_overflow=10,        # Max extra connections during spike loads
    pool_recycle=1800,      # Recycle connection after 30 minutes to prevent stale sockets
    pool_pre_ping=True      # Check connection health before using
)

# Async session factory
async_session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def init_db():
    """Initializes the database schema (creates tables if they do not exist)."""
    from database.models import Base
    from sqlalchemy import text
    async with engine.begin() as conn:
        # Create tables
        await conn.run_sync(Base.metadata.create_all)
        # Add column if not exists
        await conn.execute(text("ALTER TABLE categories ADD COLUMN IF NOT EXISTS icon VARCHAR(50) DEFAULT 'tag';"))
