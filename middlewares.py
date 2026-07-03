"""Мидлвари бота."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from db import crud


class ActivityMiddleware(BaseMiddleware):
    """Бампает last_activity_at на каждое взаимодействие пользователя с ботом.

    Это механизм «любое действие обнуляет таймер напоминаний» из ТЗ: scheduler
    просто ищет пользователей с устаревшим last_activity_at, отдельного сброса
    таймера по этапу/продукту нигде делать не нужно.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is not None:
            try:
                await crud.touch_activity(user.id, user.username, user.first_name)
            except Exception:  # noqa: BLE001
                pass
        return await handler(event, data)
