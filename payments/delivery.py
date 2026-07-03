"""Выдача доступа после успешной оплаты: инвайт в канал, PDF-тетрадь и видео
(практикум) / файл (книга)."""
from __future__ import annotations

import logging

from aiogram import Bot

from config import Config
from db import crud
from db.models import Purchase
from keyboards.inline import after_product_kb, payment_link_kb
from services import checkpoints, settings
from services.catalog import BOOK, PRACTICUM, get_available_products
from texts.messages import TEXTS

logger = logging.getLogger(__name__)


async def deliver(bot: Bot, config: Config, purchase: Purchase) -> None:
    if purchase.product == PRACTICUM:
        delivered = await _deliver_practicum(bot, config, purchase)
    elif purchase.product == BOOK:
        delivered = await _deliver_book(bot, config, purchase)
    else:
        logger.error("Неизвестный продукт %s, purchase=%s", purchase.product, purchase.id)
        return
    if not delivered:
        # Ядро продукта (инвайт/файл) не ушло из-за незаполненной настройки — НЕ
        # помечаем доставленным, иначе process_undelivered_purchases (scheduler.py)
        # больше никогда не подхватит эту покупку на ретрай, даже после того как
        # настройку заполнят.
        return
    await crud.mark_delivered(purchase.id)
    # Чекпоинт мог всё ещё указывать на "смотрит продукт" (practicum_viewed/book_viewed) —
    # без этого сброса scheduler продолжал бы считать покупку незакрытым этапом
    # (страховка cancel_check в scheduler.py это бы поймала, но лучше явно).
    await crud.set_checkpoint(purchase.user_tg_id, checkpoints.IDLE)


async def _deliver_practicum(bot: Bot, config: Config, purchase: Purchase) -> bool:
    chat_id = await settings.get_practicum_chat_id()
    if not chat_id:
        logger.error("practicum_channel_id не задан в /settings, не могу выдать доступ purchase=%s",
                     purchase.id)
        return False
    link = await bot.create_chat_invite_link(
        chat_id, member_limit=1, name=f"practicum-{purchase.user_tg_id}"[:32],
    )
    available = await get_available_products(purchase.user_tg_id)
    text = TEXTS["M6.3"].format(invite_link=link.invite_link)
    await bot.send_message(purchase.user_tg_id, text,
                           reply_markup=after_product_kb(PRACTICUM, available, config.webhook_base_url))

    workbook_file_id = await settings.get_str("practicum_workbook_file_id")
    if workbook_file_id:
        await bot.send_document(purchase.user_tg_id, workbook_file_id, protect_content=True)
    else:
        logger.error(
            "practicum_workbook_file_id не задан в /settings, не могу отправить тетрадь purchase=%s",
            purchase.id,
        )

    # file_id приоритетен над url: как только видео будет загружено в self-hosted
    # Bot API (снимает лимит 50 МБ облачного API) и file_id вписан в /settings,
    # доставка сама переключится с ссылки на нативный файл — без правок кода.
    video_file_id = await settings.get_str("practicum_video_file_id")
    video_url = await settings.get_str("practicum_video_url")
    if video_file_id:
        await bot.send_video(purchase.user_tg_id, video_file_id, protect_content=True)
    elif video_url:
        await bot.send_message(
            purchase.user_tg_id, "Видео к практикуму:",
            reply_markup=payment_link_kb(video_url, "Смотреть видео"),
        )
    else:
        logger.error(
            "practicum_video_file_id и practicum_video_url не заданы в /settings, "
            "не могу отправить видео purchase=%s",
            purchase.id,
        )

    return True


async def _deliver_book(bot: Bot, config: Config, purchase: Purchase) -> bool:
    available = await get_available_products(purchase.user_tg_id)
    await bot.send_message(purchase.user_tg_id, TEXTS["M8.3"],
                           reply_markup=after_product_kb(BOOK, available, config.webhook_base_url))
    book_file_id = await settings.get_str("book_file_id")
    if not book_file_id:
        logger.error("book_file_id не задан в /settings, не могу отправить файл purchase=%s",
                     purchase.id)
        return False
    await bot.send_document(purchase.user_tg_id, book_file_id, protect_content=True)
    return True
