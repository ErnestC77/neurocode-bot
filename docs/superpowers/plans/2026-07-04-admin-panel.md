# Админ-панель в Mini App — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать владельцу и другим админам бота веб-панель внутри существующего Mini App с тремя разделами (Лиды / Покупки / Пользователи) и выгрузкой каждого раздела в Excel.

**Architecture:** Новая таблица `admins` заменяет одиночный `owner_chat_id` только для проверки доступа (не для уведомлений — это отдельный механизм, не трогаем). Новый FastAPI-роутер `/api/admin/*` отдаёт списки и `.xlsx`-экспорт, защищён уже существующей зависимостью `current_admin`. Новый экран `/admin` в том же React SPA, доступный по ссылке из бот-команды `/admin`.

**Tech Stack:** Python 3.12, aiogram 3, FastAPI, SQLAlchemy 2.0 async + asyncpg, openpyxl (новая зависимость), React + TypeScript + react-router-dom (уже используется), Vite.

## Global Constraints

- Каждая DB-функция открывает свою сессию через `db.database.get_sessionmaker()` — см. существующий стиль в `db/crud.py`.
- Доступ к `/api/admin/*` — только через `Depends(current_admin)` (`api/deps.py`, уже существует, не менять).
- `owner_chat_id` / `get_effective_owner_chat_id` — НЕ трогать: это адресат уведомлений (`exports/notifier.py`), отдельная роль от проверки доступа.
- Тесты: HTTP-слой и чистая логика `db/crud.py` — через pytest (`asyncio_mode = auto`, sqlite-в-памяти). aiogram message-хендлеры (команды бота) в этом проекте автотестами не покрываются (нет инфраструктуры для этого) — только ручная проверка. Frontend: только `resolveScreen`-подобная чистая логика проверяется vitest; React-компоненты — вручную через `npm run build` + визуальную проверку (в проекте нет `@testing-library/react`).
- Frontend API-клиент шлёт заголовок `X-Telegram-Init-Data` на каждый запрос (`frontend/src/api/client.ts::request`) — экспорт-эндпоинты возвращают бинарный файл, обычная `<a href>`-ссылка не подойдёт, нужен `fetch` + `Blob`.

---

### Task 1: Таблица `admins` и CRUD

**Files:**
- Modify: `db/models.py` — добавить класс `Admin`
- Modify: `db/crud.py` — добавить `is_admin`, `add_admin`, `remove_admin`, `count_admins`, `ensure_admin_seeded`
- Modify: `tests/conftest.py` — добавить фикстуру `full_db` (sqlite со всей схемой, для тестов crud)
- Test: `tests/test_admin_crud.py`

**Interfaces:**
- Produces: `db.crud.is_admin(tg_id: int) -> bool`, `db.crud.add_admin(tg_id: int, added_by: int | None) -> bool`, `db.crud.remove_admin(tg_id: int) -> bool`, `db.crud.count_admins() -> int`, `db.crud.ensure_admin_seeded(env_owner_chat_id: int | None) -> None`
- Consumes: `db.database.get_sessionmaker()`, `db.models.Base`, `db.models.utcnow()` — уже существуют

- [ ] **Step 1: Добавить фикстуру `full_db` в conftest.py**

В `tests/conftest.py` добавить в конец файла:

```python
import pytest_asyncio

import db.database as database
from db.models import Base


@pytest_asyncio.fixture
async def full_db():
    """Изолированный sqlite в памяти со всей схемой — для тестов db/crud.py,
    которым нужно несколько таблиц сразу (в отличие от settings_db в
    test_settings.py, которой хватает одной bot_settings)."""
    database.init_engine("sqlite+aiosqlite:///:memory:")
    engine = database._engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()
    database._engine = None
    database._sessionmaker = None
```

- [ ] **Step 2: Написать падающие тесты**

Создать `tests/test_admin_crud.py`:

```python
"""db/crud.py: admins — CRUD и бутстрап первого админа из env owner_chat_id."""
from db import crud


async def test_is_admin_false_when_not_added(full_db):
    assert await crud.is_admin(111) is False


async def test_add_admin_then_is_admin_true(full_db):
    added = await crud.add_admin(111, added_by=None)
    assert added is True
    assert await crud.is_admin(111) is True


async def test_add_admin_twice_returns_false_second_time(full_db):
    await crud.add_admin(111, added_by=None)
    added_again = await crud.add_admin(111, added_by=None)
    assert added_again is False


async def test_remove_admin_true_when_existed(full_db):
    await crud.add_admin(111, added_by=None)
    assert await crud.remove_admin(111) is True
    assert await crud.is_admin(111) is False


async def test_remove_admin_false_when_did_not_exist(full_db):
    assert await crud.remove_admin(999) is False


async def test_ensure_admin_seeded_adds_env_owner_when_empty(full_db):
    await crud.ensure_admin_seeded(555)
    assert await crud.is_admin(555) is True


async def test_ensure_admin_seeded_noop_when_admins_exist(full_db):
    await crud.add_admin(111, added_by=None)
    await crud.ensure_admin_seeded(555)
    assert await crud.is_admin(555) is False


async def test_ensure_admin_seeded_noop_when_env_owner_none(full_db):
    await crud.ensure_admin_seeded(None)
    assert await crud.count_admins() == 0
```

- [ ] **Step 3: Запустить тесты и убедиться, что падают**

Run: `pytest tests/test_admin_crud.py -v`
Expected: FAIL — `AttributeError: module 'db.crud' has no attribute 'is_admin'` (и т.д.)

- [ ] **Step 4: Добавить модель `Admin`**

В `db/models.py` добавить после класса `Purchase` (перед `class Lead`):

```python
class Admin(Base):
    """Админ веб-панели/бот-команд — может быть несколько, в отличие от
    единственного owner_chat_id (см. services/settings.py — тот отвечает за
    адресата уведомлений, это другая роль)."""
    __tablename__ = "admins"

    tg_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    added_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
```

- [ ] **Step 5: Добавить CRUD-функции**

В `db/crud.py` добавить импорт `Admin` в существующую строку импорта моделей:

```python
from db.models import (Admin, AdminPendingEdit, Answer, BotSetting, Lead, Purchase,
                       ReminderSent, User, utcnow)
```

И добавить `func` в импорт sqlalchemy:

```python
from sqlalchemy import delete, func, select, update
```

В конец файла добавить:

```python
# ---------- Админы (доступ к /settings, /export_leads, веб-панели) ----------

async def is_admin(tg_id: int) -> bool:
    async with get_sessionmaker()() as session:
        return await session.get(Admin, tg_id) is not None


async def add_admin(tg_id: int, added_by: int | None) -> bool:
    """True, если добавлен; False, если уже был админом (идемпотентно)."""
    async with get_sessionmaker()() as session:
        if await session.get(Admin, tg_id) is not None:
            return False
        session.add(Admin(tg_id=tg_id, added_by=added_by))
        await session.commit()
        return True


async def remove_admin(tg_id: int) -> bool:
    """True, если удалён; False, если не был админом."""
    async with get_sessionmaker()() as session:
        admin = await session.get(Admin, tg_id)
        if admin is None:
            return False
        await session.delete(admin)
        await session.commit()
        return True


async def count_admins() -> int:
    async with get_sessionmaker()() as session:
        result = await session.execute(select(func.count()).select_from(Admin))
        return result.scalar_one()


async def ensure_admin_seeded(env_owner_chat_id: int | None) -> None:
    """Если таблица admins пуста и задан env owner_chat_id — сделать его первым
    админом. Идемпотентно, безопасно вызывать на каждом старте процесса
    (см. asgi.py::_bot_lifecycle)."""
    if env_owner_chat_id is None:
        return
    if await count_admins() > 0:
        return
    await add_admin(env_owner_chat_id, added_by=None)
```

- [ ] **Step 6: Запустить тесты и убедиться, что проходят**

Run: `pytest tests/test_admin_crud.py -v`
Expected: PASS (8 passed)

- [ ] **Step 7: Commit**

```bash
git add db/models.py db/crud.py tests/conftest.py tests/test_admin_crud.py
git commit -m "feat: добавить таблицу admins и CRUD для мульти-админ доступа"
```

---

### Task 2: Переписать `is_authorized_admin` на проверку таблицы `admins`

**Files:**
- Modify: `services/settings.py:135-140` — переписать `is_authorized_admin`
- Modify: `asgi.py` — вызвать `ensure_admin_seeded` при старте
- Modify: `tests/test_settings.py` — расширить фикстуру `settings_db`, добавить тесты

**Interfaces:**
- Consumes: `db.crud.is_admin`, `db.crud.ensure_admin_seeded` (Task 1)
- Produces: `services.settings.is_authorized_admin(tg_id: int, config: Config) -> bool` — сигнатура не меняется, меняется только реализация

- [ ] **Step 1: Расширить фикстуру `settings_db`, чтобы создавала и таблицу `admins`**

В `tests/test_settings.py` найти:

```python
        await conn.run_sync(Base.metadata.create_all, tables=[Base.metadata.tables["bot_settings"]])
```

Заменить на:

```python
        await conn.run_sync(Base.metadata.create_all, tables=[
            Base.metadata.tables["bot_settings"],
            Base.metadata.tables["admins"],
        ])
```

- [ ] **Step 2: Написать падающие тесты**

В конец `tests/test_settings.py` добавить:

```python
import dataclasses

from conftest import _test_config
from services.settings import is_authorized_admin


async def test_is_authorized_admin_true_for_env_owner(settings_db):
    config = dataclasses.replace(_test_config(), owner_chat_id=777)
    assert await is_authorized_admin(777, config) is True


async def test_is_authorized_admin_false_for_stranger(settings_db):
    config = _test_config()
    assert await is_authorized_admin(999, config) is False


async def test_is_authorized_admin_true_for_db_admin(settings_db):
    from db import crud

    await crud.add_admin(555, added_by=None)
    config = _test_config()
    assert await is_authorized_admin(555, config) is True
```

- [ ] **Step 3: Запустить тесты и убедиться, что падают**

Run: `pytest tests/test_settings.py -v -k is_authorized_admin`
Expected: FAIL — старая реализация `is_authorized_admin` не знает про `admins` (тест `test_is_authorized_admin_true_for_db_admin` упадёт: `assert False is True`)

- [ ] **Step 4: Переписать `is_authorized_admin`**

В `services/settings.py` заменить:

```python
async def is_authorized_admin(tg_id: int, config: Config) -> bool:
    """Доступ к /settings и /export_leads: env-владелец ИЛИ текущий БД-владелец."""
    if config.owner_chat_id and tg_id == config.owner_chat_id:
        return True
    effective = await get_effective_owner_chat_id(config)
    return effective is not None and tg_id == effective
```

на:

```python
async def is_authorized_admin(tg_id: int, config: Config) -> bool:
    """Доступ к /settings, /export_leads и веб-панели: env-владелец (бутстрап,
    страховка от самоблокировки) ИЛИ запись в таблице admins.

    Не путать с get_effective_owner_chat_id() выше — та функция отвечает
    только за адресата уведомлений (лиды/оплаты), не за проверку доступа.
    """
    if config.owner_chat_id and tg_id == config.owner_chat_id:
        return True
    return await crud.is_admin(tg_id)
```

- [ ] **Step 5: Запустить тесты и убедиться, что проходят**

Run: `pytest tests/test_settings.py -v`
Expected: PASS (все тесты файла)

- [ ] **Step 6: Засеять первого админа при старте процесса**

В `asgi.py` добавить импорт:

```python
from db.database import init_db, init_engine
from db import crud
```

И в `_bot_lifecycle` после `await init_db()` добавить:

```python
    logger.info("lifespan: init_db() завершён")

    await crud.ensure_admin_seeded(config.owner_chat_id)
```

(строка `logger.info("lifespan: init_db() завершён")` уже есть в файле — новый вызов добавляется сразу после неё, до блока про `set_chat_menu_button`)

- [ ] **Step 7: Запустить полный тестовый набор**

Run: `pytest -v`
Expected: PASS (весь набор, включая новые тесты Task 1 и Task 2)

- [ ] **Step 8: Commit**

```bash
git add services/settings.py asgi.py tests/test_settings.py
git commit -m "feat: is_authorized_admin проверяет таблицу admins, авто-бутстрап из env"
```

---

### Task 3: Команды `/add_admin` и `/remove_admin`

**Files:**
- Modify: `handlers/admin.py` — добавить два новых обработчика команд

**Interfaces:**
- Consumes: `db.crud.add_admin`, `db.crud.remove_admin` (Task 1), `services.settings.is_authorized_admin` (уже импортирован в файле)

**Примечание:** в проекте нет автотестов для aiogram message-хендлеров (только для HTTP-слоя и чистой логики) — проверка вручную, шаги описаны в конце задачи.

- [ ] **Step 1: Добавить обработчики**

В `handlers/admin.py` добавить в конец файла (после `export_leads`):

```python
@router.message(Command("add_admin"))
async def add_admin_cmd(message: Message, config: Config) -> None:
    if not await is_authorized_admin(message.from_user.id, config):
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].lstrip("-").isdigit():
        await message.reply("Использование: /add_admin <tg_id>")
        return
    added = await crud.add_admin(int(parts[1]), added_by=message.from_user.id)
    await message.reply("Добавлен." if added else "Уже был админом.")


@router.message(Command("remove_admin"))
async def remove_admin_cmd(message: Message, config: Config) -> None:
    if not await is_authorized_admin(message.from_user.id, config):
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].lstrip("-").isdigit():
        await message.reply("Использование: /remove_admin <tg_id>")
        return
    removed = await crud.remove_admin(int(parts[1]))
    await message.reply("Удалён." if removed else "Не был админом.")
```

- [ ] **Step 2: Проверить, что модуль импортируется без ошибок**

Run: `python -c "import handlers.admin"`
Expected: без вывода, без ошибок импорта

- [ ] **Step 3: Ручная проверка** (нет автотестов для aiogram-хендлеров в этом проекте)

Запустить бота (`python bot.py` локально с тестовым `.env`, или на реальном сервере) и в чате с ботом от имени существующего админа:
1. Отправить `/add_admin 123456` — ожидать ответ «Добавлен.»
2. Отправить `/add_admin 123456` ещё раз — ожидать «Уже был админом.»
3. Отправить `/remove_admin 123456` — ожидать «Удалён.»
4. Отправить `/remove_admin 123456` ещё раз — ожидать «Не был админом.»
5. Отправить `/add_admin abc` (не число) — ожидать «Использование: /add_admin <tg_id>»
6. От имени НЕ-админа отправить `/add_admin 1` — ожидать отсутствие любого ответа (тихий игнор, как и у существующих админ-команд)

- [ ] **Step 4: Commit**

```bash
git add handlers/admin.py
git commit -m "feat: команды /add_admin и /remove_admin для управления списком админов"
```

---

### Task 4: Команда `/admin` — кнопка входа в веб-панель

**Files:**
- Modify: `keyboards/inline.py` — добавить `open_admin_panel_kb`
- Modify: `handlers/admin.py` — добавить обработчик `/admin`

**Interfaces:**
- Produces: `keyboards.inline.open_admin_panel_kb(url: str) -> InlineKeyboardMarkup`
- Consumes: `config.webhook_base_url` (уже есть в `Config`)

- [ ] **Step 1: Добавить клавиатуру**

В `keyboards/inline.py` добавить в конец файла:

```python
def open_admin_panel_kb(url: str) -> InlineKeyboardMarkup:
    """Кнопка входа в веб-панель (/admin) — открывает Mini App на экране /admin."""
    return _kb([InlineKeyboardButton(text="Открыть админ-панель", web_app=WebAppInfo(url=url))])
```

- [ ] **Step 2: Добавить обработчик команды**

В `handlers/admin.py` добавить импорт:

```python
from keyboards.inline import open_admin_panel_kb
```

И обработчик в конец файла:

```python
@router.message(Command("admin"))
async def open_admin_panel(message: Message, config: Config) -> None:
    if not await is_authorized_admin(message.from_user.id, config):
        return
    url = f"{config.webhook_base_url.rstrip('/')}/#/admin"
    await message.answer("Админ-панель:", reply_markup=open_admin_panel_kb(url))
```

- [ ] **Step 3: Проверить импорт**

Run: `python -c "import handlers.admin"`
Expected: без ошибок

- [ ] **Step 4: Ручная проверка**

От имени админа отправить боту `/admin` — ожидать сообщение «Админ-панель:» с кнопкой «Открыть админ-панель». От имени НЕ-админа — ожидать отсутствие ответа.

- [ ] **Step 5: Commit**

```bash
git add keyboards/inline.py handlers/admin.py
git commit -m "feat: команда /admin с кнопкой входа в веб-панель"
```

---

### Task 5: `db/crud.py` — списки покупок и пользователей для панели

**Files:**
- Modify: `db/crud.py` — добавить `list_purchases_with_user`, `list_users`
- Test: `tests/test_admin_lists_crud.py`

**Interfaces:**
- Produces: `db.crud.list_purchases_with_user() -> list[tuple[Purchase, User | None]]`, `db.crud.list_users() -> list[User]`
- Consumes: `full_db` fixture (Task 1)

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/test_admin_lists_crud.py`:

```python
"""db/crud.py: list_purchases_with_user / list_users — данные для админ-панели."""
from db import crud


async def test_list_users_empty_when_no_users(full_db):
    assert await crud.list_users() == []


async def test_list_users_returns_created_user(full_db):
    await crud.get_or_create_user(42, username="ernest", first_name="Ernest")
    users = await crud.list_users()
    assert len(users) == 1
    assert users[0].tg_id == 42
    assert users[0].username == "ernest"
    assert users[0].checkpoint == "new"


async def test_list_purchases_with_user_empty_when_none(full_db):
    assert await crud.list_purchases_with_user() == []


async def test_list_purchases_with_user_joins_user(full_db):
    await crud.get_or_create_user(42, username="ernest", first_name="Ernest")
    purchase = await crud.create_purchase(42, "book", 990)
    rows = await crud.list_purchases_with_user()
    assert len(rows) == 1
    got_purchase, got_user = rows[0]
    assert got_purchase.id == purchase.id
    assert got_purchase.product == "book"
    assert got_purchase.status == "pending"
    assert got_user is not None
    assert got_user.username == "ernest"
```

- [ ] **Step 2: Запустить тесты и убедиться, что падают**

Run: `pytest tests/test_admin_lists_crud.py -v`
Expected: FAIL — `AttributeError: module 'db.crud' has no attribute 'list_purchases_with_user'`

- [ ] **Step 3: Добавить функции**

В `db/crud.py` добавить (рядом с `list_leads`, в раздел покупок/пользователей — можно в конец файла):

```python
async def list_purchases_with_user() -> list[tuple[Purchase, User | None]]:
    """Все покупки с данными пользователя, свежие сверху — для админ-панели."""
    async with get_sessionmaker()() as session:
        rows = await session.execute(
            select(Purchase, User)
            .join(User, User.tg_id == Purchase.user_tg_id, isouter=True)
            .order_by(Purchase.created_at.desc())
        )
        return [(purchase, user) for purchase, user in rows.all()]


async def list_users() -> list[User]:
    """Все пользователи, свежие сверху — для админ-панели."""
    async with get_sessionmaker()() as session:
        return list(await session.scalars(select(User).order_by(User.created_at.desc())))
```

- [ ] **Step 4: Запустить тесты и убедиться, что проходят**

Run: `pytest tests/test_admin_lists_crud.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add db/crud.py tests/test_admin_lists_crud.py
git commit -m "feat: crud.list_purchases_with_user и list_users для админ-панели"
```

---

### Task 6: `GET /api/admin/{leads,purchases,users}` — JSON-эндпоинты

**Files:**
- Create: `api/routers/admin.py`
- Modify: `api/app.py` — подключить роутер
- Test: `tests/test_admin_api.py`

**Interfaces:**
- Consumes: `api.deps.current_admin` (уже существует), `db.crud.list_leads`, `db.crud.list_purchases_with_user`, `db.crud.list_users` (Task 5)
- Produces: HTTP `GET /api/admin/leads`, `GET /api/admin/purchases`, `GET /api/admin/users` — каждый защищён `current_admin`, отдаёт JSON-список

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/test_admin_api.py`:

```python
"""api/routers/admin.py — HTTP-контракт веб-панели: доступ только админам,
формат списков (JSON) и Excel-экспорта (добавится в Task 7)."""
from __future__ import annotations

import dataclasses

from fastapi.testclient import TestClient

from api.app import create_app
from conftest import _sqlite_lifecycle, _test_config, init_data_for


def _client(tg_id: int) -> tuple[TestClient, dict]:
    app = create_app(bot=object(), config=_test_config(), bot_lifecycle=_sqlite_lifecycle)
    return TestClient(app), {"X-Telegram-Init-Data": init_data_for(tg_id)}


def _admin_client(tg_id: int) -> tuple[TestClient, dict]:
    config = dataclasses.replace(_test_config(), owner_chat_id=tg_id)
    app = create_app(bot=object(), config=config, bot_lifecycle=_sqlite_lifecycle)
    return TestClient(app), {"X-Telegram-Init-Data": init_data_for(tg_id)}


def test_leads_rejected_for_non_admin():
    client, headers = _client(801)
    with client:
        response = client.get("/api/admin/leads", headers=headers)
    assert response.status_code == 403


def test_leads_empty_for_admin_with_no_leads():
    client, headers = _admin_client(802)
    with client:
        response = client.get("/api/admin/leads", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


def test_purchases_empty_for_admin_with_no_purchases():
    client, headers = _admin_client(803)
    with client:
        response = client.get("/api/admin/purchases", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


def test_users_lists_self_after_first_request():
    # current_client() создаёт/трогает User-запись на каждый запрос — админ
    # уже появится в /api/admin/users после одного собственного запроса.
    client, headers = _admin_client(804)
    with client:
        response = client.get("/api/admin/users", headers=headers)
    assert response.status_code == 200
    users = response.json()
    assert len(users) == 1
    assert users[0]["tg_id"] == 804
    assert users[0]["checkpoint"] == "new"


def test_purchases_rejected_for_non_admin():
    client, headers = _client(805)
    with client:
        response = client.get("/api/admin/purchases", headers=headers)
    assert response.status_code == 403


def test_users_rejected_for_non_admin():
    client, headers = _client(806)
    with client:
        response = client.get("/api/admin/users", headers=headers)
    assert response.status_code == 403
```

- [ ] **Step 2: Запустить тесты и убедиться, что падают**

Run: `pytest tests/test_admin_api.py -v`
Expected: FAIL — 404 (роутера ещё нет)

- [ ] **Step 3: Создать роутер**

Создать `api/routers/admin.py`:

```python
"""Роутер веб-админ-панели: /api/admin/* — списки лидов/покупок/пользователей
и (Task 7) их выгрузка в Excel. Доступ — только текущим админам
(router-level Depends(current_admin), см. api/deps.py)."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import current_admin
from db import crud

router = APIRouter(prefix="/api/admin", dependencies=[Depends(current_admin)])


class LeadOut(BaseModel):
    tg_id: int
    username: str | None
    email: str | None
    created_at: datetime


class PurchaseOut(BaseModel):
    id: int
    tg_id: int
    username: str | None
    product: str
    amount_rub: int
    status: str
    paid_at: datetime | None
    delivered_at: datetime | None


class UserOut(BaseModel):
    tg_id: int
    username: str | None
    first_name: str | None
    checkpoint: str
    result_type: str | None
    test_attempt: int
    created_at: datetime


async def _leads_out() -> list[LeadOut]:
    return [
        LeadOut(tg_id=lead.user_tg_id, username=user.username if user else None,
               email=lead.email, created_at=lead.created_at)
        for lead, user in await crud.list_leads()
    ]


async def _purchases_out() -> list[PurchaseOut]:
    return [
        PurchaseOut(
            id=purchase.id, tg_id=purchase.user_tg_id,
            username=user.username if user else None, product=purchase.product,
            amount_rub=purchase.amount_rub, status=purchase.status,
            paid_at=purchase.paid_at, delivered_at=purchase.delivered_at,
        )
        for purchase, user in await crud.list_purchases_with_user()
    ]


async def _users_out() -> list[UserOut]:
    return [
        UserOut(
            tg_id=user.tg_id, username=user.username, first_name=user.first_name,
            checkpoint=user.checkpoint, result_type=user.result_type,
            test_attempt=user.test_attempt, created_at=user.created_at,
        )
        for user in await crud.list_users()
    ]


@router.get("/leads", response_model=list[LeadOut])
async def get_leads() -> list[LeadOut]:
    return await _leads_out()


@router.get("/purchases", response_model=list[PurchaseOut])
async def get_purchases() -> list[PurchaseOut]:
    return await _purchases_out()


@router.get("/users", response_model=list[UserOut])
async def get_users() -> list[UserOut]:
    return await _users_out()
```

- [ ] **Step 4: Подключить роутер в `api/app.py`**

Заменить:

```python
from api.routers import funnel, ping
```

на:

```python
from api.routers import admin, funnel, ping
```

И после `app.include_router(funnel.router)` добавить:

```python
    app.include_router(admin.router)
```

(перед `app.include_router(yookassa_webhook.router)` или после — порядок между этими тремя не важен, важно что все три идут до `app.mount("/", ...)`)

- [ ] **Step 5: Запустить тесты и убедиться, что проходят**

Run: `pytest tests/test_admin_api.py -v`
Expected: PASS (6 passed)

- [ ] **Step 6: Запустить полный набор тестов**

Run: `pytest -v`
Expected: PASS (весь проект)

- [ ] **Step 7: Commit**

```bash
git add api/routers/admin.py api/app.py tests/test_admin_api.py
git commit -m "feat: GET /api/admin/{leads,purchases,users} для веб-панели"
```

---

### Task 7: Excel-экспорт

**Files:**
- Modify: `requirements.txt` — добавить `openpyxl`
- Modify: `api/routers/admin.py` — добавить 3 эндпоинта экспорта
- Modify: `tests/test_admin_api.py` — добавить тесты экспорта

**Interfaces:**
- Consumes: `_leads_out`, `_purchases_out`, `_users_out` (Task 6)
- Produces: HTTP `GET /api/admin/{leads,purchases,users}/export` → `.xlsx`-файл

- [ ] **Step 1: Добавить зависимость**

В `requirements.txt` добавить строку:

```
openpyxl>=3.1,<4.0
```

Установить локально: `pip install openpyxl>=3.1,<4.0`

- [ ] **Step 2: Написать падающие тесты**

В `tests/test_admin_api.py` добавить в начало файла импорты:

```python
import io

import openpyxl
```

И в конец файла добавить:

```python
def test_leads_export_returns_xlsx_with_header_row():
    client, headers = _admin_client(807)
    with client:
        response = client.get("/api/admin/leads/export", headers=headers)
    assert response.status_code == 200
    assert response.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    wb = openpyxl.load_workbook(io.BytesIO(response.content))
    ws = wb.active
    assert [cell.value for cell in ws[1]] == ["tg_id", "username", "email", "created_at"]


def test_purchases_export_returns_xlsx_with_header_row():
    client, headers = _admin_client(808)
    with client:
        response = client.get("/api/admin/purchases/export", headers=headers)
    assert response.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(response.content))
    ws = wb.active
    assert [cell.value for cell in ws[1]] == [
        "id", "tg_id", "username", "product", "amount_rub", "status", "paid_at", "delivered_at",
    ]


def test_users_export_returns_xlsx_with_header_row():
    client, headers = _admin_client(809)
    with client:
        response = client.get("/api/admin/users/export", headers=headers)
    assert response.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(response.content))
    ws = wb.active
    assert [cell.value for cell in ws[1]] == [
        "tg_id", "username", "first_name", "checkpoint", "result_type", "test_attempt", "created_at",
    ]


def test_leads_export_rejected_for_non_admin():
    client, headers = _client(810)
    with client:
        response = client.get("/api/admin/leads/export", headers=headers)
    assert response.status_code == 403
```

- [ ] **Step 3: Запустить тесты и убедиться, что падают**

Run: `pytest tests/test_admin_api.py -v -k export`
Expected: FAIL — 404 (эндпоинтов ещё нет)

- [ ] **Step 4: Добавить эндпоинты экспорта**

В `api/routers/admin.py` добавить импорты в начало файла:

```python
import io
from datetime import datetime, timezone

from fastapi.responses import StreamingResponse
from openpyxl import Workbook
```

(`datetime` там уже импортирован как `from datetime import datetime` — заменить эту строку на `from datetime import datetime, timezone`)

И в конец файла добавить:

```python
def _xlsx_response(headers: list[str], rows: list[list[object]], filename_prefix: str) -> StreamingResponse:
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"{filename_prefix}_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/leads/export")
async def export_leads() -> StreamingResponse:
    leads = await _leads_out()
    rows = [[l.tg_id, l.username or "", l.email or "", l.created_at.isoformat()] for l in leads]
    return _xlsx_response(["tg_id", "username", "email", "created_at"], rows, "leads")


@router.get("/purchases/export")
async def export_purchases() -> StreamingResponse:
    purchases = await _purchases_out()
    rows = [
        [p.id, p.tg_id, p.username or "", p.product, p.amount_rub, p.status,
         p.paid_at.isoformat() if p.paid_at else "",
         p.delivered_at.isoformat() if p.delivered_at else ""]
        for p in purchases
    ]
    return _xlsx_response(
        ["id", "tg_id", "username", "product", "amount_rub", "status", "paid_at", "delivered_at"],
        rows, "purchases",
    )


@router.get("/users/export")
async def export_users() -> StreamingResponse:
    users = await _users_out()
    rows = [
        [u.tg_id, u.username or "", u.first_name or "", u.checkpoint,
         u.result_type or "", u.test_attempt, u.created_at.isoformat()]
        for u in users
    ]
    return _xlsx_response(
        ["tg_id", "username", "first_name", "checkpoint", "result_type", "test_attempt", "created_at"],
        rows, "users",
    )
```

- [ ] **Step 5: Запустить тесты и убедиться, что проходят**

Run: `pytest tests/test_admin_api.py -v`
Expected: PASS (10 passed)

- [ ] **Step 6: Запустить полный набор тестов**

Run: `pytest -v`
Expected: PASS (весь проект)

- [ ] **Step 7: Commit**

```bash
git add requirements.txt api/routers/admin.py tests/test_admin_api.py
git commit -m "feat: экспорт лидов/покупок/пользователей в Excel"
```

---

### Task 8: Frontend — роут `/admin` и экран `AdminPanel`

**Files:**
- Modify: `frontend/src/App.tsx` — вынести текущую логику в `FunnelApp`, добавить `<Routes>`
- Modify: `frontend/src/api/client.ts` — добавить типы и методы для админ-API
- Create: `frontend/src/screens/AdminPanel.tsx`

**Interfaces:**
- Consumes: `GET /api/admin/{leads,purchases,users}` и `/export` (Task 6, 7), `react-router-dom` (`Routes`, `Route` — уже в зависимостях)
- Produces: маршрут `/admin` (рендерит `AdminPanel`), маршрут `*` (вся текущая логика воронки, без изменений); React-компонент `AdminPanel` (default export)

**Примечание:** `App.tsx` и `AdminPanel.tsx` собираются в одну задачу — роут на несуществующий компонент не даёт рабочей сборки, а раздельные задачи означали бы commit с заведомо красным `npm run build`.

- [ ] **Step 1: Изменить `App.tsx`**

Заменить весь файл `frontend/src/App.tsx` на:

```tsx
import { useEffect, useState } from "react";
import { Route, Routes, useNavigate } from "react-router-dom";
import { api, ApiError, type FunnelState } from "./api/client";
import { resolveScreen } from "./funnel/resolveScreen";
import AdminPanel from "./screens/AdminPanel";
import Consent from "./screens/Consent";
import ConsultDetail from "./screens/ConsultDetail";
import ConsultEmailInput from "./screens/ConsultEmailInput";
import Offer from "./screens/Offer";
import ProductDetail from "./screens/ProductDetail";
import Quiz from "./screens/Quiz";
import Result from "./screens/Result";
import WelcomeCarousel from "./screens/WelcomeCarousel";

function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : "Ошибка сети";
}

function FunnelApp() {
  const [state, setState] = useState<FunnelState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    api
      .getFunnelState()
      .then(setState)
      .catch((err) => setError(errorMessage(err)));
  }, []);

  const screen = state ? resolveScreen(state.checkpoint, state.result_type) : null;

  useEffect(() => {
    if (screen) navigate(`/${screen}`, { replace: true });
  }, [screen, navigate]);

  if (error !== null) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-navy p-6 text-white">
        <p className="text-red-400">Ошибка: {error}</p>
      </div>
    );
  }

  if (state === null || screen === null) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-navy p-6 text-white">
        <p>Загрузка…</p>
      </div>
    );
  }

  function runAction(action: () => Promise<FunnelState>) {
    action().then(setState).catch((err) => setError(errorMessage(err)));
  }

  switch (screen) {
    case "welcome":
      return <WelcomeCarousel onComplete={() => runAction(api.completeWelcome)} />;
    case "consent":
      return <Consent onAccept={() => runAction(api.acceptConsent)} />;
    case "quiz": {
      const questionNo = state.answers.length + 1;
      return <Quiz questionNo={questionNo} onAnswer={(score) => runAction(() => api.submitAnswer(questionNo, score))} />;
    }
    case "result":
      return <Result resultType={state.result_type!} onNext={() => runAction(api.showOffer)} />;
    case "offer":
      return (
        <Offer
          state={state}
          onRetake={() => runAction(api.retake)}
          onSelectProduct={(product) =>
            runAction(() =>
              product === "consult"
                ? api.viewConsult()
                : api.viewProduct(product as "book" | "practicum"),
            )
          }
        />
      );
    case "product-detail": {
      const product = state.checkpoint === "book_viewed" ? "book" : "practicum";
      const price = product === "book" ? state.book_price_rub : state.practicum_price_rub;
      return <ProductDetail product={product} price={price} onPaymentSettled={setState} />;
    }
    case "consult-detail":
      return <ConsultDetail onBook={() => runAction(api.bookConsult)} />;
    case "consult-email-input":
      return (
        <ConsultEmailInput
          onSubmit={api.submitConsultEmail}
          onDone={setState}
          onError={(msg) => setError(msg)}
        />
      );
  }
}

export default function App() {
  return (
    <Routes>
      <Route path="/admin" element={<AdminPanel />} />
      <Route path="*" element={<FunnelApp />} />
    </Routes>
  );
}
```

- [ ] **Step 2: Добавить типы и методы в `api/client.ts`**

В `frontend/src/api/client.ts` добавить после интерфейса `PurchaseInitiatedOut`:

```ts
export interface AdminLead {
  tg_id: number;
  username: string | null;
  email: string | null;
  created_at: string;
}

export interface AdminPurchase {
  id: number;
  tg_id: number;
  username: string | null;
  product: string;
  amount_rub: number;
  status: string;
  paid_at: string | null;
  delivered_at: string | null;
}

export interface AdminUser {
  tg_id: number;
  username: string | null;
  first_name: string | null;
  checkpoint: string;
  result_type: string | null;
  test_attempt: number;
  created_at: string;
}
```

И в конец файла (после существующего `export const api = {...}`) добавить:

```ts
async function requestBlob(path: string): Promise<Blob> {
  const response = await fetch(path, {
    headers: { "X-Telegram-Init-Data": getInitData() },
  });
  if (!response.ok) {
    throw new ApiError(response.status, await response.text());
  }
  return response.blob();
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export const adminApi = {
  getLeads: () => request<AdminLead[]>("/api/admin/leads"),
  getPurchases: () => request<AdminPurchase[]>("/api/admin/purchases"),
  getUsers: () => request<AdminUser[]>("/api/admin/users"),
  exportLeads: async () => downloadBlob(await requestBlob("/api/admin/leads/export"), "leads.xlsx"),
  exportPurchases: async () =>
    downloadBlob(await requestBlob("/api/admin/purchases/export"), "purchases.xlsx"),
  exportUsers: async () => downloadBlob(await requestBlob("/api/admin/users/export"), "users.xlsx"),
};
```

- [ ] **Step 3: Создать `AdminPanel.tsx`**

Создать `frontend/src/screens/AdminPanel.tsx`:

```tsx
import { useEffect, useState } from "react";
import { adminApi, ApiError, type AdminLead, type AdminPurchase, type AdminUser } from "../api/client";

type Tab = "leads" | "purchases" | "users";

function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : "Ошибка сети";
}

export default function AdminPanel() {
  const [tab, setTab] = useState<Tab>("leads");
  const [leads, setLeads] = useState<AdminLead[] | null>(null);
  const [purchases, setPurchases] = useState<AdminPurchase[] | null>(null);
  const [users, setUsers] = useState<AdminUser[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    adminApi.getLeads().then(setLeads).catch((err) => setError(errorMessage(err)));
    adminApi.getPurchases().then(setPurchases).catch((err) => setError(errorMessage(err)));
    adminApi.getUsers().then(setUsers).catch((err) => setError(errorMessage(err)));
  }, []);

  if (error !== null) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-navy p-6 text-white">
        <p className="text-red-400">Доступ запрещён или ошибка сети: {error}</p>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-navy p-4 text-white">
      <div className="mb-4 flex gap-4">
        <button onClick={() => setTab("leads")} className={tab === "leads" ? "font-bold underline" : ""}>
          Лиды
        </button>
        <button onClick={() => setTab("purchases")} className={tab === "purchases" ? "font-bold underline" : ""}>
          Покупки
        </button>
        <button onClick={() => setTab("users")} className={tab === "users" ? "font-bold underline" : ""}>
          Пользователи
        </button>
      </div>

      {tab === "leads" && (
        <section>
          <button onClick={() => adminApi.exportLeads()} className="mb-2 rounded bg-white/10 px-3 py-1">
            Экспорт в Excel
          </button>
          <table className="w-full text-left text-sm">
            <thead>
              <tr>
                <th>tg_id</th>
                <th>username</th>
                <th>email</th>
                <th>created_at</th>
              </tr>
            </thead>
            <tbody>
              {leads?.map((l) => (
                <tr key={l.tg_id}>
                  <td>{l.tg_id}</td>
                  <td>{l.username ?? ""}</td>
                  <td>{l.email ?? ""}</td>
                  <td>{l.created_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {tab === "purchases" && (
        <section>
          <button onClick={() => adminApi.exportPurchases()} className="mb-2 rounded bg-white/10 px-3 py-1">
            Экспорт в Excel
          </button>
          <table className="w-full text-left text-sm">
            <thead>
              <tr>
                <th>id</th>
                <th>tg_id</th>
                <th>username</th>
                <th>product</th>
                <th>amount_rub</th>
                <th>status</th>
                <th>paid_at</th>
                <th>delivered_at</th>
              </tr>
            </thead>
            <tbody>
              {purchases?.map((p) => (
                <tr key={p.id}>
                  <td>{p.id}</td>
                  <td>{p.tg_id}</td>
                  <td>{p.username ?? ""}</td>
                  <td>{p.product}</td>
                  <td>{p.amount_rub}</td>
                  <td>{p.status}</td>
                  <td>{p.paid_at ?? ""}</td>
                  <td>{p.delivered_at ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {tab === "users" && (
        <section>
          <button onClick={() => adminApi.exportUsers()} className="mb-2 rounded bg-white/10 px-3 py-1">
            Экспорт в Excel
          </button>
          <table className="w-full text-left text-sm">
            <thead>
              <tr>
                <th>tg_id</th>
                <th>username</th>
                <th>first_name</th>
                <th>checkpoint</th>
                <th>result_type</th>
                <th>test_attempt</th>
                <th>created_at</th>
              </tr>
            </thead>
            <tbody>
              {users?.map((u) => (
                <tr key={u.tg_id}>
                  <td>{u.tg_id}</td>
                  <td>{u.username ?? ""}</td>
                  <td>{u.first_name ?? ""}</td>
                  <td>{u.checkpoint}</td>
                  <td>{u.result_type ?? ""}</td>
                  <td>{u.test_attempt}</td>
                  <td>{u.created_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Проверить сборку и типы**

Run: `cd frontend && npm run build`
Expected: `tsc` и `vite build` завершаются без ошибок (в т.ч. роут на `AdminPanel` из `App.tsx` резолвится), в `frontend/dist/` появляются собранные файлы

- [ ] **Step 5: Запустить существующие vitest-тесты (регрессия)**

Run: `cd frontend && npm test`
Expected: PASS (существующие тесты `resolveScreen.test.ts` не сломаны)

- [ ] **Step 6: Commit**

```bash
cd frontend
git add src/App.tsx src/api/client.ts src/screens/AdminPanel.tsx
git commit -m "feat: роут /admin и экран AdminPanel с тремя вкладками и экспортом в Excel"
```

---

### Task 9: Деплой и сквозная ручная проверка на сервере

**Files:** нет новых — деплой существующих изменений на Selectel VDS (139.100.204.242, `/opt/neurocode-bot`, systemd-юнит `neurocode-bot.service`)

- [ ] **Step 1: Запушить ветку в GitHub**

```bash
git push origin master
```

- [ ] **Step 2: Обновить код на сервере**

```bash
ssh -i ~/.ssh/id_ed25519_selectel_neurocode root@139.100.204.242 "cd /opt/neurocode-bot && git pull && source .venv/bin/activate && pip install -r requirements.txt"
```

- [ ] **Step 3: Пересобрать фронтенд на сервере**

```bash
ssh -i ~/.ssh/id_ed25519_selectel_neurocode root@139.100.204.242 "cd /opt/neurocode-bot/frontend && npm ci && npm run build"
```

- [ ] **Step 4: Перезапустить сервис**

```bash
ssh -i ~/.ssh/id_ed25519_selectel_neurocode root@139.100.204.242 "systemctl restart neurocode-bot.service && systemctl is-active neurocode-bot.service"
```

Expected: `active`

- [ ] **Step 5: Проверить, что при рестарте засеялся первый админ**

```bash
ssh -i ~/.ssh/id_ed25519_selectel_neurocode root@139.100.204.242 "sudo -u postgres psql -d neurocode -c 'SELECT * FROM admins;'"
```

Expected: минимум одна строка — либо уже существовавшие админы, либо (если таблица была пуста) владелец из `OWNER_CHAT_ID` в `.env`, если тот там задан. Если `.env` не содержит `OWNER_CHAT_ID` и таблица пуста — сразу выполнить `/add_admin <свой tg_id>` от лица владельца через существующий доступ к БД (см. Step 6).

- [ ] **Step 6: Ручная сквозная проверка в Telegram**

1. Если своего tg_id нет в таблице `admins` — добавить вручную через psql: `INSERT INTO admins (tg_id, added_at) VALUES (<твой tg_id>, now());`
2. В чате с ботом `@neurocode_m_bot` отправить `/admin` — ожидать сообщение с кнопкой «Открыть админ-панель»
3. Нажать кнопку — ожидать открытие Mini App на экране с тремя вкладками
4. Проверить вкладку «Пользователи» — должна показывать хотя бы одну строку (себя)
5. Проверить вкладки «Лиды» и «Покупки» — не должны падать (пустой список — нормально, если данных нет)
6. Нажать «Экспорт в Excel» на любой вкладке — должен скачаться `.xlsx`-файл, открыть его и убедиться, что заголовки колонок совпадают с таблицей на экране
7. Проверить `/add_admin <любой tg_id>` от своего имени — ожидать «Добавлен.»

- [ ] **Step 7: Обновить память проекта**

Если всё проверено успешно — не забыть, что это финальный шаг фичи, дальнейших коммитов не требуется (весь код уже закоммичен в предыдущих задачах).
