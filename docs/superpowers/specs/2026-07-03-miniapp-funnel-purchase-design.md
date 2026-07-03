# Mini App — детали продукта, оплата, консультация, умное меню (подпроект 2b из 3) — design spec

Дата: 2026-07-03
Статус: approved

## Контекст

Продолжение переноса воронки бота «Диагностика нейрокода» в Telegram Mini App. Подпроект 2a (welcome → согласие → 7 вопросов → результат → оффер) сдан и задеплоен — см. `docs/superpowers/specs/2026-07-03-miniapp-funnel-quiz-design.md`. На экране `Offer.tsx` уже отрисованы 3 карточки продуктов с динамическими ценами, но сознательно без обработчика клика — это и есть точка входа подпроекта 2b.

Этот документ покрывает Блоки 6–9 ТЗ (`C:\Users\mccaq\Desktop\LOGIC.MD`): детали практикума и книги, оплата ЮKassa, ветку бесплатной консультации со сбором email, и «умное меню» M9 после покупки.

## Ключевая находка: доставка не зависит от возврата в Mini App

`payments/webhook.py` + `payments/delivery.py` уже реализованы так, что доставка контента (инвайт в канал, PDF, видео, файл книги) происходит **асинхронно через прямые сообщения в чат**, как только ЮKassa подтверждает оплату через вебхук — независимо от того, что в этот момент показывает Mini App. `return_url` в `create_payment` указывает на базовый URL бота, не на конкретную «страницу успеха».

Следствие: техническая сложность «webview + оплата», из-за которой изначально разделили подпроект 2 на 2a/2b, оказалась **вопросом UX-полировки, а не корректности**. Экран Mini App не обязан ничего «знать» о завершении оплаты, чтобы пользователь получил купленное — это гарантируется существующим вебхуком. Единственная задача экрана — обновить свой вид, когда пользователь возвращается, чтобы не оставлять его залипшим на кнопке «Купить».

## Архитектура

Тот же принцип, что и в 2a: backend — источник истины о `checkpoint`, frontend перерисовывается по вернувшемуся состоянию, без собственной копии правил переходов.

### Backend: 4 новых эндпоинта в `api/routers/funnel.py`

Все зеркалят существующие aiogram-хендлеры один-в-один (тот же `db/crud.py`, `services/catalog.py`, `payments/yookassa_client.py`):

| Endpoint | Аналог в чате | Действие |
|---|---|---|
| `POST /api/funnel/product/{product}/view` | `offer:{product}` (`handlers/menu.py::open_product`) | Проверка «продукт ещё доступен» (тот же guard через `get_available_products`, что и в чате — защита от нажатия кнопки на уже купленное/забронированное); `checkpoint → {product}_viewed`; возвращает `FunnelStateOut`. |
| `POST /api/funnel/product/{product}/buy` | `practicum:buy`/`book:buy` (`handlers/practicum.py`/`book.py`) | `create_purchase` → `create_payment` (ЮKassa) → `attach_yk_payment_id`. **Возвращает не `FunnelStateOut`, а `{confirmation_url: str}`** — checkpoint не меняется (как и в чат-хендлере), возврат неизменившегося состояния был бы шумом в контракте. |
| `POST /api/funnel/consult/book` | `consult:book` (`handlers/consult.py::consult_book`) | `checkpoint → awaiting_email`; возвращает `FunnelStateOut`. |
| `POST /api/funnel/consult/email` `{email: str}` | `handle_email_input` (`handlers/consult.py`) | Валидация email через `is_valid_email` → `create_lead` → `notify_lead` (best-effort, как в чате — ошибка уведомления не блокирует ответ) → `checkpoint → idle`; возвращает `FunnelStateOut`. При невалидном email — `HTTPException(422, detail="invalid_email")`, состояние не меняется. |

`product` — литерал `"book" | "practicum"` (не `"consult"` — у консультации отдельные эндпоинты, т.к. это не покупка).

**Общий email-валидатор.** Регэксп сейчас захардкожен внутри `handlers/consult.py::_EMAIL_RE`. Выносится в новый `services/validation.py::is_valid_email(email: str) -> bool` (чистая функция, без сети/БД — тестируется как `services/scoring.py`), переиспользуется и чатом, и API — чтобы правило валидности не могло разъехаться между двумя интерфейсами.

### Frontend: 3 новых экрана + доработка Offer.tsx

- **`ProductDetail.tsx`** (параметризован `product: "book" | "practicum"`) — текст M6.2/M8.2 (из `content/texts.ts`) + цена из `state.book_price_rub`/`practicum_price_rub` + кнопка «Купить за N ₽». По клику: `POST .../buy` → получить `confirmation_url` → `Telegram.WebApp.openLink(confirmation_url)` (новый метод в `lib/telegram.ts`, деградирует до `window.open` вне Telegram). После открытия ссылки экран переходит в режим ожидания: слушает `document.visibilitychange` и параллельно поллит `GET /api/funnel/state` каждые 3 секунды (до 2 минут суммарно, дальше — кнопка «Проверить оплату» вручную вместо авто-поллинга). Как только `checkpoint` перестаёт быть `{product}_viewed`, состояние поднимается наверх в `FunnelGate`, который перерисовывает экран по новому checkpoint (обычно `idle` → Offer/M9, так как `deliver()` после вебхука сам выставляет `IDLE`).
- **`ConsultDetail.tsx`** — текст M7.1 + кнопка «Записаться» → `POST /api/funnel/consult/book`.
- **`ConsultEmailInput.tsx`** — единственный экран с настоящим `<input type="email">` (все остальные экраны 2a/2b — только кнопки); текст `CONSULT_EMAIL_PROMPT`, по вводу шлёт `POST /api/funnel/consult/email` сам (не через общий `runAction`-хелпер `FunnelGate`, как остальные экраны) — при ответе `422` ловит `ApiError` локально и показывает `CONSULT_EMAIL_INVALID` инлайн, оставаясь на экране (как чат, где невалидный email просто переспрашивается тем же сообщением); любая другая ошибка (сеть/401) всплывает через тот же `errorMessage`-путь, что и у остальных экранов. По успеху — `setState` от родителя, как везде.
- **`Offer.tsx` — доработка, не новый файл.** Карточки продуктов получают `onClick` → `POST /api/funnel/product/{id}/view` (для книги/практикума) или `POST /api/funnel/consult/book` (для консультации) → обновляет состояние, `resolveScreen` уводит на нужный detail-экран. Плюс переключение текста: `checkpoint === "offer_shown"` (свежий заход сразу после квиза) → длинный `OFFER_INTRO_TEXTS[resultType]` (M5.*, как сейчас); любой другой checkpoint с уже посчитанным `resultType` (повторный заход — купил один продукт, вернулся за остальным) → короткий `M9`-текст («С чего ещё можно начать, выбери, что откликается:»). Это заложено в самом ТЗ (Блок 9) и не покрыто текущей реализацией 2a.

### `resolveScreen` — 3 новых прямых маппинга

```
practicum_viewed → product-detail (product="practicum")
book_viewed      → product-detail (product="book")
consult_viewed   → consult-detail
awaiting_email   → consult-email-input
```

`idle` отдельного маппинга не требует — уже покрыт существующим фоллбэком 2a («результат есть → offer»), и это и есть умное меню M9.

## Явно вне скоупа

- Собственная страница возврата (`return_url` с параметрами) — не нужна, доставка не зависит от неё (см. «Ключевая находка» выше).
- Отмена/истечение платежа со стороны пользователя (закрыл ЮKassa без оплаты) — экран просто останется в режиме поллинга до тайм-аута 2 минуты, затем покажет кнопку ручной проверки; отдельного UX для явной отмены не проектируется, как и в чате (там тоже нет обработки отмены, только ожидание вебхука).
- Push/WebSocket-уведомление о завершении оплаты вместо поллинга — избыточно для этого объёма трафика (одна оплата — редкое событие на пользователя), поллинг раз в 3с 2 минуты — простое и достаточное решение.

## Верификация

- `services/validation.py::is_valid_email` — юнит-тесты (валидные/невалидные форматы), чистая функция.
- Backend HTTP-тесты по образцу `tests/test_funnel_api.py`: `product/view` меняет checkpoint и уважает guard «уже куплено»; `product/buy` возвращает `confirmation_url` и не меняет checkpoint; `consult/book` → `awaiting_email`; `consult/email` с валидным/невалидным email.
- `resolveScreen.test.ts` — 4 новых кейса на новые чекпоинты.
- Ручная проверка: пройти оба платных продукта и консультацию через реальный Mini App (тестовая оплата ЮKassa) — открытие ссылки оплаты, возврат в приложение, проверка что экран сам обновляется (или после ручного «Проверить оплату»), проверка что M9 показывает только оставшиеся продукты.
