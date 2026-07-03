"""Выдача доступа после успешной оплаты: инвайт в канал (практикум) / файл (книга)."""
from __future__ import annotations

import logging

from aiogram import Bot

from config import Config
from db import crud
from db.models import Purchase
from keyboards.inline import after_product_kb
from services import checkpoints
from services.catalog import BOOK, PRACTICUM, get_available_products
from texts.messages import TEXTS

logger = logging.getLogger(__name__)


async def deliver(bot: Bot, config: Config, purchase: Purchase) -> None:
    if purchase.product == PRACTICUM:
        await _deliver_practicum(bot, config, purchase)
    elif purchase.product == BOOK:
        await _deliver_book(bot, config, purchase)
    else:
        logger.error("Неизвестный продукт %s, purchase=%s", purchase.product, purchase.id)
        return
    await crud.mark_delivered(purchase.id)
    # Чекпоинт мог всё ещё указывать на "смотрит продукт" (practicum_viewed/book_viewed) —
    # без этого сброса scheduler продолжал бы считать покупку незакрытым этапом
    # (страховка cancel_check в scheduler.py это бы поймала, но лучше явно).
    await crud.set_checkpoint(purchase.user_tg_id, checkpoints.IDLE)


async def _deliver_practicum(bot: Bot, config: Config, purchase: Purchase) -> None:
    chat_id = config.practicum_chat_id
    if not chat_id:
        logger.error("PRACTICUM_CHANNEL_ID не задан, не могу выдать доступ purchase=%s", purchase.id)
        return
    link = await bot.create_chat_invite_link(
        chat_id, member_limit=1, name=f"practicum-{purchase.user_tg_id}"[:32],
    )
    available = await get_available_products(purchase.user_tg_id)
    text = TEXTS["M6.3"].format(invite_link=link.invite_link)
    await bot.send_message(purchase.user_tg_id, text,
                           reply_markup=after_product_kb(PRACTICUM, available))


async def _deliver_book(bot: Bot, config: Config, purchase: Purchase) -> None:
    available = await get_available_products(purchase.user_tg_id)
    await bot.send_message(purchase.user_tg_id, TEXTS["M8.3"],
                           reply_markup=after_product_kb(BOOK, available))
    if config.book_file_id:
        await bot.send_document(purchase.user_tg_id, config.book_file_id, protect_content=True)
    else:
        logger.error("BOOK_FILE_ID не задан, не могу отправить файл purchase=%s", purchase.id)
