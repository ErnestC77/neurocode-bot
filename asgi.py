"""Композиционный корень: FastAPI (Mini App + /api/*) + бот как фоновая
задача внутри lifespan. Единственный модуль, импортирующий и ``api``, и
``bot`` — так ``api/app.py`` ничего не знает про aiogram.

Запуск: ``uvicorn asgi:app --host 0.0.0.0 --port $PORT``.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import MenuButtonWebApp, WebAppInfo

from api.app import create_app
from bot import run_bot_polling
from config import Config, load_config
from db.database import init_db, init_engine

logger = logging.getLogger("asgi")

config = load_config()
init_engine(config.database_url)

bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


async def _bot_lifecycle(bot: Bot, config: Config) -> Callable[[], Awaitable[None]]:
    logger.info("lifespan: init_db() начат")
    await init_db()
    logger.info("lifespan: init_db() завершён")

    # Постоянная кнопка запуска Mini App рядом с полем ввода — не разовая
    # inline-кнопка в сообщении. Ставится один раз на старте процесса.
    logger.info("lifespan: set_chat_menu_button() начат")
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(text="Открыть", web_app=WebAppInfo(url=config.webhook_base_url)),
    )
    logger.info("lifespan: set_chat_menu_button() завершён")

    task = asyncio.create_task(run_bot_polling(bot, config))
    logger.info("lifespan: run_bot_polling запущен как фоновая задача")

    async def teardown() -> None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await bot.session.close()

    return teardown


app = create_app(bot=bot, config=config, bot_lifecycle=_bot_lifecycle)
