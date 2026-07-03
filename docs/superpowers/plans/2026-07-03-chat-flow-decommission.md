# Отключение чат-флоу воронки Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Убрать дублирующий квиз/оффер/оплата/консультация-флоу из чата (inline-кнопки Блоков 0-9 ТЗ) — Mini App остаётся единственным интерфейсом воронки; `/settings`/`/export_leads`/`/redeliver` в чате остаются без изменений.

**Architecture:** Семь файлов-хендлеров чат-флоу удаляются целиком (без замены — история в git, если понадобится откат). `handlers/start.py` заменяется минимальной версией без квиза. Всё, что чат-флоу оставляет после себя мёртвым по цепочке (клавиатуры в `keyboards/inline.py`, тексты в `texts/messages.py`, кнопки напоминаний в `scheduler.py`) — тоже вычищается или переключается на `web_app`-кнопки, открывающие Mini App напрямую.

**Tech Stack:** aiogram3 (`InlineKeyboardButton(web_app=WebAppInfo(url=...))` — та же механика, что уже используется для Menu Button в `asgi.py`).

## Global Constraints

- `/settings`, `/export_leads`, `/redeliver`, `get_file_id`, `get_forwarded_chat_id` (все — `handlers/admin.py`/`handlers/settings_admin.py`) — не трогать.
- `payments/` (`webhook.py`, `delivery.py`, `yookassa_client.py`), `api/routers/funnel.py`, весь `frontend/` — не трогать в бизнес-логике; единственная точечная правка — сигнатура вызова `after_product_kb` в `payments/delivery.py` (см. Task 2).
- `services/checkpoints.py`, `services/catalog.py`, `services/scoring.py`, `services/settings.py`, `services/validation.py`, `middlewares.py` — не трогать.
- Никаких новых callback-based кнопок с `callback_data`, ведущих в удаляемые хендлеры — только `url`/`web_app`-кнопки (не требуют зарегистрированного роутера) или отсутствие кнопки вовсе.
- Удаляемые файлы удаляются полностью (`git rm`), не оставляются как незарегистрированный мёртвый код.

---

### Task 1: Удалить чат-флоу хендлеры, минимальный `/start`, обновить диспетчер

**Files:**
- Delete: `handlers/consent.py`, `handlers/test.py`, `handlers/menu.py`, `handlers/practicum.py`, `handlers/book.py`, `handlers/consult.py`
- Modify (полная замена содержимого): `handlers/start.py`, `handlers/text_input.py`, `bot.py`

**Interfaces:**
- Produces: `handlers.start.router` (aiogram `Router`, единственный хендлер — `/start`), `handlers.text_input.router` (aiogram `Router`, единственный хендлер — свободный текст для `/settings`) — оба используются в `bot.py::build_dispatcher`, который сам является публичным интерфейсом, используемым `bot.py::run_bot_polling` (не меняется) и `asgi.py` (не меняется, вызывает `run_bot_polling` косвенно).

- [ ] **Step 1: Удалить шесть файлов чат-флоу**

```bash
git rm handlers/consent.py handlers/test.py handlers/menu.py handlers/practicum.py handlers/book.py handlers/consult.py
```

- [ ] **Step 2: Заменить `handlers/start.py` минимальной версией**

```python
"""Точка входа в чат: короткая подсказка открыть Mini App через Menu Button.

Весь квиз/оффер/оплата/консультация переехали в Mini App (Menu Button,
настраивается в asgi.py::_bot_lifecycle). Чат больше не дублирует этот
контент — только направляет пользователя открыть кнопку."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! Диагностика «Какой нейрокод блокирует твой доход» открывается "
        "кнопкой «Открыть» рядом с полем ввода 👇"
    )
```

- [ ] **Step 3: Заменить `handlers/text_input.py` — убрать ветку `consult`**

```python
"""Единственный catch-all для свободного текста во всём боте — значения
настроек, вводимые через /settings (handlers/settings_admin.py)."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.types import Message

from config import Config
from db import crud
from handlers import settings_admin
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
    # не наш текст, молчим
```

- [ ] **Step 4: Обновить `bot.py` — убрать импорты и регистрацию удалённых роутеров**

Замени блок импорта хендлеров:

```python
from handlers import (admin, book, consent, consult, menu, practicum, settings_admin,
                      start, test, text_input)
```

на:

```python
from handlers import admin, settings_admin, start, text_input
```

Замени тело `build_dispatcher`:

```python
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
```

на:

```python
def build_dispatcher(config: Config) -> Dispatcher:
    dp = Dispatcher()
    dp["config"] = config
    dp.message.middleware(ActivityMiddleware())
    dp.callback_query.middleware(ActivityMiddleware())
    dp.include_router(start.router)
    dp.include_router(admin.router)
    dp.include_router(settings_admin.router)
    # text_input.router — последним: единственный catch-all для свободного
    # текста (значения настроек), иначе он перехватил бы команды/сообщения,
    # предназначенные другим роутерам.
    dp.include_router(text_input.router)
    return dp
```

- [ ] **Step 5: Проверить, что бот импортируется без ошибок**

Run: `python -c "import bot"`
Expected: без ошибок (никаких `ImportError`/`ModuleNotFoundError` на удалённые модули).

- [ ] **Step 6: Прогнать весь тестовый набор (регресс — у удалённых хендлеров не было своих тестов, но нужно убедиться, что ничего косвенно не сломалось)**

Run: `pytest -v`
Expected: все тесты проекта PASS (61 тест, без изменений в количестве — эта задача не трогает файлы с тестами).

- [ ] **Step 7: Commit**

```bash
git add handlers/start.py handlers/text_input.py bot.py
git commit -m "feat: отключить чат-флоу воронки — Mini App единственный интерфейс квиза/покупки/консультации"
```

---

### Task 2: `keyboards/inline.py` — вычистить мёртвые билдеры, `after_product_kb` на web_app-кнопку

**Files:**
- Modify: `keyboards/inline.py`
- Modify: `payments/delivery.py`
- Modify: `scheduler.py`

**Interfaces:**
- Consumes: ничего нового снаружи.
- Produces: `keyboards.inline.after_product_kb(current: str, available: list[str], miniapp_url: str) -> InlineKeyboardMarkup` (сигнатура изменилась — третий параметр), `keyboards.inline.open_miniapp_kb(url: str) -> InlineKeyboardMarkup` (новый) — оба используются: `after_product_kb` в `payments/delivery.py` (эта же задача), `open_miniapp_kb` в `scheduler.py` (эта же задача).

- [ ] **Step 1: Заменить `keyboards/inline.py` целиком**

```python
"""Inline-клавиатуры. callback_data — namespace через ':' (см. README)."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo


def _kb(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=list(rows))


def payment_link_kb(url: str, label: str) -> InlineKeyboardMarkup:
    return _kb([InlineKeyboardButton(text=label, url=url)])


def after_product_kb(current: str, available: list[str], miniapp_url: str) -> InlineKeyboardMarkup:
    """M6.3 / M7.2 / M8.3: если остались непроданные продукты — одна кнопка,
    открывающая Mini App (там уже показывается умное меню M9 с актуальным
    списком). Раньше здесь были персональные callback-кнопки на каждый
    продукт — они вели в чат-хендлеры, которых больше нет."""
    remaining = [p for p in available if p != current]
    if not remaining:
        return _kb()
    return _kb([InlineKeyboardButton(text="Посмотреть другие варианты",
                                     web_app=WebAppInfo(url=miniapp_url))])


def open_miniapp_kb(url: str) -> InlineKeyboardMarkup:
    """Единственная кнопка «Открыть», открывающая Mini App напрямую —
    используется в напоминаниях R1-R6. Mini App сам покажет нужный экран по
    чекпоинту пользователя, поэтому одна кнопка годится для всех кодов."""
    return _kb([InlineKeyboardButton(text="Открыть", web_app=WebAppInfo(url=url))])
```

- [ ] **Step 2: Обновить оба call site `after_product_kb` в `payments/delivery.py`**

Замени:

```python
    await bot.send_message(purchase.user_tg_id, text,
                           reply_markup=after_product_kb(PRACTICUM, available))
```

на:

```python
    await bot.send_message(purchase.user_tg_id, text,
                           reply_markup=after_product_kb(PRACTICUM, available, config.webhook_base_url))
```

Замени:

```python
    await bot.send_message(purchase.user_tg_id, TEXTS["M8.3"],
                           reply_markup=after_product_kb(BOOK, available))
```

на:

```python
    await bot.send_message(purchase.user_tg_id, TEXTS["M8.3"],
                           reply_markup=after_product_kb(BOOK, available, config.webhook_base_url))
```

- [ ] **Step 3: Обновить `scheduler.py` — единая кнопка для всех напоминаний**

Замени импорт:

```python
from keyboards.inline import next_kb, reminder_cta_kb
```

на:

```python
from keyboards.inline import open_miniapp_kb
```

Замени блок `_REMINDER_KB` и функцию `_reminder_keyboard`:

```python
# Кнопки напоминаний — ровно как в Блоке 10 ТЗ: у каждого R-кода своя (короткая)
# метка и callback, который ведёт СРАЗУ к действию, а не переоткрывает intro-экран
# продукта (R4/R5/R6) или молча теряет текст вопроса (R2).
_REMINDER_KB = {
    "R1": lambda: next_kb("Продолжить", "welcome:4"),          # → повторно показать M1.1
    "R2": lambda: next_kb("Ответить", "test:resume"),          # → повторно показать вопрос
    "R3": lambda: next_kb("Какой шаг дальше?", "result:next"),  # → M5.*
    "R4": lambda: reminder_cta_kb("Купить практикум", "practicum:buy"),
    "R5": lambda: reminder_cta_kb("Записаться", "consult:book"),
    "R6": lambda: reminder_cta_kb("Купить книгу", "book:buy"),
}


def _reminder_keyboard(code: str) -> InlineKeyboardMarkup | None:
    builder = _REMINDER_KB.get(code)
    return builder() if builder else None
```

на:

```python
def _reminder_keyboard(config: Config) -> InlineKeyboardMarkup:
    """Одна и та же кнопка для всех R1-R6 — открывает Mini App, который сам
    покажет нужный экран по чекпоинту пользователя (раньше у каждого R-кода
    была своя callback-кнопка в конкретный чат-хендлер — теперь их нет)."""
    return open_miniapp_kb(config.webhook_base_url)
```

Замени вызов внутри `process_reminders` (сейчас):

```python
        try:
            kb = _reminder_keyboard(code)
            await bot.send_message(user.tg_id, TEXTS[code], reply_markup=kb)
            sent += 1
```

на:

```python
        try:
            await bot.send_message(user.tg_id, TEXTS[code], reply_markup=_reminder_keyboard(config))
            sent += 1
```

Также нужно убрать теперь неиспользуемый импорт `InlineKeyboardMarkup`, если он в файле использовался только в удалённой сигнатуре `_reminder_keyboard(code: str) -> InlineKeyboardMarkup | None` — проверь текущий блок импортов `scheduler.py`:

```python
from aiogram.types import InlineKeyboardMarkup
```

Эта строка удаляется, `InlineKeyboardMarkup` в файле больше нигде не используется (новая `_reminder_keyboard` возвращает его неявно через `open_miniapp_kb`, без аннотации типа в самом `scheduler.py`).

- [ ] **Step 4: Проверить импорты**

Run: `python -c "import keyboards.inline; import payments.delivery; import scheduler"`
Expected: без ошибок.

- [ ] **Step 5: Прогнать весь тестовый набор**

Run: `pytest -v`
Expected: все тесты проекта PASS.

- [ ] **Step 6: Commit**

```bash
git add keyboards/inline.py payments/delivery.py scheduler.py
git commit -m "feat: заменить чат callback-кнопки на web_app-кнопки Mini App"
```

---

### Task 3: `texts/messages.py` — убрать ключи мёртвого чат-флоу

**Files:**
- Modify: `texts/messages.py`

**Interfaces:**
- Consumes: ничего.
- Produces: `texts.messages.TEXTS` (сокращённый словарь — только `M6.3`, `M8.3`, `R1`-`R6`), используется `payments/delivery.py` и `scheduler.py` (обе задачи уже выполнены, ключи не меняются, только состав словаря).

- [ ] **Step 1: Заменить `texts/messages.py` целиком**

```python
"""Тексты сообщений. Ключи совпадают с ID из ТЗ (new_bot.md) для трассируемости код↔ТЗ.

Весь квиз/оффер/консультация-контент (M0.1-M9, включая CONSULT_EMAIL_*) переехал
в frontend/src/content/texts.ts (Mini App) и здесь больше не нужен — чат больше
не дублирует эти сообщения. Остаются только тексты, которые чат-бот продолжает
слать сам, независимо от интерфейса покупки: подтверждение выдачи доступа после
оплаты (M6.3/M8.3, payments/delivery.py) и напоминания об отвале (R1-R6,
scheduler.py)."""
from __future__ import annotations

TEXTS: dict[str, str] = {
    "M6.3": (
        "Готово. Добро пожаловать!\n\n"
        "Вот доступ в закрытый канал с практикумом: {invite_link}\n\n"
        "Начни с закреплённого сообщения, там инструкция, с чего стартовать. Вопросы можно "
        "задавать в комментариях в канале.\n\n"
        "Удачной работы. Дальше будет интереснее!"
    ),
    "M8.3": (
        "Готово, оплата прошла. Поздравляю, и спасибо за доверие!\n\n"
        "Пара слов, чтобы она не легла «на потом», как все прошлые цели. Эта книга работает "
        "только в одном случае, если ты делаешь упражнения, а не просто читаешь.\n\n"
        "- выдели себе час в спокойной обстановке, без спешки и уведомлений;\n"
        "- приготовь ручку и бумагу, писать нужно руками, это часть метода;\n"
        "- не глотай всё за один присест. Лучше один шаг сегодня, но сделанный, чем вся книга "
        "прочитана и забыта.\n\n"
        "А когда пройдёшь книгу и захочешь идти глубже, здесь же покажу следующий шаг."
    ),
    "R1": (
        "Ты начал диагностику, но не закончил настройку. Это меньше 5 минут, и ты узнаешь, "
        "какой код держит твой доход. Продолжим?"
    ),
    "R2": (
        "Ты остановился на полпути теста. Осталось пара вопросов, и получишь подробную "
        "расшифровку своего кода. Закончим?"
    ),
    "R3": (
        "Ты узнал свой тип кода, но это половина. Самое важное, что с ним делать. Покажу твой "
        "следующий шаг?"
    ),
    "R4": (
        "Ты смотрел практикум «Найди свой код». Это самый простой способ начать работать с "
        "причиной самому, за несколько вечеров и 2990₽. Готов начать?"
    ),
    "R5": (
        "Ты интересовался бесплатной консультацией с Марией. Это живой разбор твоего случая, "
        "без обязательств. Записать тебя?"
    ),
    "R6": (
        "Ты заглянул в книгу «Целеполагание», но так и не забрал её. Понимаю, «потом» звучит "
        "безопаснее, но это и есть то самое «потом», на котором обычно застревают все. Книга "
        "стоит 990₽ и пару вечеров твоего времени. Заберёшь?"
    ),
}
```

- [ ] **Step 2: Проверить импорт**

Run: `python -c "import texts.messages"`
Expected: без ошибок.

- [ ] **Step 3: Прогнать весь тестовый набор (финальный регресс всего плана)**

Run: `pytest -v`
Expected: все тесты проекта PASS.

- [ ] **Step 4: Commit**

```bash
git add texts/messages.py
git commit -m "feat: убрать из texts/messages.py тексты мёртвого чат-флоу"
```

- [ ] **Step 5: Ручная проверка (после деплоя)**

1. `/start` в чате → короткий текст без кнопок, без квиза.
2. Menu Button рядом с полем ввода по-прежнему открывает Mini App и показывает экран, соответствующий текущему чекпоинту тестового аккаунта.
3. `/settings` и `/export_leads` работают как раньше.
4. Тестовая оплата книги/практикума → сообщение с доступом (`M8.3`/`M6.3`) приходит как раньше, кнопка «Посмотреть другие варианты» (если остались непроданные продукты) открывает Mini App.
5. Временно уменьшить `reminder_delay_hours` через `/settings`, дождаться напоминания — текст R-кода приходит с единственной кнопкой «Открыть», ведущей в Mini App.

## Self-Review

**1. Spec coverage:** Удаление 7 файлов + новый `/start` + `text_input.py` без consult-ветки — Task 1. `keyboards/inline.py` (удаление мёртвых билдеров, `after_product_kb` на web_app) + `payments/delivery.py` call sites — Task 2. `scheduler.py` единая кнопка напоминаний — Task 2. `texts/messages.py` сокращение до `M6.3`/`M8.3`/`R1`-`R6` — Task 3. Пункт спеки «что НЕ меняется» — ни один файл из этого списка не упомянут ни в одном Task.

**2. Placeholder scan:** Нет `TBD`/`TODO`, весь код полный и исполняемый, каждый шаг с точным до/после diff.

**3. Type consistency:** `after_product_kb(current: str, available: list[str], miniapp_url: str)` — сигнатура в Task 2 Step 1 совпадает с обоими call site в Task 2 Step 2 (третий аргумент — `config.webhook_base_url`, тип `str`, совпадает с `Config.webhook_base_url: str` из `config.py`). `open_miniapp_kb(url: str)` в Task 2 Step 1 совпадает с использованием в `_reminder_keyboard(config: Config)` (Step 3) — вызывается как `open_miniapp_kb(config.webhook_base_url)`, тот же тип.

Plan complete and saved to `docs/superpowers/plans/2026-07-03-chat-flow-decommission.md`. Два варианта выполнения:

**1. Subagent-Driven (рекомендую)** — я dispatch-у свежего субагента на каждую задачу, ревью между задачами, быстрая итерация

**2. Inline Execution** — выполняю задачи в этой сессии через executing-plans, батчами с чекпоинтами

Какой вариант?
