"""Проверка initData от Telegram Mini App SDK (безопасность — читать внимательно).

Каждый запрос к /api/* аутентифицируется заново пересчитыванием подписи
``initData``. Подпись — HMAC-SHA256, ключ которого сам является
``HMAC_SHA256(key="WebAppData", msg=bot_token)``; сообщение — отсортированные
по алфавиту строки ``key=value`` всех полей, кроме ``hash``. Дополнительно
отклоняем протухшие payload'ы по ``auth_date``.

Порт из C:\\Users\\mccaq\\IdeaProjects\\barbershop-bot\\app\\api\\auth.py — тот же
алгоритм, тот же официальный Telegram-стандарт, менять нечего.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from urllib.parse import parse_qsl


class InvalidInitDataError(Exception):
    """initData отсутствует, подделана или устарела."""


def parse_and_validate_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = 86400,
    now: datetime | None = None,
) -> dict:
    pairs = dict(parse_qsl(init_data, strict_parsing=False))
    received = pairs.pop("hash", None)
    if not received:
        raise InvalidInitDataError("missing hash")

    data_check_string = "\n".join(f"{key}={pairs[key]}" for key in sorted(pairs))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received):
        raise InvalidInitDataError("bad hash")

    auth_date = int(pairs.get("auth_date", "0"))
    now = now or datetime.now(timezone.utc)
    if max_age_seconds and (now.timestamp() - auth_date) > max_age_seconds:
        raise InvalidInitDataError("expired")

    pairs["user"] = json.loads(pairs["user"]) if "user" in pairs else None
    pairs["auth_date"] = auth_date
    return pairs
