import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import database_settings

logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.engine: AsyncEngine = create_async_engine(
            database_settings.url,
            echo=False,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            future=True,
        )
        self.async_session_maker = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self.logger.info("DatabaseManager enterprise-service инициализирован")

    @asynccontextmanager
    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.async_session_maker() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def close(self):
        await self.engine.dispose()
        self.logger.info("Соединение с БД в enterprise-service закрыто")


db_manager = DatabaseManager()
