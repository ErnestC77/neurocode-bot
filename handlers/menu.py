"""Блоки 5/9 — вход в продукт (offer:*) и универсальное «умное меню» (menu:show)."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from db import crud
from keyboards.inline import (book_intro_kb, consult_intro_kb,
                              practicum_intro_kb, smart_menu_kb)
from services import checkpoints
from services.catalog import BOOK, CONSULT, PRACTICUM, get_available_products
from texts.messages import TEXTS

router = Router()

_PRODUCT_CHECKPOINT = {
    PRACTICUM: checkpoints.PRACTICUM_VIEWED,
    CONSULT: checkpoints.CONSULT_VIEWED,
    BOOK: checkpoints.BOOK_VIEWED,
}
_PRODUCT_INTRO_TEXT = {PRACTICUM: "M6.1", CONSULT: "M7.1", BOOK: "M8.1"}
_PRODUCT_INTRO_KB = {
    PRACTICUM: practicum_intro_kb,
    CONSULT: consult_intro_kb,
    BOOK: book_intro_kb,
}


@router.callback_query(F.data.startswith("offer:"))
async def open_product(callback: CallbackQuery) -> None:
    tg_id = callback.from_user.id
    product = callback.data.split(":", 1)[1]
    await callback.answer()
    if product not in _PRODUCT_INTRO_TEXT:
        return

    # Защита от нажатия старой кнопки на уже купленный/забронированный продукт.
    available = await get_available_products(tg_id)
    if product not in available:
        if not available:
            await callback.message.answer(TEXTS["M9_EMPTY"])
        else:
            await callback.message.answer(TEXTS["M9"], reply_markup=smart_menu_kb(available))
        return

    await crud.set_checkpoint(tg_id, _PRODUCT_CHECKPOINT[product])
    await callback.message.answer(
        TEXTS[_PRODUCT_INTRO_TEXT[product]], reply_markup=_PRODUCT_INTRO_KB[product](available),
    )


@router.callback_query(F.data == "menu:show")
async def show_menu(callback: CallbackQuery) -> None:
    tg_id = callback.from_user.id
    await callback.answer()
    available = await get_available_products(tg_id)
    if not available:
        await callback.message.answer(TEXTS["M9_EMPTY"])
        return
    await callback.message.answer(TEXTS["M9"], reply_markup=smart_menu_kb(available))
