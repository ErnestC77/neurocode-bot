"""Инициализация async-движка SQLAlchemy и сессий."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from db.models import Base

_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def init_engine(database_url: str) -> None:
    global _engine, _sessionmaker
    _engine = create_async_engine(database_url, echo=False, pool_pre_ping=True)
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        raise RuntimeError("init_engine() должен быть вызван до обращения к БД")
    return _sessionmaker


# Лёгкие миграции для уже существующих таблиц (Postgres). На свежей БД колонки
# создаёт create_all, эти ALTER пригодятся при будущих изменениях схемы —
# каждая строка молча отваливается, если колонка/индекс уже существует.
_MIGRATIONS: list[str] = [
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS email VARCHAR(255)",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS worked_at TIMESTAMPTZ",
    "ALTER TABLE bot_settings ALTER COLUMN value TYPE TEXT",
]


async def init_db() -> None:
    """Создаёт таблицы и применяет накопленные ручные миграции."""
    assert _engine is not None
    from sqlalchemy import text

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    for stmt in _MIGRATIONS:
        try:
            async with _engine.begin() as conn:
                await conn.execute(text(stmt))
        except Exception:  # noqa: BLE001 — колонка/индекс уже есть
            pass
