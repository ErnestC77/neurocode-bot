"""Конфигурация приложения: читает переменные окружения из .env."""
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
    owner_chat_id: int | None  # куда выгружать лиды/оплаты

    yookassa_shop_id: str
    yookassa_secret_key: str
    webhook_base_url: str

    practicum_channel_id: str  # ID закрытого канала практикума (-100...) или @username
    book_file_id: str  # file_id книги, полученный после ручной загрузки боту

    reminder_delay_hours: int  # порог бездействия для R1-R6
    reminder_check_interval: int  # период tick'а scheduler'а, сек

    @property
    def practicum_chat_id(self) -> int | str | None:
        cid = self.practicum_channel_id.strip()
        if not cid:
            return None
        if cid.lstrip("-").isdigit():
            return int(cid)
        return cid

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
        yookassa_shop_id=os.getenv("YOOKASSA_SHOP_ID", "").strip(),
        yookassa_secret_key=os.getenv("YOOKASSA_SECRET_KEY", "").strip(),
        webhook_base_url=os.getenv("WEBHOOK_BASE_URL", "http://localhost").strip(),
        practicum_channel_id=os.getenv("PRACTICUM_CHANNEL_ID", "").strip(),
        book_file_id=os.getenv("BOOK_FILE_ID", "").strip(),
        reminder_delay_hours=int(os.getenv("REMINDER_DELAY_HOURS", "24")),
        reminder_check_interval=int(os.getenv("REMINDER_CHECK_INTERVAL", "300")),
    )
