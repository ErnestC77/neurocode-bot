"""Команда /settings — редактирование бизнес-настроек прямо из Telegram.

Только callback-хендлеры (меню, выбор настройки, отмена) + команда /settings.
Сам текстовый ввод нового значения ловит handlers/text_input.py (единственный
catch-all во всём боте) и вызывает handle_setting_input() отсюда.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import Config
from db import crud
from services.settings import SETTINGS, cast_value, format_value, is_authorized_admin

router = Router()


async def _menu_kb() -> InlineKeyboardMarkup:
    rows = []
    for key, spec in SETTINGS.items():
        raw = await crud.get_setting_value(key)
        rows.append([InlineKeyboardButton(
            text=f"{spec.label}: {format_value(spec, raw)}",
            callback_data=f"settings:edit:{key}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("settings"))
async def open_settings(message: Message, config: Config) -> None:
    if not await is_authorized_admin(message.from_user.id, config):
        return
    await message.answer("Настройки бота:", reply_markup=await _menu_kb())


@router.callback_query(F.data.startswith("settings:edit:"))
async def edit_setting(callback: CallbackQuery, config: Config) -> None:
    if not await is_authorized_admin(callback.from_user.id, config):
        await callback.answer()
        return
    key = callback.data.split(":", 2)[2]
    spec = SETTINGS.get(key)
    await callback.answer()
    if spec is None:
        return

    await crud.set_pending_setting_edit(callback.from_user.id, key)
    raw = await crud.get_setting_value(key)
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отмена", callback_data="settings:cancel")],
    ])
    await callback.message.answer(
        f"Пришли новое значение для «{spec.label}» (сейчас: {format_value(spec, raw)}).",
        reply_markup=cancel_kb,
    )


@router.callback_query(F.data == "settings:cancel")
async def cancel_edit(callback: CallbackQuery, config: Config) -> None:
    if not await is_authorized_admin(callback.from_user.id, config):
        await callback.answer()
        return
    await callback.answer()
    await crud.clear_pending_setting_edit(callback.from_user.id)
    await callback.message.answer("Отменено.", reply_markup=await _menu_kb())


async def handle_setting_input(message: Message, config: Config, setting_key: str) -> None:
    """Вызывается из handlers/text_input.py, когда у админа есть pending edit."""
    spec = SETTINGS.get(setting_key)
    if spec is None:
        await crud.clear_pending_setting_edit(message.from_user.id)
        return

    raw_input = (message.text or "").strip()
    old_display = format_value(spec, await crud.get_setting_value(setting_key))
    try:
        normalized = cast_value(spec, raw_input)
    except ValueError as exc:
        await message.answer(f"Не получилось разобрать значение: {exc}.")
        return

    await crud.set_setting_value(setting_key, normalized)
    await crud.clear_pending_setting_edit(message.from_user.id)
    new_display = format_value(spec, normalized)
    await message.answer(
        f"✅ {spec.label}: {old_display} → {new_display}", reply_markup=await _menu_kb(),
    )
