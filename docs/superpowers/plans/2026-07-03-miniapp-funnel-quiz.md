# Mini App — экраны воронки, квиз (подпроект 2a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перенести экраны welcome → согласие → 7 вопросов теста → результат → оффер трёх продуктов из чата в Telegram Mini App, переиспользуя всю существующую бизнес-логику (checkpoint, scoring, catalog) без изменений схемы БД.

**Architecture:** Новый FastAPI-роутер `api/routers/funnel.py` с `GET /api/funnel/state` + 5 `POST`-действиями зеркалит существующие aiogram callback-хендлеры один-в-один (тот же `db/crud.py`/`services/scoring.py`/`services/catalog.py`). Backend — единственный источник состояния воронки (`users.checkpoint`); frontend (`FunnelGate` в `App.tsx`) при монтировании и после каждого действия перерисовывается строго по вернувшемуся `checkpoint`, без собственной копии правил переходов.

**Tech Stack:** FastAPI + Pydantic (backend), React + TypeScript + Tailwind + react-router-dom (frontend, уже установлены), pytest + pytest-asyncio + aiosqlite (backend-тесты), vitest (frontend, один pure-function тест).

## Global Constraints

- Палитра: фон `#162a48` (класс `bg-navy`), кнопки/акценты `#e8c96a` (класс `bg-gold`/`text-gold`), текст на фоне — белый. Уже объявлены в `frontend/tailwind.config.js`.
- Никаких изменений в `db/models.py` — переиспользуются существующие таблицы `users`/`answers` и существующие функции `db/crud.py`.
- Никакой FSM/дублирующей логики переходов на frontend — рендер строго по `checkpoint`, вернувшемуся с бэкенда.
- Копирайт ТЗ (`C:\Users\mccaq\Desktop\LOGIC.MD`, Блоки 0–5) переносится в `frontend/src/content/texts.ts` как есть, без перефразирования.
- Цены книги/практикума (`book_price_rub`/`practicum_price_rub`) — динамические (настраиваются через `/settings` уже сегодня), поэтому **не хардкодятся** во frontend-тексте — приходят в каждом ответе `FunnelStateOut` с бэкенда через `services.settings.get_int`.
- Карточки продуктов на экране Offer в этом подпроекте кликабельны визуально, но без обработчика — подпроект 2b подключит покупку.
- Чат-хендлеры (`handlers/`) не модифицируются и не отключаются.

---

### Task 1: Backend — `FunnelStateOut`, `GET /api/funnel/state`, `touch_activity` в auth

**Files:**
- Create: `api/routers/funnel.py`
- Create: `tests/conftest.py`
- Modify: `api/deps.py`
- Modify: `api/app.py`
- Modify: `tests/test_api.py`
- Test: `tests/test_funnel_api.py` (create)

**Interfaces:**
- Consumes: `db.crud.get_or_create_user`, `db.crud.touch_activity(tg_id, username, first_name) -> None`, `db.crud.get_user(tg_id) -> User | None`, `db.crud.get_answer_scores(tg_id) -> dict[int, int]`, `services.catalog.get_available_products(tg_id) -> list[str]`, `services.checkpoints.NEW`, `services.settings.get_int(key) -> int`.
- Produces: `api.routers.funnel.FunnelStateOut` (Pydantic, поля `checkpoint: str`, `consent_given: bool`, `result_type: str | None`, `answers: list[AnswerOut]`, `available_products: list[str] | None`, `book_price_rub: int`, `practicum_price_rub: int`) и `api.routers.funnel.AnswerOut` (`question_no: int`, `score: int`) — Task 2 и Task 3 добавляют endpoints в этот же файл и переиспользуют `_build_state()`. `tests/conftest.py::_sign`, `_test_config`, `_noop_lifecycle`, `_sqlite_lifecycle` — переиспользуются во всех последующих backend-тестах этого плана.

Сначала — общая инфраструктура тестов. До сих пор `current_client` не обращался к БД, поэтому `tests/test_api.py` тестировал auth без БД вообще. Как только `current_client` начнёт звать `touch_activity` (шаг ниже), тестам понадобится настоящая (sqlite-в-памяти) БД — и обязательно **на том же event loop**, что и запросы `TestClient` (тот держит собственный поток с своим loop для всего блока `with TestClient(app) as client:`, включая ASGI lifespan). Поэтому sqlite поднимается не в отдельной pytest-фикстуре (это был бы **другой** loop — `RuntimeError` про чужой event loop), а прямо в `bot_lifecycle`, который `TestClient` сам прогоняет через lifespan в своём loop.

- [ ] **Step 1: Создать `tests/conftest.py` с общими хелперами**

```python
"""Общие тестовые хелперы для API-тестов: подпись initData и bot_lifecycle-и
для create_app() (без БД / с sqlite-в-памяти).

sqlite поднимается внутри bot_lifecycle (а не в отдельной pytest-фикстуре),
потому что TestClient прогоняет ASGI lifespan в СВОЁМ выделенном потоке/loop —
если создать async-движок в другом loop (обычная async-фикстура), запросы
через TestClient упадут с "attached to a different event loop".
"""
from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlencode

import db.database as database
from config import Config
from db.models import Base

BOT_TOKEN = "123456:test-token"


def _sign(fields: dict) -> str:
    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": signature})


def _test_config() -> Config:
    return Config(
        bot_token=BOT_TOKEN, database_url="postgresql+asyncpg://u:p@localhost/db",
        port=8080, owner_chat_id=None, yookassa_secret_key="secret",
        webhook_base_url="https://example.com",
    )


async def _noop_lifecycle(bot, config):
    async def teardown() -> None:
        return None

    return teardown


async def _sqlite_lifecycle(bot, config):
    database.init_engine("sqlite+aiosqlite:///:memory:")
    async with database._engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def teardown() -> None:
        await database._engine.dispose()
        database._engine = None
        database._sessionmaker = None

    return teardown


def init_data_for(tg_id: int) -> str:
    return _sign({"auth_date": str(int(time.time())), "user": f'{{"id": {tg_id}}}'})
```

- [ ] **Step 2: Обновить `tests/test_api.py`, чтобы использовать общие хелперы и sqlite для happy-path**

Замени содержимое файла целиком:

```python
"""api/app.py: маршрутизация и auth на /health и /api/ping.

current_client не обращается к БД, пока подпись/пользователь не провалидированы
(422/401-ветки не требуют БД) — но happy-path теперь вызывает touch_activity(),
поэтому ему нужна настоящая (sqlite-в-памяти) БД — см. conftest._sqlite_lifecycle.
"""
from fastapi.testclient import TestClient

from api.app import create_app
from conftest import _noop_lifecycle, _sqlite_lifecycle, _test_config, init_data_for


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
    app = create_app(bot=object(), config=_test_config(), bot_lifecycle=_sqlite_lifecycle)
    with TestClient(app) as client:
        response = client.get("/api/ping", headers={"X-Telegram-Init-Data": init_data_for(777)})
    assert response.status_code == 200
    assert response.json() == {"tg_id": 777}


def test_ping_with_tampered_init_data_is_rejected():
    app = create_app(bot=object(), config=_test_config(), bot_lifecycle=_noop_lifecycle)
    init_data = init_data_for(777).replace("id%22%3A+777", "id%22%3A+1")
    with TestClient(app) as client:
        response = client.get("/api/ping", headers={"X-Telegram-Init-Data": init_data})
    assert response.status_code == 401
```

- [ ] **Step 3: Запустить тесты, убедиться что старые ещё зелёные (до правки `current_client` они обязаны пройти без изменений в поведении)**

Run: `pytest tests/test_api.py -v`
Expected: 4 passed (файл уже переписан на sqlite-lifecycle для happy-path, но `current_client` пока не трогает БД — значит `test_ping_with_valid_init_data_returns_tg_id` пройдёт и без Step 4; так и должно быть на этом шаге).

- [ ] **Step 4: Написать падающий тест на новый эндпоинт `GET /api/funnel/state`**

Создай `tests/test_funnel_api.py`:

```python
"""api/routers/funnel.py — HTTP-контракт воронки квиза.

Бизнес-логика переходов (guard на question_no, compute_result, checkpoint'ы)
1-в-1 копирует handlers/test.py и покрыта там же ручной regression-проверкой
чата; здесь проверяется HTTP-слой: коды ответов, форма JSON, фактический
переход checkpoint через полный HTTP-запрос.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import create_app
from conftest import _sqlite_lifecycle, _test_config, init_data_for


def _client(tg_id: int) -> tuple[TestClient, dict]:
    app = create_app(bot=object(), config=_test_config(), bot_lifecycle=_sqlite_lifecycle)
    return TestClient(app), {"X-Telegram-Init-Data": init_data_for(tg_id)}


def test_state_defaults_for_new_user():
    client, headers = _client(701)
    with client:
        response = client.get("/api/funnel/state", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "checkpoint": "new",
        "consent_given": False,
        "result_type": None,
        "answers": [],
        "available_products": None,
        "book_price_rub": 990,
        "practicum_price_rub": 2990,
    }
```

- [ ] **Step 5: Запустить тест, убедиться что падает (роутера ещё нет)**

Run: `pytest tests/test_funnel_api.py -v`
Expected: FAIL — `404 Not Found` (`/api/funnel/state` не зарегистрирован) либо `ModuleNotFoundError`.

- [ ] **Step 6: Добавить `touch_activity` в `current_client`**

В `api/deps.py` добавь импорт и вызов:

```python
from fastapi import Depends, Header, HTTPException, Request

from config import Config
from db import crud
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
    await crud.touch_activity(tg_id, user.get("username"), user.get("first_name"))
    return tg_id
```

(Только добавлены `from db import crud` и строка `await crud.touch_activity(...)` перед `return tg_id`; остальное без изменений.)

- [ ] **Step 7: Создать `api/routers/funnel.py` с `GET /state`**

```python
"""Роутер воронки квиза: GET/POST под /api/funnel/*.

Бизнес-логика 1-в-1 повторяет handlers/start.py, handlers/consent.py,
handlers/test.py — тот же db/crud.py, services/scoring.py, services/catalog.py,
только вызывается из HTTP-обработчика вместо aiogram callback-хендлера. Один и
тот же checkpoint в БД — истинный источник состояния для чата и Mini App разом.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import current_client
from db import crud
from services import checkpoints, settings
from services.catalog import get_available_products

router = APIRouter(prefix="/api/funnel")


class AnswerOut(BaseModel):
    question_no: int
    score: int


class FunnelStateOut(BaseModel):
    checkpoint: str
    consent_given: bool
    result_type: str | None
    answers: list[AnswerOut]
    available_products: list[str] | None
    book_price_rub: int
    practicum_price_rub: int


async def _build_state(tg_id: int) -> FunnelStateOut:
    user = await crud.get_user(tg_id)
    scores = await crud.get_answer_scores(tg_id)
    available: list[str] | None = None
    result_type = user.result_type if user is not None else None
    if result_type is not None:
        available = await get_available_products(tg_id)
    return FunnelStateOut(
        checkpoint=user.checkpoint if user is not None else checkpoints.NEW,
        consent_given=user is not None and user.consent_given_at is not None,
        result_type=result_type,
        answers=[AnswerOut(question_no=q, score=s) for q, s in sorted(scores.items())],
        available_products=available,
        book_price_rub=await settings.get_int("book_price_rub"),
        practicum_price_rub=await settings.get_int("practicum_price_rub"),
    )


@router.get("/state")
async def get_state(tg_id: int = Depends(current_client)) -> FunnelStateOut:
    return await _build_state(tg_id)
```

- [ ] **Step 8: Зарегистрировать роутер в `api/app.py`**

В `api/app.py` добавь импорт рядом с `from api.routers import ping` и подключи роутер рядом с `app.include_router(ping.router)`:

```python
from api.routers import funnel, ping
```

```python
    app.include_router(ping.router)
    app.include_router(funnel.router)
    app.include_router(yookassa_webhook.router)
```

- [ ] **Step 9: Запустить тесты, убедиться что всё зелёное**

Run: `pytest tests/test_api.py tests/test_funnel_api.py -v`
Expected: 5 passed.

- [ ] **Step 10: Commit**

```bash
git add tests/conftest.py tests/test_api.py tests/test_funnel_api.py api/deps.py api/app.py api/routers/funnel.py
git commit -m "feat: GET /api/funnel/state + touch_activity в auth Mini App"
```

---

### Task 2: Backend — `welcome/complete`, `consent`, `retake`

**Files:**
- Modify: `api/routers/funnel.py`
- Test: `tests/test_funnel_api.py`

**Interfaces:**
- Consumes: `_build_state(tg_id) -> FunnelStateOut` (Task 1), `db.crud.set_checkpoint(tg_id, checkpoint) -> None`, `db.crud.set_consent(tg_id) -> None`, `db.crud.reset_test(tg_id) -> None`, `services.checkpoints.AWAITING_CONSENT`, `services.checkpoints.IN_TEST`.
- Produces: `POST /api/funnel/welcome/complete`, `POST /api/funnel/consent`, `POST /api/funnel/retake` — все три возвращают `FunnelStateOut`, используются в Task 9 (`api/client.ts`/`App.tsx`).

- [ ] **Step 1: Написать падающие тесты**

Добавь в конец `tests/test_funnel_api.py`:

```python
def test_welcome_complete_sets_awaiting_consent():
    client, headers = _client(702)
    with client:
        response = client.post("/api/funnel/welcome/complete", headers=headers)
    assert response.status_code == 200
    assert response.json()["checkpoint"] == "awaiting_consent"


def test_consent_sets_consent_given_and_in_test():
    client, headers = _client(703)
    with client:
        response = client.post("/api/funnel/consent", headers=headers)
    body = response.json()
    assert body["checkpoint"] == "in_test"
    assert body["consent_given"] is True


def test_retake_resets_answers_and_checkpoint():
    client, headers = _client(704)
    with client:
        client.post("/api/funnel/consent", headers=headers)
        for q in range(1, 8):
            client.post("/api/funnel/answers", headers=headers, json={"question_no": q, "score": 2})
        before = client.get("/api/funnel/state", headers=headers).json()
        assert before["result_type"] is not None

        response = client.post("/api/funnel/retake", headers=headers)
    body = response.json()
    assert body["checkpoint"] == "in_test"
    assert body["result_type"] is None
    assert body["answers"] == []
```

(`test_retake_resets_answers_and_checkpoint` временно опирается на `POST /api/funnel/answers`, которого ещё нет — этот тест начнёт проходить только после Task 3. Это ожидаемо: он написан здесь, потому что логически проверяет `retake`, но будет запускаться зелёным только в конце Task 3. Отметь его `pytest.mark.skip` с этим объяснением, сними пометку в Task 3.)

Добавь в начало файла импорт `pytest` и примени пометку:

```python
import pytest
```

```python
@pytest.mark.skip(reason="POST /api/funnel/answers появится в Task 3")
def test_retake_resets_answers_and_checkpoint():
    ...
```

- [ ] **Step 2: Запустить тесты, убедиться что первые два падают, третий skipped**

Run: `pytest tests/test_funnel_api.py -v`
Expected: `test_welcome_complete_sets_awaiting_consent` и `test_consent_sets_consent_given_and_in_test` — FAIL (404); `test_retake_resets_answers_and_checkpoint` — SKIPPED.

- [ ] **Step 3: Добавить три эндпоинта в `api/routers/funnel.py`**

Добавь в конец файла (после `get_state`):

```python
@router.post("/welcome/complete")
async def complete_welcome(tg_id: int = Depends(current_client)) -> FunnelStateOut:
    await crud.set_checkpoint(tg_id, checkpoints.AWAITING_CONSENT)
    return await _build_state(tg_id)


@router.post("/consent")
async def accept_consent(tg_id: int = Depends(current_client)) -> FunnelStateOut:
    await crud.set_consent(tg_id)
    await crud.set_checkpoint(tg_id, checkpoints.IN_TEST)
    return await _build_state(tg_id)


@router.post("/retake")
async def retake(tg_id: int = Depends(current_client)) -> FunnelStateOut:
    await crud.reset_test(tg_id)
    await crud.set_checkpoint(tg_id, checkpoints.IN_TEST)
    return await _build_state(tg_id)
```

- [ ] **Step 4: Запустить тесты**

Run: `pytest tests/test_funnel_api.py -v`
Expected: `test_welcome_complete_sets_awaiting_consent` PASS, `test_consent_sets_consent_given_and_in_test` PASS, `test_retake_resets_answers_and_checkpoint` SKIPPED (снимем пометку в Task 3).

- [ ] **Step 5: Commit**

```bash
git add api/routers/funnel.py tests/test_funnel_api.py
git commit -m "feat: POST /api/funnel/welcome/complete, /consent, /retake"
```

---

### Task 3: Backend — `answers` (с guard и подсчётом результата) и `offer/show`

**Files:**
- Modify: `api/routers/funnel.py`
- Test: `tests/test_funnel_api.py`

**Interfaces:**
- Consumes: `db.crud.next_question_no(tg_id) -> int`, `db.crud.upsert_answer(tg_id, question_no, score) -> None`, `db.crud.get_answer_scores(tg_id) -> dict[int, int]`, `db.crud.set_result(tg_id, result_type) -> None`, `services.scoring.compute_result(scores) -> str`, `services.checkpoints.RESULT_SHOWN`, `services.checkpoints.OFFER_SHOWN`.
- Produces: `POST /api/funnel/answers` (body `{question_no: int, score: int}`), `POST /api/funnel/offer/show` — оба возвращают `FunnelStateOut`; используются в Task 9.

- [ ] **Step 1: Написать падающие тесты**

Добавь в `tests/test_funnel_api.py` (после существующих тестов, перед `test_retake_resets_answers_and_checkpoint`):

```python
def test_answer_appends_and_keeps_in_test_checkpoint():
    client, headers = _client(705)
    with client:
        client.post("/api/funnel/consent", headers=headers)
        response = client.post(
            "/api/funnel/answers", headers=headers, json={"question_no": 1, "score": 2},
        )
    body = response.json()
    assert body["checkpoint"] == "in_test"
    assert body["answers"] == [{"question_no": 1, "score": 2}]
    assert body["result_type"] is None


def test_stale_answer_is_ignored():
    client, headers = _client(706)
    with client:
        client.post("/api/funnel/consent", headers=headers)
        client.post("/api/funnel/answers", headers=headers, json={"question_no": 1, "score": 2})
        # Повторный ответ на уже отвеченный вопрос — no-op, не ошибка.
        response = client.post(
            "/api/funnel/answers", headers=headers, json={"question_no": 1, "score": 0},
        )
    body = response.json()
    assert response.status_code == 200
    assert body["answers"] == [{"question_no": 1, "score": 2}]  # не перезаписалось


def test_seventh_answer_computes_result_and_sets_result_shown():
    client, headers = _client(707)
    # Да,Да,Нет,Иногда,Нет,Да,Иногда -> Q1=2,Q2=2,Q3=0,Q4=1,Q5=0,Q6=2,Q7=1
    # S_survival=Q1+Q2+Q6=6, S_impostor=Q3+Q5+Q7=1, S_others=Q4+Q6+Q7=4 -> survival
    # (тот же пример, что в LOGIC.MD, Блок 3)
    scores = [2, 2, 0, 1, 0, 2, 1]
    with client:
        client.post("/api/funnel/consent", headers=headers)
        response = None
        for q, s in enumerate(scores, start=1):
            response = client.post(
                "/api/funnel/answers", headers=headers, json={"question_no": q, "score": s},
            )
    body = response.json()
    assert body["checkpoint"] == "result_shown"
    assert body["result_type"] == "survival"
    assert len(body["answers"]) == 7


def test_offer_show_sets_offer_shown_and_lists_available_products():
    client, headers = _client(708)
    with client:
        client.post("/api/funnel/consent", headers=headers)
        for q, s in enumerate([2, 2, 0, 1, 0, 2, 1], start=1):
            client.post("/api/funnel/answers", headers=headers, json={"question_no": q, "score": s})
        response = client.post("/api/funnel/offer/show", headers=headers)
    body = response.json()
    assert body["checkpoint"] == "offer_shown"
    assert set(body["available_products"]) == {"book", "practicum", "consult"}
```

Убери пометку `@pytest.mark.skip(...)` с `test_retake_resets_answers_and_checkpoint` (добавленной в Task 2) — теперь `POST /api/funnel/answers` уже существует по завершении этого шага, тест сможет пройти.

- [ ] **Step 2: Запустить тесты, убедиться что новые падают**

Run: `pytest tests/test_funnel_api.py -v`
Expected: 4 новых теста FAIL (404); `test_retake_resets_answers_and_checkpoint` FAIL (404, пометка снята) — эндпоинтов ещё нет.

- [ ] **Step 3: Добавить `answers` и `offer/show` в `api/routers/funnel.py`**

В начало файла добавь недостающие импорты (`BaseModel` уже импортирован; добавь `compute_result`):

```python
from services.scoring import compute_result
```

Добавь класс запроса рядом с `AnswerOut`/`FunnelStateOut`:

```python
class AnswerIn(BaseModel):
    question_no: int
    score: int
```

Добавь эндпоинты в конец файла:

```python
@router.post("/answers")
async def submit_answer(body: AnswerIn, tg_id: int = Depends(current_client)) -> FunnelStateOut:
    expected = await crud.next_question_no(tg_id)
    if body.question_no != expected:
        return await _build_state(tg_id)

    await crud.upsert_answer(tg_id, body.question_no, body.score)

    if body.question_no < 7:
        await crud.set_checkpoint(tg_id, checkpoints.IN_TEST)
    else:
        scores = await crud.get_answer_scores(tg_id)
        result_type = compute_result(scores)
        await crud.set_result(tg_id, result_type)
        await crud.set_checkpoint(tg_id, checkpoints.RESULT_SHOWN)

    return await _build_state(tg_id)


@router.post("/offer/show")
async def show_offer(tg_id: int = Depends(current_client)) -> FunnelStateOut:
    await crud.set_checkpoint(tg_id, checkpoints.OFFER_SHOWN)
    return await _build_state(tg_id)
```

- [ ] **Step 4: Запустить тесты**

Run: `pytest tests/test_funnel_api.py tests/test_api.py -v`
Expected: все тесты PASS (включая `test_retake_resets_answers_and_checkpoint`).

- [ ] **Step 5: Прогнать полный backend-набор**

Run: `pytest -v`
Expected: все тесты проекта (scoring, models, settings, telegram_auth, api, funnel_api) PASS.

- [ ] **Step 6: Commit**

```bash
git add api/routers/funnel.py tests/test_funnel_api.py
git commit -m "feat: POST /api/funnel/answers (с подсчётом результата) и /offer/show"
```

---

### Task 4: Frontend — копирайт (`content/texts.ts`) и API-клиент (`api/client.ts`)

**Files:**
- Create: `frontend/src/content/texts.ts`
- Modify: `frontend/src/api/client.ts`

**Interfaces:**
- Consumes: ничего (первая frontend-задача этого плана поверх уже существующего `frontend/src/api/client.ts::request`).
- Produces: `WELCOME_STEPS: {text: string; buttonLabel: string}[]`, `CONSENT_TEXT: string`, `CONSENT_BUTTON_LABEL: string`, `QUESTIONS: Record<number, string>`, `RESULT_LABELS: Record<string, string>`, `RESULT_TEXTS: Record<string, string>`, `OFFER_INTRO_TEXTS: Record<string, string>`, `OFFER_EMPTY_TEXT: string`, `PRODUCT_LABELS: Record<string, string>` (все — экспорты `frontend/src/content/texts.ts`, используются в Task 5–8). `FunnelState`, `AnswerOut` (типы) и `api.getFunnelState/completeWelcome/acceptConsent/submitAnswer/showOffer/retake` (все — экспорты `frontend/src/api/client.ts`, используются в Task 9).

- [ ] **Step 1: Создать `frontend/src/content/texts.ts`**

```typescript
// Копирайт из ТЗ (C:\Users\mccaq\Desktop\LOGIC.MD, Блоки 0-5), перенесён как есть.
// Цены НЕ хардкодятся здесь — они настраиваются через /settings и приходят
// динамически в каждом FunnelState (book_price_rub/practicum_price_rub).

export interface WelcomeStep {
  text: string;
  buttonLabel: string;
}

export const WELCOME_STEPS: WelcomeStep[] = [
  {
    buttonLabel: "Да, начнём",
    text: `Привет! Это бот Марии Ефимовой — бизнес-гипнолога и клинического психолога. И это диагностика «Какой нейрокод блокирует твой доход».

Пара слов, прежде чем начнём — чтобы ты понимал, что это и откуда.

За 6 лет работы с предпринимателями я увидела одну и ту же картину снова и снова: человек делает всё правильно, стратегия, команда, продукт, а доход замер на месте. И причина почти никогда не в действиях. Она глубже — в нервной системе.

Там записана программа, которая раньше любой логики решает, сколько денег для тебя «безопасно». Я называю это нейрокодом. Именно он тихо возвращает тебя к одной и той же цифре, тем же решениям, тому же потолку, каким бы умным ни был твой план.

Эту диагностику я собрала на основе своей практики и метода, как точный инструмент: за 7 вопросов и 5 минут он показывает, какой именно код тебя держит. Конкретно, с подробной расшифровкой и понятным первым шагом.

Готов узнать свой?`,
  },
  {
    buttonLabel: "Как проходить тест?",
    text: `Скажу как есть, из практики.

То, что ты считаешь характером или ленью, почти всегда — нейрокод. Реакция, которую нервная система записала раньше, чем ты вообще научился выбирать.

Часть ты скопировал у родителей в детстве через зеркальные нейроны: их «нам это не по карману», их страх перед крупными суммами, их привычку сжиматься в момент риска. Часть закрепил сам, там, где что-то когда-то обожгло.

За годы работы я вижу, что всё сводится к трём кодам:
- выживание: нервная система читает рост как угрозу и возвращает тебя назад.
- самозванец: ты достигаешь, но не присваиваешь.
- чужие цели: идёшь быстро, но не туда.

У каждого свой механизм. И свой первый шаг у всех разный. Поэтому сначала нужно точно понять твой. Этим сейчас и займёмся.`,
  },
  {
    buttonLabel: "Продолжить",
    text: `Теперь как проходить, это важно для точности.

7 утверждений. На каждое жми одну кнопку: Да / Иногда / Нет.

Отвечай быстро, первым, что приходит. Не «как правильнее», а как есть. Если начнёшь обдумывать, отвечать будет логика, а мне нужна реакция нервной системы: она честнее и быстрее ума.

«Иногда» — это полноценный ответ, а не способ уйти от выбора. Ставь его, когда правда по-разному.

Тест видишь только ты. Чем честнее с собой, тем точнее результат.

В конце получишь подробную расшифровку: какой код у тебя ведущий, как он проявляется в деньгах и бизнесе и с чего начать.`,
  },
];

export const CONSENT_BUTTON_LABEL = "Поделиться контактом и начать";

export const CONSENT_TEXT = `Остался один шаг и сразу к вопросам.

Чтобы прислать тебе результат и сохранить к нему доступ, мне нужно твоё согласие на обработку контакта в Telegram.

Контакт нужен только чтобы прислать расшифровку и иногда полезные материалы по теме нейрокода.

Подтверждаешь и переходим к тесту.`;

export const QUESTIONS: Record<number, string> = {
  1: "Когда мой доход начинает расти, через какое-то время что-то обязательно «прилетает». Долг, поломка, болезнь, неожиданные расходы. Как будто что-то возвращает меня назад.",
  2: "Я понимаю, что нужно делегировать, но когда доходит до дела, всё равно делаю сам. Быстрее и надёжнее.",
  3: "Я достигаю результатов, но почти сразу обесцениваю их и двигаюсь к следующей цели. Остановиться и почувствовать победу не получается.",
  4: "Если честно, я не уверен, что мои цели действительно мои. Иногда ощущение, что живу ради «правильного» образа жизни, а не своего.",
  5: "В переговорах я часто уступаю или смягчаю позицию даже когда понимаю, что не должен.",
  6: "Ощущение «достаточно» почти никогда не наступает. Я всегда хочу большего, но не потому что рад, а потому что страшно остановиться.",
  7: "Я уже обращался к коучам, психологам, проходил курсы. Что-то менялось, но через время всё возвращалось.",
};

export const RESULT_LABELS: Record<string, string> = {
  survival: "Выживание",
  impostor: "Самозванец",
  others_goals: "Чужие цели",
};

export const RESULT_TEXTS: Record<string, string> = {
  survival: `Твой нейрокод: «Выживание» — самый древний и самый упрямый из трёх кодов. Именно с ним работа даёт самые заметные сдвиги, но давай по порядку.

Твоя нервная система живёт в фоновом режиме угрозы. Не потому что ты тревожный или слабый, а потому что когда-то так было безопаснее. Может, в семье деньги означали ссоры. Может, был период, когда всё держалось на честном слове и одной ошибке. Может, рядом был человек, который постоянно ждал удара. Нервная система это запомнила и сделала вывод: спокойно = подозрительно, а контроль = выживание.

В таком режиме мозг читает рост как опасность. Логика древняя и простая: знакомое = безопасно, непривычно крупная сумма = риск. И как только ты выходишь за привычный потолок, включается компенсаторный механизм, он возвращает тебя к своей цифре любым способом. Долг, внезапная поломка, болезнь, конфликт с партнёром, импульсивная крупная трата. Со стороны выглядит как череда невезения. На деле нервная система просто делает свою работу: тянет тебя обратно в зону, которую считает безопасной.

Как это выглядит в жизни:
- доход замирает на одном уровне, хотя ты делаешь всё правильно;
- делегировать почти невозможно: отпустить контроль = почувствовать угрозу;
- ты не умеешь выключаться, даже в отпуске рука сама тянется к рабочим чатам;
- после хорошего скачка дохода обязательно «что-то случается»;
- решения чаще принимаешь из страха потерять, чем из желания вырасти;
- даже когда всё хорошо, фоном держится «а вдруг сейчас всё рухнет».

Узнаёшь? Это не набор случайностей. Это один механизм, который проявляется в десяти местах сразу.

Ты можешь сколько угодно мотивировать себя, ставить цели и «брать себя в руки», но всё это работает в коре мозга, в логике. А команда «вернись назад» приходит из лимбической системы, которая старше и быстрее. В прямой схватке логика всегда проигрывает лимбике. Поэтому стратегии держатся неделю-две, а потом откат. Дело не в дисциплине, дело в уровне, на котором ты пытаешься это решить.

Этот код — не поломка, а бывшая защита: когда-то она тебя берегла, а теперь держит. Его не нужно ломать или перебарывать. Нервной системе нужно дать новый сигнал на физиологическом уровне, а не на словах: что расти можно и новый уровень не опаснее старого. Как только сигнал доходит, компенсаторный механизм отключается сам. И тогда деньги, которые приходят, наконец остаются.

Это и есть твоя точка работы. Дальше покажу, с чего начать именно с твоим кодом.`,
  impostor: `Твой нейрокод: «Самозванец» — самый коварный из трёх, потому что снаружи у тебя всё хорошо. Ты достигаешь, растёшь, тебя ценят, а внутри пусто и тревожно. Разберём, почему.

Ты достигаешь, но не присваиваешь. Результат есть, а ощущения победы нет. Вместо радости голос внутри: «это случайность», «просто повезло», «скоро поймут, что я не настолько хорош». Ты как будто всё время на испытательном сроке у самого себя.

Этот код записывается рано, там, где тебя сравнивали, критиковали или хвалили только за результат. Где кто-то важный дал понять «ты недостаточно». Не обязательно словами, иногда хватало взгляда, вздоха, «а вот у соседского мальчика…». Ребёнок делает единственный доступный вывод «меня ценят за достижения, а сам по себе я под вопросом». И начинает доказывать, бесконечно.

При каждом успехе включается один и тот же механизм: обесценить, преуменьшить, быстро сбежать к следующей цели. Зачем? Чтобы не пришлось остановиться в победе, ведь остановиться значит дать себя рассмотреть. А рассмотрят — разоблачат, так тебе кажется. Поэтому ты не присваиваешь ни одну вершину, только взял — уже бежишь к следующей.

Как это выглядит в жизни:
- тяжело называть высокую цену, внутри сразу «это слишком, кто я такой»;
- в переговорах уступаешь там, где мог бы держать позицию;
- достиг и тут же обесценил, радость не успевает прийти;
- приписываешь успех везению, команде, обстоятельствам, кому угодно, кроме себя;
- перепроверяешь и переделываешь, потому что «недостаточно»;
- боишься заметности: чем больше видно, тем выше риск разоблачения;
- пробовал психологов и коучей, на время помогало, потом возвращалось.

Узнаёшь? Это не скромность и не «синдром отличника». Это один код, который крутит тебя по кругу: достигни — обесцень — беги дальше.

Тебе сто раз говорили «ты молодец, ты достоин». Может, ты и сам повторял аффирмации перед зеркалом. И… ничего! Потому что мозг реагирует не на слова, а на опыт. Убеждение «я достаточно хорош» отскакивает, если за ним нет прожитого опыта, на который можно опереться. Логика говорит «ты справился», а лимбика помнит другое и верит ей.

Этот код не лечится уговорами. Его меняет новый опыт, прожитый на уровне нервной системы, а не понятый умом. Именно поэтому здесь так хорошо работает клинический гипноз: он создаёт опыт безопасности и «достаточности» без реального события, и мозгу становится на что опереться. Тогда успех можно наконец присвоить и остановиться в нём без страха.

Это и есть твоя точка работы. Дальше покажу, с чего начать именно с твоим кодом.`,
  others_goals: `Твой нейрокод: «Чужие цели» — самый незаметный из трёх, потому что придраться вроде бы не к чему. Ты много работаешь, результаты есть, со стороны всё успешно, а внутри глухая пустота и вопрос «зачем всё это». Разберём, откуда он.

Ты достигаешь целей, но они не греют. Дошёл до вершины и вместо радости «и что дальше?». Будто бежишь чужой марафон, ноги несут, а внутри ничего не зажигается. Это не усталость и не неблагодарность, просто часть твоих целей — не твои.

Зеркальные нейроны работают с рождения: мы буквально копируем тех, кого наблюдали в детстве, их цели, страхи, определение «успешной жизни». Что считать достижением, к чему стремиться, как должно выглядеть «правильно» — всё это ты впитал раньше, чем смог выбирать сам. И вырос, двигаясь к тому, что одобрили бы родители, общество, окружение, а не к тому, что откликается именно тебе.

Когда цель чужая, нервная система это чувствует и саботирует. Не со зла, ей незачем вкладывать ресурс в то, что для тебя не настоящее. Отсюда странная картина: на мелочах ты собран, а к по-настоящему важному не можешь подступиться неделями. Тело будто упирается, это и есть честный сигнал, что цель не твоя.

Как это выглядит в жизни:
- выгорание без явной причины, вроде всё есть, а внутри пусто;
- прокрастинация в ключевом, оно чужое, поэтому не идёт;
- достигаешь целей, а удовлетворения нет, сразу ставишь новую;
- ощущение, что движешься не туда, но остановиться и пересмотреть страшно;
- завидуешь не деньгам других, а тому, что у них «горят глаза»;
- пробовал разные ниши, подходы, наставников, что-то менялось, а огонь так и не появился.

Узнаёшь? Это не кризис и не «зажрался», это код, который ведёт тебя по чужой карте.

Ты можешь поставить ещё десять целей, сходить на ещё один интенсив, переписать видение на год и снова потухнуть через месяц. Потому что проблема не в количестве целей, а в их источнике. Пока цель чужая, никакая мотивация её не оживит, нервная система не даёт энергию на то, что не считает своим.

Здесь работа в два шага. Сначала отделить свои цели от родительских, социальных и «правильных»: понять, что из этого действительно твоё, а что ты несёшь по привычке. Потом дать нервной системе разрешение двигаться к своему, без чувства, что предаёшь чужие ожидания. Когда цель становится по-настоящему твоей, прокрастинация исчезает сама, не нужно себя заставлять.

Это и есть твоя точка работы. Дальше покажу, с чего начать именно с твоим кодом.`,
};

export const RESULT_NEXT_BUTTON_LABEL = "Какой шаг мне делать дальше?";

export const OFFER_INTRO_TEXTS: Record<string, string> = {
  survival: `Теперь главное, что с этим делать.

Ты увидел свой код. Это уже много, большинство живёт с «Выживанием» всю жизнь и даже не догадывается, списывая всё на невезение. Но осознание само по себе код не выключает…

Ты понимаешь механизм лишь головой. А команда «вернись к знакомой цифре» приходит не из головы, а из лимбики. Понимание живёт в коре, код живёт глубже. Сколько ни объясняй нервной системе, что рост безопасен, словами до неё не достучаться, ей нужен прожитый опыт безопасности.

Пока этот сигнал не пройдёт на уровне тела, всё будет повторяться: скачок — откат, рост — «случайность», которая забирает часть назад. Не потому что ты что-то делаешь не так, а потому что компенсаторный механизм всё ещё включён.

Дать нервной системе этот опыт можно тремя путями, разной глубины. Выбирай, как хочешь начать?`,
  impostor: `Теперь главное, что с этим делать.

Ты увидел свой код. И, скорее всего, узнал себя слишком точно. Но узнать — не значит присвоить. «Самозванец» и тут не даст остановиться, сразу шепнёт «ну и что, это и так понятно».

Вот почему просто понять мало. Голова уже знает, что ты справился. А лимбика помнит другое и при каждом успехе включает обесцень и беги. Между «знаю умом» и «чувствую внутри» пропасть, и аффирмации её не закрывают, мозгу нужно не убеждение, а новый прожитый опыт. Опыт, в котором ты достаточно без доказательств.

Пока этого опыта нет, цикл продолжится: достижение — обесценивание — гонка к следующему, и так без финиша. Цена этому — ты никогда не оказываешься в своей победе.

Создать этот новый опыт можно тремя путями разной глубины. Выбирай, как хочешь начать?`,
  others_goals: `Теперь главное, что с этим делать.

Ты увидел свой код. И, возможно, впервые назвал словами то, что давно ощущал фоном: бежишь, но не туда. Это важный момент, но одного осознания мало, чтобы карта сменилась.

Понять, что цель чужая это работа головы. А энергию на цель (или на саботаж) даёт нервная система, и она пока действует по старой, впитанной программе: тянет к «правильному», глушит своё. Поэтому просто решить хотеть другого не выходит, пока не сделана внутренняя работа, нервная система так и будет забирать силы на важное и оставлять пустоту на финише.

Здесь нужно два шага: сначала честно отделить свои цели от чужих, потом дать нервной системе разрешение двигаться к своим без чувства, что предаёшь чьи-то ожидания.

Начать эту работу можно тремя путями разной глубины. Выбирай, как хочешь начать?`,
};

export const OFFER_EMPTY_TEXT =
  "Ты уже забрал всё, что здесь есть — книгу, практикум и консультацию. Спасибо за доверие!";

export const RETAKE_BUTTON_LABEL = "Пройти тест заново";

export const PRODUCT_LABELS: Record<string, string> = {
  book: "Книга «Целеполагание»",
  practicum: "Практикум «Найди свой код»",
  consult: "Бесплатная консультация с Марией",
};
```

- [ ] **Step 2: Расширить `frontend/src/api/client.ts`**

Замени содержимое файла целиком:

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

export interface AnswerOut {
  question_no: number;
  score: number;
}

export interface FunnelState {
  checkpoint: string;
  consent_given: boolean;
  result_type: string | null;
  answers: AnswerOut[];
  available_products: string[] | null;
  book_price_rub: number;
  practicum_price_rub: number;
}

function postFunnel(path: string, body?: unknown): Promise<FunnelState> {
  return request<FunnelState>(`/api/funnel/${path}`, {
    method: "POST",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
}

export const api = {
  ping: () => request<{ tg_id: number }>("/api/ping"),
  getFunnelState: () => request<FunnelState>("/api/funnel/state"),
  completeWelcome: () => postFunnel("welcome/complete"),
  acceptConsent: () => postFunnel("consent"),
  submitAnswer: (questionNo: number, score: number) =>
    postFunnel("answers", { question_no: questionNo, score }),
  showOffer: () => postFunnel("offer/show"),
  retake: () => postFunnel("retake"),
};
```

- [ ] **Step 3: Проверить, что фронтенд по-прежнему собирается**

Run: `cd frontend && npx tsc --noEmit`
Expected: без ошибок (новый код синтаксически и типово корректен; `App.tsx` пока использует только `api.ping`, который не тронут).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/content/texts.ts frontend/src/api/client.ts
git commit -m "feat: копирайт ТЗ и funnel-методы API-клиента для Mini App"
```

---

### Task 5: Frontend — `WelcomeCarousel.tsx` и `Consent.tsx`

**Files:**
- Create: `frontend/src/screens/WelcomeCarousel.tsx`
- Create: `frontend/src/screens/Consent.tsx`

**Interfaces:**
- Consumes: `WELCOME_STEPS`, `CONSENT_TEXT`, `CONSENT_BUTTON_LABEL` (Task 4, `content/texts.ts`).
- Produces: `WelcomeCarousel({ onComplete: () => void })`, `Consent({ onAccept: () => void })` — оба используются в Task 9 (`App.tsx`).

- [ ] **Step 1: Создать `frontend/src/screens/WelcomeCarousel.tsx`**

```tsx
import { useState } from "react";
import { WELCOME_STEPS } from "@/content/texts";

interface Props {
  onComplete: () => void;
}

export default function WelcomeCarousel({ onComplete }: Props) {
  const [step, setStep] = useState(0);
  const current = WELCOME_STEPS[step];

  function handleNext() {
    if (step < WELCOME_STEPS.length - 1) {
      setStep(step + 1);
    } else {
      onComplete();
    }
  }

  return (
    <div className="flex min-h-screen flex-col justify-between bg-navy p-6 text-white">
      <div className="flex-1 overflow-y-auto whitespace-pre-line text-[15px] leading-relaxed">
        {current.text}
      </div>
      <button
        onClick={handleNext}
        className="mt-6 w-full rounded-xl bg-gold py-3 text-center font-semibold text-navy"
      >
        {current.buttonLabel}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Создать `frontend/src/screens/Consent.tsx`**

```tsx
import { CONSENT_BUTTON_LABEL, CONSENT_TEXT } from "@/content/texts";

interface Props {
  onAccept: () => void;
}

export default function Consent({ onAccept }: Props) {
  return (
    <div className="flex min-h-screen flex-col justify-between bg-navy p-6 text-white">
      <div className="flex-1 overflow-y-auto whitespace-pre-line text-[15px] leading-relaxed">
        {CONSENT_TEXT}
      </div>
      <button
        onClick={onAccept}
        className="mt-6 w-full rounded-xl bg-gold py-3 text-center font-semibold text-navy"
      >
        {CONSENT_BUTTON_LABEL}
      </button>
    </div>
  );
}
```

- [ ] **Step 3: Проверить сборку**

Run: `cd frontend && npx tsc --noEmit`
Expected: без ошибок.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/screens/WelcomeCarousel.tsx frontend/src/screens/Consent.tsx
git commit -m "feat: экраны WelcomeCarousel и Consent для Mini App"
```

---

### Task 6: Frontend — `Quiz.tsx` (кольцо-прогресс + pill-кнопки, вариант B)

**Files:**
- Create: `frontend/src/screens/Quiz.tsx`

**Interfaces:**
- Consumes: `QUESTIONS` (Task 4, `content/texts.ts`).
- Produces: `Quiz({ questionNo: number, onAnswer: (score: number) => void })` — используется в Task 9.

- [ ] **Step 1: Создать `frontend/src/screens/Quiz.tsx`**

```tsx
import { QUESTIONS } from "@/content/texts";

interface Props {
  questionNo: number;
  onAnswer: (score: number) => void;
}

const OPTIONS: { label: string; score: number }[] = [
  { label: "Да", score: 2 },
  { label: "Иногда", score: 1 },
  { label: "Нет", score: 0 },
];

export default function Quiz({ questionNo, onAnswer }: Props) {
  const progressDeg = ((questionNo - 1) / 7) * 360;
  const ringStyle = {
    background: `conic-gradient(#e8c96a ${progressDeg}deg, rgba(255,255,255,0.15) ${progressDeg}deg 360deg)`,
  };

  return (
    <div className="flex min-h-screen flex-col items-center bg-navy p-6 text-white">
      <div className="mt-4 flex h-16 w-16 items-center justify-center rounded-full" style={ringStyle}>
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-navy text-xs font-bold text-gold">
          {questionNo}/7
        </div>
      </div>
      <div className="flex flex-1 items-center px-2 text-center text-lg font-semibold leading-snug">
        {QUESTIONS[questionNo]}
      </div>
      <div className="mb-4 flex w-full gap-2">
        {OPTIONS.map((option) => (
          <button
            key={option.label}
            onClick={() => onAnswer(option.score)}
            className="flex-1 rounded-full border border-gold/40 bg-gold/10 py-3 text-sm font-semibold text-gold"
          >
            {option.label}
          </button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Проверить сборку**

Run: `cd frontend && npx tsc --noEmit`
Expected: без ошибок.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/screens/Quiz.tsx
git commit -m "feat: экран Quiz (кольцо-прогресс + pill-кнопки) для Mini App"
```

---

### Task 7: Frontend — `Result.tsx`

**Files:**
- Create: `frontend/src/screens/Result.tsx`

**Interfaces:**
- Consumes: `RESULT_LABELS`, `RESULT_TEXTS`, `RESULT_NEXT_BUTTON_LABEL` (Task 4).
- Produces: `Result({ resultType: string, onNext: () => void })` — используется в Task 9.

- [ ] **Step 1: Создать `frontend/src/screens/Result.tsx`**

```tsx
import { RESULT_LABELS, RESULT_NEXT_BUTTON_LABEL, RESULT_TEXTS } from "@/content/texts";

interface Props {
  resultType: string;
  onNext: () => void;
}

export default function Result({ resultType, onNext }: Props) {
  return (
    <div className="flex min-h-screen flex-col bg-navy p-6 text-white">
      <div className="mb-4 self-center rounded-full border border-gold px-4 py-1 text-sm font-semibold text-gold">
        {RESULT_LABELS[resultType]}
      </div>
      <div className="flex-1 overflow-y-auto whitespace-pre-line text-[15px] leading-relaxed">
        {RESULT_TEXTS[resultType]}
      </div>
      <button
        onClick={onNext}
        className="mt-6 w-full rounded-xl bg-gold py-3 text-center font-semibold text-navy"
      >
        {RESULT_NEXT_BUTTON_LABEL}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Проверить сборку**

Run: `cd frontend && npx tsc --noEmit`
Expected: без ошибок.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/screens/Result.tsx
git commit -m "feat: экран Result для Mini App"
```

---

### Task 8: Frontend — `Offer.tsx`

**Files:**
- Create: `frontend/src/screens/Offer.tsx`

**Interfaces:**
- Consumes: `OFFER_INTRO_TEXTS`, `OFFER_EMPTY_TEXT`, `PRODUCT_LABELS`, `RETAKE_BUTTON_LABEL` (Task 4), `FunnelState` (Task 4, `api/client.ts`).
- Produces: `Offer({ state: FunnelState, onRetake: () => void })` — используется в Task 9. Карточки продуктов — без обработчика клика (заглушка под подпроект 2b, см. design spec).

- [ ] **Step 1: Создать `frontend/src/screens/Offer.tsx`**

```tsx
import type { FunnelState } from "@/api/client";
import { OFFER_EMPTY_TEXT, OFFER_INTRO_TEXTS, PRODUCT_LABELS, RETAKE_BUTTON_LABEL } from "@/content/texts";

interface Props {
  state: FunnelState;
  onRetake: () => void;
}

function priceLabel(product: string, state: FunnelState): string {
  if (product === "book") return `${PRODUCT_LABELS.book} — ${state.book_price_rub} ₽`;
  if (product === "practicum") return `${PRODUCT_LABELS.practicum} — ${state.practicum_price_rub} ₽`;
  return PRODUCT_LABELS.consult;
}

export default function Offer({ state, onRetake }: Props) {
  const available = state.available_products ?? [];
  const resultType = state.result_type;

  return (
    <div className="flex min-h-screen flex-col bg-navy p-6 text-white">
      <div className="mb-4 whitespace-pre-line text-[15px] leading-relaxed">
        {available.length > 0 && resultType !== null ? OFFER_INTRO_TEXTS[resultType] : OFFER_EMPTY_TEXT}
      </div>
      <div className="flex flex-col gap-3">
        {available.map((product) => (
          <div
            key={product}
            className="rounded-xl border border-gold/40 bg-gold/10 px-4 py-3 text-sm font-semibold text-gold"
          >
            {priceLabel(product, state)}
          </div>
        ))}
      </div>
      <button onClick={onRetake} className="mt-auto pt-6 text-center text-sm text-gold/70 underline">
        {RETAKE_BUTTON_LABEL}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Проверить сборку**

Run: `cd frontend && npx tsc --noEmit`
Expected: без ошибок.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/screens/Offer.tsx
git commit -m "feat: экран Offer (карточки продуктов, без обработчика — 2b подключит покупку)"
```

---

### Task 9: Frontend — `resolveScreen`, `FunnelGate` (`App.tsx`), hash-роутинг

**Files:**
- Create: `frontend/src/funnel/resolveScreen.ts`
- Test: `frontend/src/funnel/resolveScreen.test.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/main.tsx`

**Interfaces:**
- Consumes: `api.getFunnelState/completeWelcome/acceptConsent/submitAnswer/showOffer/retake`, `FunnelState`, `ApiError` (Task 4); `WelcomeCarousel`, `Consent`, `Quiz`, `Result`, `Offer` (Task 5–8).
- Produces: `resolveScreen(checkpoint: string, resultType: string | null): "welcome" | "consent" | "quiz" | "result" | "offer"` — финальная функция плана, конец цепочки задач.

Важное уточнение к design spec: в чате `/start` при существующем `result_type` показывает retake-подсказку **независимо от текущего checkpoint** (пользователь мог уйти в любую точку воронки — Блок 6/7/8 — эти чекпоинты вне скоупа 2a). Прямое отображение `checkpoint -> screen` для пяти известных 2a-чекпоинтов плюс дефолт «welcome» для всего остального сломало бы это: пользователь с готовым результатом, чей checkpoint сейчас, например, `practicum_viewed` (2b, ещё не построен), увидел бы Welcome-карусель заново вместо Offer. Поэтому `resolveScreen` принимает `resultType` вторым параметром и для любого неизвестного 2a-чекпоинта возвращает `"offer"`, если результат уже есть, и только иначе — `"welcome"`.

- [ ] **Step 1: Написать падающий тест**

Создай `frontend/src/funnel/resolveScreen.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { resolveScreen } from "./resolveScreen";

describe("resolveScreen", () => {
  it("maps awaiting_consent to consent", () => {
    expect(resolveScreen("awaiting_consent", null)).toBe("consent");
  });

  it("maps in_test to quiz", () => {
    expect(resolveScreen("in_test", null)).toBe("quiz");
  });

  it("maps result_shown to result", () => {
    expect(resolveScreen("result_shown", "survival")).toBe("result");
  });

  it("maps offer_shown to offer", () => {
    expect(resolveScreen("offer_shown", "survival")).toBe("offer");
  });

  it("defaults unknown checkpoint without result to welcome", () => {
    expect(resolveScreen("new", null)).toBe("welcome");
  });

  it("falls back to offer for out-of-2a-scope checkpoints when result already exists", () => {
    // practicum_viewed/consult_viewed/book_viewed/idle принадлежат подпроекту 2b —
    // у 2a для них нет экрана; если результат уже есть, Offer самодостаточен.
    expect(resolveScreen("practicum_viewed", "impostor")).toBe("offer");
  });
});
```

- [ ] **Step 2: Запустить тест, убедиться что падает**

Run: `cd frontend && npx vitest run src/funnel/resolveScreen.test.ts`
Expected: FAIL — `Cannot find module './resolveScreen'`.

- [ ] **Step 3: Создать `frontend/src/funnel/resolveScreen.ts`**

```typescript
export type ScreenId = "welcome" | "consent" | "quiz" | "result" | "offer";

export function resolveScreen(checkpoint: string, resultType: string | null): ScreenId {
  if (checkpoint === "awaiting_consent") return "consent";
  if (checkpoint === "in_test") return "quiz";
  if (checkpoint === "result_shown") return "result";
  if (checkpoint === "offer_shown") return "offer";
  return resultType !== null ? "offer" : "welcome";
}
```

- [ ] **Step 4: Запустить тест, убедиться что проходит**

Run: `cd frontend && npx vitest run src/funnel/resolveScreen.test.ts`
Expected: 6 passed.

- [ ] **Step 5: Переписать `frontend/src/App.tsx` на `FunnelGate`**

Замени содержимое файла целиком:

```tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError, type FunnelState } from "./api/client";
import { resolveScreen } from "./funnel/resolveScreen";
import Consent from "./screens/Consent";
import Offer from "./screens/Offer";
import Quiz from "./screens/Quiz";
import Result from "./screens/Result";
import WelcomeCarousel from "./screens/WelcomeCarousel";

function errorMessage(err: unknown): string {
  return err instanceof ApiError ? err.message : "Ошибка сети";
}

export default function App() {
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
      return <Offer state={state} onRetake={() => runAction(api.retake)} />;
  }
}
```

- [ ] **Step 6: Обернуть `App` в `HashRouter` в `frontend/src/main.tsx`**

Замени содержимое файла целиком:

```tsx
import "@telegram-apps/telegram-ui/dist/styles.css";
import { AppRoot } from "@telegram-apps/telegram-ui";
import React from "react";
import ReactDOM from "react-dom/client";
import { HashRouter } from "react-router-dom";
import App from "./App";
import { initTelegram } from "./lib/telegram";
import "./styles.css";

initTelegram();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <HashRouter>
      <AppRoot appearance="dark" platform="base">
        <App />
      </AppRoot>
    </HashRouter>
  </React.StrictMode>,
);
```

- [ ] **Step 7: Проверить сборку и полный набор фронтенд-тестов**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: без ошибок компиляции; все vitest-тесты (включая `resolveScreen.test.ts`) PASS.

- [ ] **Step 8: Собрать production-бандл, чтобы убедиться, что `vite build` не ломается**

Run: `cd frontend && npm run build`
Expected: сборка завершается без ошибок, `frontend/dist/` обновлён.

- [ ] **Step 9: Прогнать весь backend-набор ещё раз (регресс после Task 1-3 изменений в auth)**

Run: `pytest -v`
Expected: все тесты PASS.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/funnel/resolveScreen.ts frontend/src/funnel/resolveScreen.test.ts frontend/src/App.tsx frontend/src/main.tsx
git commit -m "feat: FunnelGate — рендер экрана по checkpoint, hash-роутинг синхронизирован с состоянием"
```

- [ ] **Step 11: Ручная проверка в реальном Mini App**

Открыть Mini App через Menu Button в Telegram (после деплоя):
1. Свежий tg_id → должен показать Welcome шаг 1/3 → «Далее» → шаг 2/3 → «Далее» → шаг 3/3 → «Продолжить» → экран согласия.
2. Принять согласие → вопрос 1/7 (кольцо-прогресс, три золотые pill-кнопки) → ответить на все 7 → экран результата (соответствует набранным очкам, свериться по `services/scoring.py::compute_result`) → «Какой шаг мне делать дальше?» → экран Offer с тремя карточками продуктов.
3. Закрыть Mini App на середине теста (после 3-4 вопроса) → открыть заново → должен продолжиться с того же вопроса (checkpoint сохранился в БД).
4. На экране Offer нажать «Пройти тест заново» → должен вернуться на вопрос 1/7 с очищенными ответами.
5. Регресс: пройти тот же путь через чат (`/start` → инлайн-кнопки) → должен работать без изменений.

---

## Self-Review

**1. Spec coverage:** Все экраны спеки (Welcome/Consent/Quiz/Result/Offer) — Tasks 5-9. Все 5 backend-действий (`welcome/complete`, `consent`, `answers`, `offer/show`, `retake`) плюс `GET /state` — Tasks 1-3. `touch_activity` в auth — Task 1. Динамические цены вместо хардкода — Task 4 (`book_price_rub`/`practicum_price_rub` в `FunnelStateOut`, обнаружено при проработке плана как необходимое уточнение по сравнению с исходной формулировкой спеки — цены редактируются через уже существующий `/settings`, хардкод в `texts.ts` был бы багом с первого дня). Hash-роутинг, синхронизированный с состоянием — Task 9. Отступление №1 (retake без диалога, Offer как самодостаточный fallback) — уточнено и реализовано в `resolveScreen` (Task 9) с явным вторым параметром `resultType`, точнее исходной спеки (спека не уточняла поведение для чекпоинтов вне 2a-скоупа — пробел закрыт). Отступление №2 (карточки без обработчика) — Task 8. Отступление №3 (чат не трогается) — ни один backend-таск не модифицирует `handlers/`.

**2. Placeholder scan:** Нет `TBD`/`TODO`, весь код полный и исполняемый, все команды с ожидаемым результатом.

**3. Type consistency:** `FunnelStateOut` (Python, Task 1) и `FunnelState` (TypeScript, Task 4) — поля совпадают 1-в-1 (`checkpoint`, `consent_given`, `result_type`, `answers`, `available_products`, `book_price_rub`, `practicum_price_rub`). `resolveScreen(checkpoint: string, resultType: string | null)` — сигнатура одинакова в тесте (Step 1) и реализации (Step 3) Task 9. Компонентные пропсы (`onComplete`, `onAccept`, `onAnswer`, `onNext`, `onRetake`) объявлены в Tasks 5-8 и используются с теми же именами в Task 9's `App.tsx`.

Plan complete and saved to `docs/superpowers/plans/2026-07-03-miniapp-funnel-quiz.md`. Два варианта выполнения:

**1. Subagent-Driven (рекомендую)** — я дispatch-у свежего субагента на каждую задачу, ревью между задачами, быстрая итерация

**2. Inline Execution** — выполняю задачи в этой сессии через executing-plans, батчами с чекпоинтами

Какой вариант?
