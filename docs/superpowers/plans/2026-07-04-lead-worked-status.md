# Статус «Отработан» для лидов — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Дать админ-панели возможность отмечать лида как «отработан» и фильтровать список лидов по этому статусу.

**Architecture:** Новая nullable-колонка `Lead.worked_at` (`NULL` = новый) по той же схеме, что уже используется в проекте для `paid_at`/`delivered_at`/`exported_at`. Один toggle-эндпоинт на бэкенде, фильтрация — чисто на клиенте (данные и так грузятся целиком одним запросом).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async + asyncpg, React + TypeScript + Vite.

## Global Constraints

- Каждая DB-функция открывает свою сессию через `db.database.get_sessionmaker()`.
- Таблица `leads` уже существует в проде — новая колонка добавляется через ручную ALTER-миграцию в `db/database.py::_MIGRATIONS`, `create_all()` её не создаст.
- Доступ к `/api/admin/*` — только через существующий `Depends(current_admin)` на уровне роутера (не трогать).
- Фильтрация лидов по статусу — только на клиенте, без нового query-параметра на бэкенде (v1-масштаб, данные уже грузятся целиком).
- Тесты: HTTP-слой и `db/crud.py` — pytest (`asyncio_mode = auto`, sqlite-в-памяти, фикстура `full_db` из `tests/conftest.py`). Frontend: `npm run build` (TypeScript) + `npm test` (vitest regression на `resolveScreen`) — компоненты в этом проекте не покрываются `@testing-library/react`.

---

### Task 1: Колонка `Lead.worked_at` и `crud.toggle_lead_worked`

**Files:**
- Modify: `db/models.py:100-108` (класс `Lead`)
- Modify: `db/database.py:27-29` (`_MIGRATIONS`)
- Modify: `db/crud.py` — добавить `toggle_lead_worked`
- Test: `tests/test_lead_worked_crud.py`

**Interfaces:**
- Produces: `db.crud.toggle_lead_worked(tg_id: int) -> Lead | None`
- Consumes: `full_db` fixture (`tests/conftest.py`, уже существует), `db.crud.get_or_create_user`, `db.crud.create_lead` (уже существуют)

- [ ] **Step 1: Написать падающие тесты**

Создать `tests/test_lead_worked_crud.py`:

```python
"""db/crud.py::toggle_lead_worked — переключение статуса «отработан» у лида."""
from db import crud


async def test_toggle_lead_worked_sets_timestamp_when_new(full_db):
    await crud.get_or_create_user(1)
    await crud.create_lead(1, "a@b.com")

    lead = await crud.toggle_lead_worked(1)

    assert lead is not None
    assert lead.worked_at is not None


async def test_toggle_lead_worked_clears_timestamp_when_already_worked(full_db):
    await crud.get_or_create_user(1)
    await crud.create_lead(1, "a@b.com")
    await crud.toggle_lead_worked(1)

    lead = await crud.toggle_lead_worked(1)

    assert lead is not None
    assert lead.worked_at is None


async def test_toggle_lead_worked_returns_none_for_unknown_lead(full_db):
    assert await crud.toggle_lead_worked(999) is None
```

- [ ] **Step 2: Запустить тесты и убедиться, что падают**

Run: `pytest tests/test_lead_worked_crud.py -v`
Expected: FAIL — `AttributeError: module 'db.crud' has no attribute 'toggle_lead_worked'`

- [ ] **Step 3: Добавить колонку в модель**

В `db/models.py` найти класс `Lead`:

```python
class Lead(Base):
    """Заявка на бесплатную консультацию — одна на пользователя."""
    __tablename__ = "leads"

    user_tg_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.tg_id"), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

Добавить `worked_at` после `exported_at`:

```python
class Lead(Base):
    """Заявка на бесплатную консультацию — одна на пользователя."""
    __tablename__ = "leads"

    user_tg_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.tg_id"), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    worked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 4: Добавить ручную миграцию для прода**

В `db/database.py` найти:

```python
_MIGRATIONS: list[str] = [
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS email VARCHAR(255)",
]
```

Заменить на:

```python
_MIGRATIONS: list[str] = [
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS email VARCHAR(255)",
    "ALTER TABLE leads ADD COLUMN IF NOT EXISTS worked_at TIMESTAMPTZ",
]
```

- [ ] **Step 5: Добавить `crud.toggle_lead_worked`**

В `db/crud.py` добавить сразу после `create_lead` (перед `has_lead`):

```python
async def toggle_lead_worked(tg_id: int) -> Lead | None:
    """Переключает статус «отработан». None, если лида с таким tg_id нет."""
    async with get_sessionmaker()() as session:
        lead = await session.get(Lead, tg_id)
        if lead is None:
            return None
        lead.worked_at = None if lead.worked_at is not None else utcnow()
        await session.commit()
        await session.refresh(lead)
        return lead
```

- [ ] **Step 6: Запустить тесты и убедиться, что проходят**

Run: `pytest tests/test_lead_worked_crud.py -v`
Expected: PASS (3 passed)

- [ ] **Step 7: Запустить полный набор тестов**

Run: `pytest -v`
Expected: PASS (весь проект)

- [ ] **Step 8: Commit**

```bash
git add db/models.py db/database.py db/crud.py tests/test_lead_worked_crud.py
git commit -m "feat: добавить Lead.worked_at и crud.toggle_lead_worked"
```

---

### Task 2: `POST /api/admin/leads/{tg_id}/worked`

**Files:**
- Modify: `api/routers/admin.py` — `LeadOut.worked_at`, helper `_lead_out`, новый эндпоинт
- Test: `tests/test_admin_api.py`

**Interfaces:**
- Consumes: `db.crud.toggle_lead_worked` (Task 1), `db.crud.get_user` (уже существует)
- Produces: HTTP `POST /api/admin/leads/{tg_id}/worked` → `LeadOut` (200) или 404, если лида нет

- [ ] **Step 1: Написать падающие тесты**

В `tests/test_admin_api.py` добавить в конец файла:

```python
def test_toggle_lead_worked_flips_status_and_back():
    client, headers = _admin_client_with_username(830, "lead_toggle")
    with client:
        client.post("/api/funnel/consult/book", headers=headers)
        client.post(
            "/api/funnel/consult/email", headers=headers, json={"email": "toggle@example.com"},
        )

        first = client.post("/api/admin/leads/830/worked", headers=headers)
        assert first.status_code == 200
        assert first.json()["worked_at"] is not None

        second = client.post("/api/admin/leads/830/worked", headers=headers)
        assert second.status_code == 200
        assert second.json()["worked_at"] is None


def test_toggle_lead_worked_404_for_unknown_lead():
    client, headers = _admin_client(831)
    with client:
        response = client.post("/api/admin/leads/999999/worked", headers=headers)
    assert response.status_code == 404


def test_toggle_lead_worked_rejected_for_non_admin():
    client, headers = _client(832)
    with client:
        response = client.post("/api/admin/leads/832/worked", headers=headers)
    assert response.status_code == 403
```

- [ ] **Step 2: Запустить тесты и убедиться, что падают**

Run: `pytest tests/test_admin_api.py -v -k toggle_lead_worked`
Expected: FAIL — все три теста падают с 404 (эндпоинта `/api/admin/leads/{tg_id}/worked` ещё нет)

- [ ] **Step 3: Добавить `worked_at` в `LeadOut` и эндпоинт**

В `api/routers/admin.py` заменить:

```python
class LeadOut(BaseModel):
    tg_id: int
    username: str | None
    email: str | None
    created_at: datetime
```

на:

```python
class LeadOut(BaseModel):
    tg_id: int
    username: str | None
    email: str | None
    worked_at: datetime | None
    created_at: datetime
```

Заменить:

```python
async def _leads_out() -> list[LeadOut]:
    # crud.list_leads() сортирует по возрастанию (для CSV-экспорта /export_leads,
    # где это уже устоявшийся порядок) — для панели разворачиваем в свежие сверху,
    # как у purchases/users, не трогая сам crud (не ломаем существующий экспорт).
    leads = sorted(await crud.list_leads(), key=lambda pair: pair[0].created_at, reverse=True)
    return [
        LeadOut(tg_id=lead.user_tg_id, username=user.username if user else None,
               email=lead.email, created_at=lead.created_at)
        for lead, user in leads
    ]
```

на:

```python
def _lead_out(lead: Lead, user: User | None) -> LeadOut:
    return LeadOut(
        tg_id=lead.user_tg_id, username=user.username if user else None,
        email=lead.email, worked_at=lead.worked_at, created_at=lead.created_at,
    )


async def _leads_out() -> list[LeadOut]:
    # crud.list_leads() сортирует по возрастанию (для CSV-экспорта /export_leads,
    # где это уже устоявшийся порядок) — для панели разворачиваем в свежие сверху,
    # как у purchases/users, не трогая сам crud (не ломаем существующий экспорт).
    leads = sorted(await crud.list_leads(), key=lambda pair: pair[0].created_at, reverse=True)
    return [_lead_out(lead, user) for lead, user in leads]
```

Добавить импорт моделей для типов в начало файла (после `from db import crud`):

```python
from db.models import Lead, User
```

Добавить `HTTPException` в импорт fastapi:

```python
from fastapi import APIRouter, Depends, HTTPException
```

И новый эндпоинт после `get_leads`:

```python
@router.post("/leads/{tg_id}/worked", response_model=LeadOut)
async def toggle_lead(tg_id: int) -> LeadOut:
    lead = await crud.toggle_lead_worked(tg_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="lead not found")
    user = await crud.get_user(tg_id)
    return _lead_out(lead, user)
```

- [ ] **Step 4: Обновить существующие тесты лидов под новое поле**

В `tests/test_admin_api.py` найти существующий тест `test_leads_returns_joined_user_fields_for_real_lead` и добавить в конец его тела ассерт:

```python
    assert lead["worked_at"] is None
```

(остальные существующие тесты на `/api/admin/leads` не завязаны на конкретные ключи ответа и не требуют правок)

- [ ] **Step 5: Запустить тесты и убедиться, что проходят**

Run: `pytest tests/test_admin_api.py -v`
Expected: PASS (все тесты файла, включая новые)

- [ ] **Step 6: Запустить полный набор тестов**

Run: `pytest -v`
Expected: PASS (весь проект)

- [ ] **Step 7: Commit**

```bash
git add api/routers/admin.py tests/test_admin_api.py
git commit -m "feat: POST /api/admin/leads/{tg_id}/worked, worked_at в LeadOut"
```

---

### Task 3: Колонка «Отработан» в Excel-экспорте лидов

**Files:**
- Modify: `api/routers/admin.py` (`export_leads`)
- Test: `tests/test_admin_api.py`

**Interfaces:**
- Consumes: `LeadOut.worked_at` (Task 2)

- [ ] **Step 1: Написать падающий тест**

В `tests/test_admin_api.py` добавить в конец файла:

```python
def test_leads_export_includes_worked_column():
    client, headers = _admin_client(834)
    with client:
        response = client.get("/api/admin/leads/export", headers=headers)
    assert response.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(response.content))
    ws = wb.active
    assert [cell.value for cell in ws[1]] == ["tg_id", "username", "email", "worked", "created_at"]
```

- [ ] **Step 2: Запустить тест и убедиться, что падает**

Run: `pytest tests/test_admin_api.py -v -k leads_export_includes_worked_column`
Expected: FAIL — заголовок без колонки `worked`

- [ ] **Step 3: Добавить колонку в экспорт**

В `api/routers/admin.py` заменить:

```python
@router.get("/leads/export")
async def export_leads() -> StreamingResponse:
    leads = await _leads_out()
    rows = [[l.tg_id, l.username or "", l.email or "", l.created_at.isoformat()] for l in leads]
    return _xlsx_response(["tg_id", "username", "email", "created_at"], rows, "leads")
```

на:

```python
@router.get("/leads/export")
async def export_leads() -> StreamingResponse:
    leads = await _leads_out()
    rows = [
        [l.tg_id, l.username or "", l.email or "", "Да" if l.worked_at else "Нет", l.created_at.isoformat()]
        for l in leads
    ]
    return _xlsx_response(["tg_id", "username", "email", "worked", "created_at"], rows, "leads")
```

- [ ] **Step 4: Запустить тесты и убедиться, что проходят**

Run: `pytest tests/test_admin_api.py -v`
Expected: PASS (все тесты файла)

- [ ] **Step 5: Запустить полный набор тестов**

Run: `pytest -v`
Expected: PASS (весь проект)

- [ ] **Step 6: Commit**

```bash
git add api/routers/admin.py tests/test_admin_api.py
git commit -m "feat: колонка 'Отработан' в Excel-экспорте лидов"
```

---

### Task 4: Frontend — фильтр и чекбокс в таблице лидов

**Files:**
- Modify: `frontend/src/api/client.ts` — `AdminLead.worked_at`, `adminApi.toggleLeadWorked`
- Modify: `frontend/src/screens/AdminPanel.tsx` — фильтр-переключатель, колонка с чекбоксом

**Interfaces:**
- Consumes: `POST /api/admin/leads/{tg_id}/worked` (Task 2)

- [ ] **Step 1: Обновить `api/client.ts`**

Заменить:

```ts
export interface AdminLead {
  tg_id: number;
  username: string | null;
  email: string | null;
  created_at: string;
}
```

на:

```ts
export interface AdminLead {
  tg_id: number;
  username: string | null;
  email: string | null;
  worked_at: string | null;
  created_at: string;
}
```

В `export const adminApi = { ... }` добавить новый метод (после `getLeads`):

```ts
  toggleLeadWorked: (tgId: number) =>
    request<AdminLead>(`/api/admin/leads/${tgId}/worked`, { method: "POST" }),
```

- [ ] **Step 2: Обновить `AdminPanel.tsx`**

Добавить состояние фильтра (после `const [error, setError] ...`):

```tsx
  const [leadsFilter, setLeadsFilter] = useState<"all" | "new" | "worked">("all");
```

Заменить блок вкладки «Лиды» целиком:

```tsx
      {tab === "leads" && (
        <section>
          <div className="mb-2 flex items-center justify-between">
            <button
              onClick={() => adminApi.exportLeads().catch((err) => setError(errorMessage(err)))}
              className="rounded bg-white/10 px-3 py-1"
            >
              Экспорт в Excel
            </button>
            <div className="flex gap-2">
              <button
                onClick={() => setLeadsFilter("all")}
                className={leadsFilter === "all" ? "font-bold underline" : ""}
              >
                Все
              </button>
              <button
                onClick={() => setLeadsFilter("new")}
                className={leadsFilter === "new" ? "font-bold underline" : ""}
              >
                Новые
              </button>
              <button
                onClick={() => setLeadsFilter("worked")}
                className={leadsFilter === "worked" ? "font-bold underline" : ""}
              >
                Отработанные
              </button>
            </div>
          </div>
          <table className="w-full text-left text-sm">
            <thead>
              <tr>
                <th>Telegram ID</th>
                <th>Username</th>
                <th>Email</th>
                <th>Отработан</th>
                <th>Дата создания</th>
              </tr>
            </thead>
            <tbody>
              {leads
                ?.filter((l) => {
                  if (leadsFilter === "new") return l.worked_at === null;
                  if (leadsFilter === "worked") return l.worked_at !== null;
                  return true;
                })
                .map((l) => (
                  <tr key={l.tg_id}>
                    <td>{l.tg_id}</td>
                    <td>{l.username ?? ""}</td>
                    <td>{l.email ?? ""}</td>
                    <td>
                      <input
                        type="checkbox"
                        checked={l.worked_at !== null}
                        onChange={() =>
                          adminApi
                            .toggleLeadWorked(l.tg_id)
                            .then((updated) =>
                              setLeads((prev) =>
                                prev?.map((x) => (x.tg_id === updated.tg_id ? updated : x)) ?? prev,
                              ),
                            )
                            .catch((err) => setError(errorMessage(err)))
                        }
                      />
                    </td>
                    <td>{formatDateTime(l.created_at)}</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </section>
      )}
```

- [ ] **Step 3: Проверить сборку и типы**

Run: `cd frontend && npm run build`
Expected: `tsc` и `vite build` завершаются без ошибок

- [ ] **Step 4: Запустить существующие vitest-тесты (регрессия)**

Run: `cd frontend && npm test`
Expected: PASS (существующие тесты `resolveScreen.test.ts` не сломаны)

- [ ] **Step 5: Commit**

```bash
cd frontend
git add src/api/client.ts src/screens/AdminPanel.tsx
git commit -m "feat: фильтр и переключатель статуса 'Отработан' для лидов"
```

---

### Task 5: Деплой и ручная проверка

**Files:** нет новых — деплой на Selectel VDS (139.100.204.242, `/opt/neurocode-bot`, systemd-юнит `neurocode-bot.service`)

- [ ] **Step 1: Запушить в GitHub**

```bash
git push origin master
```

- [ ] **Step 2: Обновить код и пересобрать фронтенд на сервере**

```bash
ssh -i ~/.ssh/id_ed25519_selectel_neurocode root@139.100.204.242 "cd /opt/neurocode-bot && git pull && cd frontend && npm ci && npm run build"
```

- [ ] **Step 3: Перезапустить сервис**

```bash
ssh -i ~/.ssh/id_ed25519_selectel_neurocode root@139.100.204.242 "systemctl restart neurocode-bot.service && sleep 2 && systemctl is-active neurocode-bot.service"
```

Expected: `active`

- [ ] **Step 4: Проверить, что миграция применилась**

```bash
ssh -i ~/.ssh/id_ed25519_selectel_neurocode root@139.100.204.242 "sudo -u postgres psql -d neurocode -c '\d leads'"
```

Expected: колонка `worked_at` (timestamp with time zone) присутствует в выводе

- [ ] **Step 5: Ручная проверка в Telegram**

1. Открыть `/admin` → вкладку «Лиды»
2. Проверить, что переключатель «Все / Новые / Отработанные» переключает видимые строки
3. Отметить чекбоксом любой лид как отработанный — строка должна остаться на месте (порядок не меняется), но пропасть из фильтра «Новые» и появиться в «Отработанные»
4. Снять галочку — обратный эффект
5. Экспортировать в Excel — убедиться, что колонка «Отработан» содержит «Да»/«Нет» для соответствующих строк
