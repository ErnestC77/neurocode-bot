# «Назад / другие варианты» на экранах покупки — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Добавить кнопку «← Другие варианты» на экраны «Практикум», «Книга» (`ProductDetail.tsx`) и «Консультация» (`ConsultDetail.tsx`), чтобы пользователь мог вернуться к списку продуктов вместо тупика.

**Architecture:** Новый backend-эндпоинт `POST /api/funnel/back` переводит checkpoint из `practicum_viewed`/`book_viewed`/`consult_viewed` в `idle` (no-op из любого другого чекпоинта). `idle` — уже существующий чекпоинт: `Offer.tsx` на нём и так показывает короткий текст M9 со списком оставшихся продуктов, поэтому `resolveScreen.ts` и `Offer.tsx` не меняются. Три экрана фронтенда получают проп `onBack`, зовущий этот эндпоинт через `runAction` в `App.tsx` — тот же паттерн, что и у всех остальных действий воронки.

**Tech Stack:** FastAPI (backend), pytest + `TestClient` (backend-тесты), React + TypeScript (frontend), vitest (frontend-тесты, не требуются для этой задачи — см. Global Constraints).

## Global Constraints

- Текст кнопки — ровно `"← Другие варианты"` (константа `BACK_TO_OFFER_LABEL`).
- `POST /api/funnel/back` переводит в `idle` **только** из `practicum_viewed` / `book_viewed` / `consult_viewed`; из любого другого чекпоинта — no-op (checkpoint не меняется).
- В `ProductDetail.tsx` кнопка «назад» видна **только когда `!waiting`** — во время «Проверяем оплату…» она скрыта.
- В `ConsultDetail.tsx` кнопка «назад» видна всегда (там нет состояния ожидания).
- `ConsultEmailInput.tsx`, `Offer.tsx`, `resolveScreen.ts` — не трогаем, вне скоупа.
- Backend-тесты пишутся по паттерну `tests/test_funnel_api.py` (TDD: тест → убедиться что падает → реализация → убедиться что проходит).
- Frontend-изменения в этой задаче — без новых unit-тестов (в кодовой базе нет прецедента юнит-тестов на JSX-экраны, кроме чистой функции `resolveScreen`; проверка — `npm run build` на типы + ручной прогон, как в верификации других 2b-задач).

---

### Task 1: Backend — эндпоинт `POST /api/funnel/back`

**Files:**
- Modify: `api/routers/funnel.py:42-49` (добавить множество чекпоинтов рядом с `_PRODUCT_CHECKPOINT`), конец файла (добавить эндпоинт)
- Test: `tests/test_funnel_api.py` (добавить тесты в конец файла)

**Interfaces:**
- Consumes: `services.checkpoints.PRACTICUM_VIEWED/BOOK_VIEWED/CONSULT_VIEWED/IDLE` (уже существуют, `api/routers/funnel.py:22` уже импортирует `checkpoints`), `crud.get_user`, `crud.set_checkpoint`, `_build_state` (все уже определены в этом файле).
- Produces: `POST /api/funnel/back` → `FunnelStateOut` (та же форма, что у остальных эндпоинтов воронки — используется Task 2's `api.goBack()`).

- [ ] **Step 1: Написать падающие тесты**

Добавить в конец `tests/test_funnel_api.py`:

```python
def test_back_from_practicum_viewed_sets_idle():
    client, headers = _client(718)
    with client:
        client.post("/api/funnel/consent", headers=headers)
        for q, s in enumerate([2, 2, 0, 1, 0, 2, 1], start=1):
            client.post("/api/funnel/answers", headers=headers, json={"question_no": q, "score": s})
        client.post("/api/funnel/product/practicum/view", headers=headers)
        response = client.post("/api/funnel/back", headers=headers)
    assert response.status_code == 200
    assert response.json()["checkpoint"] == "idle"


def test_back_from_consult_viewed_sets_idle():
    client, headers = _client(719)
    with client:
        client.post("/api/funnel/consent", headers=headers)
        for q, s in enumerate([2, 2, 0, 1, 0, 2, 1], start=1):
            client.post("/api/funnel/answers", headers=headers, json={"question_no": q, "score": s})
        client.post("/api/funnel/consult/view", headers=headers)
        response = client.post("/api/funnel/back", headers=headers)
    assert response.json()["checkpoint"] == "idle"


def test_back_from_unrelated_checkpoint_is_a_noop():
    client, headers = _client(720)
    with client:
        client.post("/api/funnel/consult/book", headers=headers)  # -> awaiting_email
        response = client.post("/api/funnel/back", headers=headers)
    assert response.status_code == 200
    assert response.json()["checkpoint"] == "awaiting_email"  # не сдвинулся на idle
```

- [ ] **Step 2: Убедиться, что тесты падают**

Run: `python -m pytest tests/test_funnel_api.py -k back -v`
Expected: FAIL — `404 Not Found` (эндпоинт `/api/funnel/back` ещё не существует).

- [ ] **Step 3: Реализовать эндпоинт**

В `api/routers/funnel.py` заменить блок (строки 42-49):

```python
_PRODUCT_CHECKPOINT: dict[str, str] = {
    "book": checkpoints.BOOK_VIEWED,
    "practicum": checkpoints.PRACTICUM_VIEWED,
}
_PRODUCT_LABELS: dict[str, str] = {
    "book": "Книга «Целеполагание»",
    "practicum": "Практикум «Найди свой код»",
}
```

на:

```python
_PRODUCT_CHECKPOINT: dict[str, str] = {
    "book": checkpoints.BOOK_VIEWED,
    "practicum": checkpoints.PRACTICUM_VIEWED,
}
_PRODUCT_LABELS: dict[str, str] = {
    "book": "Книга «Целеполагание»",
    "practicum": "Практикум «Найди свой код»",
}
_BACK_ELIGIBLE_CHECKPOINTS: set[str] = {
    checkpoints.PRACTICUM_VIEWED,
    checkpoints.BOOK_VIEWED,
    checkpoints.CONSULT_VIEWED,
}
```

Добавить в конец файла (после `submit_consult_email`, после строки 199):

```python


@router.post("/back")
async def go_back(tg_id: int = Depends(current_client)) -> FunnelStateOut:
    user = await crud.get_user(tg_id)
    if user is not None and user.checkpoint in _BACK_ELIGIBLE_CHECKPOINTS:
        await crud.set_checkpoint(tg_id, checkpoints.IDLE)
    return await _build_state(tg_id)
```

- [ ] **Step 4: Убедиться, что тесты проходят**

Run: `python -m pytest tests/test_funnel_api.py -k back -v`
Expected: PASS (3 теста)

Также прогнать весь файл, чтобы убедиться, что ничего не сломано:

Run: `python -m pytest tests/test_funnel_api.py -v`
Expected: все тесты PASS

- [ ] **Step 5: Commit**

```bash
git add api/routers/funnel.py tests/test_funnel_api.py
git commit -m "feat: добавить POST /api/funnel/back — возврат из product/consult-detail к офферу"
```

---

### Task 2: Frontend — API-клиент и текст кнопки

**Files:**
- Modify: `frontend/src/api/client.ts:94-95` (добавить метод `goBack`)
- Modify: `frontend/src/content/texts.ts` (конец файла — добавить константу)

**Interfaces:**
- Consumes: `postFunnel` (уже определён в `client.ts:74-80`)
- Produces: `api.goBack(): Promise<FunnelState>` (используется в Task 5, `App.tsx`), `BACK_TO_OFFER_LABEL: string` (используется в Task 3 и Task 4)

- [ ] **Step 1: Добавить метод в API-клиент**

В `frontend/src/api/client.ts` заменить:

```typescript
  bookConsult: () => postFunnel("consult/book"),
  viewConsult: () => postFunnel("consult/view"),
```

на:

```typescript
  bookConsult: () => postFunnel("consult/book"),
  viewConsult: () => postFunnel("consult/view"),
  goBack: () => postFunnel("back"),
```

- [ ] **Step 2: Добавить текстовую константу**

В конец `frontend/src/content/texts.ts` (после `CONSULT_EMAIL_INVALID`) добавить:

```typescript

export const BACK_TO_OFFER_LABEL = "← Другие варианты";
```

- [ ] **Step 3: Проверить типы**

Run: `cd frontend && npx tsc --noEmit`
Expected: без ошибок (новый экспорт и метод пока никем не используются — TS это не считает ошибкой)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/content/texts.ts
git commit -m "feat: добавить api.goBack и BACK_TO_OFFER_LABEL"
```

---

### Task 3: Frontend — кнопка «назад» в `ProductDetail.tsx`

**Files:**
- Modify: `frontend/src/screens/ProductDetail.tsx`

**Interfaces:**
- Consumes: `BACK_TO_OFFER_LABEL` (из Task 2), существующий `waiting` state (`ProductDetail.tsx:18`)
- Produces: новый проп `onBack: () => void` на `ProductDetail` (используется в Task 5, `App.tsx`)

- [ ] **Step 1: Добавить проп и импорт**

В `frontend/src/screens/ProductDetail.tsx` заменить:

```typescript
import { BUY_BUTTON_LABEL, PRODUCT_DETAIL_TEXTS } from "@/content/texts";
```

на:

```typescript
import { BACK_TO_OFFER_LABEL, BUY_BUTTON_LABEL, PRODUCT_DETAIL_TEXTS } from "@/content/texts";
```

Заменить:

```typescript
interface Props {
  product: Product;
  price: number;
  onPaymentSettled: (state: FunnelState) => void;
}
```

на:

```typescript
interface Props {
  product: Product;
  price: number;
  onPaymentSettled: (state: FunnelState) => void;
  onBack: () => void;
}
```

Заменить сигнатуру компонента:

```typescript
export default function ProductDetail({ product, price, onPaymentSettled }: Props) {
```

на:

```typescript
export default function ProductDetail({ product, price, onPaymentSettled, onBack }: Props) {
```

- [ ] **Step 2: Добавить кнопку в разметку (только когда `!waiting`)**

Заменить блок (текущие строки 117-124):

```typescript
      ) : (
        <button
          onClick={handleBuy}
          className="mt-6 w-full rounded-xl bg-gold py-3 text-center font-semibold text-navy"
        >
          {`${BUY_BUTTON_LABEL[product]} за ${price} ₽`}
        </button>
      )}
```

на:

```typescript
      ) : (
        <>
          <button
            onClick={handleBuy}
            className="mt-6 w-full rounded-xl bg-gold py-3 text-center font-semibold text-navy"
          >
            {`${BUY_BUTTON_LABEL[product]} за ${price} ₽`}
          </button>
          <button onClick={onBack} className="mt-4 text-center text-sm text-gold/70 underline">
            {BACK_TO_OFFER_LABEL}
          </button>
        </>
      )}
```

- [ ] **Step 3: Проверить типы**

Run: `cd frontend && npx tsc --noEmit`
Expected: ошибка — `App.tsx` вызывает `<ProductDetail>` без обязательного пропа `onBack` (это ожидаемо, до Task 5). Убедиться, что ошибка ровно в этом — про недостающий `onBack` в `App.tsx`, а не где-то ещё.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/screens/ProductDetail.tsx
git commit -m "feat: кнопка «Другие варианты» на ProductDetail (скрыта во время ожидания оплаты)"
```

---

### Task 4: Frontend — кнопка «назад» в `ConsultDetail.tsx`

**Files:**
- Modify: `frontend/src/screens/ConsultDetail.tsx`

**Interfaces:**
- Consumes: `BACK_TO_OFFER_LABEL` (из Task 2)
- Produces: новый проп `onBack: () => void` на `ConsultDetail` (используется в Task 5, `App.tsx`)

- [ ] **Step 1: Переписать файл целиком**

Заменить содержимое `frontend/src/screens/ConsultDetail.tsx` на:

```typescript
import { BACK_TO_OFFER_LABEL, CONSULT_BOOK_BUTTON_LABEL, CONSULT_INTRO_TEXT } from "@/content/texts";

interface Props {
  onBook: () => void;
  onBack: () => void;
}

export default function ConsultDetail({ onBook, onBack }: Props) {
  return (
    <div className="flex min-h-screen flex-col justify-between bg-navy p-6 text-white">
      <div className="flex-1 overflow-y-auto whitespace-pre-line text-[15px] leading-relaxed">
        {CONSULT_INTRO_TEXT}
      </div>
      <div>
        <button
          onClick={onBook}
          className="mt-6 w-full rounded-xl bg-gold py-3 text-center font-semibold text-navy"
        >
          {CONSULT_BOOK_BUTTON_LABEL}
        </button>
        <button onClick={onBack} className="mt-4 w-full text-center text-sm text-gold/70 underline">
          {BACK_TO_OFFER_LABEL}
        </button>
      </div>
    </div>
  );
}
```

(Обёртка `<div>` вокруг двух кнопок нужна, т.к. родительский контейнер — `flex justify-between` с двумя детьми: текст и кнопка; теперь второй ребёнок — блок из двух кнопок.)

- [ ] **Step 2: Проверить типы**

Run: `cd frontend && npx tsc --noEmit`
Expected: ошибка — `App.tsx` вызывает `<ConsultDetail>` без обязательного пропа `onBack` (ожидаемо, до Task 5).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/screens/ConsultDetail.tsx
git commit -m "feat: кнопка «Другие варианты» на ConsultDetail"
```

---

### Task 5: Frontend — связать всё в `App.tsx` и проверить вручную

**Files:**
- Modify: `frontend/src/App.tsx:82-88`

**Interfaces:**
- Consumes: `api.goBack` (Task 2), `onBack` пропы `ProductDetail`/`ConsultDetail` (Task 3, Task 4), существующий `runAction` (`App.tsx:53-55`)
- Produces: рабочая фича целиком — конечная точка задачи, ничего дальше на неё не полагается

- [ ] **Step 1: Пробросить `onBack`**

В `frontend/src/App.tsx` заменить:

```typescript
    case "product-detail": {
      const product = state.checkpoint === "book_viewed" ? "book" : "practicum";
      const price = product === "book" ? state.book_price_rub : state.practicum_price_rub;
      return <ProductDetail product={product} price={price} onPaymentSettled={setState} />;
    }
    case "consult-detail":
      return <ConsultDetail onBook={() => runAction(api.bookConsult)} />;
```

на:

```typescript
    case "product-detail": {
      const product = state.checkpoint === "book_viewed" ? "book" : "practicum";
      const price = product === "book" ? state.book_price_rub : state.practicum_price_rub;
      return (
        <ProductDetail
          product={product}
          price={price}
          onPaymentSettled={setState}
          onBack={() => runAction(api.goBack)}
        />
      );
    }
    case "consult-detail":
      return (
        <ConsultDetail onBook={() => runAction(api.bookConsult)} onBack={() => runAction(api.goBack)} />
      );
```

- [ ] **Step 2: Проверить типы и собрать фронт**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: без ошибок, сборка проходит.

- [ ] **Step 3: Прогнать существующие фронт-тесты (регрессия)**

Run: `cd frontend && npm run test`
Expected: PASS (`resolveScreen.test.ts` — новых веток эта задача не добавляет, чекпоинт `idle` уже обрабатывался фоллбэком до этой задачи).

- [ ] **Step 4: Прогнать весь backend-набор (регрессия)**

Run: `python -m pytest tests/ -v`
Expected: все тесты PASS, включая 3 новых из Task 1.

- [ ] **Step 5: Ручная проверка в dev-режиме**

Run: `cd frontend && npm run dev` (плюс backend — `uvicorn asgi:app --reload`, как в остальной разработке проекта)

Пройти вручную:
1. Дойти до Offer (после теста) → открыть «Практикум» → убедиться, что под кнопкой «Купить практикум» есть «← Другие варианты» → нажать → вернулись на Offer, текст короткий (M9: «С чего ещё можно начать...»), практикум снова в списке.
2. С Offer → открыть «Книга» → «← Другие варианты» → снова на Offer.
3. С Offer → открыть «Консультация» → «← Другие варианты» → снова на Offer.
4. На «Практикум» нажать «Купить практикум» (тестовая оплата ЮKassa) → экран переходит в «Проверяем оплату…» → убедиться, что кнопки «← Другие варианты» в этом состоянии НЕТ, только «Проверить оплату».

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: связать кнопку «Другие варианты» с App.tsx (goBack на ProductDetail и ConsultDetail)"
```
