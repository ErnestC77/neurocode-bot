"""Единственный catch-all для свободного текста во всём боте — значения
настроек, вводимые через /settings (handlers/settings_admin.py)."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from config import Config
from db import crud
from handlers import settings_admin
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
    # не наш текст, молчим
