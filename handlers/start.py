"""Точка входа в чат: короткая подсказка открыть Mini App через Menu Button.

Весь квиз/оффер/оплата/консультация переехали в Mini App (Menu Button,
настраивается в asgi.py::_bot_lifecycle). Чат больше не дублирует этот
контент — только направляет пользователя открыть кнопку."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Диагностика «Какой нейрокод блокирует твой доход» открывается "
        "кнопкой «Открыть» рядом с полем ввода 👇"
    )
