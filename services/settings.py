"""Реестр бизнес-настроек бота, редактируемых через /settings.

Хранилище — таблица bot_settings (key -> value, обе колонки TEXT), типизация
и валидация — здесь, на стороне Python. Если в БД для ключа нет строки,
используется default из SettingSpec (те же значения, что раньше были в
.env.example) — на свежем деплое без единого визита в /settings бот работает
как раньше.

owner_chat_id — особый случай: у него ЕСТЬ запись в этом реестре (чтобы он
редактировался тем же UI /settings), но читается не через get_int() (см.
get_effective_owner_chat_id) — env-значение Config.owner_chat_id остаётся
постоянным запасным админом, БД-значение никогда не может его полностью
вытеснить (защита от самоблокировки, см. design spec).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SettingSpec:
    key: str
    label: str
    value_type: type  # int | str
    default: str
    suffix: str = ""  # добавляется к значению при отображении в /settings


SETTINGS: dict[str, SettingSpec] = {
    "book_file_id": SettingSpec(
        "book_file_id", "📄 File ID книги", str, ""),
    "practicum_channel_id": SettingSpec(
        "practicum_channel_id", "📢 ID канала практикума", str, ""),
    "book_price_rub": SettingSpec(
        "book_price_rub", "📕 Цена книги", int, "990", suffix=" ₽"),
    "practicum_price_rub": SettingSpec(
        "practicum_price_rub", "📗 Цена практикума", int, "2990", suffix=" ₽"),
    "reminder_delay_hours": SettingSpec(
        "reminder_delay_hours", "⏰ Порог бездействия для напоминаний", int, "24", suffix=" ч"),
    "reminder_check_interval": SettingSpec(
        "reminder_check_interval", "🔁 Интервал проверки scheduler'а", int, "300", suffix=" с"),
    "owner_chat_id": SettingSpec(
        "owner_chat_id", "👤 Доп. владелец (лиды/оплаты/доступ к панели)", int, ""),
    "yookassa_shop_id": SettingSpec(
        "yookassa_shop_id", "🔑 ЮKassa shop_id", str, ""),
}


def cast_value(spec: SettingSpec, raw: str) -> str:
    """Валидирует и нормализует пользовательский ввод. ValueError при мусоре."""
    raw = raw.strip()
    if not raw:
        raise ValueError("значение не может быть пустым")
    if spec.value_type is int:
        int(raw)  # бросит ValueError, если не число
    return raw


def format_value(spec: SettingSpec, raw: str | None) -> str:
    """Человекочитаемое текущее значение для меню /settings."""
    value = raw if raw else spec.default
    if not value:
        return "не задан"
    return f"{value}{spec.suffix}"


def _parse_chat_id(raw: str) -> int | str | None:
    """Пусто -> None; только цифры (с '-') -> int; иначе строка (@username)."""
    raw = raw.strip()
    if not raw:
        return None
    if raw.lstrip("-").isdigit():
        return int(raw)
    return raw


def _resolve_owner_chat_id(db_raw: str, env_owner_chat_id: int | None) -> int | None:
    """БД-значение приоритетно; при пустом/испорченном значении — откат на env.

    Это и есть страховка от самоблокировки: опечатка в owner_chat_id через
    /settings не может лишить владельца доступа к самой панели.
    """
    db_raw = db_raw.strip()
    if db_raw.lstrip("-").isdigit():
        return int(db_raw)
    return env_owner_chat_id


from config import Config
from db import crud


async def get_str(key: str) -> str:
    spec = SETTINGS[key]
    raw = await crud.get_setting_value(key)
    return raw if raw else spec.default


async def get_int(key: str) -> int:
    return int(await get_str(key))


async def set_value(key: str, raw: str) -> None:
    """Валидирует по SETTINGS[key].value_type и сохраняет. ValueError при мусоре."""
    spec = SETTINGS[key]
    normalized = cast_value(spec, raw)
    await crud.set_setting_value(key, normalized)


async def get_effective_owner_chat_id(config: Config) -> int | None:
    """БД-значение owner_chat_id, если задано и валидно, иначе config.owner_chat_id (env)."""
    db_raw = await crud.get_setting_value("owner_chat_id") or ""
    return _resolve_owner_chat_id(db_raw, config.owner_chat_id)


async def get_practicum_chat_id() -> int | str | None:
    return _parse_chat_id(await get_str("practicum_channel_id"))


async def is_authorized_admin(tg_id: int, config: Config) -> bool:
    """Доступ к /settings и /export_leads: env-владелец ИЛИ текущий БД-владелец."""
    if config.owner_chat_id and tg_id == config.owner_chat_id:
        return True
    effective = await get_effective_owner_chat_id(config)
    return effective is not None and tg_id == effective
