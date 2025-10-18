"""
Async PostgreSQL Database Configuration with SQLAlchemy 2.0
Optimized for 100+ concurrent device connections
"""

import os
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool
from typing import AsyncGenerator
import logging
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Convert postgres:// to postgresql+asyncpg:// for async support
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# Remove sslmode parameter if present (asyncpg handles SSL differently)
if "sslmode=" in DATABASE_URL:
    import re
    DATABASE_URL = re.sub(r'[?&]sslmode=[^&]*', '', DATABASE_URL)
    DATABASE_URL = DATABASE_URL.rstrip('?&')

# Development fallback
if not DATABASE_URL or DATABASE_URL == "postgresql+asyncpg://":
    DATABASE_URL = "postgresql+asyncpg://postgres:password@localhost:5432/mdm_dev"
    logger.warning("Using development database URL")

# Base class for all models with async support
class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all database models with async support"""
    pass

# Create async engine with connection pooling optimized for high concurrency
engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("DEBUG", "false").lower() == "true",  # SQL logging in debug mode
    pool_size=20,  # Base pool size for 100+ devices
    max_overflow=40,  # Additional connections when needed
    pool_timeout=30,  # Timeout for getting connection from pool
    pool_recycle=1800,  # Recycle connections after 30 minutes
    pool_pre_ping=True,  # Verify connections before use
    connect_args={
        "server_settings": {
            "application_name": "MDM_Backend",
            "jit": "off"
        },
        "command_timeout": 60
    }
)

# Session factory with expire_on_commit=False for async patterns
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Important for async to avoid lazy loading issues
    autoflush=False,
    autocommit=False
)

# Dependency for FastAPI routes
async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency to get async database session.
    Use in FastAPI routes with Depends(get_async_db)
    """
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# Context manager for standalone database operations
@asynccontextmanager
async def get_db_session():
    """Context manager for getting a database session outside of FastAPI"""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# Database management functions
async def init_db():
    """Initialize database, create tables if they don't exist"""
    try:
        async with engine.begin() as conn:
            # Import models to ensure they're registered
            from models_async import (
                User, Device, DeviceEvent, PasswordResetToken,
                ApkVersion, ApkInstallation, BatteryWhitelist
            )
            
            # Create all tables
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created/verified successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise

async def ping_database():
    """Test database connection"""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            logger.info("✅ Database connection successful")
            return True
    except Exception as e:
        logger.error(f"❌ Database connection failed: {e}")
        return False

async def close_db():
    """Close database connections"""
    await engine.dispose()
    logger.info("Database connections closed")

# Connection pool statistics
def get_pool_status():
    """Get current connection pool statistics"""
    pool = engine.pool
    return {
        "size": pool.size(),
        "checked_in": pool.checked_in_connections,
        "overflow": pool.overflow(),
        "total": pool.size() + pool.overflow(),
    }

# Performance monitoring
async def analyze_query_performance(query_str: str):
    """Analyze query performance using EXPLAIN ANALYZE"""
    from sqlalchemy import text
    
    async with engine.connect() as conn:
        result = await conn.execute(
            text(f"EXPLAIN ANALYZE {query_str}")
        )
        return result.fetchall()

# Database maintenance tasks
async def cleanup_old_events(days: int = 2):
    """Remove device events older than specified days (default: 2)"""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import delete, select
    from server.models_async import DeviceEvent
    
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    async with async_session_maker() as session:
        # Count events to be deleted
        count_stmt = select(func.count()).select_from(DeviceEvent).where(
            DeviceEvent.timestamp < cutoff_date
        )
        count_result = await session.execute(count_stmt)
        count = count_result.scalar()
        
        if count > 0:
            # Delete old events
            delete_stmt = delete(DeviceEvent).where(
                DeviceEvent.timestamp < cutoff_date
            )
            await session.execute(delete_stmt)
            await session.commit()
            logger.info(f"Cleaned up {count} device events older than {days} days")
        
        return count

async def optimize_tables():
    """Run VACUUM ANALYZE on all tables for optimization"""
    from sqlalchemy import text
    
    async with engine.connect() as conn:
        # Get all table names
        result = await conn.execute(
            text("""
                SELECT tablename 
                FROM pg_tables 
                WHERE schemaname = 'public'
            """)
        )
        tables = [row[0] for row in result]
        
        # Run VACUUM ANALYZE on each table
        for table in tables:
            await conn.execute(text(f"VACUUM ANALYZE {table}"))
            logger.info(f"Optimized table: {table}")
        
        await conn.commit()
        return tables

from sqlalchemy import text, func