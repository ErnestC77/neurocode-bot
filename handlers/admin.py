"""Админ-команды. Пока одна: экспорт лидов из Postgres в CSV."""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, ChatMemberUpdated, Message

from config import Config
from db import crud
from payments import delivery
from services.settings import get_effective_owner_chat_id, is_authorized_admin

router = Router()


@router.message(F.document)
async def get_file_id(message: Message, config: Config) -> None:
    """Владелец присылает PDF книги боту — бот отвечает file_id для BOOK_FILE_ID в /settings."""
    if not await is_authorized_admin(message.from_user.id, config):
        return
    await message.reply(f"file_id: <code>{message.document.file_id}</code>")


@router.message(F.video)
async def get_video_file_id(message: Message, config: Config) -> None:
    """Владелец присылает видео практикума боту — бот отвечает file_id для
    practicum_video_file_id в /settings."""
    if not await is_authorized_admin(message.from_user.id, config):
        return
    await message.reply(f"file_id: <code>{message.video.file_id}</code>")


@router.message(F.forward_from_chat)
async def get_forwarded_chat_id(message: Message, config: Config) -> None:
    """Владелец пересылает любое сообщение из канала — бот отвечает его chat_id
    (для practicum_channel_id в /settings). Нужно для приватных каналов без
    @username, у которых есть только инвайт-ссылка — из неё ID не получить
    напрямую, а пересланное сообщение содержит настоящий числовой ID."""
    if not await is_authorized_admin(message.from_user.id, config):
        return
    chat = message.forward_from_chat
    await message.reply(f"chat_id: <code>{chat.id}</code> ({chat.title})")


@router.my_chat_member()
async def bot_membership_changed(event: ChatMemberUpdated, config: Config) -> None:
    """Telegram сам присылает это событие боту при любом изменении его прав в
    чате/канале (добавили, повысили до админа, сняли права и т.д.) — вместе с
    настоящим chat_id, без пересылки сообщений. Полезно для каналов с защитой
    контента (запрет пересылки), где handlers/admin.py::get_forwarded_chat_id
    не сработает."""
    owner_chat_id = await get_effective_owner_chat_id(config)
    if not owner_chat_id:
        return
    chat = event.chat
    await event.bot.send_message(
        owner_chat_id,
        f"Права бота изменились в «{chat.title}» (chat_id: <code>{chat.id}</code>), "
        f"новый статус: {event.new_chat_member.status}",
    )


@router.message(Command("redeliver"))
async def redeliver_purchase(message: Message, config: Config) -> None:
    """Повторно запускает выдачу доступа для конкретной оплаченной покупки —
    на случай, если она уже помечена доставленной, но настройка (channel_id/
    file_id) была не заполнена в момент выдачи, и автоматический ретрай
    scheduler'а её больше не подхватит."""
    if not await is_authorized_admin(message.from_user.id, config):
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit():
        await message.reply("Использование: /redeliver <purchase_id>")
        return
    purchase = await crud.get_purchase(int(parts[1]))
    if purchase is None or purchase.status != "paid":
        await message.reply("Оплаченная покупка с таким id не найдена.")
        return
    await delivery.deliver(message.bot, config, purchase)
    await message.reply("Готово. Если настройки заполнены — доступ должен был уйти.")


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
