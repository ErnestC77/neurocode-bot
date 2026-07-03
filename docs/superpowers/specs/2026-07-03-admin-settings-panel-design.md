# Админ-панель настроек в Telegram — design spec

Дата: 2026-07-03
Статус: approved (ожидает review пользователем перед implementation plan)

## Контекст и цель

Часть операционного конфига бота сейчас живёт в env-переменных Render и требует передеплоя для любого изменения: `BOOK_FILE_ID`, `PRACTICUM_CHANNEL_ID`, цены книги/практикума (сейчас захардкожены в `services/catalog.py`), интервалы напоминаний, `OWNER_CHAT_ID`, `YOOKASSA_SHOP_ID`. Владелец бота (не разработчик) должен уметь менять это сам, без обращения к разработчику и без редеплоя — через сам Telegram-бот, командой `/settings`.

Секреты, необходимые для самого запуска процесса (`BOT_TOKEN`, `DATABASE_URL`, `YOOKASSA_SECRET_KEY`, `PORT`, `WEBHOOK_BASE_URL`), остаются в env — их нельзя редактировать через бота в принципе (например, `DATABASE_URL` нужен ещё до того, как появится доступ к БД, где хранились бы настройки).

## Список настроек, выносимых в панель

| key | Метка | Тип | Дефолт (если в БД пусто) |
|---|---|---|---|
| `book_file_id` | File ID книги | str | `""` |
| `practicum_channel_id` | ID канала практикума | str | `""` |
| `book_price_rub` | Цена книги, ₽ | int | `990` |
| `practicum_price_rub` | Цена практикума, ₽ | int | `2990` |
| `reminder_delay_hours` | Порог бездействия для R1-R6, ч | int | `24` |
| `reminder_check_interval` | Интервал tick'а scheduler'а, сек | int | `300` |
| `owner_chat_id` | Доп. владелец (лиды/оплаты/доступ к панели) | int | не задан |
| `yookassa_shop_id` | ЮKassa shop_id | str | `""` |

Дефолты — те же значения, что сейчас в `.env.example`. На свежем деплое без единого визита в `/settings` бот работает как сегодня.

## Подход к хранению — вариант A (универсальная key-value таблица + типизированный реестр)

Рассмотрены и отклонены:
- **B. Отдельные типизированные колонки** (как `User`/`Purchase`) — типобезопаснее на уровне схемы, но каждая новая настройка = миграция + новый пункт меню руками. Список настроек уже сейчас открытый и будет расти.
- **C. Один JSONB-столбец** — теряется атомарность правки одного поля, тяжелее валидировать по ключу. Хуже A и B по всем параметрам для этой задачи.

Выбран **вариант A**: простая KV-таблица в БД, типизация и валидация — на стороне Python-реестра `services/settings.py`. Добавление новой настройки в будущем = одна строка в реестре, без ALTER TABLE.

## Схема БД

```
BotSetting
  key         TEXT PRIMARY KEY   -- см. таблицу выше
  value       TEXT NOT NULL
  updated_at  TIMESTAMPTZ

AdminPendingEdit
  admin_tg_id  BIGINT PRIMARY KEY
  setting_key  TEXT NOT NULL
  created_at   TIMESTAMPTZ
```

`AdminPendingEdit` **не переиспользует** `users.checkpoint`. Чекпоинт — состояние воронки продаж; «админ сейчас редактирует настройку» — состояние другого слоя (админ теоретически может сам проходить тест как обычный пользователь, и эти два состояния не должны друг другу мешать). Хранится в БД, а не в памяти процесса — переживает рестарт, как и всё остальное состояние в проекте.

## `services/settings.py` — реестр и типизированный доступ

```python
@dataclass(frozen=True)
class SettingSpec:
    key: str
    label: str
    value_type: type       # int | str
    default: str            # хранится как строка, парсится по value_type

SETTINGS: dict[str, SettingSpec]  # 8 записей из таблицы выше

async def get_str(key: str) -> str
async def get_int(key: str) -> int
async def set_value(key: str, raw: str) -> None    # валидирует по value_type, бросает ValueError при мусоре
async def get_effective_owner_chat_id(config: Config) -> int | None
    # БД-значение owner_chat_id, если задано и валидно, иначе config.owner_chat_id (env)
async def get_practicum_chat_id() -> int | str | None
    # get_str("practicum_channel_id") + та же конвертация, что раньше была
    # в Config.practicum_chat_id: пусто → None, только цифры (с "-") → int, иначе строка (@username)
```

Если строки в БД нет — `get_str`/`get_int` отдают дефолт из `SETTINGS[key].default`.

## Безопасность доступа: OWNER_CHAT_ID

Так как `owner_chat_id` теперь редактируется через саму панель, нужна страховка от самоблокировки (опечатался — сам себя лишил доступа):

- **Доступ к `/settings` и `/export_leads`**: `is_authorized_admin(tg_id, config) -> bool` = `tg_id == config.owner_chat_id` (значение из env, всегда действующий запасной вариант) **ИЛИ** `tg_id == текущее значение owner_chat_id из БД`.
- **Куда слать уведомления о новых лидах/оплатах** (`exports/notifier.py`): только одно значение — `get_effective_owner_chat_id()` (БД, если задано, иначе env). Не два получателя — один текущий действующий.

## UX

`/settings` (только `is_authorized_admin`) → инлайн-меню, одна кнопка на настройку, текст кнопки включает текущее значение:

```
📕 Цена книги: 990 ₽
📗 Цена практикума: 2990 ₽
📄 File ID книги: (не задан)
📢 ID канала практикума: (не задан)
⏰ Порог бездействия: 24 ч
🔁 Интервал проверки напоминаний: 300 с
👤 Доп. владелец: (не задан)
🔑 ЮKassa shop_id: 1400988
```

Клик по кнопке (`callback_data="settings:edit:{key}"`):
1. Upsert строки в `AdminPendingEdit(admin_tg_id, setting_key=key)`.
2. Бот отправляет «Пришли новое значение для «{label}» (сейчас: {текущее значение})» + кнопка «Отмена» (`callback_data="settings:cancel"`).

Следующее текстовое сообщение от этого админа (диспетчеризация — см. ниже) валидируется по `SETTINGS[key].value_type`:
- Успех → `settings.set_value(key, raw)`, `AdminPendingEdit` удаляется, бот подтверждает («✅ Цена книги: 990 ₽ → 1490 ₽») и повторно показывает меню.
- Ошибка валидации (например, буквы вместо числа) → «Это не похоже на число. Пришли, пожалуйста, целое число.», `AdminPendingEdit` не трогаем, ждём следующую попытку.

«Отмена» → удаляет `AdminPendingEdit`, возвращает в меню без изменений.

## Рефакторинг: единая точка диспетчеризации свободного текста

**Проблема.** Сейчас `handlers/consult.py` — единственный роутер в проекте с catch-all текстовым хендлером (`F.text & ~F.text.startswith("/")`, для сбора email), и именно поэтому он специально зарегистрирован **последним** в `bot.py` — иначе он перехватил бы команды/сообщения, предназначенные другим роутерам. Если добавить второй независимый catch-all в `admin.py`/`settings_admin.py`, порядок регистрации роутеров станет неочевидно определять, чей обработчик получит апдейт первым — хрупкая и незаметная связность.

**Решение.** Выносим диспетчеризацию свободного текста в новый файл `handlers/text_input.py` — единственный catch-all во всём боте, регистрируется последним в `bot.py` (место, которое сейчас занимает `consult.router`):

```python
@router.message(F.text & ~F.text.startswith("/"))
async def handle_free_text(message: Message, config: Config) -> None:
    tg_id = message.from_user.id
    if await is_authorized_admin(tg_id, config):
        pending = await crud.get_pending_setting_edit(tg_id)
        if pending is not None:
            await settings_admin.handle_setting_input(message, config, pending)
            return
    user = await crud.get_user(tg_id)
    if user is not None and user.checkpoint == checkpoints.AWAITING_EMAIL:
        await consult.handle_email_input(message, config)
        return
    # ни то, ни другое — не наш текст, молчим
```

`handlers/consult.py` оставляет только callback-хендлер `consult:book` (ставит checkpoint) и экспортирует `handle_email_input(message, config)` как обычную функцию — без собственного `@router.message`. Аналогично `handlers/settings_admin.py` экспортирует `handle_setting_input(message, config, pending)`.

## Что меняется в существующем коде (ripple)

- **`services/catalog.py`** — `PRODUCT_PRICE_RUB` (статический dict) заменяется на `await settings.get_int("book_price_rub")` / `get_int("practicum_price_rub")` в местах использования.
- **`keyboards/inline.py`** — `_MENU_LABELS` сейчас строится один раз при импорте модуля со статичной ценой в тексте кнопки. Функции, показывающие цену (`offer_kb`, `smart_menu_kb`, `practicum_buy_kb`, `book_buy_kb`), становятся `async def` и берут цену на момент вызова. Вызовы этих функций в `handlers/menu.py`, `handlers/practicum.py`, `handlers/book.py`, `scheduler.py` — добавляется `await`.
- **`payments/delivery.py`** — `config.book_file_id` / `config.practicum_chat_id` заменяются на `await settings.get_str("book_file_id")` / `await settings.get_practicum_chat_id()`.
- **`payments/webhook.py`, `payments/yookassa_client.py`** — `config.yookassa_shop_id` заменяется на `await settings.get_str("yookassa_shop_id")`; `yookassa_secret_key` остаётся из `config` (env, без изменений).
- **`scheduler.py`** — `config.reminder_delay_hours` / `config.reminder_check_interval` читаются из `settings` **на каждой итерации** цикла `reminder_loop`, а не один раз при старте процесса — правки в `/settings` применяются без передеплоя.
- **`handlers/admin.py`** — проверки `message.from_user.id != config.owner_chat_id` заменяются на `not await is_authorized_admin(...)`; логика `/export_leads` и определения `file_id` не меняется.
- **`exports/notifier.py`** — адресат уведомлений `config.owner_chat_id` заменяется на `await settings.get_effective_owner_chat_id(config)`.
- **`.env.example`, `render.yaml`, `config.py`** — убираются `BOOK_FILE_ID`, `PRACTICUM_CHANNEL_ID`, `REMINDER_DELAY_HOURS`, `REMINDER_CHECK_INTERVAL`, `YOOKASSA_SHOP_ID` (переезжают в БД-настройки); `OWNER_CHAT_ID` остаётся в env как запасной админ.
- **`db/database.py`** — новые таблицы через `Base.metadata.create_all` (обе модели новые, ручная миграция `ALTER TABLE` не нужна).

## Тестирование

- Юнит-тест `services/settings.py`: дефолт при пустой БД; `set_value`+`get_int` round-trip; `ValueError` на нечисловой ввод для int-настроек; `get_effective_owner_chat_id` — приоритет БД над env, откат на env если БД пусто/невалидно.
- Ручная проверка: `/settings` → смена цены книги → сразу видна в кнопке M8.1/M9 без рестарта процесса; смена `book_file_id` → следующая доставка книги использует новый файл; намеренно испорченный `owner_chat_id` через панель — доступ к `/settings` с исходного env-id всё ещё работает.

## Явно вне скоупа

- Групповое/ролевое разграничение прав (несколько разных админов с разными правами) — сейчас один эффективный владелец + один запасной (env). Если понадобится — отдельная задача.
- Валидация `practicum_channel_id`/`yookassa_shop_id` на реальное существование (например, проверка что бот — админ канала) — не проверяется на этапе сохранения, только формат непустой строки.
