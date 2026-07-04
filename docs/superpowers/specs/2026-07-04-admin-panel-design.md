# Админ-панель в Mini App — дизайн

## Проблема

Сейчас у владельца бота нет способа посмотреть в вебе список лидов, покупок
и пользователей — только `/export_leads` (CSV в чат бота) и `/settings`
(редактирование конфигурации). Нужна веб-панель с тремя разделами и
выгрузкой каждого в Excel, доступная не только владельцу, но и другим
админам.

## 1. Множественные админы

Сейчас авторизация админа (`services/settings.py::is_authorized_admin`)
основана на единственном `owner_chat_id` — либо из `.env`, либо из
DB-настройки "Доп. владелец" (одна запись, перезаписывает друг друга).

**Новое:**
- Таблица `admins` (`db/models.py`): `tg_id BIGINT PRIMARY KEY`, `added_at`,
  `added_by BIGINT NULL`.
- При первом обращении, если таблица пуста, автоматически засеивается
  текущим `config.owner_chat_id` (env) — чтобы никто не потерял доступ при
  миграции.
- `is_authorized_admin(tg_id, config)` переписывается на проверку
  членства в `admins` (плюс запасной вариант — `config.owner_chat_id` из env,
  как и раньше, на случай пустой/повреждённой таблицы).
- Настройка "👤 Доп. владелец" убирается из `services/settings.py::SETTINGS`
  — её заменяет таблица `admins`.
- Команды в `handlers/admin.py`:
  - `/add_admin <tg_id>` — доступна только текущим админам, добавляет строку.
  - `/remove_admin <tg_id>` — то же самое, для удаления.

## 2. Backend API

Новый роутер `api/routers/admin.py`, префикс `/api/admin`, каждый эндпоинт —
`Depends(current_admin)` (уже существует в `api/deps.py`, просто не
используется до сих пор).

- `GET /api/admin/leads` → список: tg_id, username, email, created_at.
- `GET /api/admin/purchases` → список: tg_id, username, product, amount_rub,
  status, paid_at, delivered_at.
- `GET /api/admin/users` → список: tg_id, username, first_name, checkpoint,
  result_type, test_attempt, created_at.
- `GET /api/admin/leads/export`, `/api/admin/purchases/export`,
  `/api/admin/users/export` → тот же набор данных, отдаётся как файл
  `.xlsx` (генерация через `openpyxl`, добавить в `requirements.txt`).

Без пагинации — объём данных (десятки-сотни строк) не требует усложнения.
Новые функции в `db/crud.py`: `list_purchases_with_user()`, `list_users()`
(`list_leads()` уже есть).

## 3. Доступ из бота

В `handlers/admin.py`:
- `/admin` — доступна только админам (`is_authorized_admin`), отправляет
  сообщение с inline-кнопкой Mini App (WebApp button), ведущей на
  `{config.webhook_base_url}/#/admin`.

## 4. Frontend

`App.tsx` сейчас не использует `<Routes>` — просто императивно рендерит
экран воронки на основе `checkpoint`. Меняется на:

```
<Routes>
  <Route path="/admin" element={<AdminPanel />} />
  <Route path="*" element={<FunnelApp />} />  {/* текущая логика App.tsx, вынесена как есть */}
</Routes>
```

Новый экран `screens/AdminPanel.tsx`:
- 3 вкладки: Лиды / Покупки / Пользователи.
- Каждая вкладка — простая таблица (без пагинации, без фильтров — v1).
- Кнопка «Экспорт в Excel» в каждой вкладке: `fetch` с заголовком
  `X-Telegram-Init-Data` → ответ как `blob` → скачивание через временный
  `<a>` с `URL.createObjectURL` (обычная ссылка не подойдёт — нужен кастомный
  заголовок авторизации, а не query-параметр).
- Если сервер вернул 403 (не админ) — показываем текст «Доступ запрещён»
  вместо таблиц.

`frontend/src/api/client.ts` — добавить методы `getLeads`, `getPurchases`,
`getUsers`, `exportLeads`, `exportPurchases`, `exportUsers` (последние три
возвращают `Blob` вместо JSON).

## Вне рамок (сознательно не делаем)

- Пагинация/фильтры/поиск в таблицах — объём данных не требует.
- Права разного уровня между админами (все админы видят и могут всё
  одинаково) — не просили.
- Отдельный веб-логин вне Telegram — панель работает только внутри Mini App.
