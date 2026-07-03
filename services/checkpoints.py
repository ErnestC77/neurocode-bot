"""Чекпоинты воронки — замена aiogram FSM.

Единственный источник истины о прогрессе пользователя — колонка
``users.checkpoint``. Каждый хендлер читает состояние из БД, отвечает и
записывает новый checkpoint последней строкой. Смысл: «где сейчас завис
пользователь» — последний открытый, но не закрытый действием этап.
"""
from __future__ import annotations

NEW = "new"                          # начал Блок 0, /start только что нажат
AWAITING_CONSENT = "awaiting_consent"  # M1.1 показан, согласие не дано
IN_TEST = "in_test"                  # тест начат, не закончен
RESULT_SHOWN = "result_shown"        # результат выдан, «шаг дальше» не нажат
OFFER_SHOWN = "offer_shown"          # Блок 5 показан, продукт не открыт
PRACTICUM_VIEWED = "practicum_viewed"  # открыл практикум, не оплатил
CONSULT_VIEWED = "consult_viewed"    # открыл консультацию, не записался
AWAITING_EMAIL = "awaiting_email"    # нажал «записаться», не прислал email
BOOK_VIEWED = "book_viewed"          # открыл книгу, не купил
IDLE = "idle"                        # нечего напоминать (купил/записался/просто листает меню)

# checkpoint -> код напоминания R1-R6. Чекпоинтов без записи здесь (NEW, OFFER_SHOWN,
# IDLE) напоминания не касаются — так задумано в ТЗ (Блок 5 без своего напоминания).
REMINDER_CODES: dict[str, str] = {
    AWAITING_CONSENT: "R1",
    IN_TEST: "R2",
    RESULT_SHOWN: "R3",
    PRACTICUM_VIEWED: "R4",
    CONSULT_VIEWED: "R5",
    BOOK_VIEWED: "R6",
}
