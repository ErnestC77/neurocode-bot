"""Модели БД (SQLAlchemy 2.0, async).

Прогресс пользователя по воронке не хранится в aiogram FSM — единственный
источник истины — колонка ``users.checkpoint``. Это даёт устойчивость к
рестартам процесса и делает возможным декларативный scheduler напоминаний
(см. scheduler.py): чтобы понять, кому пора слать R1-R6, достаточно одного
SELECT по этой таблице, без per-user таймеров.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (BigInteger, DateTime, ForeignKey, Index, Integer,
                        SmallInteger, String, UniqueConstraint, text)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    tg_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(128), nullable=True)

    consent_given_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # "Где завис пользователь" — единственный источник состояния воронки.
    checkpoint: Mapped[str] = mapped_column(String(32), default="new")
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    result_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    result_computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    test_attempt: Mapped[int] = mapped_column(SmallInteger, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Answer(Base):
    """Ответ на один вопрос теста. Retake = удалить все строки юзера и вставить заново."""
    __tablename__ = "answers"
    __table_args__ = (
        UniqueConstraint("user_tg_id", "question_no", name="uq_answer_user_question"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_tg_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.tg_id"))
    question_no: Mapped[int] = mapped_column(SmallInteger)  # 1..7
    score: Mapped[int] = mapped_column(SmallInteger)  # 0 | 1 | 2
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Purchase(Base):
    """Покупка книги или практикума. У юзера может быть несколько (по одной на продукт)."""
    __tablename__ = "purchases"
    __table_args__ = (
        # Один ОПЛАЧЕННЫЙ продукт на юзера; сколько угодно брошенных pending разрешено.
        # sqlite_where нужен отдельно от postgresql_where — без него SQLAlchemy
        # молча создаёт на sqlite ПОЛНЫЙ (не частичный) уникальный индекс, и тесты
        # на этой фикстуре не могут воспроизвести реальное поведение Postgres
        # (несколько pending-покупок одного продукта — валидный кейс в проде).
        Index(
            "uq_purchase_paid_product", "user_tg_id", "product",
            unique=True, postgresql_where=text("status = 'paid'"),
            sqlite_where=text("status = 'paid'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_tg_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.tg_id"))
    product: Mapped[str] = mapped_column(String(16))  # 'book' | 'practicum'
    amount_rub: Mapped[int] = mapped_column(Integer)
    yk_payment_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending | paid | canceled

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Admin(Base):
    """Админ веб-панели/бот-команд — может быть несколько, в отличие от
    единственного owner_chat_id (см. services/settings.py — тот отвечает за
    адресата уведомлений, это другая роль)."""
    __tablename__ = "admins"

    tg_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    added_by: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Lead(Base):
    """Заявка на бесплатную консультацию — одна на пользователя."""
    __tablename__ = "leads"

    user_tg_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.tg_id"), primary_key=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReminderSent(Base):
    """Факт отправки напоминания R1-R6 — одно на (юзер, код), навсегда."""
    __tablename__ = "reminders_sent"

    user_tg_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.tg_id"), primary_key=True)
    reminder_code: Mapped[str] = mapped_column(String(4), primary_key=True)  # 'R1'..'R6'
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BotSetting(Base):
    """Бизнес-настройка, редактируемая владельцем через /settings — не секрет.

    Ключи и типы описаны в реестре services/settings.py::SETTINGS, эта таблица
    хранит только сырые строки; парсинг/валидация — на стороне Python.
    """
    __tablename__ = "bot_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(512))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AdminPendingEdit(Base):
    """«Админ X сейчас редактирует настройку Y» — состояние UI /settings.

    Отдельно от users.checkpoint: это не состояние воронки продаж, а состояние
    админ-панели, и смешивать их в одном поле рискованно (админ теоретически
    может сам проходить тест как обычный пользователь).
    """
    __tablename__ = "admin_pending_edits"

    admin_tg_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    setting_key: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
