"""Выгрузка лидов и фактов оплаты владельцу бота.

MVP: сообщение в OWNER_CHAT_ID. Интерфейс изолирован от остального кода — если
решится сменить канал выгрузки (Google Sheets/CRM), меняется только этот файл.
"""
from __future__ import annotations

import logging

from aiogram import Bot

from config import Config
from db import crud
from db.models import Lead, Purchase
from services import settings

logger = logging.getLogger(__name__)

_PRODUCT_LABELS = {"book": "Книга «Целеполагание»", "practicum": "Практикум «Найди свой код»"}


async def notify_lead(bot: Bot, config: Config, lead: Lead) -> None:
    owner_chat_id = await settings.get_effective_owner_chat_id(config)
    if not owner_chat_id:
        return
    user = await crud.get_user(lead.user_tg_id)
    username = f"@{user.username}" if user and user.username else str(lead.user_tg_id)
    text = (f"📩 Новая заявка на консультацию\n"
           f"Пользователь: {username} (id {lead.user_tg_id})\n"
           f"Email: {lead.email}")
    await bot.send_message(owner_chat_id, text)
    await crud.mark_lead_exported(lead.user_tg_id)


async def notify_payment(bot: Bot, config: Config, purchase: Purchase) -> None:
    owner_chat_id = await settings.get_effective_owner_chat_id(config)
    if not owner_chat_id:
        return
    user = await crud.get_user(purchase.user_tg_id)
    username = f"@{user.username}" if user and user.username else str(purchase.user_tg_id)
    label = _PRODUCT_LABELS.get(purchase.product, purchase.product)
    text = (f"💰 Оплата: {label} — {purchase.amount_rub} ₽\n"
           f"Пользователь: {username} (id {purchase.user_tg_id})")
    await bot.send_message(owner_chat_id, text)


async def retry_unexported_leads(bot: Bot, config: Config) -> None:
    """Ретрай выгрузки лидов, которые не удалось отправить с первого раза (из scheduler'а)."""
    for lead in await crud.get_unexported_leads():
        try:
            await notify_lead(bot, config, lead)
        except Exception:  # noqa: BLE001
            logger.exception("Не удалось выгрузить лид user=%s", lead.user_tg_id)
