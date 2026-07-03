"""Единственный catch-all для свободного текста во всём боте.

Раньше эту роль играл handlers/consult.py (сбор email) и был обязан быть
последним зарегистрированным роутером в bot.py, чтобы не перехватывать чужие
сообщения. С появлением второго сценария свободного ввода (значения настроек
в /settings) вся диспетчеризация собрана здесь, в одном месте — конкурирующих
catch-all роутеров в проекте больше нет.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from config import Config
from db import crud
from handlers import consult, settings_admin
from services import checkpoints
from services.settings import is_authorized_admin

router = Router()


@router.message(F.text & ~F.text.startswith("/"))
async def handle_free_text(message: Message, config: Config) -> None:
    tg_id = message.from_user.id

    if await is_authorized_admin(tg_id, config):
        pending_key = await crud.get_pending_setting_edit(tg_id)
        if pending_key is not None:
            await settings_admin.handle_setting_input(message, config, pending_key)
            return

    user = await crud.get_user(tg_id)
    if user is not None and user.checkpoint == checkpoints.AWAITING_EMAIL:
        await consult.handle_email_input(message, config)
        return
    # ни то, ни другое — не наш текст, молчим
