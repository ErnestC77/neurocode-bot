"""Конфигурация приложения: читает переменные окружения из .env.

Здесь только секреты и то, что нужно до подключения к БД (сама БД, порт,
токен бота). Бизнес-настройки (цены, file_id книги, id канала практикума,
интервалы напоминаний, доп. владелец, ЮKassa shop_id) — в services/settings.py,
редактируются через /settings в самом боте.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    database_url: str
    port: int
    owner_chat_id: int | None  # запасной админ (bootstrap) — см. services/settings.py

    yookassa_secret_key: str
    webhook_base_url: str

    yookassa_webhook_path: str = "/yookassa/webhook"

    @property
    def yookassa_webhook_url(self) -> str:
        return f"{self.webhook_base_url.rstrip('/')}{self.yookassa_webhook_path}"


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN не задан. Заполните .env по образцу .env.example")

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL не задан. Укажите строку подключения к PostgreSQL")
    if database_url.startswith("postgres://"):
        database_url = "postgresql+asyncpg://" + database_url[len("postgres://"):]
    elif database_url.startswith("postgresql://"):
        database_url = "postgresql+asyncpg://" + database_url[len("postgresql://"):]

    owner_chat_id_raw = os.getenv("OWNER_CHAT_ID", "").strip()

    return Config(
        bot_token=token,
        database_url=database_url,
        port=int(os.getenv("PORT", "8080")),
        owner_chat_id=int(owner_chat_id_raw) if owner_chat_id_raw.lstrip("-").isdigit() else None,
        yookassa_secret_key=os.getenv("YOOKASSA_SECRET_KEY", "").strip(),
        webhook_base_url=os.getenv("WEBHOOK_BASE_URL", "http://localhost").strip(),
    )
