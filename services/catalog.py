"""«Умное меню»: какие продукты пользователь ещё не купил / не забронировал."""
from __future__ import annotations

from db import crud

BOOK = "book"
PRACTICUM = "practicum"
CONSULT = "consult"

ALL_PRODUCTS = (BOOK, PRACTICUM, CONSULT)


async def get_available_products(tg_id: int) -> list[str]:
    """Продукты, которые пользователь ещё не купил (книга/практикум) или не забронировал
    (консультация). Используется и для меню M9, и для кросс-ссылок «2 других продукта»."""
    paid = await crud.get_paid_products(tg_id)
    has_lead = await crud.has_lead(tg_id)
    available: list[str] = []
    if BOOK not in paid:
        available.append(BOOK)
    if PRACTICUM not in paid:
        available.append(PRACTICUM)
    if not has_lead:
        available.append(CONSULT)
    return available
