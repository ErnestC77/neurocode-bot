# Mini App — инфраструктура (подпроект 1/3) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить aiohttp на FastAPI, раздать Telegram Mini App (React+TS+Vite SPA) с того же Render-сервиса, что и бот, добавить аутентификацию через `initData`, и запустить Mini App нативной Menu Button — без единого экрана внутри (это подпроекты 2/3), только рабочая труба.

**Architecture:** `asgi.py` — новый композиционный корень (`uvicorn asgi:app`). Бот (aiogram long-polling) выполняется как фоновая задача внутри FastAPI `lifespan`. Webhook ЮKassa переезжает из aiohttp-роута в FastAPI-роутер (та же бизнес-логика, другой транспортный слой). Frontend — отдельная Vite-сборка (`frontend/dist`), монтируется в FastAPI после `/api/*`, чтобы статика не могла перекрыть API.

**Tech Stack:** FastAPI, uvicorn; React 18 + TypeScript + Vite + `@telegram-apps/telegram-ui` + Tailwind CSS + shadcn/ui-совместимый тулинг (`clsx`, `tailwind-merge`, `class-variance-authority`), `react-router-dom` (устанавливается, но не используется в этой задаче — экраны появятся в подпроекте 2).

## Global Constraints

- Палитра (зафиксирована спекой): фон `#162a48` (навy), кнопки золотые `#e8c96a`, текст на фоне — белый. Текст ВНУТРИ золотой кнопки — `#162a48` (тот же навy — сильный контраст, держит систему из двух цветов, а не трёх).
- Текущий чат-флоу на aiogram inline-кнопках (весь `handlers/`, `scheduler.py`, `services/`) — **не трогаем**, должен продолжать работать без изменений.
- Auth — HMAC-SHA256 проверка `initData` (алгоритм из `C:\Users\mccaq\IdeaProjects\barbershop-bot\app\api\auth.py`, порт без изменений логики).
- Тот же Render-сервис (`srv-d93l7lm7r5hc73db981g`), тот же URL (`neurocode-bot.onrender.com`), та же Postgres.
- Без MUI (см. спеку — конфликтует с Tailwind/shadcn по дизайн-языку и стилевому движку).
- Спека: `docs/superpowers/specs/2026-07-03-miniapp-infrastructure-design.md`.

---

## Task 1: `services/telegram_auth.py` — проверка initData (TDD)

**Files:**
- Create: `services/telegram_auth.py`
- Test: `tests/test_telegram_auth.py`

**Interfaces:**
- Produces: `InvalidInitDataError(Exception)`, `parse_and_validate_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86400, now: datetime | None = None) -> dict`

Чистая функция, без БД/сети/aiogram — тестируется как `services/settings.py`. Полностью самостоятельная задача, не трогает существующий код.

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/test_telegram_auth.py`:
```python
"""services/telegram_auth.py: HMAC-проверка initData — чистая логика, без БД/сети."""
import hashlib
import hmac
import time
from urllib.parse import urlencode

import pytest

from services.telegram_auth import InvalidInitDataError, parse_and_validate_init_data

BOT_TOKEN = "123456:test-token"


def _sign(fields: dict, bot_token: str = BOT_TOKEN) -> str:
    """Строит валидно подписанную initData-строку — тот же алгоритм, что и
    в проверяемом коде (иначе happy-path протестировать нечем: подпись
    нужно с чего-то посчитать)."""
    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": signature})


def test_valid_init_data_is_accepted():
    fields = {"auth_date": str(int(time.time())), "user": '{"id": 42, "first_name": "A"}'}
    result = parse_and_validate_init_data(_sign(fields), BOT_TOKEN)
    assert result["user"]["id"] == 42
    assert result["auth_date"] == int(fields["auth_date"])


def test_missing_hash_is_rejected():
    with pytest.raises(InvalidInitDataError):
        parse_and_validate_init_data("auth_date=1&user=%7B%7D", BOT_TOKEN)


def test_tampered_field_is_rejected():
    fields = {"auth_date": str(int(time.time())), "user": '{"id": 42}'}
    signed = _sign(fields)
    tampered = signed.replace("id%22%3A+42", "id%22%3A+999")
    with pytest.raises(InvalidInitDataError):
        parse_and_validate_init_data(tampered, BOT_TOKEN)


def test_wrong_bot_token_is_rejected():
    fields = {"auth_date": str(int(time.time())), "user": '{"id": 42}'}
    signed = _sign(fields, bot_token="999999:other-token")
    with pytest.raises(InvalidInitDataError):
        parse_and_validate_init_data(signed, BOT_TOKEN)


def test_expired_auth_date_is_rejected():
    old_timestamp = int(time.time()) - 100_000
    fields = {"auth_date": str(old_timestamp), "user": '{"id": 42}'}
    with pytest.raises(InvalidInitDataError):
        parse_and_validate_init_data(_sign(fields), BOT_TOKEN, max_age_seconds=86400)


def test_no_user_field_is_ok():
    fields = {"auth_date": str(int(time.time()))}
    result = parse_and_validate_init_data(_sign(fields), BOT_TOKEN)
    assert result["user"] is None
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `cd C:\Users\mccaq\neurocode-bot && python -m pytest tests/test_telegram_auth.py -v`
Expected: `ModuleNotFoundError: No module named 'services.telegram_auth'`

- [ ] **Step 3: Создать `services/telegram_auth.py`**

```python
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
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `python -m pytest tests/test_telegram_auth.py -v`
Expected: `6 passed`

- [ ] **Step 5: Прогнать весь набор тестов и закоммитить**

Run: `python -m pytest -q`
Expected: `38 passed` (32 существующих + 6 новых)

```bash
git add services/telegram_auth.py tests/test_telegram_auth.py
git commit -m "feat: проверка initData Telegram Mini App (services/telegram_auth.py)"
```

---

## Task 2: FastAPI-бэкенд — app factory, auth-зависимости, webhook ЮKassa, композиционный корень

**Files:**
- Create: `api/__init__.py`
- Create: `api/deps.py`
- Create: `api/app.py`
- Create: `api/routers/__init__.py`
- Create: `api/routers/ping.py`
- Modify: `payments/webhook.py` (полная замена — aiohttp → FastAPI `APIRouter`)
- Modify: `bot.py` (извлечь `run_bot_polling`, убрать aiohttp-бутстрап)
- Create: `asgi.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `services.telegram_auth.parse_and_validate_init_data`, `InvalidInitDataError` (Task 1); `services.settings.is_authorized_admin` (существует); `db.crud.mark_paid`, `payments.delivery.deliver`, `payments.yookassa_client.get_payment`, `exports.notifier.notify_payment` (существуют, без изменений сигнатур); `config.Config`, `config.load_config` (существует); `db.database.init_engine`, `init_db` (существует); `handlers.*` роутеры (существуют, без изменений); `scheduler.reminder_loop` (существует)
- Produces:
  - `api.deps.current_client(request: Request) -> int` (FastAPI dependency, возвращает `tg_id`)
  - `api.deps.current_admin(request: Request, tg_id: int = Depends(current_client)) -> int`
  - `api.app.create_app(bot: Bot, config: Config, bot_lifecycle: Callable[[Bot, Config], Awaitable[Callable[[], Awaitable[None]]]]) -> FastAPI`
  - `payments.webhook.router` (FastAPI `APIRouter`, было `setup_routes(app, bot, config)` для aiohttp — **сигнатура полностью меняется**, это единственный ломающий интерфейс из существующего кода)
  - `bot.run_bot_polling(bot: Bot, config: Config) -> None` (новое — извлечено из старого `bot.py::main()`)
  - `asgi.app` (готовый FastAPI-инстанс, точка входа `uvicorn asgi:app`)

Это одна задача, а не несколько: `bot.py`, `payments/webhook.py` и `asgi.py` взаимозависимы (`asgi.py` собирает обе половины) — раздельные коммиты оставили бы репозиторий в нерабочем состоянии между ними.

- [ ] **Step 1: Создать `api/deps.py`**

```python
"""FastAPI-зависимости: аутентификация через initData Telegram Mini App SDK."""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request

from config import Config
from services.settings import is_authorized_admin
from services.telegram_auth import InvalidInitDataError, parse_and_validate_init_data


async def current_client(
    request: Request,
    x_telegram_init_data: str = Header(..., alias="X-Telegram-Init-Data"),
) -> int:
    config: Config = request.app.state.config
    try:
        data = parse_and_validate_init_data(x_telegram_init_data, config.bot_token)
    except InvalidInitDataError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    user = data.get("user") or {}
    tg_id = user.get("id")
    if tg_id is None:
        raise HTTPException(status_code=401, detail="no user in initData")
    return tg_id


async def current_admin(
    request: Request,
    tg_id: int = Depends(current_client),
) -> int:
    config: Config = request.app.state.config
    if not await is_authorized_admin(tg_id, config):
        raise HTTPException(status_code=403, detail="not an admin")
    return tg_id
```

- [ ] **Step 2: Создать `api/routers/__init__.py` (пустой) и `api/routers/ping.py`**

`api/routers/__init__.py`:
```python
```

`api/routers/ping.py`:
```python
"""Тестовый эндпоинт для проверки инфраструктуры Mini App (Task E1)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import current_client

router = APIRouter(prefix="/api")


@router.get("/ping")
async def ping(tg_id: int = Depends(current_client)) -> dict:
    return {"tg_id": tg_id}
```

- [ ] **Step 3: Создать `api/__init__.py` (пустой) и `api/app.py`**

`api/__init__.py`:
```python
```

`api/app.py`:
```python
"""FastAPI application factory.

``create_app`` принимает уже собранный ``bot`` и ``bot_lifecycle`` — callable,
который FastAPI ``lifespan`` вызывает на старте и должен вернуть teardown-
функцию для остановки. Сам ``create_app`` ничего не знает о том, как именно
бот запускается (polling/webhook) — эту развязку делает asgi.py.
"""
from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

from aiogram import Bot
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

from api.routers import ping
from config import Config
from payments import webhook as yookassa_webhook

Teardown = Callable[[], Awaitable[None]]
BotLifecycle = Callable[[Bot, Config], Awaitable[Teardown]]


class _SpaStaticFiles(StaticFiles):
    """Раздаёт собранный SPA, но не даёт закэшировать index.html.

    Telegram WebView агрессивно кэширует index.html — после деплоя без этого
    он продолжал бы грузить старую сборку (старые хэшированные JS/CSS), пока
    пользователь не почистит кэш вручную. Хэшированные ассеты кэшируются
    нормально, не-cache — только у HTML-точки входа.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if path in ("", ".") or path.endswith(".html"):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


def create_app(bot: Bot, config: Config, bot_lifecycle: BotLifecycle) -> FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        teardown = await bot_lifecycle(bot, config)
        try:
            yield
        finally:
            await teardown()

    app = FastAPI(lifespan=lifespan)
    app.state.bot = bot
    app.state.config = config

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    app.include_router(ping.router)
    app.include_router(yookassa_webhook.router)

    # Собранный Mini App (Vite outDir=dist) — монтируется ПОСЛЕ /api/* и
    # /health//yookassa роутов: Starlette матчит по порядку регистрации,
    # так что /api/* никогда не будет перекрыт статикой. check_dir=False —
    # чтобы create_app() был импортируемым в тестах и до первой сборки
    # фронтенда (frontend/dist ещё не существует).
    dist_dir = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    app.mount("/", _SpaStaticFiles(directory=str(dist_dir), html=True, check_dir=False), name="static")
    return app
```

- [ ] **Step 4: Переписать `payments/webhook.py` под FastAPI**

Заменить весь файл (текущее содержимое — aiohttp `make_webhook_handler`/`setup_routes` — полностью удаляется):

```python
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
```

(Логика внутри — байт-в-байт та же, что была в aiohttp-версии; поменялся только транспортный слой: `web.Request`/`web.Response` → `fastapi.Request`/`fastapi.Response`, `bot`/`config` берутся из `request.app.state` вместо замыкания `make_webhook_handler(bot, config)`.)

- [ ] **Step 5: Извлечь `run_bot_polling` в `bot.py`, убрать aiohttp**

Полностью заменить `bot.py`:

```python
"""aiogram-диспетчер и общий раннер long-polling.

``run_bot_polling`` используется в двух местах:
- здесь же, для локального standalone-запуска (``python bot.py``, без
  Mini App/FastAPI — удобно для быстрой проверки чат-флоу);
- из ``asgi.py`` как фоновая задача внутри FastAPI lifespan (продакшен).

Сам этот модуль ничего не знает про FastAPI — раздельность частей: этот
файл только про бота, ``api/app.py`` только про HTTP, ``asgi.py`` их сводит.
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import Config, load_config
from db.database import init_db, init_engine
from handlers import (admin, book, consent, consult, menu, practicum, settings_admin,
                      start, test, text_input)
from middlewares import ActivityMiddleware
from scheduler import reminder_loop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("bot")


def build_dispatcher(config: Config) -> Dispatcher:
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


async def run_bot_polling(bot: Bot, config: Config) -> None:
    dp = build_dispatcher(config)
    reminder_task = asyncio.create_task(reminder_loop(bot, config))
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Запуск long-polling…")
        await dp.start_polling(bot)
    finally:
        reminder_task.cancel()


async def _standalone_main() -> None:
    config = load_config()
    init_engine(config.database_url)
    await init_db()

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        await run_bot_polling(bot, config)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(_standalone_main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Остановлено")
```

- [ ] **Step 6: Создать `asgi.py` (композиционный корень)**

```python
"""Композиционный корень: FastAPI (Mini App + /api/*) + бот как фоновая
задача внутри lifespan. Единственный модуль, импортирующий и ``api``, и
``bot`` — так ``api/app.py`` ничего не знает про aiogram.

Запуск: ``uvicorn asgi:app --host 0.0.0.0 --port $PORT``.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import MenuButtonWebApp, WebAppInfo

from api.app import create_app
from bot import run_bot_polling
from config import Config, load_config
from db.database import init_db, init_engine

logger = logging.getLogger("asgi")

config = load_config()
init_engine(config.database_url)

bot = Bot(token=config.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


async def _bot_lifecycle(bot: Bot, config: Config) -> Callable[[], Awaitable[None]]:
    await init_db()

    # Постоянная кнопка запуска Mini App рядом с полем ввода — не разовая
    # inline-кнопка в сообщении. Ставится один раз на старте процесса.
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(text="Открыть", web_app=WebAppInfo(url=config.webhook_base_url)),
    )

    task = asyncio.create_task(run_bot_polling(bot, config))

    async def teardown() -> None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await bot.session.close()

    return teardown


app = create_app(bot=bot, config=config, bot_lifecycle=_bot_lifecycle)
```

- [ ] **Step 7: Написать тест `tests/test_api.py` (только для маршрутов, не требующих БД)**

```python
"""api/app.py: маршрутизация и auth на /health и /api/ping — без БД
(current_client не обращается к Postgres, только проверяет подпись
initData; current_admin — обращается, поэтому здесь не тестируется)."""
import hashlib
import hmac
import time
from urllib.parse import urlencode

from fastapi.testclient import TestClient

from api.app import create_app
from config import Config

BOT_TOKEN = "123456:test-token"


def _sign(fields: dict) -> str:
    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": signature})


async def _noop_lifecycle(bot, config):
    async def teardown() -> None:
        return None

    return teardown


def _test_config() -> Config:
    return Config(
        bot_token=BOT_TOKEN, database_url="postgresql+asyncpg://u:p@localhost/db",
        port=8080, owner_chat_id=None, yookassa_secret_key="secret",
        webhook_base_url="https://example.com",
    )


def test_health_returns_ok():
    app = create_app(bot=object(), config=_test_config(), bot_lifecycle=_noop_lifecycle)
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ping_without_init_data_is_rejected():
    app = create_app(bot=object(), config=_test_config(), bot_lifecycle=_noop_lifecycle)
    with TestClient(app) as client:
        response = client.get("/api/ping")
    assert response.status_code == 422  # заголовок обязателен (Header(...))


def test_ping_with_valid_init_data_returns_tg_id():
    app = create_app(bot=object(), config=_test_config(), bot_lifecycle=_noop_lifecycle)
    init_data = _sign({"auth_date": str(int(time.time())), "user": '{"id": 777}'})
    with TestClient(app) as client:
        response = client.get("/api/ping", headers={"X-Telegram-Init-Data": init_data})
    assert response.status_code == 200
    assert response.json() == {"tg_id": 777}


def test_ping_with_tampered_init_data_is_rejected():
    app = create_app(bot=object(), config=_test_config(), bot_lifecycle=_noop_lifecycle)
    init_data = _sign({"auth_date": str(int(time.time())), "user": '{"id": 777}'}).replace(
        "id%22%3A+777", "id%22%3A+1"
    )
    with TestClient(app) as client:
        response = client.get("/api/ping", headers={"X-Telegram-Init-Data": init_data})
    assert response.status_code == 401
```

- [ ] **Step 8: Добавить `httpx` в dev-зависимости (нужен `TestClient`)**

В `requirements-dev.txt` добавить строку:
```
httpx>=0.27,<1.0
```

Run: `pip install -r requirements-dev.txt`

- [ ] **Step 9: Убедиться, что тесты проходят**

Run: `python -m pytest tests/test_api.py -v`
Expected: `4 passed`

- [ ] **Step 10: Проверить полный набор тестов и что приложение импортируется**

Run:
```bash
python -m pytest -q
python -m py_compile api/app.py api/deps.py api/routers/ping.py payments/webhook.py bot.py asgi.py
python -c "
import os
os.environ.setdefault('BOT_TOKEN', '123456:test')
os.environ.setdefault('DATABASE_URL', 'postgresql://u:p@localhost/db')
os.environ.setdefault('WEBHOOK_BASE_URL', 'https://example.com')
from asgi import app
print('asgi.py imports OK, app =', type(app).__name__)
"
```
Expected: `42 passed` (38 из Task 1 + 4 новых), компиляция без ошибок, `asgi.py imports OK, app = FastAPI`

- [ ] **Step 11: Закоммитить**

```bash
git add api/ payments/webhook.py bot.py asgi.py tests/test_api.py requirements-dev.txt
git commit -m "feat: FastAPI-бэкенд для Mini App, webhook ЮKassa и бот через lifespan"
```

---

## Task 3: `requirements.txt` + `render.yaml` — обновить под FastAPI/uvicorn

**Files:**
- Modify: `requirements.txt`
- Modify: `render.yaml`

**Interfaces:** нет — чистая конфигурация, никакого кода.

- [ ] **Step 1: Обновить `requirements.txt`**

Заменить содержимое:
```
aiogram>=3.4,<4.0
aiohttp>=3.9
SQLAlchemy[asyncio]>=2.0
asyncpg>=0.29
python-dotenv>=1.0
fastapi>=0.110,<1.0
uvicorn[standard]>=0.29,<1.0
```

(`aiohttp` остаётся — это транзитивная зависимость aiogram, используется им для HTTP-клиента к Telegram API, не для нашего веб-сервера.)

- [ ] **Step 2: Обновить `render.yaml`**

Заменить блоки `buildCommand`/`startCommand` (без изменений в `envVars` — секреты и URL те же):
```yaml
    buildCommand: pip install -r requirements.txt && cd frontend && npm ci && npm run build
    startCommand: uvicorn asgi:app --host 0.0.0.0 --port $PORT
```

Добавить комментарий рядом с `buildCommand` (после существующего блока комментариев в шапке файла):
```yaml
# NODE-НА-RENDER РИСК: сборка вызывает npm для компиляции фронтенда. Python-
# рантайм Render обычно включает Node, но это не гарантировано. Если сборка
# упадёт на `npm: command not found` — переключить сервис на Dockerfile-деплой
# (см. аналогичный кейс в C:\Users\mccaq\IdeaProjects\barbershop-bot\DEPLOY.md).
```

- [ ] **Step 3: Проверить, что файлы валидны**

Run:
```bash
python -c "import yaml; yaml.safe_load(open('render.yaml', encoding='utf-8')); print('render.yaml OK')"
```
Expected: `render.yaml OK` (если модуль `yaml` не установлен — `pip install pyyaml` разово для проверки, в зависимости проекта не добавлять)

- [ ] **Step 4: Закоммитить**

```bash
git add requirements.txt render.yaml
git commit -m "chore: requirements.txt и render.yaml под FastAPI/uvicorn/npm-сборку"
```

---

## Task 4: Frontend — каркас (Vite + React + TS + Tailwind + shadcn-тулинг)

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/components.json`
- Create: `frontend/index.html`
- Create: `frontend/.gitignore`

**Interfaces:**
- Produces: собираемый пустой Vite-проект (`npm run build` → `frontend/dist`), Tailwind-токены `navy` (#162a48) и `gold` (#e8c96a), alias `@/*` → `frontend/src/*` (нужен для shadcn/ui и `lib/utils.ts` из Task 5).

Только конфигурация и тулинг — без единой строчки экранного кода (это Task 5). Проверяется установкой зависимостей, реальную сборку делает Task 5 (там появится `src/`).

- [ ] **Step 1: Создать `frontend/package.json`**

```json
{
  "name": "neurocode-bot-miniapp",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "test": "vitest run"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.2",
    "@telegram-apps/telegram-ui": "^2.1.6",
    "clsx": "^2.1.1",
    "tailwind-merge": "^2.5.2",
    "class-variance-authority": "^0.7.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.10",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.2",
    "typescript": "^5.6.2",
    "vite": "^5.4.8",
    "vitest": "^2.1.2",
    "tailwindcss": "^3.4.13",
    "postcss": "^8.4.47",
    "autoprefixer": "^10.4.20"
  }
}
```

(`react-router-dom` устанавливается сейчас, но не используется в Task 5 — экраны и роутинг появятся в подпроекте 2. Это осознанное решение: стек зафиксирован спекой целиком, ставим один раз.)

- [ ] **Step 2: Создать `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": false,
    "noUnusedParameters": false,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **Step 3: Создать `frontend/tsconfig.node.json`**

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 4: Создать `frontend/vite.config.ts`**

```typescript
import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Вывод в ./dist; FastAPI раздаёт эту папку как Mini App (см. api/app.py).
// Dev-прокси перенаправляет /api на локально запущенный `uvicorn asgi:app`.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
```

- [ ] **Step 5: Создать `frontend/tailwind.config.js`**

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: "#162a48",
        gold: "#e8c96a",
      },
    },
  },
  plugins: [],
};
```

- [ ] **Step 6: Создать `frontend/postcss.config.js`**

```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 7: Создать `frontend/components.json`** (позволяет `npx shadcn add <component>` в подпроекте 2 без переконфигурации)

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "default",
  "rsc": false,
  "tsx": true,
  "tailwind": {
    "config": "tailwind.config.js",
    "css": "src/styles.css",
    "baseColor": "slate",
    "cssVariables": false
  },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils"
  }
}
```

- [ ] **Step 8: Создать `frontend/index.html`**

```html
<!doctype html>
<html lang="ru">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
    <meta name="theme-color" content="#162a48" />
    <title>Диагностика нейрокода</title>
    <!-- Красим фон сразу, чтобы не было белой вспышки до монтирования React/CSS. -->
    <style>
      html, body { background: #162a48; }
    </style>
    <!--
      Telegram WebApp SDK. Намеренно без Subresource Integrity: Telegram
      обновляет этот скрипт по стабильному URL без публикации хэша — атрибут
      integrity сломал бы Mini App при следующем их обновлении. Это
      официальная, требуемая настройка.
    -->
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 9: Создать `frontend/.gitignore`**

```
node_modules
dist
```

- [ ] **Step 10: Установить зависимости и проверить, что конфиг валиден**

Run:
```bash
cd C:\Users\mccaq\neurocode-bot\frontend
npm install
```
Expected: установка проходит без ошибок (пакетов ещё много, `src/` пока нет — это нормально, `npm install` не требует исходников)

- [ ] **Step 11: Закоммитить**

```bash
cd C:\Users\mccaq\neurocode-bot
git add frontend/package.json frontend/package-lock.json frontend/tsconfig.json frontend/tsconfig.node.json frontend/vite.config.ts frontend/tailwind.config.js frontend/postcss.config.js frontend/components.json frontend/index.html frontend/.gitignore
git commit -m "feat: каркас Mini App — Vite+React+TS+Tailwind+shadcn-тулинг"
```

---

## Task 5: Frontend — тестовый экран (auth через initData, вызов `/api/ping`)

**Files:**
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/styles.css`
- Create: `frontend/src/lib/telegram.ts`
- Create: `frontend/src/lib/utils.ts`
- Create: `frontend/src/api/client.ts`

**Interfaces:**
- Consumes: `GET /api/ping` (Task 2, требует заголовок `X-Telegram-Init-Data`)
- Produces: работающий `npm run build`, единственный экран, подтверждающий: initData провалидирован бэкендом, `tg_id` получен и отображён.

- [ ] **Step 1: Создать `frontend/src/lib/telegram.ts`**

```typescript
// Минимальная типизированная обёртка над Telegram WebApp JS SDK (грузится в
// index.html). Вне Telegram (например, обычный браузер при `npm run dev`)
// window.Telegram не определён — все хелперы деградируют, не роняя UI.

interface TelegramWebApp {
  initData: string;
  ready(): void;
  expand(): void;
}

declare global {
  interface Window {
    Telegram?: { WebApp: TelegramWebApp };
  }
}

export const tg: TelegramWebApp | undefined = window.Telegram?.WebApp;

export function initTelegram(): void {
  if (!tg) return;
  tg.ready();
  tg.expand();
}

export function getInitData(): string {
  return tg?.initData ?? "";
}
```

- [ ] **Step 2: Создать `frontend/src/lib/utils.ts`** (стандартный shadcn-хелпер `cn()`)

```typescript
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
```

- [ ] **Step 3: Создать `frontend/src/api/client.ts`**

```typescript
import { getInitData } from "../lib/telegram";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: {
      ...init?.headers,
      "X-Telegram-Init-Data": getInitData(),
    },
  });
  if (!response.ok) {
    throw new ApiError(response.status, await response.text());
  }
  return response.json() as Promise<T>;
}

export const api = {
  ping: () => request<{ tg_id: number }>("/api/ping"),
};
```

- [ ] **Step 4: Создать `frontend/src/styles.css`**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

html,
body,
#root {
  min-height: 100vh;
  background-color: #162a48;
  color: #ffffff;
}
```

- [ ] **Step 5: Создать `frontend/src/App.tsx`** (тестовый экран этой задачи)

```tsx
import { useEffect, useState } from "react";
import { api, ApiError } from "./api/client";

export default function App() {
  const [tgId, setTgId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .ping()
      .then((res) => setTgId(res.tg_id))
      .catch((err) => setError(err instanceof ApiError ? err.message : "Ошибка сети"));
  }, []);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-navy p-6 text-white">
      <h1 className="text-2xl font-bold text-gold">Диагностика нейрокода</h1>
      {tgId !== null && <p>Mini App подключён. Твой tg_id: {tgId}</p>}
      {error !== null && <p className="text-red-400">Ошибка: {error}</p>}
      {tgId === null && error === null && <p>Проверяю подключение…</p>}
    </div>
  );
}
```

- [ ] **Step 6: Создать `frontend/src/main.tsx`**

```tsx
import "@telegram-apps/telegram-ui/dist/styles.css";
import { AppRoot } from "@telegram-apps/telegram-ui";
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { initTelegram } from "./lib/telegram";
import "./styles.css";

initTelegram();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AppRoot appearance="dark" platform="base">
      <App />
    </AppRoot>
  </React.StrictMode>,
);
```

- [ ] **Step 7: Собрать фронтенд и проверить, что сборка проходит**

Run:
```bash
cd C:\Users\mccaq\neurocode-bot\frontend
npm run build
```
Expected: `tsc` без ошибок типов, `vite build` создаёт `frontend/dist/index.html` + хэшированные `assets/*.js`/`*.css`

- [ ] **Step 8: Проверить, что FastAPI теперь реально отдаёт собранный SPA**

Run:
```bash
cd C:\Users\mccaq\neurocode-bot
python -m pytest tests/test_api.py -v
```
Expected: `4 passed` (сборка `dist/` не влияет на эти тесты — `check_dir=False`, но полезно перепроверить, что ничего не сломалось)

- [ ] **Step 9: Закоммитить**

```bash
git add frontend/src
git commit -m "feat: тестовый экран Mini App — initData → /api/ping → tg_id"
```

---

## Task 6: Финальная проверка и синхронизация живого Render-деплоя

**Files:** нет изменений кода — только верификация и ручные операционные шаги.

- [ ] **Step 1: Полный прогон тестов и сборки**

Run:
```bash
cd C:\Users\mccaq\neurocode-bot
python -m pytest -q
python -m py_compile $(find . -name "*.py" -not -path "./.venv/*" -not -path "./.git/*" -not -path "./frontend/*")
cd frontend && npm run build && cd ..
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
```
Expected: `42 passed`, компиляция без ошибок, фронтенд собирается без ошибок

- [ ] **Step 2: Push в GitHub**

Run:
```bash
git push origin master
```

- [ ] **Step 3: Триггернуть деплой на Render вручную**

Автодеплой по push не подключён (см. `.superpowers/sdd/progress.md` — GitHub-вебхук Render не привязан к этому репозиторию, репозиторий создан через личный `gh`-токен). Запустить деплой через API:
```bash
RENDER_KEY=$(grep -o 'rnd_[A-Za-z0-9]*' "C:/Users/mccaq/Desktop/api_key.md")
curl -s -X POST "https://api.render.com/v1/services/srv-d93l7lm7r5hc73db981g/deploys" \
  -H "Authorization: Bearer $RENDER_KEY" -H "Content-Type: application/json" -d '{}'
```

- [ ] **Step 4: Дождаться деплоя, проверить статус и логи**

Run (опрашивать раз в 10-15 секунд до `status: live` или `build_failed`):
```bash
RENDER_KEY=$(grep -o 'rnd_[A-Za-z0-9]*' "C:/Users/mccaq/Desktop/api_key.md")
curl -s -H "Authorization: Bearer $RENDER_KEY" "https://api.render.com/v1/services/srv-d93l7lm7r5hc73db981g/deploys?limit=1"
```
Если `build_failed` и причина — `npm: command not found`: см. `render.yaml`'s комментарий из Task 3, переключить сервис на Dockerfile-деплой (Node + Python) — обратиться к `DEPLOY.md` в `C:\Users\mccaq\IdeaProjects\barbershop-bot` за рабочим Dockerfile-примером.

- [ ] **Step 5: Проверить health и главную страницу**

Run:
```bash
curl -s -o /dev/null -w "health: HTTP:%{http_code}\n" "https://neurocode-bot.onrender.com/health"
curl -s -o /dev/null -w "spa: HTTP:%{http_code}\n" "https://neurocode-bot.onrender.com/"
```
Expected: оба `HTTP:200`

- [ ] **Step 6: Проверить, что YooKassa webhook и текущий чат-флоу не сломались**

В Render-логах убедиться, что бот стартовал (`Run polling for bot @test_anastasia2_bot`), нет трейсбеков при старте. В Telegram: `/start` должен по-прежнему открывать текстовую воронку как раньше (эта задача её не меняла).

- [ ] **Step 7: Проверить Mini App вручную в Telegram**

Открыть чат с `@test_anastasia2_bot` → рядом с полем ввода должна появиться кнопка Menu Button (открывает Mini App) → внутри должен показаться тёмно-синий экран с золотым заголовком «Диагностика нейрокода» и строкой «Mini App подключён. Твой tg_id: ...» с реальным tg_id пользователя.

- [ ] **Step 8: Обновить `.superpowers/sdd/progress.md`**

Зафиксировать в леджере: подпроект 1/3 (инфраструктура Mini App) завершён, коммиты, live-проверка пройдена. Файл гитигнорится — коммитить не нужно, просто дописать для собственной памяти сессии.
