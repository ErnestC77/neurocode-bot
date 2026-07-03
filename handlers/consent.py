"""Блок 1 — согласие на обработку контакта (M1.1)."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from db import crud
from handlers.test import send_question
from services import checkpoints

router = Router()


@router.callback_query(F.data == "consent:accept")
async def consent_accept(callback: CallbackQuery) -> None:
    tg_id = callback.from_user.id
    await callback.answer()
    await crud.set_consent(tg_id)
    await crud.set_checkpoint(tg_id, checkpoints.IN_TEST)
    await send_question(callback.bot, tg_id, 1)
