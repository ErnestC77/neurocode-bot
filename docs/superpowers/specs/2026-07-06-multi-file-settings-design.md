# Несколько файлов на продукт (книга/тетрадь/видео) — дизайн

## Проблема

Сейчас каждая файловая настройка (`book_file_id`, `practicum_workbook_file_id`,
`practicum_video_file_id`) хранит ровно один `file_id` — продукт может
состоять только из одного файла. Нужно уметь прикреплять к выдаче несколько
файлов сразу (например, книга + бонусные материалы).

## 1. Данные и хранилище

Новой таблицы не нужно — `bot_settings.value` остаётся простой строкой
(`VARCHAR(512)`). Для многофайловых настроек несколько `file_id` хранятся
через перенос строки в том же поле; парсинг — на стороне Python
(`value.split("\n")`, пустые строки отфильтровываются).

Существующие продовые значения (один `file_id` без переносов) автоматически
читаются как список из одного элемента — миграция БД не требуется.

`services/settings.py::SettingSpec` получает новое поле:

```python
multi: bool = False
```

`multi=True` выставляется только для трёх настроек:
- `book_file_id`
- `practicum_workbook_file_id`
- `practicum_video_file_id`

`practicum_video_url` остаётся `multi=False` — это текстовая ссылка-фолбэк на
случай отсутствия файла, а не сам файл.

Новые функции в `services/settings.py`:

```python
async def get_file_list(key: str) -> list[str]:
    """Для multi-настроек: список file_id (пустой список, если не задано)."""
    raw = await get_str(key)
    return [line.strip() for line in raw.splitlines() if line.strip()]


async def add_file_id(key: str, file_id: str) -> int:
    """Добавляет file_id в конец списка. Возвращает новую длину списка."""
    current = await get_file_list(key)
    current.append(file_id)
    await crud.set_setting_value(key, "\n".join(current))
    return len(current)
```

## 2. Загрузка через `/settings`

**Меню (`_menu_kb` в `handlers/settings_admin.py`):** для `multi`-настроек
показываем не сырое значение, а количество файлов — «📄 File ID книги: 3
файла» (склонение можно не усложнять: «N файлов» всегда, кроме 0 — «не
задано», как и для обычных настроек).

**Открытие редактирования (`edit_setting`):** для `multi`-настроек текст
приглашения другой: «Пришли файл(ы) для «{label}» (сейчас загружено: N).
Каждый присланный файл добавляется в список.» Кнопки — **«Очистить»**
(`settings:clear:{key}`, стирает список, остаётся в режиме добавления) и
**«Готово»** (`settings:done:{key}`, то же самое действие, что нынешняя
«Отмена» — `clear_pending_setting_edit` + показать меню; для не-multi
настроек кнопка остаётся «Отмена» без изменений).

**Приём файла:** `handlers/admin.py::get_file_id` (для PDF) и
`get_video_file_id` (для видео) — перед тем как ответить сырым `file_id`
текстом (как сейчас), проверяют `crud.get_pending_setting_edit(admin_id)`.
Если есть pending edit на multi-настройку **того же типа файла** (документ →
`book_file_id`/`practicum_workbook_file_id`, видео → `practicum_video_file_id`)
— вызывают `settings.add_file_id(key, file_id)` и отвечают «Добавлено (N/…):
{label}» вместо старого «file_id: `...`». Если pending edit нет или тип не
совпадает — прежнее поведение (просто показать `file_id` текстом) без
изменений.

**Приём голого текста при pending multi-edit:** `handle_setting_input` в
`handlers/settings_admin.py` — если `spec.multi`, воспринимает присланный
текст как «сырой» `file_id` и добавляет через `add_file_id` (не через
`cast_value`/перезапись), не завершая режим редактирования — сохранена
обратная совместимость со старым способом «скопировал `file_id` вручную».
Для не-multi настроек логика не меняется.

## 3. Доставка (`payments/delivery.py`)

- `_deliver_book`: вместо одного `bot.send_document(book_file_id)` —
  `for file_id in await settings.get_file_list("book_file_id"): await
  bot.send_document(...)`. Пустой список = как сейчас «не задано», ядро не
  доставлено.
- `_deliver_practicum` (тетрадь): аналогично циклом по
  `practicum_workbook_file_id`.
- `_deliver_practicum` (видео): приоритет сохраняется — если список
  `practicum_video_file_id` не пуст, шлём все видео из списка; если пуст —
  как и сейчас, показываем кнопку-ссылку на `practicum_video_url`.

## Вне рамок (сознательно не делаем)

- Удаление/переупорядочивание ОТДЕЛЬНОГО файла из списка — только «добавить»
  и «очистить всё» (не просили).
- Многофайловость для `practicum_video_url` (ссылка, не файл).
- Загрузка через веб-панель — явно отклонённый вариант, оставляем текущий
  канал (Telegram-чат с ботом).
