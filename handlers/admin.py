"""Админ-команды. Пока одна: экспорт лидов из Postgres в CSV."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from config import Config
from db import crud
from services.settings import is_authorized_admin

router = Router()


@router.message(F.document)
async def get_file_id(message: Message, config: Config) -> None:
    """Владелец присылает PDF книги боту — бот отвечает file_id для BOOK_FILE_ID в /settings."""
    if not await is_authorized_admin(message.from_user.id, config):
        return
    await message.reply(f"file_id: <code>{message.document.file_id}</code>")


@router.message(Command("export_leads"))
async def export_leads(message: Message, config: Config) -> None:
    if not await is_authorized_admin(message.from_user.id, config):
        return  # команда доступна только владельцу бота

    leads = await crud.list_leads()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["tg_id", "username", "email", "created_at"])
    for lead, user in leads:
        writer.writerow([
            lead.user_tg_id,
            user.username if user and user.username else "",
            lead.email or "",
            lead.created_at.isoformat(),
        ])

    filename = f"leads_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.csv"
    # utf-8-sig — чтобы Excel сразу правильно показал кириллицу/эмодзи в username.
    document = BufferedInputFile(buf.getvalue().encode("utf-8-sig"), filename=filename)
    await message.answer_document(document, caption=f"Заявок на консультацию: {len(leads)}")
