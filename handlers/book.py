"""Блок 8 — книга «Целеполагание» (990 ₽)."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import CallbackQuery

from config import Config
from db import crud
from keyboards.inline import book_buy_kb, payment_link_kb
from payments.yookassa_client import create_payment
from services import settings
from services.catalog import BOOK, get_available_products
from texts.messages import TEXTS

router = Router()


@router.callback_query(F.data == "book:details")
async def book_details(callback: CallbackQuery) -> None:
    tg_id = callback.from_user.id
    await callback.answer()
    available = await get_available_products(tg_id)
    await callback.message.answer(TEXTS["M8.2"], reply_markup=await book_buy_kb(available))


@router.callback_query(F.data == "book:buy")
async def book_buy(callback: CallbackQuery, config: Config) -> None:
    tg_id = callback.from_user.id
    await callback.answer()

    amount = await settings.get_int("book_price_rub")
    purchase = await crud.create_purchase(tg_id, BOOK, amount)
    payment_id, confirmation_url = await create_payment(
        shop_id=await settings.get_str("yookassa_shop_id"), secret_key=config.yookassa_secret_key,
        amount_rub=amount, description="Книга «Целеполагание»",
        idempotence_key=str(purchase.id), return_url=config.webhook_base_url,
        metadata={"tg_id": tg_id, "product": BOOK, "purchase_id": purchase.id},
    )
    await crud.attach_yk_payment_id(purchase.id, payment_id)

    await callback.message.answer(
        f"Книга «Целеполагание» — {amount} ₽. Оплата откроется по кнопке ниже.",
        reply_markup=payment_link_kb(confirmation_url, f"Оплатить {amount} ₽"),
    )
