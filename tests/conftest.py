"""Общие тестовые хелперы для API-тестов: подпись initData и bot_lifecycle-и
для create_app() (без БД / с sqlite-в-памяти).

sqlite поднимается внутри bot_lifecycle (а не в отдельной pytest-фикстуре),
потому что TestClient прогоняет ASGI lifespan в СВОЁМ выделенном потоке/loop —
если создать async-движок в другом loop (обычная async-фикстура), запросы
через TestClient упадут с "attached to a different event loop".
"""
from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlencode

import db.database as database
from config import Config
from db.models import Base

BOT_TOKEN = "123456:test-token"


def _sign(fields: dict) -> str:
    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": signature})


def _test_config() -> Config:
    return Config(
        bot_token=BOT_TOKEN, database_url="postgresql+asyncpg://u:p@localhost/db",
        port=8080, owner_chat_id=None, yookassa_secret_key="secret",
        webhook_base_url="https://example.com",
    )


async def _noop_lifecycle(bot, config):
    async def teardown() -> None:
        return None

    return teardown


async def _sqlite_lifecycle(bot, config):
    database.init_engine("sqlite+aiosqlite:///:memory:")
    async with database._engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def teardown() -> None:
        await database._engine.dispose()
        database._engine = None
        database._sessionmaker = None

    return teardown


def init_data_for(tg_id: int) -> str:
    return _sign({"auth_date": str(int(time.time())), "user": f'{{"id": {tg_id}}}'})
