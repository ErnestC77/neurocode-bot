"""Inline-клавиатуры. callback_data — namespace через ':' (см. README)."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo


def _kb(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=list(rows))


def payment_link_kb(url: str, label: str) -> InlineKeyboardMarkup:
    return _kb([InlineKeyboardButton(text=label, url=url)])


def after_product_kb(current: str, available: list[str], miniapp_url: str) -> InlineKeyboardMarkup:
    """M6.3 / M7.2 / M8.3: если остались непроданные продукты — одна кнопка,
    открывающая Mini App (там уже показывается умное меню M9 с актуальным
    списком). Раньше здесь были персональные callback-кнопки на каждый
    продукт — они вели в чат-хендлеры, которых больше нет."""
    remaining = [p for p in available if p != current]
    if not remaining:
        return _kb()
    return _kb([InlineKeyboardButton(text="Посмотреть другие варианты",
                                     web_app=WebAppInfo(url=miniapp_url))])


def open_miniapp_kb(url: str) -> InlineKeyboardMarkup:
    """Единственная кнопка «Открыть», открывающая Mini App напрямую —
    используется в напоминаниях R1-R6. Mini App сам покажет нужный экран по
    чекпоинту пользователя, поэтому одна кнопка годится для всех кодов."""
    return _kb([InlineKeyboardButton(text="Открыть", web_app=WebAppInfo(url=url))])
