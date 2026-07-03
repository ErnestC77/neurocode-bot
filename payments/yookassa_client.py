"""Голый aiohttp-клиент ЮKassa (api.yookassa.ru/v3) — без официального SDK,
как и остальные платёжные интеграции в проекте (см. allpay-sub-bot/payments/allpay.py)."""
from __future__ import annotations

from typing import Any

import aiohttp

API_URL = "https://api.yookassa.ru/v3/payments"


async def create_payment(
    *,
    shop_id: str,
    secret_key: str,
    amount_rub: int,
    description: str,
    idempotence_key: str,
    return_url: str,
    metadata: dict[str, Any],
) -> tuple[str, str]:
    """Создаёт платёж. Возвращает (payment_id, confirmation_url).

    ``idempotence_key`` — стабильный ключ повторной отправки (используем
    purchase_id): при повторном вызове с тем же ключом ЮKassa не создаст
    дублирующий платёж.
    """
    payload = {
        "amount": {"value": f"{amount_rub:.2f}", "currency": "RUB"},
        "capture": True,
        "confirmation": {"type": "redirect", "return_url": return_url},
        "description": description,
        "metadata": metadata,
    }
    headers = {"Idempotence-Key": idempotence_key}
    auth = aiohttp.BasicAuth(shop_id, secret_key)

    async with aiohttp.ClientSession() as session:
        async with session.post(
            API_URL, json=payload, headers=headers, auth=auth,
            timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            resp.raise_for_status()
            body = await resp.json()

    return body["id"], body["confirmation"]["confirmation_url"]


async def get_payment(*, shop_id: str, secret_key: str, payment_id: str) -> dict[str, Any]:
    """Актуальное состояние платежа. ЮKassa не подписывает webhook'и HMAC'ом,
    поэтому верификация уведомления идёт через повторный запрос сюда, а не через
    доверие телу вебхука."""
    auth = aiohttp.BasicAuth(shop_id, secret_key)
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{API_URL}/{payment_id}", auth=auth, timeout=aiohttp.ClientTimeout(total=30),
        ) as resp:
            resp.raise_for_status()
            return await resp.json()
