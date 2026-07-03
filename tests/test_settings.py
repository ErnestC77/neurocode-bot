"""services/settings.py: чистая логика (валидация/форматирование/резолвинг
owner_chat_id) без обращения к БД, плюс DB-обёртки на sqlite-фикстуре
(единственное исключение из конвенции проекта «DB-код тестируется вручную» —
эта логика достаточно некритична для регрессии, чтобы стоило зафиксировать
автотестом; см. design spec, раздел «Тестирование»)."""
import pytest

from services.settings import SETTINGS, cast_value, format_value
from services.settings import _parse_chat_id, _resolve_owner_chat_id


def test_cast_value_int_ok():
    assert cast_value(SETTINGS["book_price_rub"], "1490") == "1490"


def test_cast_value_int_strips_whitespace():
    assert cast_value(SETTINGS["book_price_rub"], "  1490  ") == "1490"


def test_cast_value_int_rejects_garbage():
    with pytest.raises(ValueError):
        cast_value(SETTINGS["book_price_rub"], "не число")


def test_cast_value_rejects_empty():
    with pytest.raises(ValueError):
        cast_value(SETTINGS["book_file_id"], "   ")


def test_cast_value_str_ok():
    assert cast_value(SETTINGS["practicum_channel_id"], "@mychannel") == "@mychannel"


def test_format_value_uses_default_when_unset():
    assert format_value(SETTINGS["book_price_rub"], None) == "990 ₽"


def test_format_value_empty_default_is_ne_zadan():
    assert format_value(SETTINGS["book_file_id"], None) == "не задан"


def test_format_value_with_suffix():
    assert format_value(SETTINGS["reminder_delay_hours"], "48") == "48 ч"


def test_parse_chat_id_empty_is_none():
    assert _parse_chat_id("") is None


def test_parse_chat_id_numeric_negative_is_int():
    assert _parse_chat_id("-1001234567890") == -1001234567890


def test_parse_chat_id_username_stays_str():
    assert _parse_chat_id("@mychannel") == "@mychannel"


def test_resolve_owner_chat_id_prefers_db():
    assert _resolve_owner_chat_id("456", env_owner_chat_id=123) == 456


def test_resolve_owner_chat_id_falls_back_to_env_when_empty():
    # пустая строка в БД = настройка не задана -> откат на env
    assert _resolve_owner_chat_id("", env_owner_chat_id=123) == 123


def test_resolve_owner_chat_id_falls_back_to_env_when_corrupted():
    # опечатка/мусор в БД не должна блокировать доступ — откат на env
    assert _resolve_owner_chat_id("не число", env_owner_chat_id=123) == 123


def test_resolve_owner_chat_id_none_env_and_empty_db():
    assert _resolve_owner_chat_id("", env_owner_chat_id=None) is None


import pytest_asyncio

import db.database as database
from db.models import Base
from services import settings


@pytest_asyncio.fixture
async def settings_db():
    """Изолированный sqlite в памяти — только таблица bot_settings.

    Переиспользует db.database.init_engine(), поэтому crud-функции внутри
    services/settings.py работают точно так же, как с реальным Postgres.
    """
    database.init_engine("sqlite+aiosqlite:///:memory:")
    engine = database._engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[Base.metadata.tables["bot_settings"]])
    yield
    await engine.dispose()
    database._engine = None
    database._sessionmaker = None


async def test_get_int_returns_default_when_unset(settings_db):
    assert await settings.get_int("book_price_rub") == 990


async def test_set_value_then_get_int_roundtrip(settings_db):
    await settings.set_value("book_price_rub", "1490")
    assert await settings.get_int("book_price_rub") == 1490
