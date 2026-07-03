"""Inline-клавиатуры. callback_data — namespace через ':' (см. README)."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from services.catalog import BOOK, CONSULT, PRACTICUM, PRODUCT_PRICE_RUB

# Полные названия — для Блока 5 и «умного меню» M9.
_MENU_LABELS = {
    BOOK: f"Книга «Целеполагание» — {PRODUCT_PRICE_RUB[BOOK]} ₽",
    PRACTICUM: f"Практикум «Найди свой код» — {PRODUCT_PRICE_RUB[PRACTICUM]} ₽",
    CONSULT: "Бесплатная консультация с Марией",
}
# Кросс-ссылки на экранах M6.1/M7.1/M8.1 («А что за…»).
_QUESTION_LABELS = {
    BOOK: "А что за книга?",
    PRACTICUM: "А что за практикум?",
    CONSULT: "А что за консультация?",
}
# Кросс-ссылки после покупки/записи (M6.3/M7.2/M8.3).
_AFTER_LABELS = {
    BOOK: "Книга «Целеполагание»",
    PRACTICUM: "Посмотреть практикум",
    CONSULT: "Посмотреть консультацию",
}


def _kb(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=list(rows))


def _other_products_rows(current: str | None, available: list[str],
                         labels: dict[str, str]) -> list[list[InlineKeyboardButton]]:
    return [
        [InlineKeyboardButton(text=labels[p], callback_data=f"offer:{p}")]
        for p in available if p != current
    ]


def next_kb(label: str, callback_data: str) -> InlineKeyboardMarkup:
    """Одна кнопка «далее» — используется в линейных экранах Блока 0."""
    return _kb([InlineKeyboardButton(text=label, callback_data=callback_data)])


def consent_kb() -> InlineKeyboardMarkup:
    return _kb([InlineKeyboardButton(text="Поделиться контактом и начать",
                                     callback_data="consent:accept")])


def question_kb(question_no: int) -> InlineKeyboardMarkup:
    return _kb([
        InlineKeyboardButton(text="Да", callback_data=f"test:a:{question_no}:2"),
        InlineKeyboardButton(text="Иногда", callback_data=f"test:a:{question_no}:1"),
        InlineKeyboardButton(text="Нет", callback_data=f"test:a:{question_no}:0"),
    ])


def result_next_kb() -> InlineKeyboardMarkup:
    return _kb([InlineKeyboardButton(text="Какой шаг мне делать дальше?",
                                     callback_data="result:next")])


def offer_kb(available: list[str]) -> InlineKeyboardMarkup:
    """Блок 5: до трёх кнопок продуктов (уже купленные/забронированные скрыты)."""
    rows = [[InlineKeyboardButton(text=_MENU_LABELS[p], callback_data=f"offer:{p}")]
            for p in available]
    return _kb(*rows)


def practicum_intro_kb(available: list[str]) -> InlineKeyboardMarkup:
    """M6.1: «Да, что внутри» + кросс-ссылки на оставшиеся продукты."""
    rows = [[InlineKeyboardButton(text="Да, что внутри", callback_data="practicum:details")]]
    rows += _other_products_rows(PRACTICUM, available, _QUESTION_LABELS)
    return _kb(*rows)


def practicum_buy_kb(available: list[str]) -> InlineKeyboardMarkup:
    """M6.2: кнопка покупки + кросс-ссылки."""
    price = PRODUCT_PRICE_RUB[PRACTICUM]
    rows = [[InlineKeyboardButton(text=f"Купить практикум за {price} ₽",
                                  callback_data="practicum:buy")]]
    rows += _other_products_rows(PRACTICUM, available, _QUESTION_LABELS)
    return _kb(*rows)


def book_intro_kb(available: list[str]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="Да, что внутри", callback_data="book:details")]]
    rows += _other_products_rows(BOOK, available, _QUESTION_LABELS)
    return _kb(*rows)


def book_buy_kb(available: list[str]) -> InlineKeyboardMarkup:
    price = PRODUCT_PRICE_RUB[BOOK]
    rows = [[InlineKeyboardButton(text=f"Купить книгу за {price} ₽", callback_data="book:buy")]]
    rows += _other_products_rows(BOOK, available, _QUESTION_LABELS)
    return _kb(*rows)


def consult_intro_kb(available: list[str]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="Записаться на консультацию", callback_data="consult:book")]]
    rows += _other_products_rows(CONSULT, available, _QUESTION_LABELS)
    return _kb(*rows)


def payment_link_kb(url: str, label: str) -> InlineKeyboardMarkup:
    return _kb([InlineKeyboardButton(text=label, url=url)])


def reminder_cta_kb(label: str, action_callback: str) -> InlineKeyboardMarkup:
    """R4/R5/R6 из ТЗ: прямая кнопка действия + «Посмотреть другие варианты»."""
    return _kb(
        [InlineKeyboardButton(text=label, callback_data=action_callback)],
        [InlineKeyboardButton(text="Посмотреть другие варианты", callback_data="menu:show")],
    )


def after_product_kb(current: str, available: list[str]) -> InlineKeyboardMarkup:
    """M6.3 / M7.2 / M8.3: кросс-ссылки на оставшиеся не купленные/не забронированные продукты."""
    rows = _other_products_rows(current, available, _AFTER_LABELS)
    return _kb(*rows) if rows else _kb()


def smart_menu_kb(available: list[str]) -> InlineKeyboardMarkup:
    """M9: показывает только то, что ещё не куплено/не забронировано."""
    rows = [[InlineKeyboardButton(text=_MENU_LABELS[p], callback_data=f"offer:{p}")]
            for p in available]
    return _kb(*rows)


def retake_kb() -> InlineKeyboardMarkup:
    return _kb([InlineKeyboardButton(text="Пройти заново", callback_data="retake:confirm")])
