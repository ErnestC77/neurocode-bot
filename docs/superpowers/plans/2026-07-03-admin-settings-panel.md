# Админ-панель настроек в Telegram — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перенести операционный конфиг бота (`BOOK_FILE_ID`, `PRACTICUM_CHANNEL_ID`, цены книги/практикума, интервалы напоминаний, `OWNER_CHAT_ID`, `YOOKASSA_SHOP_ID`) из env-переменных Render в редактируемые прямо в Telegram настройки (`/settings`), без передеплоя.

**Architecture:** Новая KV-таблица `bot_settings` в Postgres + типизированный Python-реестр `services/settings.py` (валидация/дефолты/форматирование). Единственный catch-all для свободного текста во всём боте — новый `handlers/text_input.py`, диспетчеризующий между вводом email (было в `consult.py`) и вводом значения настройки. `OWNER_CHAT_ID` из env остаётся постоянным запасным админом — БД-значение никогда не может полностью его вытеснить.

**Tech Stack:** aiogram 3.x, SQLAlchemy 2.0 async + asyncpg, pytest (только для чистых функций — проект не тестирует DB/aiogram-код автотестами, см. `README.md`).

## Global Constraints

- Секреты (`BOT_TOKEN`, `DATABASE_URL`, `YOOKASSA_SECRET_KEY`, `PORT`, `WEBHOOK_BASE_URL`) остаются в env — НЕ переносятся в БД.
- `OWNER_CHAT_ID` из env — постоянный запасной админ (проверяется ВСЕГДА в дополнение к БД-значению), чтобы исключить самоблокировку.
- Никакого aiogram FSM — состояние `AdminPendingEdit` хранится в БД, как и весь остальной прогресс в проекте.
- Не более одного catch-all текстового хендлера (`F.text & ~F.text.startswith("/")`) во всём боте — только в `handlers/text_input.py`.
- Автотесты пишем только для чистых функций без БД/aiogram (следуем текущей конвенции проекта: `tests/test_scoring.py`).
- Спека: `docs/superpowers/specs/2026-07-03-admin-settings-panel-design.md`.

---

## Task 1: Модели БД — BotSetting, AdminPendingEdit

**Files:**
- Modify: `db/models.py` (добавить 2 класса в конец файла, после `ReminderSent`)
- Test: `tests/test_models.py` (новый)

**Interfaces:**
- Produces: `db.models.BotSetting` (columns: `key: str` PK, `value: str`, `updated_at: datetime`), `db.models.AdminPendingEdit` (columns: `admin_tg_id: int` PK, `setting_key: str`, `created_at: datetime`)

- [ ] **Step 1: Написать падающий тест схемы**

Создать `tests/test_models.py`:
```python
"""Схема новых таблиц настроек — проверка через метаданные SQLAlchemy, без БД."""
from db.models import AdminPendingEdit, BotSetting


def test_bot_setting_columns():
    columns = set(BotSetting.__table__.columns.keys())
    assert columns == {"key", "value", "updated_at"}
    assert BotSetting.__table__.primary_key.columns.keys() == ["key"]


def test_admin_pending_edit_columns():
    columns = set(AdminPendingEdit.__table__.columns.keys())
    assert columns == {"admin_tg_id", "setting_key", "created_at"}
    assert AdminPendingEdit.__table__.primary_key.columns.keys() == ["admin_tg_id"]
```

- [ ] **Step 2: Убедиться, что тест падает**

Run: `cd C:\Users\mccaq\neurocode-bot && python -m pytest tests/test_models.py -v`
Expected: `ImportError: cannot import name 'BotSetting' from 'db.models'`

- [ ] **Step 3: Добавить модели в `db/models.py`**

Открыть `db/models.py`, добавить в конец файла (после класса `ReminderSent`, который сейчас заканчивается на строке 100 полем `sent_at`):

```python


class BotSetting(Base):
    """Бизнес-настройка, редактируемая владельцем через /settings — не секрет.

    Ключи и типы описаны в реестре services/settings.py::SETTINGS, эта таблица
    хранит только сырые строки; парсинг/валидация — на стороне Python.
    """
    __tablename__ = "bot_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(512))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AdminPendingEdit(Base):
    """«Админ X сейчас редактирует настройку Y» — состояние UI /settings.

    Отдельно от users.checkpoint: это не состояние воронки продаж, а состояние
    админ-панели, и смешивать их в одном поле рискованно (админ теоретически
    может сам проходить тест как обычный пользователь).
    """
    __tablename__ = "admin_pending_edits"

    admin_tg_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    setting_key: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
```

- [ ] **Step 4: Убедиться, что тест проходит**

Run: `python -m pytest tests/test_models.py -v`
Expected: `2 passed`

- [ ] **Step 5: Прогнать весь набор тестов и закоммитить**

Run: `python -m pytest -q`
Expected: `9 passed` (7 старых из `test_scoring.py` + 2 новых)

```bash
git add db/models.py tests/test_models.py
git commit -m "feat: добавить модели BotSetting и AdminPendingEdit"
```

---

## Task 2: CRUD-функции для настроек и pending-edit

**Files:**
- Modify: `db/crud.py` (добавить в конец файла)

**Interfaces:**
- Consumes: `db.models.BotSetting`, `db.models.AdminPendingEdit` (Task 1)
- Produces: `crud.get_setting_value(key: str) -> str | None`, `crud.set_setting_value(key: str, value: str) -> None`, `crud.get_pending_setting_edit(admin_tg_id: int) -> str | None`, `crud.set_pending_setting_edit(admin_tg_id: int, setting_key: str) -> None`, `crud.clear_pending_setting_edit(admin_tg_id: int) -> None`

Эти функции DB-touching (async SQLAlchemy) — по конвенции проекта (см. `README.md`, раздел «Тесты») автотестами не покрываются, проверяются вручную в Task 6-7 через живой `/settings`.

- [ ] **Step 1: Обновить импорт моделей**

В `db/crud.py` заменить строку 10:
```python
from db.models import Answer, Lead, Purchase, ReminderSent, User, utcnow
```
на:
```python
from db.models import (AdminPendingEdit, Answer, BotSetting, Lead, Purchase,
                       ReminderSent, User, utcnow)
```

- [ ] **Step 2: Добавить функции в конец `db/crud.py`**

```python


# ---------- Настройки (/settings) ----------

async def get_setting_value(key: str) -> str | None:
    async with get_sessionmaker()() as session:
        setting = await session.get(BotSetting, key)
        return setting.value if setting else None


async def set_setting_value(key: str, value: str) -> None:
    async with get_sessionmaker()() as session:
        setting = await session.get(BotSetting, key)
        if setting is None:
            session.add(BotSetting(key=key, value=value))
        else:
            setting.value = value
        await session.commit()


async def get_pending_setting_edit(admin_tg_id: int) -> str | None:
    """Ключ настройки, которую сейчас редактирует админ, или None."""
    async with get_sessionmaker()() as session:
        pending = await session.get(AdminPendingEdit, admin_tg_id)
        return pending.setting_key if pending else None


async def set_pending_setting_edit(admin_tg_id: int, setting_key: str) -> None:
    async with get_sessionmaker()() as session:
        pending = await session.get(AdminPendingEdit, admin_tg_id)
        if pending is None:
            session.add(AdminPendingEdit(admin_tg_id=admin_tg_id, setting_key=setting_key))
        else:
            pending.setting_key = setting_key
        await session.commit()


async def clear_pending_setting_edit(admin_tg_id: int) -> None:
    async with get_sessionmaker()() as session:
        pending = await session.get(AdminPendingEdit, admin_tg_id)
        if pending:
            await session.delete(pending)
            await session.commit()
```

- [ ] **Step 3: Проверить, что файл импортируется без ошибок**

Run: `python -c "import db.crud; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Прогнать тесты и закоммитить**

Run: `python -m pytest -q`
Expected: `9 passed`

```bash
git add db/crud.py
git commit -m "feat: CRUD-функции для bot_settings и admin_pending_edits"
```

---

## Task 3: `services/settings.py` — реестр, валидация, типизированный доступ

**Files:**
- Create: `services/settings.py`
- Create: `tests/test_settings.py`
- Create: `pytest.ini`
- Modify: `requirements-dev.txt`

**Interfaces:**
- Consumes: `crud.get_setting_value`, `crud.set_setting_value` (Task 2); `config.Config` (существующий `config.py`); `db.database.init_engine`, `db.models.Base` (для sqlite-фикстуры в тестах)
- Produces:
  - `SettingSpec` (dataclass: `key: str, label: str, value_type: type, default: str, suffix: str = ""`)
  - `SETTINGS: dict[str, SettingSpec]` — 8 ключей: `book_file_id, practicum_channel_id, book_price_rub, practicum_price_rub, reminder_delay_hours, reminder_check_interval, owner_chat_id, yookassa_shop_id`
  - `cast_value(spec: SettingSpec, raw: str) -> str` — бросает `ValueError` при мусоре
  - `format_value(spec: SettingSpec, raw: str | None) -> str`
  - `async def get_str(key: str) -> str`
  - `async def get_int(key: str) -> int`
  - `async def set_value(key: str, raw: str) -> None`
  - `async def get_effective_owner_chat_id(config: Config) -> int | None`
  - `async def get_practicum_chat_id() -> int | str | None`
  - `async def is_authorized_admin(tg_id: int, config: Config) -> bool`

Спека требует автотест и на DB-обёртки (`get_int`/`set_value` round-trip, дефолт при пустой БД) — в отличие от остального проекта, где DB-код тестируется только вручную. Здесь оправдано: логика достаточно некритична для ручной проверки (легко сломать переименованием ключа), а изолированный sqlite в памяти не тянет за собой постоянную тестовую инфраструктуру. Поэтому у Task 3 два прохода TDD: сначала чистые функции, потом — DB-обёртки на sqlite-фикстуре.

### Часть A — чистая логика (без БД)

- [ ] **Step 1: Написать падающие тесты на чистую логику**

Создать `tests/test_settings.py`:
```python
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
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `python -m pytest tests/test_settings.py -v`
Expected: `ModuleNotFoundError: No module named 'services.settings'`

- [ ] **Step 3: Создать `services/settings.py` — реестр и чистые функции (пока БЕЗ async-обёрток)**

```python
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
```

- [ ] **Step 4: Убедиться, что тесты чистой логики проходят**

Run: `python -m pytest tests/test_settings.py -v`
Expected: `15 passed`

### Часть B — DB-обёртки (sqlite-фикстура)

- [ ] **Step 5: Добавить тестовые зависимости**

В `requirements-dev.txt` заменить содержимое на:
```
-r requirements.txt
pytest>=8.0
pytest-asyncio>=0.24
aiosqlite>=0.20
```

Создать `pytest.ini` в корне проекта:
```ini
[pytest]
asyncio_mode = auto
```

Run: `pip install -r requirements-dev.txt`
Expected: успешная установка `pytest-asyncio` и `aiosqlite`

- [ ] **Step 6: Дописать падающие тесты на DB-обёртки**

Добавить в конец `tests/test_settings.py`:
```python
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
```

- [ ] **Step 7: Убедиться, что новые тесты падают**

Run: `python -m pytest tests/test_settings.py -v -k "unset or roundtrip"`
Expected: `AttributeError: module 'services.settings' has no attribute 'get_int'`

- [ ] **Step 8: Добавить async-обёртки в `services/settings.py`**

Добавить в конец `services/settings.py` (после `_resolve_owner_chat_id`):
```python


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
```

(импорты `Config`/`crud` намеренно перенесены вниз файла, а не в шапку — `db/crud.py` в конечном счёте импортирует `db/database.py`, а `config.py` ничего не импортирует из `services/`, циклов нет; расположение — исключительно чтобы Части A/B были явно разделены при чтении диффа)

- [ ] **Step 9: Убедиться, что все тесты `test_settings.py` проходят**

Run: `python -m pytest tests/test_settings.py -v`
Expected: `17 passed`

- [ ] **Step 10: Прогнать весь набор тестов и закоммитить**

Run: `python -m pytest -q`
Expected: `26 passed` (9 из Task 1 + 17 из Task 3)

```bash
git add services/settings.py tests/test_settings.py pytest.ini requirements-dev.txt
git commit -m "feat: реестр настроек services/settings.py с валидацией, is_authorized_admin и тестами (sqlite)"
```

---

## Task 4: Динамические цены, file_id книги, id канала практикума, shop_id ЮKassa

**Files:**
- Modify: `keyboards/inline.py`
- Modify: `handlers/test.py`
- Modify: `handlers/menu.py`
- Modify: `handlers/practicum.py`
- Modify: `handlers/book.py`
- Modify: `payments/delivery.py`
- Modify: `payments/webhook.py`

**Interfaces:**
- Consumes: `services.settings.get_int`, `get_str`, `get_practicum_chat_id` (Task 3)
- Produces: `offer_kb`, `smart_menu_kb`, `practicum_buy_kb`, `book_buy_kb` становятся `async def` (сигнатуры возврата не меняются — по-прежнему `InlineKeyboardMarkup`, просто требуют `await`)

Без автотестов (aiogram/DB-touching) — проверка вручную в конце задачи.

- [ ] **Step 1: `services/catalog.py` — убрать статичный `PRODUCT_PRICE_RUB`**

В `services/catalog.py` удалить строку:
```python
PRODUCT_PRICE_RUB = {BOOK: 990, PRACTICUM: 2990}  # консультация бесплатна
```
Цены теперь только в `services/settings.py` (`book_price_rub`, `practicum_price_rub`).

- [ ] **Step 2: `keyboards/inline.py` — убрать статичный `_MENU_LABELS`, сделать ценозависимые функции async**

Заменить строки 1-13 (шапка файла и `_MENU_LABELS`):
```python
"""Inline-клавиатуры. callback_data — namespace через ':' (см. README)."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from services import settings
from services.catalog import BOOK, CONSULT, PRACTICUM

# Кросс-ссылки на экранах M6.1/M7.1/M8.1 («А что за…»).
```
(строка `_QUESTION_LABELS = {...}` и далее — без изменений)

Заменить `offer_kb` (было `def offer_kb`):
```python
async def offer_kb(available: list[str]) -> InlineKeyboardMarkup:
    """Блок 5: до трёх кнопок продуктов (уже купленные/забронированные скрыты)."""
    labels = await _menu_labels()
    rows = [[InlineKeyboardButton(text=labels[p], callback_data=f"offer:{p}")]
            for p in available]
    return _kb(*rows)
```

Добавить перед `offer_kb` вспомогательную функцию:
```python
async def _menu_labels() -> dict[str, str]:
    book_price = await settings.get_int("book_price_rub")
    practicum_price = await settings.get_int("practicum_price_rub")
    return {
        BOOK: f"Книга «Целеполагание» — {book_price} ₽",
        PRACTICUM: f"Практикум «Найди свой код» — {practicum_price} ₽",
        CONSULT: "Бесплатная консультация с Марией",
    }
```

Заменить `practicum_buy_kb`:
```python
async def practicum_buy_kb(available: list[str]) -> InlineKeyboardMarkup:
    """M6.2: кнопка покупки + кросс-ссылки."""
    price = await settings.get_int("practicum_price_rub")
    rows = [[InlineKeyboardButton(text=f"Купить практикум за {price} ₽",
                                  callback_data="practicum:buy")]]
    rows += _other_products_rows(PRACTICUM, available, _QUESTION_LABELS)
    return _kb(*rows)
```

Заменить `book_buy_kb`:
```python
async def book_buy_kb(available: list[str]) -> InlineKeyboardMarkup:
    price = await settings.get_int("book_price_rub")
    rows = [[InlineKeyboardButton(text=f"Купить книгу за {price} ₽", callback_data="book:buy")]]
    rows += _other_products_rows(BOOK, available, _QUESTION_LABELS)
    return _kb(*rows)
```

Заменить `smart_menu_kb`:
```python
async def smart_menu_kb(available: list[str]) -> InlineKeyboardMarkup:
    """M9: показывает только то, что ещё не куплено/не забронировано."""
    labels = await _menu_labels()
    rows = [[InlineKeyboardButton(text=labels[p], callback_data=f"offer:{p}")]
            for p in available]
    return _kb(*rows)
```

Функции `practicum_intro_kb`, `book_intro_kb`, `consult_intro_kb`, `next_kb`, `consent_kb`, `question_kb`, `result_next_kb`, `payment_link_kb`, `reminder_cta_kb`, `after_product_kb`, `retake_kb` — **без изменений** (цену не показывают).

- [ ] **Step 3: `handlers/test.py` — добавить `await` для `offer_kb`**

Строка 76-77, было:
```python
    await callback.message.answer(TEXTS[_OFFER_TEXT_KEY[user.result_type]],
                                  reply_markup=offer_kb(available))
```
стало:
```python
    await callback.message.answer(TEXTS[_OFFER_TEXT_KEY[user.result_type]],
                                  reply_markup=await offer_kb(available))
```

- [ ] **Step 4: `handlers/menu.py` — добавить `await` для `smart_menu_kb` (2 места)**

Строка 43, было:
```python
            await callback.message.answer(TEXTS["M9"], reply_markup=smart_menu_kb(available))
```
стало:
```python
            await callback.message.answer(TEXTS["M9"], reply_markup=await smart_menu_kb(available))
```

Строка 60 (в `show_menu`), было:
```python
    await callback.message.answer(TEXTS["M9"], reply_markup=smart_menu_kb(available))
```
стало:
```python
    await callback.message.answer(TEXTS["M9"], reply_markup=await smart_menu_kb(available))
```

- [ ] **Step 5: `handlers/practicum.py` — динамическая цена и `await` для клавиатуры**

Заменить импорты (строки 7-12):
```python
from config import Config
from db import crud
from keyboards.inline import payment_link_kb, practicum_buy_kb
from payments.yookassa_client import create_payment
from services import settings
from services.catalog import PRACTICUM, get_available_products
from texts.messages import TEXTS
```

Заменить `practicum_details` (строки 17-22):
```python
@router.callback_query(F.data == "practicum:details")
async def practicum_details(callback: CallbackQuery) -> None:
    tg_id = callback.from_user.id
    await callback.answer()
    available = await get_available_products(tg_id)
    await callback.message.answer(TEXTS["M6.2"], reply_markup=await practicum_buy_kb(available))
```

Заменить `practicum_buy` (строки 25-43): `amount = PRODUCT_PRICE_RUB[PRACTICUM]` → `amount = await settings.get_int("practicum_price_rub")`; `shop_id=config.yookassa_shop_id` → `shop_id=await settings.get_str("yookassa_shop_id")`:
```python
@router.callback_query(F.data == "practicum:buy")
async def practicum_buy(callback: CallbackQuery, config: Config) -> None:
    tg_id = callback.from_user.id
    await callback.answer()

    amount = await settings.get_int("practicum_price_rub")
    purchase = await crud.create_purchase(tg_id, PRACTICUM, amount)
    payment_id, confirmation_url = await create_payment(
        shop_id=await settings.get_str("yookassa_shop_id"), secret_key=config.yookassa_secret_key,
        amount_rub=amount, description="Практикум «Найди свой код»",
        idempotence_key=str(purchase.id), return_url=config.webhook_base_url,
        metadata={"tg_id": tg_id, "product": PRACTICUM, "purchase_id": purchase.id},
    )
    await crud.attach_yk_payment_id(purchase.id, payment_id)

    await callback.message.answer(
        f"Практикум «Найди свой код» — {amount} ₽. Оплата откроется по кнопке ниже.",
        reply_markup=payment_link_kb(confirmation_url, f"Оплатить {amount} ₽"),
    )
```

- [ ] **Step 6: `handlers/book.py` — то же самое для книги**

Заменить импорты (строки 7-12):
```python
from config import Config
from db import crud
from keyboards.inline import book_buy_kb, payment_link_kb
from payments.yookassa_client import create_payment
from services import settings
from services.catalog import BOOK, get_available_products
from texts.messages import TEXTS
```

Заменить `book_details` (строки 17-22):
```python
@router.callback_query(F.data == "book:details")
async def book_details(callback: CallbackQuery) -> None:
    tg_id = callback.from_user.id
    await callback.answer()
    available = await get_available_products(tg_id)
    await callback.message.answer(TEXTS["M8.2"], reply_markup=await book_buy_kb(available))
```

Заменить `book_buy` (строки 25-43):
```python
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
```

- [ ] **Step 7: `payments/delivery.py` — book_file_id и practicum_channel_id из настроек**

Заменить импорты (строки 6-14):
```python
import logging

from aiogram import Bot

from config import Config
from db import crud
from db.models import Purchase
from keyboards.inline import after_product_kb
from services import checkpoints, settings
from services.catalog import BOOK, PRACTICUM, get_available_products
from texts.messages import TEXTS
```

Заменить `_deliver_practicum` (строки 34-45):
```python
async def _deliver_practicum(bot: Bot, config: Config, purchase: Purchase) -> None:
    chat_id = await settings.get_practicum_chat_id()
    if not chat_id:
        logger.error("practicum_channel_id не задан в /settings, не могу выдать доступ purchase=%s",
                     purchase.id)
        return
    link = await bot.create_chat_invite_link(
        chat_id, member_limit=1, name=f"practicum-{purchase.user_tg_id}"[:32],
    )
    available = await get_available_products(purchase.user_tg_id)
    text = TEXTS["M6.3"].format(invite_link=link.invite_link)
    await bot.send_message(purchase.user_tg_id, text,
                           reply_markup=after_product_kb(PRACTICUM, available))
```

Заменить `_deliver_book` (строки 48-55):
```python
async def _deliver_book(bot: Bot, config: Config, purchase: Purchase) -> None:
    available = await get_available_products(purchase.user_tg_id)
    await bot.send_message(purchase.user_tg_id, TEXTS["M8.3"],
                           reply_markup=after_product_kb(BOOK, available))
    book_file_id = await settings.get_str("book_file_id")
    if book_file_id:
        await bot.send_document(purchase.user_tg_id, book_file_id, protect_content=True)
    else:
        logger.error("book_file_id не задан в /settings, не могу отправить файл purchase=%s",
                     purchase.id)
```

- [ ] **Step 8: `payments/webhook.py` — shop_id из настроек**

Заменить импорты (строки 9-13):
```python
from config import Config
from db import crud
from exports.notifier import notify_payment
from payments import delivery
from payments.yookassa_client import get_payment
from services import settings
```

Заменить вызов `get_payment` (строки 31-35):
```python
        try:
            remote = await get_payment(
                shop_id=await settings.get_str("yookassa_shop_id"),
                secret_key=config.yookassa_secret_key,
                payment_id=payment_id,
            )
```

- [ ] **Step 9: Проверить, что всё импортируется**

Run:
```bash
python -m py_compile keyboards/inline.py handlers/test.py handlers/menu.py handlers/practicum.py handlers/book.py payments/delivery.py payments/webhook.py services/catalog.py
python -c "
import os
os.environ.setdefault('BOT_TOKEN', 'test')
os.environ.setdefault('DATABASE_URL', 'postgresql://u:p@localhost/db')
import bot
print('ok')
"
```
Expected: без ошибок, `ok`

- [ ] **Step 10: Прогнать тесты и закоммитить**

Run: `python -m pytest -q`
Expected: `26 passed`

```bash
git add services/catalog.py keyboards/inline.py handlers/test.py handlers/menu.py handlers/practicum.py handlers/book.py payments/delivery.py payments/webhook.py
git commit -m "feat: цены, book_file_id, practicum_channel_id, yookassa_shop_id читаются из /settings"
```

---

## Task 5: Динамический интервал напоминаний и эффективный владелец

**Files:**
- Modify: `scheduler.py`
- Modify: `exports/notifier.py`

**Interfaces:**
- Consumes: `services.settings.get_int`, `get_effective_owner_chat_id` (Task 3)

- [ ] **Step 1: `scheduler.py` — читать интервалы из настроек на каждой итерации**

Заменить импорты (строки 14-24):
```python
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup

from config import Config
from db import crud
from exports.notifier import retry_unexported_leads
from keyboards.inline import next_kb, reminder_cta_kb
from payments import delivery
from services import checkpoints, settings
from services.catalog import BOOK, PRACTICUM
from texts.messages import TEXTS
```

Заменить `process_reminders` (строка 55, было `delay = timedelta(hours=config.reminder_delay_hours)`):
```python
async def process_reminders(bot: Bot, config: Config) -> int:
    sent = 0
    delay = timedelta(hours=await settings.get_int("reminder_delay_hours"))
    for user, code in await crud.due_reminder_users(checkpoints.REMINDER_CODES, delay):
```
(остальное тело функции — без изменений)

Заменить `reminder_loop` (строки 92-102):
```python
async def reminder_loop(bot: Bot, config: Config) -> None:
    logger.info("Планировщик запущен")
    while True:
        try:
            await process_reminders(bot, config)
            await process_undelivered_purchases(bot, config)
            await retry_unexported_leads(bot, config)
        except Exception:  # noqa: BLE001
            logger.exception("Ошибка в цикле планировщика")
        interval = await settings.get_int("reminder_check_interval")
        await asyncio.sleep(interval)
```

- [ ] **Step 2: `exports/notifier.py` — эффективный владелец вместо `config.owner_chat_id`**

Заменить импорты (строки 10-14):
```python
from aiogram import Bot

from config import Config
from db import crud
from db.models import Lead, Purchase
from services import settings
```

Заменить `notify_lead` (строки 21-30):
```python
async def notify_lead(bot: Bot, config: Config, lead: Lead) -> None:
    owner_chat_id = await settings.get_effective_owner_chat_id(config)
    if not owner_chat_id:
        return
    user = await crud.get_user(lead.user_tg_id)
    username = f"@{user.username}" if user and user.username else str(lead.user_tg_id)
    text = (f"📩 Новая заявка на консультацию\n"
           f"Пользователь: {username} (id {lead.user_tg_id})\n"
           f"Email: {lead.email}")
    await bot.send_message(owner_chat_id, text)
    await crud.mark_lead_exported(lead.user_tg_id)
```

Заменить `notify_payment` (строки 33-41):
```python
async def notify_payment(bot: Bot, config: Config, purchase: Purchase) -> None:
    owner_chat_id = await settings.get_effective_owner_chat_id(config)
    if not owner_chat_id:
        return
    user = await crud.get_user(purchase.user_tg_id)
    username = f"@{user.username}" if user and user.username else str(purchase.user_tg_id)
    label = _PRODUCT_LABELS.get(purchase.product, purchase.product)
    text = (f"💰 Оплата: {label} — {purchase.amount_rub} ₽\n"
           f"Пользователь: {username} (id {purchase.user_tg_id})")
    await bot.send_message(owner_chat_id, text)
```

- [ ] **Step 3: Проверить импорт**

Run:
```bash
python -m py_compile scheduler.py exports/notifier.py
python -c "
import os
os.environ.setdefault('BOT_TOKEN', 'test')
os.environ.setdefault('DATABASE_URL', 'postgresql://u:p@localhost/db')
import bot
print('ok')
"
```
Expected: без ошибок, `ok`

- [ ] **Step 4: Прогнать тесты и закоммитить**

Run: `python -m pytest -q`
Expected: `26 passed`

```bash
git add scheduler.py exports/notifier.py
git commit -m "feat: интервалы напоминаний и адресат уведомлений — из /settings"
```

---

## Task 6: Команда `/settings` — меню и редактирование

**Files:**
- Create: `handlers/settings_admin.py`

**Interfaces:**
- Consumes: `services.settings.SETTINGS, cast_value, format_value, is_authorized_admin` (Task 3); `crud.get_setting_value, set_setting_value, set_pending_setting_edit, clear_pending_setting_edit` (Task 2)
- Produces: `router` (aiogram Router, только callback-хендлеры + команда — БЕЗ catch-all текстового хендлера), `async def handle_setting_input(message: Message, config: Config, setting_key: str) -> None` — вызывается из Task 7 (`handlers/text_input.py`)

- [ ] **Step 1: Создать `handlers/settings_admin.py`**

```python
"""Команда /settings — редактирование бизнес-настроек прямо из Telegram.

Только callback-хендлеры (меню, выбор настройки, отмена) + команда /settings.
Сам текстовый ввод нового значения ловит handlers/text_input.py (единственный
catch-all во всём боте) и вызывает handle_setting_input() отсюда.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import Config
from db import crud
from services.settings import SETTINGS, cast_value, format_value, is_authorized_admin

router = Router()


async def _menu_kb() -> InlineKeyboardMarkup:
    rows = []
    for key, spec in SETTINGS.items():
        raw = await crud.get_setting_value(key)
        rows.append([InlineKeyboardButton(
            text=f"{spec.label}: {format_value(spec, raw)}",
            callback_data=f"settings:edit:{key}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("settings"))
async def open_settings(message: Message, config: Config) -> None:
    if not await is_authorized_admin(message.from_user.id, config):
        return
    await message.answer("Настройки бота:", reply_markup=await _menu_kb())


@router.callback_query(F.data.startswith("settings:edit:"))
async def edit_setting(callback: CallbackQuery, config: Config) -> None:
    if not await is_authorized_admin(callback.from_user.id, config):
        await callback.answer()
        return
    key = callback.data.split(":", 2)[2]
    spec = SETTINGS.get(key)
    await callback.answer()
    if spec is None:
        return

    await crud.set_pending_setting_edit(callback.from_user.id, key)
    raw = await crud.get_setting_value(key)
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отмена", callback_data="settings:cancel")],
    ])
    await callback.message.answer(
        f"Пришли новое значение для «{spec.label}» (сейчас: {format_value(spec, raw)}).",
        reply_markup=cancel_kb,
    )


@router.callback_query(F.data == "settings:cancel")
async def cancel_edit(callback: CallbackQuery) -> None:
    await callback.answer()
    await crud.clear_pending_setting_edit(callback.from_user.id)
    await callback.message.answer("Отменено.", reply_markup=await _menu_kb())


async def handle_setting_input(message: Message, config: Config, setting_key: str) -> None:
    """Вызывается из handlers/text_input.py, когда у админа есть pending edit."""
    spec = SETTINGS.get(setting_key)
    if spec is None:
        await crud.clear_pending_setting_edit(message.from_user.id)
        return

    raw_input = (message.text or "").strip()
    old_display = format_value(spec, await crud.get_setting_value(setting_key))
    try:
        normalized = cast_value(spec, raw_input)
    except ValueError:
        hint = "Пришли целое число." if spec.value_type is int else "Значение не должно быть пустым."
        await message.answer(f"Не получилось разобрать значение. {hint}")
        return

    await crud.set_setting_value(setting_key, normalized)
    await crud.clear_pending_setting_edit(message.from_user.id)
    new_display = format_value(spec, normalized)
    await message.answer(
        f"✅ {spec.label}: {old_display} → {new_display}", reply_markup=await _menu_kb(),
    )
```

- [ ] **Step 2: Проверить импорт**

Run: `python -c "import handlers.settings_admin; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Прогнать тесты и закоммитить**

Run: `python -m pytest -q`
Expected: `26 passed`

```bash
git add handlers/settings_admin.py
git commit -m "feat: команда /settings — меню и редактирование настроек"
```

---

## Task 7: Единая точка диспетчеризации свободного текста

**Files:**
- Create: `handlers/text_input.py`
- Modify: `handlers/consult.py`
- Modify: `handlers/admin.py`
- Modify: `bot.py`

**Interfaces:**
- Consumes: `handlers.settings_admin.handle_setting_input` (Task 6), `services.settings.is_authorized_admin` (Task 3)
- Produces: `handlers.consult.handle_email_input(message: Message, config: Config) -> None` (обычная функция, без `@router.message`)

- [ ] **Step 1: `handlers/consult.py` — убрать catch-all, оставить обычную функцию**

Заменить весь блок строк 33-55 (было `@router.message(...) async def consult_email_input(...)`):
```python
async def handle_email_input(message: Message, config: Config) -> None:
    """Вызывается из handlers/text_input.py, когда checkpoint == AWAITING_EMAIL."""
    tg_id = message.from_user.id
    email = (message.text or "").strip()
    if not _EMAIL_RE.match(email):
        await message.answer(TEXTS["CONSULT_EMAIL_INVALID"])
        return

    lead = await crud.create_lead(tg_id, email)
    await crud.set_checkpoint(tg_id, checkpoints.IDLE)

    if lead is not None:
        try:
            await notify_lead(message.bot, config, lead)
        except Exception:  # noqa: BLE001 — не выгрузилось сейчас, ретрай подхватит scheduler
            logger.exception("Не удалось выгрузить лид user=%s сразу", tg_id)

    available = await get_available_products(tg_id)
    await message.answer(TEXTS["M7.2"], reply_markup=after_product_kb(CONSULT, available))
```

(проверка `user.checkpoint != checkpoints.AWAITING_EMAIL` больше не нужна здесь — её теперь делает `text_input.py` ДО вызова этой функции)

- [ ] **Step 2: Создать `handlers/text_input.py`**

```python
"""Единственный catch-all для свободного текста во всём боте.

Раньше эту роль играл handlers/consult.py (сбор email) и был обязан быть
последним зарегистрированным роутером в bot.py, чтобы не перехватывать чужие
сообщения. С появлением второго сценария свободного ввода (значения настроек
в /settings) вся диспетчеризация собрана здесь, в одном месте — конкурирующих
catch-all роутеров в проекте больше нет.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from config import Config
from db import crud
from handlers import consult, settings_admin
from services import checkpoints
from services.settings import is_authorized_admin

router = Router()


@router.message(F.text & ~F.text.startswith("/"))
async def handle_free_text(message: Message, config: Config) -> None:
    tg_id = message.from_user.id

    if await is_authorized_admin(tg_id, config):
        pending_key = await crud.get_pending_setting_edit(tg_id)
        if pending_key is not None:
            await settings_admin.handle_setting_input(message, config, pending_key)
            return

    user = await crud.get_user(tg_id)
    if user is not None and user.checkpoint == checkpoints.AWAITING_EMAIL:
        await consult.handle_email_input(message, config)
        return
    # ни то, ни другое — не наш текст, молчим
```

- [ ] **Step 3: `handlers/admin.py` — заменить проверки владельца на `is_authorized_admin`**

Заменить импорты (строки 8-13):
```python
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from config import Config
from db import crud
from services.settings import is_authorized_admin
```

Заменить проверку в `get_file_id` (строки 18-23):
```python
@router.message(F.document)
async def get_file_id(message: Message, config: Config) -> None:
    """Владелец присылает PDF книги боту — бот отвечает file_id для BOOK_FILE_ID в /settings."""
    if not await is_authorized_admin(message.from_user.id, config):
        return
    await message.reply(f"file_id: <code>{message.document.file_id}</code>")
```

Заменить проверку в `export_leads` (строки 26-29):
```python
@router.message(Command("export_leads"))
async def export_leads(message: Message, config: Config) -> None:
    if not await is_authorized_admin(message.from_user.id, config):
        return  # команда доступна только владельцу бота
```

- [ ] **Step 4: `bot.py` — зарегистрировать новые роутеры, `text_input` — последним**

Заменить импорт (строка 14):
```python
from handlers import (admin, book, consent, consult, menu, practicum, settings_admin,
                      start, test, text_input)
```

Заменить `build_dispatcher` (строки 26-41):
```python
def build_dispatcher(config) -> Dispatcher:
    dp = Dispatcher()
    dp["config"] = config
    dp.message.middleware(ActivityMiddleware())
    dp.callback_query.middleware(ActivityMiddleware())
    dp.include_router(start.router)
    dp.include_router(consent.router)
    dp.include_router(test.router)
    dp.include_router(menu.router)
    dp.include_router(practicum.router)
    dp.include_router(book.router)
    dp.include_router(consult.router)
    dp.include_router(admin.router)
    dp.include_router(settings_admin.router)
    # text_input.router — последним: единственный catch-all для свободного
    # текста (email консультации + значения настроек), иначе он перехватил бы
    # команды/сообщения, предназначенные другим роутерам.
    dp.include_router(text_input.router)
    return dp
```

- [ ] **Step 5: Проверить импорт**

Run:
```bash
python -m py_compile handlers/consult.py handlers/text_input.py handlers/admin.py bot.py
python -c "
import os
os.environ.setdefault('BOT_TOKEN', 'test')
os.environ.setdefault('DATABASE_URL', 'postgresql://u:p@localhost/db')
import bot
print('ok')
"
```
Expected: без ошибок, `ok`

- [ ] **Step 6: Прогнать тесты и закоммитить**

Run: `python -m pytest -q`
Expected: `26 passed`

```bash
git add handlers/consult.py handlers/text_input.py handlers/admin.py bot.py
git commit -m "refactor: единый catch-all для свободного текста (email + значения настроек)"
```

---

## Task 8: Убрать перенесённые настройки из env-поверхности

**Files:**
- Modify: `config.py`
- Modify: `.env.example`
- Modify: `render.yaml`
- Modify: `README.md`

**Interfaces:**
- Consumes: ничего нового — этот таск можно делать только после Task 4 и Task 5 (все читатели `config.book_file_id` и т.п. уже переключены на `services/settings.py`)

- [ ] **Step 1: Переписать `config.py`**

Полностью заменить содержимое `config.py`:
```python
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
```

- [ ] **Step 2: Переписать `.env.example`**

```
BOT_TOKEN=
DATABASE_URL=postgresql://user:password@localhost:5432/neurocode
PORT=8080
OWNER_CHAT_ID=

YOOKASSA_SECRET_KEY=
# Публичный URL этого сервиса (после первого деплоя на Render):
WEBHOOK_BASE_URL=http://localhost:8080

# Остальные настройки (цены книги/практикума, BOOK_FILE_ID,
# PRACTICUM_CHANNEL_ID, интервалы напоминаний, YOOKASSA_SHOP_ID) больше не
# задаются через .env — редактируются прямо в боте командой /settings
# (доступна только OWNER_CHAT_ID).
```

- [ ] **Step 3: Обновить `render.yaml`**

Заменить блок `envVars` (строки 28-55):
```yaml
    envVars:
      - key: DATABASE_URL
        fromDatabase:
          name: neurocode-bot-db
          property: connectionString
      - key: PYTHON_VERSION
        value: "3.12.6"
      # --- секреты: задаются вручную в дашборде (Environment) ---
      - key: BOT_TOKEN
        sync: false
      - key: OWNER_CHAT_ID
        sync: false
      - key: YOOKASSA_SECRET_KEY
        sync: false
      # WEBHOOK_BASE_URL = публичный URL этого сервиса (например,
      # https://neurocode-bot.onrender.com). Заполнить после первого деплоя.
      - key: WEBHOOK_BASE_URL
        sync: false
      # Остальное (цены, BOOK_FILE_ID, PRACTICUM_CHANNEL_ID, интервалы
      # напоминаний, YOOKASSA_SHOP_ID) настраивается командой /settings в
      # самом боте, а не здесь.
```

- [ ] **Step 4: Обновить `README.md`**

Заменить раздел «Переменные окружения» (строки 38-49):
```markdown
## Переменные окружения

См. `.env.example`. Это только секреты и то, что нужно до первого запуска.
Бизнес-настройки — командой `/settings` в самом боте (доступна только
`OWNER_CHAT_ID` или тому, кто назначен доп. владельцем через саму панель, см.
ниже).

- **`OWNER_CHAT_ID`** — постоянный запасной админ. Доступ к `/settings` и
  `/export_leads` даётся ЛИБО ему, ЛИБО текущему БД-значению `owner_chat_id`
  из `/settings` (какое бы из них ни совпало) — так опечатка в панели не
  может заблокировать доступ самому себе (см. `services/settings.py`).

## Настройки бота (`/settings`)

Редактируются прямо в Telegram, без передеплоя: `book_file_id`,
`practicum_channel_id`, цены книги/практикума, интервалы напоминаний
(`reminder_delay_hours`, `reminder_check_interval`), доп. владелец
(`owner_chat_id`), `yookassa_shop_id`. Хранятся в таблице `bot_settings`
(Postgres), реестр с дефолтами и валидацией — `services/settings.py`.

- **`book_file_id`** — получить: прислать PDF книги боту, он ответит
  `file_id` (`handlers/admin.py::get_file_id`), скопировать в `/settings`.
- **`practicum_channel_id`** — ID закрытого канала практикума (`-100...`);
  бот должен быть администратором канала с правом приглашать пользователей.
```

Заменить пункт 5 в «Верификация вручную» (строки 95-97):
```markdown
5. Напоминания: временно поставить `reminder_delay_hours=0` и
   `reminder_check_interval=30` через `/settings`, убедиться что R1–R6
   приходят по одному разу и не дублируются при повторных тиках scheduler'а.
6. `/settings` → сменить цену книги → она сразу видна в кнопке M8.1/M9 без
   рестарта процесса. Намеренно испортить `owner_chat_id` через `/settings`
   (например, вписать свой левый id) → доступ к `/settings` с исходного
   env-`OWNER_CHAT_ID` всё ещё работает.
```

- [ ] **Step 5: Проверить, что бот стартует с новым конфигом**

Run:
```bash
python -m py_compile config.py
python -c "
import os
os.environ.setdefault('BOT_TOKEN', 'test')
os.environ.setdefault('DATABASE_URL', 'postgresql://u:p@localhost/db')
import bot
print('ok')
"
```
Expected: без ошибок, `ok`

- [ ] **Step 6: Прогнать тесты и закоммитить**

Run: `python -m pytest -q`
Expected: `26 passed`

```bash
git add config.py .env.example render.yaml README.md
git commit -m "chore: убрать перенесённые в /settings ключи из env-поверхности"
```

---

## Task 9: Финальная проверка и синхронизация живого Render-деплоя

**Files:** нет изменений кода — только верификация и ручные операционные шаги.

- [ ] **Step 1: Полный прогон тестов**

Run: `python -m pytest -q`
Expected: `26 passed`

- [ ] **Step 2: Полная компиляция и импорт**

Run:
```bash
cd C:\Users\mccaq\neurocode-bot
python -m py_compile $(find . -name "*.py" -not -path "./.venv/*" -not -path "./.git/*")
python -c "
import os
os.environ.setdefault('BOT_TOKEN', 'test')
os.environ.setdefault('DATABASE_URL', 'postgresql://u:p@localhost/db')
import bot
print('bot.py imports OK')
"
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
```
Expected: без ошибок, `bot.py imports OK`

- [ ] **Step 3: Push в GitHub — Render передеплоит автоматически**

Run:
```bash
git push origin master
```

- [ ] **Step 4: Дождаться деплоя и проверить health**

Run (Render передеплоит по push, обычно 1-2 минуты):
```bash
curl -s -o /dev/null -w "HTTP:%{http_code}\n" https://neurocode-bot.onrender.com/health
```
Expected: `HTTP:200`

- [ ] **Step 5: ВАЖНО — вручную перенести реальные значения в `/settings`**

На старом деплое `YOOKASSA_SHOP_ID`, `PRACTICUM_CHANNEL_ID`, `BOOK_FILE_ID` были заданы через env — после этой задачи код их больше не читает, а в новой таблице `bot_settings` для них пока нет строк (дефолты пустые). **Без этого шага оплата сломается** (нет `yookassa_shop_id` → `create_payment` уйдёт с пустым shop_id).

В Telegram, от аккаунта `OWNER_CHAT_ID`, отправить боту `@test_anastasia2_bot`:
1. `/settings` → нажать «🔑 ЮKassa shop_id» → прислать тот же shop_id, что был в Render env (`1400988`, см. историю деплоя).
2. Если `PRACTICUM_CHANNEL_ID` был задан — то же для «📢 ID канала практикума».
3. Если `BOOK_FILE_ID` был задан — то же для «📄 File ID книги» (или прислать PDF заново — `handlers/admin.py::get_file_id` подскажет свежий file_id).

Цены (990 ₽ / 2990 ₽) и интервалы напоминаний (24ч / 300с) переносить не нужно — дефолты в `services/settings.py` совпадают с прежними env-значениями.

- [ ] **Step 6: Сквозная проверка `/settings`**

В Telegram: `/settings` → нажать «📕 Цена книги» → прислать `1490` → убедиться, что пришло подтверждение `✅ 📕 Цена книги: 990 ₽ → 1490 ₽` → открыть M9 (кнопка «Посмотреть другие варианты» из любого места воронки) → убедиться, что кнопка книги показывает `1490 ₽`. Вернуть цену обратно на `990` тем же способом.

- [ ] **Step 7: Проверка защиты от самоблокировки**

`/settings` → «👤 Доп. владелец» → прислать заведомо чужой id, например `1`. Затем снова отправить `/settings` с исходного `OWNER_CHAT_ID` — меню должно открыться (доступ не потерян, т.к. env-id остаётся запасным). Вернуть «Доп. владелец» на пустое значение невозможно через текущий UI (по спеке — вне скоупа); при необходимости можно записать туда сам `OWNER_CHAT_ID` явно.

- [ ] **Step 8: Обновить `render.yaml`-комментарий и закоммитить финальный статус**

Если Step 5 потребовал реальных значений — они живут только в БД, `render.yaml`/`.env.example` менять не нужно (уже сделано в Task 8). Финальный коммит не требуется, если предыдущие шаги ничего не меняли в коде.
