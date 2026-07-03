"""Точка входа: бот (long-polling) + aiohttp-сервер для webhook ЮKassa в одном процессе."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiohttp import web

from config import load_config
from db.database import init_db, init_engine
from handlers import admin, book, consent, consult, menu, practicum, start, test
from middlewares import ActivityMiddleware
from payments.webhook import setup_routes
from scheduler import reminder_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("bot")


def build_dispatcher(config) -> Dispatcher:
    dp = Dispatcher()
    dp["config"] = config
    dp.message.middleware(ActivityMiddleware())
    dp.callback_query.middleware(ActivityMiddleware())
    dp.include_router(start.router)
    dp.include_router(consent.router)
    dp.include_router(test.router)
    dp.include_router(menu.router)
    dp.include_router(practicum.router)
    dp.include_router(book.router)
    dp.include_router(admin.router)
    # consult.router — последним: у него catch-all текстовый хендлер (ввод email),
    # который иначе перехватил бы команды/сообщения последующих роутеров.
    dp.include_router(consult.router)
    return dp


async def main() -> None:
    config = load_config()

    init_engine(config.database_url)
    await init_db()

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher(config)

    # aiohttp-сервер для webhook ЮKassa (заодно биндит PORT — нужно для хостинга).
    app = web.Application()
    setup_routes(app, bot, config)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=config.port)
    await site.start()
    logger.info("Webhook-сервер ЮKassa слушает порт %s (%s)", config.port, config.yookassa_webhook_url)

    # Фоновая рассылка напоминаний R1-R6 + ретраи выгрузки/выдачи доступа.
    reminder_task = asyncio.create_task(reminder_loop(bot, config))

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Запуск long-polling…")
        await dp.start_polling(bot)
    finally:
        reminder_task.cancel()
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Остановлено")
