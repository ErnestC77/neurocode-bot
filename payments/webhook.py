"""FastAPI-роутер webhook ЮKassa: подтверждение оплаты книги/практикума."""
from __future__ import annotations

import logging

from aiogram import Bot
from fastapi import APIRouter, Request, Response

from config import Config
from db import crud
from exports.notifier import notify_payment
from payments import delivery
from payments.yookassa_client import get_payment
from services import settings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/yookassa/webhook")
async def yookassa_webhook(request: Request) -> Response:
    bot: Bot = request.app.state.bot
    config: Config = request.app.state.config

    try:
        data = await request.json()
    except Exception:  # noqa: BLE001
        return Response(content="bad json", status_code=200)

    payment_id = str((data.get("object") or {}).get("id", ""))
    if not payment_id:
        return Response(content="ok", status_code=200)

    # ЮKassa не подписывает webhook HMAC'ом — не доверяем телу уведомления,
    # перечитываем платёж по API и статус берём только из ответа.
    try:
        remote = await get_payment(
            shop_id=await settings.get_str("yookassa_shop_id"), secret_key=config.yookassa_secret_key,
            payment_id=payment_id,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось перепроверить платёж %s", payment_id)
        return Response(content="ok", status_code=200)

    if remote.get("status") != "succeeded":
        logger.info("YooKassa webhook: статус %s (не оплачено), payment_id=%s",
                   remote.get("status"), payment_id)
        return Response(content="ok", status_code=200)

    purchase = await crud.mark_paid(payment_id)
    if purchase is None:
        # Уже обработан ранее или неизвестный платёж — подтверждаем приём, чтобы
        # ЮKassa не ретраила бесконечно.
        logger.info("YooKassa webhook: повтор/неизвестный платёж, payment_id=%s", payment_id)
        return Response(content="ok", status_code=200)

    try:
        await delivery.deliver(bot, config, purchase)
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось выдать доступ purchase=%s", purchase.id)

    try:
        await notify_payment(bot, config, purchase)
    except Exception:  # noqa: BLE001
        logger.exception("Не удалось уведомить владельца об оплате purchase=%s", purchase.id)

    return Response(content="ok", status_code=200)
