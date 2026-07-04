# Статус «Отработан» для лидов в админ-панели — дизайн

## Проблема

В админ-панели (раздел «Лиды») нет способа отметить, что с лидом уже
связались — заявки на консультацию накапливаются без возможности отличить
новые от уже отработанных.

## 1. Данные

В `db/models.py::Lead` добавляется:

```python
worked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

`NULL` = лид новый (не отработан), дата = когда отметили отработанным. Та же
схема, что уже используется в проекте для `Purchase.paid_at/delivered_at` и
`Lead.exported_at` — единообразно, ничего нового не изобретаем.

Таблица `leads` уже существует в проде, `Base.metadata.create_all()` не
добавляет колонки в существующие таблицы — нужна ручная миграция в
`db/database.py::_MIGRATIONS` (в списке уже есть прецедент ровно для этого
случая: `"ALTER TABLE leads ADD COLUMN IF NOT EXISTS email VARCHAR(255)"`):

```python
"ALTER TABLE leads ADD COLUMN IF NOT EXISTS worked_at TIMESTAMPTZ",
```

## 2. Backend

- `db.crud.toggle_lead_worked(tg_id: int) -> Lead` — если `worked_at is None`,
  ставит `utcnow()`, иначе сбрасывает в `None`; возвращает обновлённую запись
  целиком (лид с этим `user_tg_id` всегда существует на момент вызова, так
  как эндпоинт вызывается по строке, уже отрисованной из `list_leads()`).
- `api/routers/admin.py::LeadOut` получает поле `worked_at: datetime | None`.
- Новый эндпоинт `POST /api/admin/leads/{tg_id}/worked` (роутер уже защищён
  `Depends(current_admin)` на уровне router, отдельно навешивать не нужно) —
  вызывает `toggle_lead_worked`, возвращает обновлённый `LeadOut` через
  существующий helper для сборки одного лида (переиспользовать логику
  `_leads_out()`, но для одной строки — понадобится маленький helper
  `_lead_out(lead, user)`, из которого `_leads_out()` тоже может собираться).
- Экспорт лидов в Excel (`GET /api/admin/leads/export`) — колонки
  `["tg_id", "username", "email", "worked", "created_at"]`, где `worked` —
  `"Да"` / `"Нет"` (не сырой timestamp, для читаемости в таблице-эффекте).

## 3. Frontend

`screens/AdminPanel.tsx`, вкладка «Лиды»:

- Локальное состояние `leadsFilter: "all" | "new" | "worked"` (по умолчанию
  `"all"`), три кнопки-переключателя над таблицей.
- Фильтрация — чисто на клиенте (`leads.filter(...)` по `worked_at`), без
  нового query-параметра на бэкенде: данные и так грузятся целиком одним
  запросом (v1-масштаб, без пагинации, см. spec 2026-07-04-admin-panel).
- Новая колонка «Отработан» с чекбоксом (`<input type="checkbox">`,
  `checked={lead.worked_at !== null}`), `onChange` дёргает
  `adminApi.toggleLeadWorked(tg_id)` и подменяет только эту строку в
  `leads`-состоянии результатом ответа (без рефетча всего списка).
- Порядок строк не меняется (по-прежнему `created_at desc`) — фильтр влияет
  только на то, что показано, не на сортировку.
- `api/client.ts`: новый метод `adminApi.toggleLeadWorked(tgId: number):
  Promise<AdminLead>`, `AdminLead` получает поле `worked_at: string | null`.

## Вне рамок (сознательно не делаем)

- Массовое отмечание нескольких лидов сразу — не просили.
- Кто и когда отметил (audit-лог смены статуса) — `worked_at` уже даёт факт
  и время, отдельного лога не нужно.
- Серверная пагинация/фильтрация — не нужна на текущем объёме данных.
