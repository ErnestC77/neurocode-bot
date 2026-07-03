"""aiogram-диспетчер и общий раннер long-polling.

``run_bot_polling`` используется в двух местах:
- здесь же, для локального standalone-запуска (``python bot.py``, без
  Mini App/FastAPI — удобно для быстрой проверки /settings и напоминаний);
- из ``asgi.py`` как фоновая задача внутри FastAPI lifespan (продакшен).

Сам этот модуль ничего не знает про FastAPI — раздельность частей: этот
файл только про бота, ``api/app.py`` только про HTTP, ``asgi.py`` их сводит.
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import Config, load_config
from db.database import init_db, init_engine
from handlers import admin, settings_admin, start, text_input
from middlewares import ActivityMiddleware
from scheduler import reminder_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("bot")


def build_dispatcher(config: Config) -> Dispatcher:
    dp = Dispatcher()
    dp["config"] = config
    dp.message.middleware(ActivityMiddleware())
    dp.callback_query.middleware(ActivityMiddleware())
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(settings_admin.router)
    # text_input.router — последним: единственный catch-all для свободного
    # текста (значения настроек), иначе он перехватил бы команды/сообщения,
    # предназначенные другим роутерам.
    dp.include_router(text_input.router)
    return dp


async def run_bot_polling(bot: Bot, config: Config) -> None:
    dp = build_dispatcher(config)
    reminder_task = asyncio.create_task(reminder_loop(bot, config))
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Запуск long-polling…")
        await dp.start_polling(bot)
    finally:
        reminder_task.cancel()


async def _standalone_main() -> None:
    config = load_config()
    init_engine(config.database_url)
    await init_db()

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        await run_bot_polling(bot, config)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(_standalone_main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Остановлено")
