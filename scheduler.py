"""Фоновая задача: напоминания R1-R6 + ретрай выгрузки лидов и выдачи доступа.

Декларативный tick, без per-user таймеров: периодический SELECT по
users.checkpoint + last_activity_at (db/crud.py::due_reminder_users).
Дедупликация — уникальность (user_tg_id, reminder_code) в reminders_sent,
маркер «занимается» до отправки (паттерн из allpay-sub-bot/scheduler.py).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

from config import Config
from db import crud
from exports.notifier import retry_unexported_leads
from keyboards.inline import open_miniapp_kb
from payments import delivery
from services import checkpoints, settings
from services.catalog import BOOK, PRACTICUM
from texts.messages import TEXTS

logger = logging.getLogger("scheduler")

# checkpoint -> доп. проверка, что напоминание уже неактуально (юзер довёл этап до конца).
_CANCEL_CHECK = {
    checkpoints.PRACTICUM_VIEWED: lambda tg_id: crud.has_paid(tg_id, PRACTICUM),
    checkpoints.CONSULT_VIEWED: crud.has_lead,
    checkpoints.BOOK_VIEWED: lambda tg_id: crud.has_paid(tg_id, BOOK),
}


def _reminder_keyboard(config: Config) -> InlineKeyboardMarkup:
    """Одна и та же кнопка для всех R1-R6 — открывает Mini App, который сам
    покажет нужный экран по чекпоинту пользователя (раньше у каждого R-кода
    была своя callback-кнопка в конкретный чат-хендлер — теперь их нет)."""
    return open_miniapp_kb(config.webhook_base_url)


async def process_reminders(bot: Bot, config: Config) -> int:
    sent = 0
    delay = timedelta(hours=await settings.get_int("reminder_delay_hours"))
    for user, code in await crud.due_reminder_users(checkpoints.REMINDER_CODES, delay):
        cancel_check = _CANCEL_CHECK.get(user.checkpoint)
        if cancel_check is not None and await cancel_check(user.tg_id):
            # Условие уже неактуально (купил/записался) — просто гасим будущие проверки.
            await crud.log_reminder(user.tg_id, code)
            continue

        if not await crud.log_reminder(user.tg_id, code):
            continue  # уже отправлено (гонка между тиками) — пропускаем

        try:
            await bot.send_message(user.tg_id, TEXTS[code], reply_markup=_reminder_keyboard(config))
            sent += 1
        except Exception:  # noqa: BLE001
            logger.exception("Не удалось отправить напоминание %s user=%s", code, user.tg_id)
    if sent:
        logger.info("Отправлено напоминаний: %s", sent)
    return sent


async def process_undelivered_purchases(bot: Bot, config: Config) -> int:
    """Ретрай выдачи доступа для оплаченных, но не доставленных покупок — на случай,
    если процесс упал между webhook mark_paid() и фактической отправкой инвайта/файла."""
    delivered = 0
    for purchase in await crud.get_undelivered_paid_purchases():
        try:
            await delivery.deliver(bot, config, purchase)
            delivered += 1
        except Exception:  # noqa: BLE001
            logger.exception("Не удалось повторно выдать доступ purchase=%s", purchase.id)
    if delivered:
        logger.info("Повторно выдан доступ: %s", delivered)
    return delivered


async def reminder_loop(bot: Bot, config: Config) -> None:
    logger.info("Планировщик запущен")
    while True:
        interval = 300
        try:
            await process_reminders(bot, config)
            await process_undelivered_purchases(bot, config)
            await retry_unexported_leads(bot, config)
            interval = await settings.get_int("reminder_check_interval")
        except Exception:  # noqa: BLE001
            logger.exception("Ошибка в цикле планировщика")
        await asyncio.sleep(interval)
