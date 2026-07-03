"""Блок 7 — бесплатная консультация с Марией + сбор email для лида."""
from __future__ import annotations

import logging
import re

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from config import Config
from db import crud
from exports.notifier import notify_lead
from keyboards.inline import after_product_kb
from services import checkpoints
from services.catalog import CONSULT, get_available_products
from texts.messages import TEXTS

logger = logging.getLogger(__name__)

router = Router()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@router.callback_query(F.data == "consult:book")
async def consult_book(callback: CallbackQuery) -> None:
    tg_id = callback.from_user.id
    await callback.answer()
    await crud.set_checkpoint(tg_id, checkpoints.AWAITING_EMAIL)
    await callback.message.answer(TEXTS["CONSULT_EMAIL_PROMPT"])


@router.message(F.text & ~F.text.startswith("/"))
async def consult_email_input(message: Message, config: Config) -> None:
    tg_id = message.from_user.id
    user = await crud.get_user(tg_id)
    if user is None or user.checkpoint != checkpoints.AWAITING_EMAIL:
        return  # не ждём здесь текст от этого пользователя — не мешаем остальному

    email = (message.text or "").strip()
    if not _EMAIL_RE.match(email):
        await message.answer(TEXTS["CONSULT_EMAIL_INVALID"])
        return

    lead = await crud.create_lead(tg_id, email)
    await crud.set_checkpoint(tg_id, checkpoints.IDLE)

    if lead is not None:
        try:
            await notify_lead(message.bot, config, lead)
        except Exception:  # noqa: BLE001 — не выгрузилось сейчас, ретрай подхватит scheduler
            logger.exception("Не удалось выгрузить лид user=%s сразу", tg_id)

    available = await get_available_products(tg_id)
    await message.answer(TEXTS["M7.2"], reply_markup=after_product_kb(CONSULT, available))
