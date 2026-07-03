# Mini App — детали продукта, оплата, консультация, умное меню (подпроект 2b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Достроить воронку Mini App до полного цикла: карточки на экране Offer становятся кликабельными, ведут на детали книги/практикума/консультации, платные продукты открывают оплату ЮKassa через `Telegram.WebApp.openLink`, консультация собирает email, а после любого действия пользователь возвращается на умное меню M9.

**Architecture:** 4 новых `POST`-эндпоинта в `api/routers/funnel.py`, зеркалящих существующие aiogram-хендлеры (`handlers/menu.py`, `practicum.py`, `book.py`, `consult.py`) один-в-один. Доставка контента после оплаты не меняется — она уже происходит асинхронно через `payments/webhook.py` → `payments/delivery.py`, независимо от экрана Mini App. Frontend получает 3 новых экрана + доработку `Offer.tsx`, все по тому же принципу: backend владеет `checkpoint`, экраны только рендерят то, что он говорит.

**Tech Stack:** FastAPI, aiogram (переиспользуется `payments/yookassa_client.py`, `exports/notifier.py`), React + TypeScript, `Telegram.WebApp.openLink`.

## Global Constraints

- Никаких изменений в `db/models.py`.
- Никакой доставки контента заново — `payments/delivery.py::deliver()` уже отправляет всё нужное через чат-сообщения после вебхука, этот подпроект её не трогает.
- `product`-путь принимает только `"book"` и `"practicum"` — консультация не покупка, у неё отдельные эндпоинты (`consult/book`, `consult/email`).
- Email-регэксп — общая функция `services/validation.py::is_valid_email`, используется и чатом, и API (не две копии одного правила).
- Цены в кнопках оплаты — только динамически, из `state.book_price_rub`/`practicum_price_rub` (не хардкод). Маркетинговый текст M6.2/M8.2 переносится из ТЗ как есть, включая упоминания цены внутри абзацев — это уже так в существующем чат-боте (`texts/messages.py`), это предсуществующая (не вносимая этим планом) неточность, не в скоупе задачи.
- `payments/`-пакет не имеет автотестов (сетевые вызовы к ЮKassa) — эндпоинт `product/{product}/buy` тестируется через `monkeypatch` на `create_payment`, не через реальную сеть.

---

### Task 1: Общий email-валидатор

**Files:**
- Create: `services/validation.py`
- Modify: `handlers/consult.py`
- Test: `tests/test_validation.py`

**Interfaces:**
- Produces: `is_valid_email(email: str) -> bool` — используется в Task 3 (`api/routers/funnel.py`).

- [ ] **Step 1: Написать падающий тест**

Создай `tests/test_validation.py`:

```python
from services.validation import is_valid_email


def test_valid_email_accepted():
    assert is_valid_email("name@example.com") is True


def test_missing_at_rejected():
    assert is_valid_email("nameexample.com") is False


def test_missing_domain_dot_rejected():
    assert is_valid_email("name@examplecom") is False


def test_spaces_rejected():
    assert is_valid_email("name @example.com") is False


def test_empty_string_rejected():
    assert is_valid_email("") is False
```

- [ ] **Step 2: Запустить, убедиться что падает**

Run: `pytest tests/test_validation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'services.validation'`.

- [ ] **Step 3: Создать `services/validation.py`**

```python
"""Валидация email — переиспользуется чатом (handlers/consult.py) и Mini App API
(api/routers/funnel.py), чтобы правило не могло разъехаться между интерфейсами."""
from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email))
```

- [ ] **Step 4: Запустить, убедиться что проходит**

Run: `pytest tests/test_validation.py -v`
Expected: 5 passed.

- [ ] **Step 5: Убрать дублирующий регэксп из `handlers/consult.py`**

В `handlers/consult.py` замени:

```python
import logging
import re

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from config import Config
from db import crud
from exports.notifier import notify_lead
from keyboards.inline import after_product_kb
from services import checkpoints
from services.catalog import CONSULT, get_available_products
from texts.messages import TEXTS

logger = logging.getLogger(__name__)

router = Router()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
```

на:

```python
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from config import Config
from db import crud
from exports.notifier import notify_lead
from keyboards.inline import after_product_kb
from services import checkpoints
from services.catalog import CONSULT, get_available_products
from services.validation import is_valid_email
from texts.messages import TEXTS

logger = logging.getLogger(__name__)

router = Router()
```

И замени строку:

```python
    if not _EMAIL_RE.match(email):
```

на:

```python
    if not is_valid_email(email):
```

- [ ] **Step 6: Проверить импорт и прогнать весь набор (регресс)**

Run: `python -c "import handlers.consult" && pytest -v`
Expected: импорт без ошибок; все тесты проекта PASS (58 — 53 предыдущих + 5 новых).

- [ ] **Step 7: Commit**

```bash
git add services/validation.py tests/test_validation.py handlers/consult.py
git commit -m "refactor: общий is_valid_email вместо дублирующего регэкспа в handlers/consult.py"
```

---

### Task 2: Backend — детали и покупка продукта

**Files:**
- Modify: `api/routers/funnel.py`
- Test: `tests/test_funnel_api.py`

**Interfaces:**
- Consumes: `db.crud.set_checkpoint`, `db.crud.create_purchase(tg_id, product, amount_rub) -> Purchase`, `db.crud.attach_yk_payment_id(purchase_id, yk_payment_id) -> None`, `services.catalog.get_available_products`, `services.checkpoints.BOOK_VIEWED`/`PRACTICUM_VIEWED`, `services.settings.get_int`/`get_str`, `payments.yookassa_client.create_payment(*, shop_id, secret_key, amount_rub, description, idempotence_key, return_url, metadata) -> tuple[str, str]` (возвращает `(payment_id, confirmation_url)`).
- Produces: `POST /api/funnel/product/{product}/view` → `FunnelStateOut`; `POST /api/funnel/product/{product}/buy` → `PurchaseInitiatedOut { confirmation_url: str }`. Используются в Task 5/7 (frontend).

- [ ] **Step 1: Написать падающие тесты**

Добавь в конец `tests/test_funnel_api.py`:

```python
def test_view_product_sets_checkpoint_when_available():
    client, headers = _client(711)
    with client:
        client.post("/api/funnel/consent", headers=headers)
        for q, s in enumerate([2, 2, 0, 1, 0, 2, 1], start=1):
            client.post("/api/funnel/answers", headers=headers, json={"question_no": q, "score": s})
        response = client.post("/api/funnel/product/practicum/view", headers=headers)
    body = response.json()
    assert body["checkpoint"] == "practicum_viewed"


def test_view_invalid_product_is_rejected():
    client, headers = _client(712)
    with client:
        response = client.post("/api/funnel/product/consult/view", headers=headers)
    assert response.status_code == 422


def test_buy_product_creates_purchase_and_returns_confirmation_url(monkeypatch):
    async def fake_create_payment(**kwargs):
        return "yk-payment-123", "https://yookassa.ru/pay/yk-payment-123"

    monkeypatch.setattr("api.routers.funnel.create_payment", fake_create_payment)

    client, headers = _client(713)
    with client:
        client.post("/api/funnel/consent", headers=headers)
        for q, s in enumerate([2, 2, 0, 1, 0, 2, 1], start=1):
            client.post("/api/funnel/answers", headers=headers, json={"question_no": q, "score": s})
        response = client.post("/api/funnel/product/practicum/buy", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"confirmation_url": "https://yookassa.ru/pay/yk-payment-123"}
```

- [ ] **Step 2: Запустить, убедиться что падают**

Run: `pytest tests/test_funnel_api.py -v -k "view_product or buy_product or view_invalid"`
Expected: все три FAIL (404 — эндпоинтов ещё нет).

- [ ] **Step 3: Добавить эндпоинты в `api/routers/funnel.py`**

Добавь импорты в начало файла (после существующих):

```python
from typing import Literal

from fastapi import Request

from config import Config
from payments.yookassa_client import create_payment
```

(Итоговый блок импортов вверху файла: `from __future__ import annotations`, затем `from typing import Literal`, затем `from fastapi import APIRouter, Depends, Request`, `from pydantic import BaseModel`, `from api.deps import current_client`, `from config import Config`, `from db import crud`, `from payments.yookassa_client import create_payment`, `from services import checkpoints, settings`, `from services.catalog import get_available_products`, `from services.scoring import compute_result`.)

Добавь модуль-константы и класс сразу после `class AnswerIn`:

```python
_PRODUCT_CHECKPOINT: dict[str, str] = {
    "book": checkpoints.BOOK_VIEWED,
    "practicum": checkpoints.PRACTICUM_VIEWED,
}
_PRODUCT_LABELS: dict[str, str] = {
    "book": "Книга «Целеполагание»",
    "practicum": "Практикум «Найди свой код»",
}


class PurchaseInitiatedOut(BaseModel):
    confirmation_url: str
```

Добавь эндпоинты в конец файла:

```python
@router.post("/product/{product}/view")
async def view_product(
    product: Literal["book", "practicum"], tg_id: int = Depends(current_client),
) -> FunnelStateOut:
    available = await get_available_products(tg_id)
    if product in available:
        await crud.set_checkpoint(tg_id, _PRODUCT_CHECKPOINT[product])
    return await _build_state(tg_id)


@router.post("/product/{product}/buy")
async def buy_product(
    product: Literal["book", "practicum"], request: Request,
    tg_id: int = Depends(current_client),
) -> PurchaseInitiatedOut:
    config: Config = request.app.state.config
    amount = await settings.get_int(f"{product}_price_rub")
    purchase = await crud.create_purchase(tg_id, product, amount)
    payment_id, confirmation_url = await create_payment(
        shop_id=await settings.get_str("yookassa_shop_id"), secret_key=config.yookassa_secret_key,
        amount_rub=amount, description=_PRODUCT_LABELS[product],
        idempotence_key=str(purchase.id), return_url=config.webhook_base_url,
        metadata={"tg_id": tg_id, "product": product, "purchase_id": purchase.id},
    )
    await crud.attach_yk_payment_id(purchase.id, payment_id)
    return PurchaseInitiatedOut(confirmation_url=confirmation_url)
```

- [ ] **Step 4: Запустить тесты**

Run: `pytest tests/test_funnel_api.py -v`
Expected: все тесты файла PASS, включая три новых.

- [ ] **Step 5: Commit**

```bash
git add api/routers/funnel.py tests/test_funnel_api.py
git commit -m "feat: POST /api/funnel/product/{product}/view и /buy"
```

---

### Task 3: Backend — консультация

**Files:**
- Modify: `api/routers/funnel.py`
- Test: `tests/test_funnel_api.py`

**Interfaces:**
- Consumes: `services.validation.is_valid_email` (Task 1), `db.crud.create_lead(tg_id, email) -> Lead | None`, `exports.notifier.notify_lead(bot, config, lead) -> None`, `services.checkpoints.AWAITING_EMAIL`/`IDLE`.
- Produces: `POST /api/funnel/consult/book` → `FunnelStateOut`; `POST /api/funnel/consult/email` `{email: str}` → `FunnelStateOut` (или `422` при невалидном email). Используются в Task 6/7 (frontend).

- [ ] **Step 1: Написать падающие тесты**

Добавь в конец `tests/test_funnel_api.py`:

```python
def test_consult_book_sets_awaiting_email():
    client, headers = _client(714)
    with client:
        response = client.post("/api/funnel/consult/book", headers=headers)
    assert response.json()["checkpoint"] == "awaiting_email"


def test_consult_email_invalid_is_rejected():
    client, headers = _client(715)
    with client:
        client.post("/api/funnel/consult/book", headers=headers)
        response = client.post(
            "/api/funnel/consult/email", headers=headers, json={"email": "not-an-email"},
        )
    assert response.status_code == 422


def test_consult_email_valid_creates_lead_and_sets_idle():
    client, headers = _client(716)
    with client:
        client.post("/api/funnel/consult/book", headers=headers)
        response = client.post(
            "/api/funnel/consult/email", headers=headers, json={"email": "test@example.com"},
        )
    assert response.status_code == 200
    assert response.json()["checkpoint"] == "idle"
```

(Эти тесты безопасны с `bot=object()`-заглушкой из `_sqlite_lifecycle`: `notify_lead` первым делом читает `owner_chat_id` через `settings.get_effective_owner_chat_id`, а в тестовом `Config` он `None` и в БД не задан — функция вернётся до первого обращения к `bot`.)

- [ ] **Step 2: Запустить, убедиться что падают**

Run: `pytest tests/test_funnel_api.py -v -k consult`
Expected: все три FAIL (404).

- [ ] **Step 3: Добавить импорты и эндпоинты**

Добавь импорты в начало `api/routers/funnel.py` (после существующих):

```python
import logging

from aiogram import Bot
from fastapi import HTTPException

from exports.notifier import notify_lead
from services.validation import is_valid_email
```

Добавь логгер сразу после блока импортов, перед `router = APIRouter(...)`:

```python
logger = logging.getLogger(__name__)
```

Добавь класс рядом с `PurchaseInitiatedOut`:

```python
class EmailIn(BaseModel):
    email: str
```

Добавь эндпоинты в конец файла:

```python
@router.post("/consult/book")
async def book_consult(tg_id: int = Depends(current_client)) -> FunnelStateOut:
    await crud.set_checkpoint(tg_id, checkpoints.AWAITING_EMAIL)
    return await _build_state(tg_id)


@router.post("/consult/email")
async def submit_consult_email(
    body: EmailIn, request: Request, tg_id: int = Depends(current_client),
) -> FunnelStateOut:
    if not is_valid_email(body.email):
        raise HTTPException(status_code=422, detail="invalid_email")

    bot: Bot = request.app.state.bot
    config: Config = request.app.state.config
    lead = await crud.create_lead(tg_id, body.email)
    await crud.set_checkpoint(tg_id, checkpoints.IDLE)
    if lead is not None:
        try:
            await notify_lead(bot, config, lead)
        except Exception:  # noqa: BLE001 — не выгрузилось сейчас, ретрай подхватит scheduler
            logger.exception("Не удалось выгрузить лид user=%s", tg_id)
    return await _build_state(tg_id)
```

- [ ] **Step 4: Запустить тесты**

Run: `pytest tests/test_funnel_api.py -v`
Expected: все тесты файла PASS.

- [ ] **Step 5: Прогнать весь backend-набор (регресс)**

Run: `pytest -v`
Expected: все тесты проекта PASS.

- [ ] **Step 6: Commit**

```bash
git add api/routers/funnel.py tests/test_funnel_api.py
git commit -m "feat: POST /api/funnel/consult/book и /consult/email"
```

---

### Task 4: Frontend — копирайт, API-клиент, `openLink`

**Files:**
- Modify: `frontend/src/content/texts.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/lib/telegram.ts`

**Interfaces:**
- Produces: `PRODUCT_DETAIL_TEXTS: Record<"book"|"practicum", string>`, `BUY_BUTTON_LABEL: Record<"book"|"practicum", string>`, `CONSULT_INTRO_TEXT: string`, `CONSULT_BOOK_BUTTON_LABEL: string`, `CONSULT_EMAIL_PROMPT: string`, `CONSULT_EMAIL_INVALID: string`, `CONSULT_CONTINUE_BUTTON_LABEL: string`, `M7_2_TEXT: string`, `M9_TEXT: string` (все — `content/texts.ts`, используются в Task 5/6/7); `PurchaseInitiatedOut` (тип), `api.viewProduct(product)`, `api.buyProduct(product) -> Promise<PurchaseInitiatedOut>`, `api.bookConsult()`, `api.submitConsultEmail(email) -> Promise<FunnelState>` (все — `api/client.ts`, используются в Task 5/6/7); `openLink(url: string): void` (`lib/telegram.ts`, используется в Task 5).

- [ ] **Step 1: Добавить копирайт в `frontend/src/content/texts.ts`**

Добавь в конец файла:

```typescript
export const PRODUCT_DETAIL_TEXTS: Record<"book" | "practicum", string> = {
  practicum: `Окей. Только честно предупрежу об одной ловушке.

Сейчас ты знаешь свой код. Это ощущается как прорыв, вот оно, вот что мной управляло. Но я видела это сотни раз: проходит три-четыре дня, инсайт тускнеет, текучка засасывает, и всё возвращается на круги своя. Код остался на месте. Знание о нём ничего в нервной системе не сдвинуло.

Так теряется самый ценный момент, когда ты уже видишь причину и ещё готов с ней что-то сделать. Через неделю этой готовности не будет.

Практикум «Найди свой код» придуман ровно для этого окна, чтобы за несколько вечеров ты не просто понял, а сделал, превратил осознание в первое реальное движение. Пока горячо.

Это не лекция и не «мотивашка». Это пошаговая работа над твоей причиной в закрытом Telegram-канале, где собраны все материалы.

Что ты сделаешь за практикум:
- найдёшь свой главный ограничивающий паттерн и сформулируешь его одной фразой — конкретно, без «что-то внутри мешает»;
- поймёшь, где он живёт: деньги, команда, состояние или цели;
- проверишь, твой это код или ты несёшь чужой, родительский (и да, чаще всего он чужой);
- через упражнение «Три провала» увидишь, как именно код управлял твоими решениями годами;
- получишь три конкретных первых шага, которые начинают расшатывать программу уже на этой неделе.

Что внутри:
- короткие видеоуроки, по делу, без воды;
- рабочая тетрадь с заданиями;
- мои голосовые и кружки с разборами и пользой;
- инструкция, что и в каком порядке делать;
- возможность задать мне вопрос.

Проходишь когда удобно, в своём темпе, без групп и эфиров. Купил один раз, остаёшься в канале навсегда и возвращаешься, когда захочешь.

И теперь честно про цену. Личная работа со мной, это другой бюджет. Годы у психологов и коучей — это десятки тысяч, и часто без результата. Практикум стоит 2990 ₽, меньше, чем один сеанс у психолога. Это сделано специально, чтобы цена не стала ещё одной причиной остаться там, где ты есть.

Доступ открывается сразу после оплаты, начать можно сегодня вечером.`,
  book: `Скажу честно, зачем она тебе.

Вспомни, сколько раз это уже было. Новый год, новый понедельник, новая точка «всё, с завтрашнего дня по-другому». Ты ставишь цель, внутри загорается, вот оно, в этот раз точно. Первые дни прёт, а потом, незаметно, всё гаснет. Появляются более срочные дела. Важное сдвигается на потом, потом ещё на потом, и через пару недель ты уже даже не вспоминаешь, к чему шёл. Цель тихо легла на ту же полку, где лежат все прошлые.

И ты делаешь привычный вывод: значит, я ленивый, не хватает дисциплины, соберись уже. Загоняешь себя обратно силой воли, и цикл повторяется по новой.

Я скажу то, что снимет с тебя этот груз: дело не в лени и не в слабом характере. Цель не доходит до результата всего по двум причинам.

Первая, она поставлена так, что внутри на неё просто нет энергии. Звучит красиво, правильно, но не зажигает по-настоящему, и тело отказывается её тянуть.

Вторая, самосаботаж. Ты подходишь к чему-то важному, и будто кто-то изнутри жмёт на тормоз: откладываешь, отвлекаешься, находишь тысячу других дел. Это защитный механизм, и пока он включён, никакая мотивация его не передавит.

Эта книга про то, как ставить цели, к которым тебя тянет идти само, без насилия. И как выключать саботаж, а не воевать с собой каждый день.

«Целеполагание» — не книга на почитать и вдохновиться. Через три дня от таких не остаётся ничего. Это рабочая книга: берёшь ручку, лист и идёшь по шагам. Делаешь и к концу что-то реально меняется в голове.

Вот через что я тебя проведу:

Найдёшь, чего хочешь на самом деле. Упражнение «100 желаний» вытаскивает наружу то, что годами было погребено под надо, положено и чужими ожиданиями. Ты увидишь, какие цели тебя по-настоящему зажигают, а какие ты тащил по привычке, и сразу перестанешь сливать на них силы.

Превратишь размытое «хочу больше» в конкретную цель. Я разложу, как ставить цель так, чтобы мозг воспринял её как реальную и достижимую, а не как абстрактную мечту, до которой «когда-нибудь». Конкретика вместо тумана, и цель перестаёт пугать.

Поймёшь, где именно тебя клинит. Разберём самосаботаж и прокрастинацию: почему они включаются особенно сильно на самом важном, и как их обойти без «возьми себя в руки», а через понимание механизма.

Построишь маршрут к цели. Техника «Линия времени» — это когда ты буквально прокладываешь путь от сегодняшнего дня до результата, видишь все этапы, расставляешь приоритеты и, главное, понимаешь, какой первый шаг сделать прямо сейчас.

Получишь то, чего нет в обычных книгах по целям. Техники самогипноза и самопрограммирования мой профильный инструмент. Они работают не на силе воли, которая заканчивается через неделю, а на уровне нервной системы, где и принимаются настоящие решения.

Ты выходишь из состояния опять поставил и не дошёл. У тебя на руках ясные, свои цели и конкретная карта к ним. И понимание, почему раньше не получалось, чтобы это больше не повторялось.

Это, по сути, мой метод, собранный так, чтобы ты мог начать сам, без сессий и созвонов, в своём темпе, уже сегодня вечером. Стоит 990 ₽. Доступ приходит сразу после оплаты, открыть и начать можно прямо сейчас.`,
};

export const BUY_BUTTON_LABEL: Record<"book" | "practicum", string> = {
  book: "Купить книгу",
  practicum: "Купить практикум",
};

export const CONSULT_INTRO_TEXT = `Хороший выбор!

Расшифровка, которую ты получил, точная, но общая, она описывает код, а не тебя. А у тебя своя история, свои цифры, свой конкретный затык. Один и тот же «код выживания» у двух людей разворачивается по-разному.

Чтобы попасть в точку, это нужно разобрать вживую. Для этого и есть первичная консультация, живой созвон со мной один на один.

Как проходит: 45 минут, видеосозвон, бесплатно.

Что мы сделаем за это время:
- разберём твою конкретную ситуацию через призму твоего кода, именно твой случай;
- найдём, что тебя останавливает на самом деле и где это живёт (часто это не то, на что ты думал);
- я скажу прямо, какой путь подходит именно тебе и какой один шаг стоит сделать уже завтра.

Ты уйдёшь с ясностью, что происходит с тобой на уровне нервной системы и что с этим делать. Этого достаточно, чтобы сдвинуться, даже если дальше ты не пойдёшь со мной никуда.

И сразу честно, это лишь разговор, но решать, что дальше, будешь только ты.

Единственное, такие созвоны я провожу лично, поэтому мест немного и они быстро разбираются. Если откликается, лучше занять своё сейчас.`;

export const CONSULT_BOOK_BUTTON_LABEL = "Записаться на консультацию";

export const CONSULT_EMAIL_PROMPT =
  "Окей! Чтобы мы могли связаться с тобой и прислать детали созвона, оставь, пожалуйста, свой email.";

export const CONSULT_EMAIL_INVALID = "Это не похоже на email. Пришли, пожалуйста, в формате name@example.com";

export const CONSULT_CONTINUE_BUTTON_LABEL = "Дальше";

export const M7_2_TEXT = `Принято! Передаю твой контакт, мы свяжемся с тобой в Telegram, чтобы подобрать удобные дату и время.

А пока можешь посмотреть и другие варианты.`;

export const M9_TEXT = "С чего ещё можно начать, выбери, что откликается:";
```

- [ ] **Step 2: Расширить `frontend/src/api/client.ts`**

Добавь в файл (после интерфейса `FunnelState`, перед `postFunnel`):

```typescript
export interface PurchaseInitiatedOut {
  confirmation_url: string;
}
```

Замени экспорт `api` целиком на:

```typescript
export const api = {
  ping: () => request<{ tg_id: number }>("/api/ping"),
  getFunnelState: () => request<FunnelState>("/api/funnel/state"),
  completeWelcome: () => postFunnel("welcome/complete"),
  acceptConsent: () => postFunnel("consent"),
  submitAnswer: (questionNo: number, score: number) =>
    postFunnel("answers", { question_no: questionNo, score }),
  showOffer: () => postFunnel("offer/show"),
  retake: () => postFunnel("retake"),
  viewProduct: (product: "book" | "practicum") => postFunnel(`product/${product}/view`),
  buyProduct: (product: "book" | "practicum") =>
    request<PurchaseInitiatedOut>(`/api/funnel/product/${product}/buy`, { method: "POST" }),
  bookConsult: () => postFunnel("consult/book"),
  submitConsultEmail: (email: string) =>
    request<FunnelState>("/api/funnel/consult/email", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    }),
};
```

- [ ] **Step 3: Добавить `openLink` в `frontend/src/lib/telegram.ts`**

Замени содержимое файла целиком:

```typescript
// Минимальная типизированная обёртка над Telegram WebApp JS SDK (грузится в
// index.html). Вне Telegram (например, обычный браузер при `npm run dev`)
// window.Telegram не определён — все хелперы деградируют, не роняя UI.

interface TelegramWebApp {
  initData: string;
  ready(): void;
  expand(): void;
  openLink(url: string, options?: { try_instant_view?: boolean }): void;
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

export function openLink(url: string): void {
  if (tg) {
    tg.openLink(url);
  } else {
    window.open(url, "_blank");
  }
}
```

- [ ] **Step 4: Проверить сборку**

Run: `cd frontend && npx tsc --noEmit`
Expected: без ошибок.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/content/texts.ts frontend/src/api/client.ts frontend/src/lib/telegram.ts
git commit -m "feat: копирайт деталей продукта/консультации, funnel-методы покупки, openLink"
```

---

### Task 5: Frontend — `ProductDetail.tsx`

**Files:**
- Create: `frontend/src/screens/ProductDetail.tsx`

**Interfaces:**
- Consumes: `PRODUCT_DETAIL_TEXTS`, `BUY_BUTTON_LABEL` (Task 4, `content/texts.ts`); `api.buyProduct`, `api.getFunnelState`, `FunnelState`, `PurchaseInitiatedOut` (Task 4, `api/client.ts`); `openLink` (Task 4, `lib/telegram.ts`).
- Produces: `ProductDetail({ product: "book"|"practicum", price: number, onPaymentSettled: (state: FunnelState) => void })` — используется в Task 7 (`App.tsx`).

- [ ] **Step 1: Создать `frontend/src/screens/ProductDetail.tsx`**

```tsx
import { useEffect, useState } from "react";
import { api, type FunnelState } from "@/api/client";
import { BUY_BUTTON_LABEL, PRODUCT_DETAIL_TEXTS } from "@/content/texts";
import { openLink } from "@/lib/telegram";

type Product = "book" | "practicum";

interface Props {
  product: Product;
  price: number;
  onPaymentSettled: (state: FunnelState) => void;
}

const POLL_INTERVAL_MS = 3000;
const POLL_TIMEOUT_MS = 120000;

export default function ProductDetail({ product, price, onPaymentSettled }: Props) {
  const [waiting, setWaiting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!waiting) return;

    let stopped = false;
    const deadline = Date.now() + POLL_TIMEOUT_MS;

    async function check() {
      const state = await api.getFunnelState();
      if (stopped) return;
      if (state.checkpoint !== `${product}_viewed`) {
        stopped = true;
        onPaymentSettled(state);
      }
    }

    function onVisible() {
      if (document.visibilityState === "visible") check();
    }

    const interval = setInterval(() => {
      if (Date.now() > deadline) {
        clearInterval(interval);
        return;
      }
      check();
    }, POLL_INTERVAL_MS);
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      stopped = true;
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [waiting, product, onPaymentSettled]);

  async function handleBuy() {
    setError(null);
    try {
      const { confirmation_url } = await api.buyProduct(product);
      openLink(confirmation_url);
      setWaiting(true);
    } catch {
      setError("Не получилось открыть оплату. Попробуй ещё раз.");
    }
  }

  async function handleManualCheck() {
    const state = await api.getFunnelState();
    if (state.checkpoint !== `${product}_viewed`) onPaymentSettled(state);
  }

  return (
    <div className="flex min-h-screen flex-col bg-navy p-6 text-white">
      <div className="flex-1 overflow-y-auto whitespace-pre-line text-[15px] leading-relaxed">
        {PRODUCT_DETAIL_TEXTS[product]}
      </div>
      {error !== null && <p className="mt-2 text-sm text-red-400">{error}</p>}
      {waiting ? (
        <div className="mt-6 flex flex-col items-center gap-2">
          <p className="text-sm text-white/70">Проверяем оплату…</p>
          <button onClick={handleManualCheck} className="text-sm text-gold underline">
            Проверить оплату
          </button>
        </div>
      ) : (
        <button
          onClick={handleBuy}
          className="mt-6 w-full rounded-xl bg-gold py-3 text-center font-semibold text-navy"
        >
          {`${BUY_BUTTON_LABEL[product]} за ${price} ₽`}
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Проверить сборку**

Run: `cd frontend && npx tsc --noEmit`
Expected: без ошибок.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/screens/ProductDetail.tsx
git commit -m "feat: экран ProductDetail — оплата через openLink + поллинг статуса"
```

---

### Task 6: Frontend — `ConsultDetail.tsx` и `ConsultEmailInput.tsx`

**Files:**
- Create: `frontend/src/screens/ConsultDetail.tsx`
- Create: `frontend/src/screens/ConsultEmailInput.tsx`

**Interfaces:**
- Consumes: `CONSULT_INTRO_TEXT`, `CONSULT_BOOK_BUTTON_LABEL`, `CONSULT_EMAIL_PROMPT`, `CONSULT_EMAIL_INVALID`, `CONSULT_CONTINUE_BUTTON_LABEL`, `M7_2_TEXT` (Task 4); `ApiError`, `FunnelState` (Task 4, `api/client.ts`).
- Produces: `ConsultDetail({ onBook: () => void })`, `ConsultEmailInput({ onSubmit: (email: string) => Promise<FunnelState>, onDone: (state: FunnelState) => void, onError: (message: string) => void })` — оба используются в Task 7.

- [ ] **Step 1: Создать `frontend/src/screens/ConsultDetail.tsx`**

```tsx
import { CONSULT_BOOK_BUTTON_LABEL, CONSULT_INTRO_TEXT } from "@/content/texts";

interface Props {
  onBook: () => void;
}

export default function ConsultDetail({ onBook }: Props) {
  return (
    <div className="flex min-h-screen flex-col justify-between bg-navy p-6 text-white">
      <div className="flex-1 overflow-y-auto whitespace-pre-line text-[15px] leading-relaxed">
        {CONSULT_INTRO_TEXT}
      </div>
      <button
        onClick={onBook}
        className="mt-6 w-full rounded-xl bg-gold py-3 text-center font-semibold text-navy"
      >
        {CONSULT_BOOK_BUTTON_LABEL}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Создать `frontend/src/screens/ConsultEmailInput.tsx`**

```tsx
import { useState } from "react";
import { ApiError, type FunnelState } from "@/api/client";
import {
  CONSULT_CONTINUE_BUTTON_LABEL,
  CONSULT_EMAIL_INVALID,
  CONSULT_EMAIL_PROMPT,
  M7_2_TEXT,
} from "@/content/texts";

interface Props {
  onSubmit: (email: string) => Promise<FunnelState>;
  onDone: (state: FunnelState) => void;
  onError: (message: string) => void;
}

export default function ConsultEmailInput({ onSubmit, onDone, onError }: Props) {
  const [email, setEmail] = useState("");
  const [invalid, setInvalid] = useState(false);
  const [pendingState, setPendingState] = useState<FunnelState | null>(null);

  async function handleSubmit() {
    setInvalid(false);
    try {
      const state = await onSubmit(email);
      setPendingState(state);
    } catch (err) {
      if (err instanceof ApiError && err.status === 422) {
        setInvalid(true);
      } else {
        onError(err instanceof ApiError ? err.message : "Ошибка сети");
      }
    }
  }

  if (pendingState !== null) {
    return (
      <div className="flex min-h-screen flex-col justify-between bg-navy p-6 text-white">
        <div className="flex-1 overflow-y-auto whitespace-pre-line text-[15px] leading-relaxed">
          {M7_2_TEXT}
        </div>
        <button
          onClick={() => onDone(pendingState)}
          className="mt-6 w-full rounded-xl bg-gold py-3 text-center font-semibold text-navy"
        >
          {CONSULT_CONTINUE_BUTTON_LABEL}
        </button>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col justify-between bg-navy p-6 text-white">
      <div className="flex-1">
        <p className="whitespace-pre-line text-[15px] leading-relaxed">{CONSULT_EMAIL_PROMPT}</p>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="name@example.com"
          className="mt-4 w-full rounded-lg border border-gold/40 bg-white/5 px-4 py-3 text-white placeholder:text-white/40"
        />
        {invalid && <p className="mt-2 text-sm text-red-400">{CONSULT_EMAIL_INVALID}</p>}
      </div>
      <button
        onClick={handleSubmit}
        className="mt-6 w-full rounded-xl bg-gold py-3 text-center font-semibold text-navy"
      >
        Отправить
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
git add frontend/src/screens/ConsultDetail.tsx frontend/src/screens/ConsultEmailInput.tsx
git commit -m "feat: экраны ConsultDetail и ConsultEmailInput для Mini App"
```

---

### Task 7: Frontend — `Offer.tsx` доработка, `resolveScreen`, `App.tsx` (финальная интеграция)

**Files:**
- Modify: `frontend/src/screens/Offer.tsx`
- Modify: `frontend/src/funnel/resolveScreen.ts`
- Modify: `frontend/src/funnel/resolveScreen.test.ts`
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: всё из Task 1–6 (`api.viewProduct/buyProduct/bookConsult/submitConsultEmail`, `ProductDetail`, `ConsultDetail`, `ConsultEmailInput`, `M9_TEXT`).
- Produces: финальная функция плана — расширенный `resolveScreen(checkpoint, resultType): ScreenId` (теперь с 8 вариантами) и полностью подключённый `App.tsx`.

- [ ] **Step 1: Написать падающие тесты на новые ветки `resolveScreen`**

Добавь в `frontend/src/funnel/resolveScreen.test.ts` (в существующий `describe`, после текущих кейсов):

```typescript
  it("maps practicum_viewed to product-detail", () => {
    expect(resolveScreen("practicum_viewed", "survival")).toBe("product-detail");
  });

  it("maps book_viewed to product-detail", () => {
    expect(resolveScreen("book_viewed", "survival")).toBe("product-detail");
  });

  it("maps consult_viewed to consult-detail", () => {
    expect(resolveScreen("consult_viewed", "survival")).toBe("consult-detail");
  });

  it("maps awaiting_email to consult-email-input", () => {
    expect(resolveScreen("awaiting_email", "survival")).toBe("consult-email-input");
  });
```

(Существующий кейс `"falls back to offer for out-of-2a-scope checkpoints when result already exists"` с `"practicum_viewed"` перестанет отражать реальность после этого таска — это ожидаемо: `practicum_viewed` получает собственный маппинг вместо фоллбэка. В Step 3 этот старый тест-кейс меняется на другой чекпоинт, не покрытый ни одним прямым маппингом.)

- [ ] **Step 2: Запустить, убедиться что новые падают**

Run: `cd frontend && npx vitest run src/funnel/resolveScreen.test.ts`
Expected: 4 новых теста FAIL (получают `"welcome"` вместо ожидаемого), старый тест на фоллбэк с `practicum_viewed` пока проходит (пока не тронут).

- [ ] **Step 3: Расширить `frontend/src/funnel/resolveScreen.ts`**

Замени содержимое файла целиком:

```typescript
export type ScreenId =
  | "welcome"
  | "consent"
  | "quiz"
  | "result"
  | "offer"
  | "product-detail"
  | "consult-detail"
  | "consult-email-input";

export function resolveScreen(checkpoint: string, resultType: string | null): ScreenId {
  if (checkpoint === "awaiting_consent") return "consent";
  if (checkpoint === "in_test") return "quiz";
  if (checkpoint === "result_shown") return "result";
  if (checkpoint === "offer_shown") return "offer";
  if (checkpoint === "practicum_viewed" || checkpoint === "book_viewed") return "product-detail";
  if (checkpoint === "consult_viewed") return "consult-detail";
  if (checkpoint === "awaiting_email") return "consult-email-input";
  return resultType !== null ? "offer" : "welcome";
}
```

- [ ] **Step 4: Обновить старый тест на фоллбэк — теперь он должен использовать чекпоинт вне всех известных маппингов**

В `frontend/src/funnel/resolveScreen.test.ts` замени:

```typescript
  it("falls back to offer for out-of-2a-scope checkpoints when result already exists", () => {
    // practicum_viewed/consult_viewed/book_viewed/idle принадлежат подпроекту 2b —
    // у 2a для них нет экрана; если результат уже есть, Offer самодостаточен.
    expect(resolveScreen("practicum_viewed", "impostor")).toBe("offer");
  });
```

на:

```typescript
  it("falls back to offer for idle (post-purchase/post-lead) when result already exists", () => {
    // idle наступает после deliver()/create_lead — своего экрана не имеет,
    // Offer с available_products и есть умное меню M9.
    expect(resolveScreen("idle", "impostor")).toBe("offer");
  });
```

- [ ] **Step 5: Запустить весь файл, убедиться что всё проходит**

Run: `cd frontend && npx vitest run src/funnel/resolveScreen.test.ts`
Expected: 9 passed (5 старых с обновлённым последним + 4 новых).

- [ ] **Step 6: Доработать `frontend/src/screens/Offer.tsx`**

Замени содержимое файла целиком:

```tsx
import type { FunnelState } from "@/api/client";
import {
  M9_TEXT,
  OFFER_EMPTY_TEXT,
  OFFER_INTRO_TEXTS,
  PRODUCT_LABELS,
  RETAKE_BUTTON_LABEL,
} from "@/content/texts";

interface Props {
  state: FunnelState;
  onRetake: () => void;
  onSelectProduct: (product: string) => void;
}

function priceLabel(product: string, state: FunnelState): string {
  if (product === "book") return `${PRODUCT_LABELS.book} — ${state.book_price_rub} ₽`;
  if (product === "practicum") return `${PRODUCT_LABELS.practicum} — ${state.practicum_price_rub} ₽`;
  return PRODUCT_LABELS.consult;
}

export default function Offer({ state, onRetake, onSelectProduct }: Props) {
  const available = state.available_products ?? [];
  const resultType = state.result_type;

  let introText: string;
  if (available.length === 0) {
    introText = OFFER_EMPTY_TEXT;
  } else if (state.checkpoint === "offer_shown" && resultType !== null) {
    introText = OFFER_INTRO_TEXTS[resultType];
  } else {
    introText = M9_TEXT;
  }

  return (
    <div className="flex min-h-screen flex-col bg-navy p-6 text-white">
      <div className="mb-4 whitespace-pre-line text-[15px] leading-relaxed">{introText}</div>
      <div className="flex flex-col gap-3">
        {available.map((product) => (
          <button
            key={product}
            onClick={() => onSelectProduct(product)}
            className="rounded-xl border border-gold/40 bg-gold/10 px-4 py-3 text-left text-sm font-semibold text-gold"
          >
            {priceLabel(product, state)}
          </button>
        ))}
      </div>
      <button onClick={onRetake} className="mt-auto pt-6 text-center text-sm text-gold/70 underline">
        {RETAKE_BUTTON_LABEL}
      </button>
    </div>
  );
}
```

- [ ] **Step 7: Подключить новые экраны в `frontend/src/App.tsx`**

Замени содержимое файла целиком:

```tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError, type FunnelState } from "./api/client";
import { resolveScreen } from "./funnel/resolveScreen";
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
      return (
        <Offer
          state={state}
          onRetake={() => runAction(api.retake)}
          onSelectProduct={(product) =>
            runAction(() =>
              product === "consult"
                ? api.bookConsult()
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
```

- [ ] **Step 8: Проверить сборку и полный набор фронтенд-тестов**

Run: `cd frontend && npx tsc --noEmit && npx vitest run`
Expected: без ошибок компиляции; все vitest-тесты PASS (9 в `resolveScreen.test.ts`).

- [ ] **Step 9: Собрать production-бандл**

Run: `cd frontend && npm run build`
Expected: сборка завершается без ошибок, `frontend/dist/` обновлён.

- [ ] **Step 10: Прогнать весь backend-набор ещё раз (регресс)**

Run: `pytest -v`
Expected: все тесты проекта PASS.

- [ ] **Step 11: Commit**

```bash
git add frontend/src/screens/Offer.tsx frontend/src/funnel/resolveScreen.ts frontend/src/funnel/resolveScreen.test.ts frontend/src/App.tsx
git commit -m "feat: подключить детали продукта/консультацию/оплату в FunnelGate, M9 на Offer"
```

- [ ] **Step 12: Ручная проверка в реальном Mini App (после деплоя)**

1. Пройти квиз до экрана Offer, нажать на карточку практикума → должен открыться `ProductDetail` с полным текстом M6.1+M6.2 и кнопкой «Купить практикум за 2990 ₽» (или актуальную цену из `/settings`).
2. Нажать «Купить» → должна открыться страница оплаты ЮKassa (через `openLink`, в системном браузере или Telegram-браузере).
3. Совершить тестовую оплату → вернуться в Telegram → экран должен сам обновиться (или после нажатия «Проверить оплату») на Offer с текстом M9 и оставшимися двумя продуктами (практикум исчез из списка).
4. Параллельно в чате должны прийти: инвайт в канал, PDF-тетрадь, видео/ссылка на видео (доставка не зависит от Mini App — уже проверено в подпроекте practicum-content-delivery).
5. Повторить для книги (файл книги должен прийти в чат).
6. Пройти консультацию: карточка → `ConsultDetail` → «Записаться» → `ConsultEmailInput` → неверный email → инлайн-ошибка без ухода с экрана → верный email → M7.2-подтверждение → «Дальше» → Offer с M9, без карточки консультации.
7. Регресс: чат-версия воронки продолжает работать без изменений.

## Self-Review

**1. Spec coverage:** Детали практикума/книги (M6.1+M6.2/M8.1+M8.2) — Task 5. Консультация + email (M7.1/M7.2, CONSULT_EMAIL_PROMPT/INVALID) — Task 6. Оплата через `openLink` + поллинг — Task 2 (backend) + Task 5 (frontend). Доставка контента — сознательно не переделывается (уже работает через вебхук, зафиксировано в Global Constraints). Умное меню M9 — Task 7 (переключение текста в `Offer.tsx` + отсутствие отдельного маппинга в `resolveScreen`, `idle` уже покрыт фоллбэком). Общий email-валидатор — Task 1.

**2. Placeholder scan:** Нет `TBD`/`TODO`, весь код полный и исполняемый.

**3. Type consistency:** `PurchaseInitiatedOut` (Python, Task 2) и `PurchaseInitiatedOut` (TypeScript, Task 4) — оба `{confirmation_url: string}`. `ProductDetail`'s `product: "book" | "practicum"` совпадает с backend'ским `Literal["book", "practicum"]` (Task 2) и с `_PRODUCT_CHECKPOINT`/`_PRODUCT_LABELS`. `resolveScreen`'s новые `ScreenId`-варианты (`"product-detail"`, `"consult-detail"`, `"consult-email-input"`) совпадают с `switch`-кейсами в `App.tsx` (Task 7) один-в-один — TypeScript отловит несовпадение при сборке (`tsc --noEmit` в Step 8 это подтверждает).

Plan complete and saved to `docs/superpowers/plans/2026-07-03-miniapp-funnel-purchase.md`. Два варианта выполнения:

**1. Subagent-Driven (рекомендую)** — я dispatch-у свежего субагента на каждую задачу, ревью между задачами, быстрая итерация

**2. Inline Execution** — выполняю задачи в этой сессии через executing-plans, батчами с чекпоинтами

Какой вариант?
