# Несколько файлов на продукт — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать книге, тетради практикума и видео практикума возможность состоять из нескольких файлов вместо одного.

**Architecture:** Новое поле `SettingSpec.multi` помечает файловые настройки; несколько `file_id` хранятся через перенос строки в том же текстовом поле `bot_settings.value` (без миграции БД). Админ пересылает файлы боту один за другим, пока активен режим редактирования этой настройки — каждый файл дописывается в список. Доставка проходит циклом по списку вместо одного `send_document`/`send_video`.

**Tech Stack:** Python 3.12, aiogram 3, SQLAlchemy 2.0 async.

## Global Constraints

- `multi=True` только для `book_file_id`, `practicum_workbook_file_id`, `practicum_video_file_id`. `practicum_video_url` остаётся `multi=False` (текстовая ссылка, не файл).
- Существующие продовые значения (один `file_id` без переносов строки) должны читаться как список из одного элемента — без миграции БД.
- Тесты: только `services/settings.py` (уже единственное исключение из конвенции «DB-код тестируется вручную», см. `tests/test_settings.py`). Aiogram-хендлеры (`handlers/admin.py`, `handlers/settings_admin.py`) и `payments/delivery.py` в этом проекте автотестами не покрываются — только ручная проверка.

---

### Task 1: `services/settings.py` — `SettingSpec.multi`, `get_file_list`, `add_file_id`

**Files:**
- Modify: `services/settings.py`
- Test: `tests/test_settings.py`

**Interfaces:**
- Produces: `SettingSpec.multi: bool` (новое поле датакласса), `services.settings.get_file_list(key: str) -> list[str]`, `services.settings.add_file_id(key: str, file_id: str) -> int`, `services.settings.format_multi_count(count: int) -> str`
- Consumes: `db.crud.set_setting_value` (уже существует), `settings_db` fixture (`tests/test_settings.py`, уже существует)

- [ ] **Step 1: Написать падающие тесты**

В конец `tests/test_settings.py` добавить:

```python
async def test_get_file_list_empty_when_unset(settings_db):
    assert await settings.get_file_list("book_file_id") == []


async def test_add_file_id_then_get_file_list(settings_db):
    n = await settings.add_file_id("book_file_id", "file-1")
    assert n == 1
    assert await settings.get_file_list("book_file_id") == ["file-1"]


async def test_add_file_id_appends_to_existing(settings_db):
    await settings.add_file_id("book_file_id", "file-1")
    n = await settings.add_file_id("book_file_id", "file-2")
    assert n == 2
    assert await settings.get_file_list("book_file_id") == ["file-1", "file-2"]


def test_multi_flag_set_for_file_settings():
    for key in ("book_file_id", "practicum_workbook_file_id", "practicum_video_file_id"):
        assert SETTINGS[key].multi is True


def test_multi_flag_false_for_non_file_settings():
    assert SETTINGS["practicum_video_url"].multi is False
    assert SETTINGS["book_price_rub"].multi is False


def test_format_multi_count_zero_is_ne_zadano():
    assert settings.format_multi_count(0) == "не задано"


def test_format_multi_count_nonzero():
    assert settings.format_multi_count(3) == "3 файлов"
```

- [ ] **Step 2: Запустить тесты и убедиться, что падают**

Run: `pytest tests/test_settings.py -v -k "file_list or add_file_id or multi_flag or format_multi_count"`
Expected: FAIL — `AttributeError` (`get_file_list`/`add_file_id`/`format_multi_count` не существуют), `TypeError` (`SettingSpec` не принимает `multi`)

- [ ] **Step 3: Добавить `multi` в `SettingSpec` и проставить флаг**

В `services/settings.py` заменить:

```python
@dataclass(frozen=True)
class SettingSpec:
    key: str
    label: str
    value_type: type  # int | str
    default: str
    suffix: str = ""  # добавляется к значению при отображении в /settings
    min_value: int | None = None  # нижняя граница для int-настроек (None = без ограничения)
```

на:

```python
@dataclass(frozen=True)
class SettingSpec:
    key: str
    label: str
    value_type: type  # int | str
    default: str
    suffix: str = ""  # добавляется к значению при отображении в /settings
    min_value: int | None = None  # нижняя граница для int-настроек (None = без ограничения)
    multi: bool = False  # несколько file_id через перенос строки вместо одного значения
```

Заменить три файловые настройки:

```python
    "book_file_id": SettingSpec(
        "book_file_id", "📄 File ID книги", str, ""),
    "practicum_channel_id": SettingSpec(
        "practicum_channel_id", "📢 ID канала практикума", str, ""),
    "practicum_workbook_file_id": SettingSpec(
        "practicum_workbook_file_id", "📓 File ID рабочей тетради", str, ""),
    "practicum_video_file_id": SettingSpec(
        "practicum_video_file_id", "🎬 File ID видео", str, ""),
```

на:

```python
    "book_file_id": SettingSpec(
        "book_file_id", "📄 File ID книги", str, "", multi=True),
    "practicum_channel_id": SettingSpec(
        "practicum_channel_id", "📢 ID канала практикума", str, ""),
    "practicum_workbook_file_id": SettingSpec(
        "practicum_workbook_file_id", "📓 File ID рабочей тетради", str, "", multi=True),
    "practicum_video_file_id": SettingSpec(
        "practicum_video_file_id", "🎬 File ID видео", str, "", multi=True),
```

- [ ] **Step 4: Добавить `get_file_list`, `add_file_id`, `format_multi_count`**

В `services/settings.py` после `set_value` добавить:

```python
async def get_file_list(key: str) -> list[str]:
    """Для multi-настроек: список file_id (пустой список, если не задано)."""
    raw = await get_str(key)
    return [line.strip() for line in raw.splitlines() if line.strip()]


async def add_file_id(key: str, file_id: str) -> int:
    """Добавляет file_id в конец списка multi-настройки. Возвращает новую длину списка."""
    current = await get_file_list(key)
    current.append(file_id)
    await crud.set_setting_value(key, "\n".join(current))
    return len(current)
```

И рядом с `format_value` добавить:

```python
def format_multi_count(count: int) -> str:
    """Человекочитаемое количество файлов для multi-настроек в меню /settings."""
    return "не задано" if count == 0 else f"{count} файлов"
```

- [ ] **Step 5: Запустить тесты и убедиться, что проходят**

Run: `pytest tests/test_settings.py -v`
Expected: PASS (все тесты файла)

- [ ] **Step 6: Запустить полный набор тестов**

Run: `pytest -v`
Expected: PASS (весь проект)

- [ ] **Step 7: Commit**

```bash
git add services/settings.py tests/test_settings.py
git commit -m "feat: SettingSpec.multi, get_file_list/add_file_id для многофайловых настроек"
```

---

### Task 2: `/settings` — меню, режим добавления файлов, кнопки «Очистить»/«Готово»

**Files:**
- Modify: `handlers/settings_admin.py`

**Interfaces:**
- Consumes: `SettingSpec.multi`, `services.settings.get_file_list`, `services.settings.add_file_id`, `services.settings.format_multi_count` (Task 1)
- Produces: callback-паттерны `settings:clear:{key}`, `settings:done:{key}` (использует `handlers/admin.py` в Task 3 не будет — там свой отдельный поток через pending edit)

**Примечание:** нет автотестов для aiogram-хендлеров в этом проекте — проверка вручную (шаги в конце задачи).

- [ ] **Step 1: Обновить импорт**

В `handlers/settings_admin.py` заменить:

```python
from services.settings import SETTINGS, cast_value, format_value, is_authorized_admin
```

на:

```python
from services.settings import (SETTINGS, add_file_id, cast_value, format_multi_count,
                               format_value, get_file_list, is_authorized_admin)
```

- [ ] **Step 2: Обновить меню — показывать количество файлов для multi-настроек**

Заменить:

```python
async def _menu_kb() -> InlineKeyboardMarkup:
    rows = []
    for key, spec in SETTINGS.items():
        raw = await crud.get_setting_value(key)
        rows.append([InlineKeyboardButton(
            text=f"{spec.label}: {format_value(spec, raw)}",
            callback_data=f"settings:edit:{key}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)
```

на:

```python
async def _menu_kb() -> InlineKeyboardMarkup:
    rows = []
    for key, spec in SETTINGS.items():
        if spec.multi:
            display = format_multi_count(len(await get_file_list(key)))
        else:
            display = format_value(spec, await crud.get_setting_value(key))
        rows.append([InlineKeyboardButton(
            text=f"{spec.label}: {display}",
            callback_data=f"settings:edit:{key}",
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)
```

- [ ] **Step 3: Обновить `edit_setting` — отдельная ветка для multi-настроек**

Заменить:

```python
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
```

на:

```python
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

    if spec.multi:
        count = len(await get_file_list(key))
        await callback.message.answer(
            f"Пришли файл(ы) для «{spec.label}» (сейчас загружено: {count}). "
            "Каждый присланный файл добавляется в список.",
            reply_markup=_multi_edit_kb(key),
        )
        return

    raw = await crud.get_setting_value(key)
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отмена", callback_data="settings:cancel")],
    ])
    await callback.message.answer(
        f"Пришли новое значение для «{spec.label}» (сейчас: {format_value(spec, raw)}).",
        reply_markup=cancel_kb,
    )
```

Добавить helper перед `edit_setting` (после `_menu_kb`):

```python
def _multi_edit_kb(key: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Очистить", callback_data=f"settings:clear:{key}")],
        [InlineKeyboardButton(text="Готово", callback_data=f"settings:done:{key}")],
    ])
```

- [ ] **Step 4: Добавить обработчики `settings:clear:` и `settings:done:`**

После `cancel_edit` добавить:

```python
@router.callback_query(F.data.startswith("settings:clear:"))
async def clear_multi_setting(callback: CallbackQuery, config: Config) -> None:
    if not await is_authorized_admin(callback.from_user.id, config):
        await callback.answer()
        return
    key = callback.data.split(":", 2)[2]
    spec = SETTINGS.get(key)
    await callback.answer()
    if spec is None or not spec.multi:
        return
    await crud.set_setting_value(key, "")
    await callback.message.answer(
        f"Список для «{spec.label}» очищен (сейчас загружено: 0).",
        reply_markup=_multi_edit_kb(key),
    )


@router.callback_query(F.data.startswith("settings:done:"))
async def done_multi_setting(callback: CallbackQuery, config: Config) -> None:
    if not await is_authorized_admin(callback.from_user.id, config):
        await callback.answer()
        return
    await callback.answer()
    await crud.clear_pending_setting_edit(callback.from_user.id)
    await callback.message.answer("Готово.", reply_markup=await _menu_kb())
```

- [ ] **Step 5: Обновить `handle_setting_input` — для multi-настроек текст добавляется в список, а не заменяет значение**

Заменить:

```python
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
    except ValueError as exc:
        await message.answer(f"Не получилось разобрать значение: {exc}.")
        return

    await crud.set_setting_value(setting_key, normalized)
    await crud.clear_pending_setting_edit(message.from_user.id)
    new_display = format_value(spec, normalized)
    await message.answer(
        f"✅ {spec.label}: {old_display} → {new_display}", reply_markup=await _menu_kb(),
    )
```

на:

```python
async def handle_setting_input(message: Message, config: Config, setting_key: str) -> None:
    """Вызывается из handlers/text_input.py, когда у админа есть pending edit."""
    spec = SETTINGS.get(setting_key)
    if spec is None:
        await crud.clear_pending_setting_edit(message.from_user.id)
        return

    raw_input = (message.text or "").strip()

    if spec.multi:
        # Голый текст воспринимаем как file_id, добавленный вручную (обратная
        # совместимость со старым способом «скопировал — вставил») — не
        # заменяем список и не выходим из режима редактирования.
        if not raw_input:
            return
        count = await add_file_id(setting_key, raw_input)
        await message.answer(f"Добавлено ({count}): {spec.label}")
        return

    old_display = format_value(spec, await crud.get_setting_value(setting_key))
    try:
        normalized = cast_value(spec, raw_input)
    except ValueError as exc:
        await message.answer(f"Не получилось разобрать значение: {exc}.")
        return

    await crud.set_setting_value(setting_key, normalized)
    await crud.clear_pending_setting_edit(message.from_user.id)
    new_display = format_value(spec, normalized)
    await message.answer(
        f"✅ {spec.label}: {old_display} → {new_display}", reply_markup=await _menu_kb(),
    )
```

- [ ] **Step 6: Проверить импорт**

Run: `python -c "import handlers.settings_admin"`
Expected: без ошибок

- [ ] **Step 7: Запустить полный набор тестов (регрессия)**

Run: `pytest -v`
Expected: PASS (весь проект — эта задача не меняет `services/settings.py`, только UI-хендлеры)

- [ ] **Step 8: Ручная проверка**

1. `/settings` → нажать «📄 File ID книги: не задано» — ожидать сообщение «Пришли файл(ы)... (сейчас загружено: 0)» с кнопками «Очистить»/«Готово»
2. Отправить текстом `test-file-1` — ожидать «Добавлено (1): 📄 File ID книги»
3. Отправить текстом `test-file-2` — ожидать «Добавлено (2): 📄 File ID книги»
4. Нажать «Очистить» — ожидать «Список... очищен (сейчас загружено: 0)»
5. Нажать «Готово» — ожидать «Готово.» и меню настроек
6. Открыть `/settings` снова — «📄 File ID книги» должна показывать «не задано» (список действительно очистился)

- [ ] **Step 9: Commit**

```bash
git add handlers/settings_admin.py
git commit -m "feat: /settings — режим добавления нескольких файлов, кнопки Очистить/Готово"
```

---

### Task 3: Приём файлов ботом — добавление в активную multi-настройку

**Files:**
- Modify: `handlers/admin.py`

**Interfaces:**
- Consumes: `SETTINGS`, `add_file_id` (Task 1), `db.crud.get_pending_setting_edit` (уже существует)

**Примечание:** нет автотестов для aiogram-хендлеров — проверка вручную.

- [ ] **Step 1: Обновить импорт**

В `handlers/admin.py` заменить:

```python
from services.settings import get_effective_owner_chat_id, is_authorized_admin
```

на:

```python
from services.settings import SETTINGS, add_file_id, get_effective_owner_chat_id, is_authorized_admin
```

- [ ] **Step 2: Добавить типизацию множеств настроек по типу файла и helper**

Перед `get_file_id` добавить:

```python
_DOCUMENT_SETTINGS = {"book_file_id", "practicum_workbook_file_id"}
_VIDEO_SETTINGS = {"practicum_video_file_id"}


async def _try_append_to_pending(message: Message, file_id: str, allowed_keys: set[str]) -> bool:
    """Если у отправителя есть pending edit ровно на одну из allowed_keys —
    добавляет file_id в список этой настройки и отвечает подтверждением.

    allowed_keys ограничивает, какие multi-настройки принимают этот тип файла
    (документ vs видео) — без этого видео, присланное во время редактирования
    book_file_id, испортило бы список PDF-файлов книги.

    True, если обработано так; False — вызывающий хендлер должен ответить
    сырым file_id как раньше (нет активного релевантного pending edit).
    """
    pending_key = await crud.get_pending_setting_edit(message.from_user.id)
    if pending_key not in allowed_keys:
        return False
    spec = SETTINGS[pending_key]
    count = await add_file_id(pending_key, file_id)
    await message.reply(f"Добавлено ({count}): {spec.label}")
    return True
```

- [ ] **Step 3: Подключить в `get_file_id` и `get_video_file_id`**

Заменить:

```python
@router.message(F.document)
async def get_file_id(message: Message, config: Config) -> None:
    """Владелец присылает PDF книги боту — бот отвечает file_id для BOOK_FILE_ID в /settings."""
    if not await is_authorized_admin(message.from_user.id, config):
        return
    await message.reply(f"file_id: <code>{message.document.file_id}</code>")


@router.message(F.video)
async def get_video_file_id(message: Message, config: Config) -> None:
    """Владелец присылает видео практикума боту — бот отвечает file_id для
    practicum_video_file_id в /settings."""
    if not await is_authorized_admin(message.from_user.id, config):
        return
    await message.reply(f"file_id: <code>{message.video.file_id}</code>")
```

на:

```python
@router.message(F.document)
async def get_file_id(message: Message, config: Config) -> None:
    """Владелец присылает PDF — если активно редактирование book_file_id/
    practicum_workbook_file_id, файл добавляется в список; иначе бот просто
    отвечает file_id текстом для ручной вставки в /settings."""
    if not await is_authorized_admin(message.from_user.id, config):
        return
    file_id = message.document.file_id
    if await _try_append_to_pending(message, file_id, _DOCUMENT_SETTINGS):
        return
    await message.reply(f"file_id: <code>{file_id}</code>")


@router.message(F.video)
async def get_video_file_id(message: Message, config: Config) -> None:
    """Владелец присылает видео практикума — если активно редактирование
    practicum_video_file_id, видео добавляется в список; иначе бот отвечает
    file_id текстом."""
    if not await is_authorized_admin(message.from_user.id, config):
        return
    file_id = message.video.file_id
    if await _try_append_to_pending(message, file_id, _VIDEO_SETTINGS):
        return
    await message.reply(f"file_id: <code>{file_id}</code>")
```

- [ ] **Step 4: Проверить импорт**

Run: `python -c "import handlers.admin"`
Expected: без ошибок

- [ ] **Step 5: Запустить полный набор тестов (регрессия)**

Run: `pytest -v`
Expected: PASS

- [ ] **Step 6: Ручная проверка**

1. `/settings` → «📓 File ID рабочей тетради» → отправить боту реальный PDF-файл — ожидать «Добавлено (1): 📓 File ID рабочей тетради» (файл добавился напрямую, без копирования file_id)
2. Отправить второй PDF — ожидать «Добавлено (2): ...»
3. Отправить видео, пока всё ещё активно редактирование тетради (PDF-настройка) — ожидать, что видео НЕ добавится в тетрадь (`_VIDEO_SETTINGS` не пересекается с `practicum_workbook_file_id`), бот должен ответить обычным `file_id: <video_file_id>`
4. Нажать «Готово», без активного pending edit отправить PDF — ожидать старое поведение: просто `file_id: <code>...</code>`

- [ ] **Step 7: Commit**

```bash
git add handlers/admin.py
git commit -m "feat: приём файлов boтом добавляет их в активную multi-настройку"
```

---

### Task 4: Доставка — цикл по списку файлов

**Files:**
- Modify: `payments/delivery.py`

**Interfaces:**
- Consumes: `services.settings.get_file_list` (Task 1)

**Примечание:** `payments/delivery.py` не покрыт автотестами в этом проекте (нужен реальный `Bot` для `send_document`/`send_video`) — проверка вручную через `/redeliver`.

- [ ] **Step 1: Обновить `_deliver_practicum`**

Заменить:

```python
    workbook_file_id = await settings.get_str("practicum_workbook_file_id")
    if workbook_file_id:
        await bot.send_document(purchase.user_tg_id, workbook_file_id, protect_content=True)
    else:
        logger.error(
            "practicum_workbook_file_id не задан в /settings, не могу отправить тетрадь purchase=%s",
            purchase.id,
        )

    # file_id приоритетен над url: как только видео будет загружено в self-hosted
    # Bot API (снимает лимит 50 МБ облачного API) и file_id вписан в /settings,
    # доставка сама переключится с ссылки на нативный файл — без правок кода.
    video_file_id = await settings.get_str("practicum_video_file_id")
    video_url = await settings.get_str("practicum_video_url")
    if video_file_id:
        await bot.send_video(purchase.user_tg_id, video_file_id, protect_content=True)
    elif video_url:
```

на:

```python
    workbook_file_ids = await settings.get_file_list("practicum_workbook_file_id")
    if workbook_file_ids:
        for file_id in workbook_file_ids:
            await bot.send_document(purchase.user_tg_id, file_id, protect_content=True)
    else:
        logger.error(
            "practicum_workbook_file_id не задан в /settings, не могу отправить тетрадь purchase=%s",
            purchase.id,
        )

    # file_id приоритетен над url: как только видео будет загружено в self-hosted
    # Bot API (снимает лимит 50 МБ облачного API) и file_id вписан в /settings,
    # доставка сама переключится с ссылки на нативный файл — без правок кода.
    video_file_ids = await settings.get_file_list("practicum_video_file_id")
    video_url = await settings.get_str("practicum_video_url")
    if video_file_ids:
        for file_id in video_file_ids:
            await bot.send_video(purchase.user_tg_id, file_id, protect_content=True)
    elif video_url:
```

- [ ] **Step 2: Обновить `_deliver_book`**

Заменить:

```python
async def _deliver_book(bot: Bot, config: Config, purchase: Purchase) -> bool:
    available = await get_available_products(purchase.user_tg_id)
    await bot.send_message(purchase.user_tg_id, TEXTS["M8.3"],
                           reply_markup=after_product_kb(BOOK, available, config.webhook_base_url))
    book_file_id = await settings.get_str("book_file_id")
    if not book_file_id:
        logger.error("book_file_id не задан в /settings, не могу отправить файл purchase=%s",
                     purchase.id)
        return False
    await bot.send_document(purchase.user_tg_id, book_file_id, protect_content=True)
    return True
```

на:

```python
async def _deliver_book(bot: Bot, config: Config, purchase: Purchase) -> bool:
    available = await get_available_products(purchase.user_tg_id)
    await bot.send_message(purchase.user_tg_id, TEXTS["M8.3"],
                           reply_markup=after_product_kb(BOOK, available, config.webhook_base_url))
    book_file_ids = await settings.get_file_list("book_file_id")
    if not book_file_ids:
        logger.error("book_file_id не задан в /settings, не могу отправить файл purchase=%s",
                     purchase.id)
        return False
    for file_id in book_file_ids:
        await bot.send_document(purchase.user_tg_id, file_id, protect_content=True)
    return True
```

- [ ] **Step 3: Запустить полный набор тестов (регрессия)**

Run: `pytest -v`
Expected: PASS

- [ ] **Step 4: Ручная проверка**

1. Через `/settings` загрузить 2 PDF в «📄 File ID книги» (см. Task 3, Step 6)
2. Найти в БД любую свою оплаченную покупку книги (или создать тестовую) и выполнить `/redeliver <purchase_id>`
3. Ожидать: приходят ОБА PDF-файла отдельными сообщениями
4. Повторить для тетради практикума с 2 файлами через `/redeliver` на покупке практикума

- [ ] **Step 5: Commit**

```bash
git add payments/delivery.py
git commit -m "feat: доставка книги/тетради/видео практикума циклом по списку файлов"
```

---

### Task 5: Деплой и сквозная проверка на сервере

**Files:** нет новых — деплой на Selectel VDS (139.100.204.242, `/opt/neurocode-bot`, systemd-юнит `neurocode-bot.service`). Миграция БД не нужна — `bot_settings.value` уже существующая TEXT-колонка, схема не меняется.

- [ ] **Step 1: Запушить в GitHub**

```bash
git push origin master
```

- [ ] **Step 2: Обновить код на сервере**

```bash
ssh -i ~/.ssh/id_ed25519_selectel_neurocode root@139.100.204.242 "cd /opt/neurocode-bot && git pull"
```

- [ ] **Step 3: Перезапустить сервис**

```bash
ssh -i ~/.ssh/id_ed25519_selectel_neurocode root@139.100.204.242 "systemctl restart neurocode-bot.service && sleep 2 && systemctl is-active neurocode-bot.service"
```

Expected: `active`

- [ ] **Step 4: Проверить логи на ошибки после рестарта**

```bash
ssh -i ~/.ssh/id_ed25519_selectel_neurocode root@139.100.204.242 "journalctl -u neurocode-bot.service --since '1 minute ago' --no-pager | grep -iE 'error|exception'"
```

Expected: пусто

- [ ] **Step 5: Сквозная ручная проверка в Telegram**

Повторить шаги ручной проверки из Task 2 (Step 8), Task 3 (Step 6) и Task 4 (Step 4) уже на боевом боте `@neurocode_m_bot`, с реальными PDF/видео файлами книги и практикума.
