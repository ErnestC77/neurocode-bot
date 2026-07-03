# Доставка PDF-тетради и видео практикума Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** После оплаты практикума бот присылает не только инвайт в канал, но и PDF-рабочую тетрадь и видео (файлом или ссылкой — переключается через `/settings` без правок кода).

**Architecture:** Три новых str-ключа в существующем реестре `services/settings.py::SETTINGS` (тот же паттерн, что и `book_file_id`) + расширение `payments/delivery.py::_deliver_practicum` тремя последовательными шагами отправки после уже существующего текста с инвайтом. `/settings`-меню (`handlers/settings_admin.py`) полностью управляется словарём `SETTINGS` и не требует правок.

**Tech Stack:** aiogram3 (`bot.send_document`/`bot.send_video`), существующий `services/settings.py` реестр.

## Global Constraints

- Три новых ключа реестра: `practicum_workbook_file_id` (📓 File ID рабочей тетради), `practicum_video_file_id` (🎬 File ID видео), `practicum_video_url` (🔗 Ссылка на видео (пока файл не загружен)) — все `str`, дефолт `""`.
- Приоритет доставки видео: `practicum_video_file_id` > `practicum_video_url`. Если задан file_id — видео шлётся файлом (`bot.send_video`, нативный плеер); иначе, если задан url — сообщение с инлайн-кнопкой-ссылкой; иначе — ничего не отправляется, только `logger.error`.
- Пустой `practicum_workbook_file_id` → `logger.error`, без падения (как и сейчас для `book_file_id` в `_deliver_book`).
- Никаких автотестов для `payments/delivery.py` — этот файл не покрыт тестами и сейчас (aiogram/DB-touching код), только ручная проверка. Не придумывать моки `Bot` ради тестового покрытия.

---

### Task 1: Три новых ключа в реестре настроек

**Files:**
- Modify: `services/settings.py`
- Test: `tests/test_settings.py`

**Interfaces:**
- Consumes: `services.settings.SettingSpec` (уже существует).
- Produces: `SETTINGS["practicum_workbook_file_id"]`, `SETTINGS["practicum_video_file_id"]`, `SETTINGS["practicum_video_url"]` — все три используются в Task 2 через `await settings.get_str(key)`.

- [ ] **Step 1: Написать падающий тест на наличие и форму трёх новых ключей**

Добавь в конец `tests/test_settings.py`:

```python
def test_practicum_content_settings_registered():
    for key in ("practicum_workbook_file_id", "practicum_video_file_id", "practicum_video_url"):
        spec = SETTINGS[key]
        assert spec.value_type is str
        assert spec.default == ""
```

- [ ] **Step 2: Запустить тест, убедиться что падает**

Run: `pytest tests/test_settings.py::test_practicum_content_settings_registered -v`
Expected: FAIL — `KeyError: 'practicum_workbook_file_id'`.

- [ ] **Step 3: Добавить три ключа в `SETTINGS`**

В `services/settings.py` добавь три строки в словарь `SETTINGS` сразу после существующей записи `"practicum_channel_id"` (сохраняя порядок «сначала практикум, потом остальное» как в текущем файле):

```python
    "practicum_workbook_file_id": SettingSpec(
        "practicum_workbook_file_id", "📓 File ID рабочей тетради", str, ""),
    "practicum_video_file_id": SettingSpec(
        "practicum_video_file_id", "🎬 File ID видео", str, ""),
    "practicum_video_url": SettingSpec(
        "practicum_video_url", "🔗 Ссылка на видео (пока файл не загружен)", str, ""),
```

(Итоговый порядок ключей в `SETTINGS` после этого шага: `book_file_id`, `practicum_channel_id`, `practicum_workbook_file_id`, `practicum_video_file_id`, `practicum_video_url`, `book_price_rub`, `practicum_price_rub`, `reminder_delay_hours`, `reminder_check_interval`, `owner_chat_id`, `yookassa_shop_id`.)

- [ ] **Step 4: Запустить тест, убедиться что проходит**

Run: `pytest tests/test_settings.py -v`
Expected: все тесты `test_settings.py` PASS, включая новый.

- [ ] **Step 5: Прогнать весь набор (регресс)**

Run: `pytest -v`
Expected: все тесты проекта PASS (новые ключи не ломают `handlers/settings_admin.py::_menu_kb`, так как оно просто итерирует `SETTINGS.items()`).

- [ ] **Step 6: Commit**

```bash
git add services/settings.py tests/test_settings.py
git commit -m "feat: настройки для доставки PDF-тетради и видео практикума"
```

---

### Task 2: Доставка PDF-тетради и видео в `_deliver_practicum`

**Files:**
- Modify: `payments/delivery.py`

**Interfaces:**
- Consumes: `SETTINGS["practicum_workbook_file_id"]`/`["practicum_video_file_id"]`/`["practicum_video_url"]` (Task 1), `services.settings.get_str(key: str) -> str` (существует, возвращает `spec.default` — то есть `""` — если значение не задано в БД), `keyboards.inline.payment_link_kb(url: str, label: str) -> InlineKeyboardMarkup` (существует, уже используется в `handlers/book.py`/`handlers/practicum.py` тем же способом), `logger` (уже определён в файле, `logging.getLogger(__name__)`).
- Produces: расширенная `_deliver_practicum` — конец цепочки, ничего дальше её не использует.

- [ ] **Step 1: Прочитать текущую `_deliver_practicum`, чтобы точно знать место вставки**

`payments/delivery.py` сейчас (строки 34-46):

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

Новый код добавляется в самом конце функции — после отправки текста с инвайтом.

- [ ] **Step 2: Добавить импорт `payment_link_kb`**

В начале `payments/delivery.py` замени строку:

```python
from keyboards.inline import after_product_kb
```

на:

```python
from keyboards.inline import after_product_kb, payment_link_kb
```

- [ ] **Step 3: Дописать `_deliver_practicum` — PDF и видео**

Замени всю функцию `_deliver_practicum` на:

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

    workbook_file_id = await settings.get_str("practicum_workbook_file_id")
    if workbook_file_id:
        await bot.send_document(purchase.user_tg_id, workbook_file_id, protect_content=True)
    else:
        logger.error(
            "practicum_workbook_file_id не задан в /settings, не могу отправить тетрадь purchase=%s",
            purchase.id,
        )

    video_file_id = await settings.get_str("practicum_video_file_id")
    video_url = await settings.get_str("practicum_video_url")
    if video_file_id:
        await bot.send_video(purchase.user_tg_id, video_file_id, protect_content=True)
    elif video_url:
        await bot.send_message(
            purchase.user_tg_id, "Видео к практикуму:",
            reply_markup=payment_link_kb(video_url, "Смотреть видео"),
        )
    else:
        logger.error(
            "practicum_video_file_id и practicum_video_url не заданы в /settings, "
            "не могу отправить видео purchase=%s",
            purchase.id,
        )
```

(Порядок отправки: текст с инвайтом → PDF-тетрадь → видео (файлом или ссылкой). `protect_content=True` на тетради — тот же паттерн защиты от пересылки, что уже используется для книги в `_deliver_book`; на видео добавлено по аналогии, так как это тоже платный контент практикума.)

- [ ] **Step 4: Убедиться, что модуль импортируется без ошибок**

Run: `python -c "import payments.delivery"`
Expected: без ошибок (синтаксис и импорты корректны).

- [ ] **Step 5: Прогнать весь тестовый набор (регресс — `payments/delivery.py` без автотестов, но модуль импортируется другими модулями, которые тестируются косвенно)**

Run: `pytest -v`
Expected: все тесты проекта PASS (без изменений в количестве — эта задача не добавляет тестов, по дизайну спеки).

- [ ] **Step 6: Commit**

```bash
git add payments/delivery.py
git commit -m "feat: доставка PDF-тетради и видео практикума после оплаты"
```

- [ ] **Step 7: Ручная проверка (после деплоя, требует реальных значений в /settings)**

1. Через `/settings` в боте вписать `practicum_workbook_file_id` (file_id PDF «Нейрокод денег Рабочая тетрадь.pdf») и `practicum_video_url` (ссылка на mail.ru, пока видео не перенесено на self-hosted сервер).
2. Совершить тестовую оплату практикума.
3. Проверить, что бот присылает по порядку: (а) текст с инвайтом в канал, (б) PDF-документ, (в) сообщение с кнопкой-ссылкой «Смотреть видео».
4. Позже, когда видео будет доступно как file_id (после миграции на self-hosted Bot API — вне скоупа этой задачи) — вписать `practicum_video_file_id` через `/settings`; следующая оплата должна автоматически прислать видео файлом вместо ссылки, без правок кода.

## Self-Review

**1. Spec coverage:** Три новых ключа реестра — Task 1. Логика доставки PDF (Task 2, Step 3, блок `workbook_file_id`) — соответствует спеке. Логика доставки видео с приоритетом `video_file_id > video_url` и `logger.error`-фоллбэком (Task 2, Step 3, блок `video_file_id`/`video_url`) — соответствует спеке. `/settings`-меню не требует правок (подтверждено чтением `handlers/settings_admin.py::_menu_kb` — итерирует `SETTINGS.items()` универсально) — явно упомянуто в Global Constraints, отдельной задачи не заводилось намеренно.

**2. Placeholder scan:** Нет `TBD`/`TODO`, весь код полный и исполняемый.

**3. Type consistency:** `SettingSpec(key, label, value_type, default, suffix="", min_value=None)` — сигнатура в Task 1 совпадает с уже существующей в `services/settings.py` (проверено чтением файла перед написанием плана). `payment_link_kb(url: str, label: str)` в Task 2 совпадает с существующей сигнатурой в `keyboards/inline.py:111` и способом вызова в `handlers/book.py:43`/`handlers/practicum.py:43`.

Plan complete and saved to `docs/superpowers/plans/2026-07-03-practicum-content-delivery.md`. Два варианта выполнения:

**1. Subagent-Driven (рекомендую)** — я dispatch-у свежего субагента на каждую задачу, ревью между задачами, быстрая итерация

**2. Inline Execution** — выполняю задачи в этой сессии через executing-plans, батчами с чекпоинтами

Какой вариант?
