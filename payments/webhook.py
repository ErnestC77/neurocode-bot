"""aiohttp-обработчик webhook ЮKassa: подтверждение оплаты книги/практикума."""
from __future__ import annotations

import logging

from aiogram import Bot
from aiohttp import web

from config import Config
from db import crud
from exports.notifier import notify_payment
from payments import delivery
from payments.yookassa_client import get_payment

logger = logging.getLogger(__name__)


def make_webhook_handler(bot: Bot, config: Config):
    async def handler(request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except Exception:  # noqa: BLE001
            return web.Response(text="bad json", status=200)

        payment_id = str((data.get("object") or {}).get("id", ""))
        if not payment_id:
            return web.Response(text="ok", status=200)

        # ЮKassa не подписывает webhook HMAC'ом — не доверяем телу уведомления,
        # перечитываем платёж по API и статус берём только из ответа.
        try:
            remote = await get_payment(
                shop_id=config.yookassa_shop_id, secret_key=config.yookassa_secret_key,
                payment_id=payment_id,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Не удалось перепроверить платёж %s", payment_id)
            return web.Response(text="ok", status=200)

        if remote.get("status") != "succeeded":
            logger.info("YooKassa webhook: статус %s (не оплачено), payment_id=%s",
                       remote.get("status"), payment_id)
            return web.Response(text="ok", status=200)

        purchase = await crud.mark_paid(payment_id)
        if purchase is None:
            # Уже обработан ранее или неизвестный платёж — подтверждаем приём, чтобы
            # ЮKassa не ретраила бесконечно.
            logger.info("YooKassa webhook: повтор/неизвестный платёж, payment_id=%s", payment_id)
            return web.Response(text="ok", status=200)

        try:
            await delivery.deliver(bot, config, purchase)
        except Exception:  # noqa: BLE001
            logger.exception("Не удалось выдать доступ purchase=%s", purchase.id)

        try:
            await notify_payment(bot, config, purchase)
        except Exception:  # noqa: BLE001
            logger.exception("Не удалось уведомить владельца об оплате purchase=%s", purchase.id)

        return web.Response(text="ok", status=200)

    return handler


def setup_routes(app: web.Application, bot: Bot, config: Config) -> None:
    app.router.add_post(config.yookassa_webhook_path, make_webhook_handler(bot, config))
    app.router.add_get("/health", lambda r: web.Response(text="ok"))
