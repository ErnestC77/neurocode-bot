"""Запросы к БД. Каждая функция открывает свою сессию (без FSM — БД и есть состояние)."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError

from db.database import get_sessionmaker
from db.models import (Admin, AdminPendingEdit, Answer, BotSetting, Lead, Purchase,
                       ReminderSent, User, utcnow)


# ---------- Пользователи / чекпоинты ----------

async def get_or_create_user(tg_id: int, username: str | None = None,
                              first_name: str | None = None) -> User:
    async with get_sessionmaker()() as session:
        user = await session.get(User, tg_id)
        if user is None:
            user = User(tg_id=tg_id, username=username, first_name=first_name,
                       last_activity_at=utcnow())
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user


async def touch_activity(tg_id: int, username: str | None, first_name: str | None) -> None:
    """Вызывается middleware на КАЖДЫЙ update: бампает last_activity_at и профиль.

    Это и есть механизм «любое действие обнуляет таймер напоминаний» —
    отдельного сброса нигде делать не нужно.
    """
    async with get_sessionmaker()() as session:
        user = await session.get(User, tg_id)
        if user is None:
            session.add(User(tg_id=tg_id, username=username, first_name=first_name,
                             last_activity_at=utcnow()))
        else:
            user.last_activity_at = utcnow()
            if username:
                user.username = username
            if first_name:
                user.first_name = first_name
        await session.commit()


async def get_user(tg_id: int) -> User | None:
    async with get_sessionmaker()() as session:
        return await session.get(User, tg_id)


async def set_checkpoint(tg_id: int, checkpoint: str) -> None:
    async with get_sessionmaker()() as session:
        user = await session.get(User, tg_id)
        if user:
            user.checkpoint = checkpoint
            await session.commit()


async def set_consent(tg_id: int) -> None:
    """Согласие фиксируется один раз и никогда не сбрасывается (в т.ч. при retake)."""
    async with get_sessionmaker()() as session:
        user = await session.get(User, tg_id)
        if user and user.consent_given_at is None:
            user.consent_given_at = utcnow()
            await session.commit()


# ---------- Тест ----------

async def get_answer_scores(tg_id: int) -> dict[int, int]:
    async with get_sessionmaker()() as session:
        rows = await session.scalars(
            select(Answer).where(Answer.user_tg_id == tg_id).order_by(Answer.question_no)
        )
        return {a.question_no: a.score for a in rows}


async def next_question_no(tg_id: int) -> int:
    scores = await get_answer_scores(tg_id)
    return len(scores) + 1


async def upsert_answer(tg_id: int, question_no: int, score: int) -> None:
    async with get_sessionmaker()() as session:
        existing = await session.scalar(
            select(Answer).where(Answer.user_tg_id == tg_id, Answer.question_no == question_no)
        )
        if existing:
            existing.score = score
            existing.answered_at = utcnow()
        else:
            session.add(Answer(user_tg_id=tg_id, question_no=question_no, score=score))
        await session.commit()


async def reset_test(tg_id: int) -> None:
    """Retake: стереть ответы и результат, согласие (consent_given_at) не трогаем."""
    async with get_sessionmaker()() as session:
        await session.execute(delete(Answer).where(Answer.user_tg_id == tg_id))
        user = await session.get(User, tg_id)
        if user:
            user.result_type = None
            user.result_computed_at = None
            user.test_attempt += 1
        await session.commit()


async def set_result(tg_id: int, result_type: str) -> None:
    async with get_sessionmaker()() as session:
        user = await session.get(User, tg_id)
        if user:
            user.result_type = result_type
            user.result_computed_at = utcnow()
            await session.commit()


# ---------- Покупки ----------

async def create_purchase(tg_id: int, product: str, amount_rub: int) -> Purchase:
    async with get_sessionmaker()() as session:
        purchase = Purchase(user_tg_id=tg_id, product=product, amount_rub=amount_rub, status="pending")
        session.add(purchase)
        await session.commit()
        await session.refresh(purchase)
        return purchase


async def get_purchase(purchase_id: int) -> Purchase | None:
    async with get_sessionmaker()() as session:
        return await session.get(Purchase, purchase_id)


async def attach_yk_payment_id(purchase_id: int, yk_payment_id: str) -> None:
    async with get_sessionmaker()() as session:
        purchase = await session.get(Purchase, purchase_id)
        if purchase:
            purchase.yk_payment_id = yk_payment_id
            await session.commit()


async def mark_paid(yk_payment_id: str) -> Purchase | None:
    """Идемпотентно помечает платёж оплаченным.

    Возвращает Purchase только при ПЕРВОЙ успешной обработке; ``None`` — если
    платёж уже был обработан ранее или неизвестен (защита от повторных webhook).
    """
    async with get_sessionmaker()() as session:
        stmt = (
            update(Purchase)
            .where(Purchase.yk_payment_id == yk_payment_id, Purchase.status == "pending")
            .values(status="paid", paid_at=utcnow())
            .returning(Purchase)
        )
        result = await session.execute(stmt)
        purchase = result.scalar_one_or_none()
        await session.commit()
        return purchase


async def mark_delivered(purchase_id: int) -> None:
    async with get_sessionmaker()() as session:
        purchase = await session.get(Purchase, purchase_id)
        if purchase:
            purchase.delivered_at = utcnow()
            await session.commit()


async def get_paid_products(tg_id: int) -> set[str]:
    async with get_sessionmaker()() as session:
        rows = await session.scalars(
            select(Purchase.product).where(Purchase.user_tg_id == tg_id, Purchase.status == "paid")
        )
        return set(rows)


async def has_paid(tg_id: int, product: str) -> bool:
    return product in await get_paid_products(tg_id)


# ---------- Лиды на консультацию ----------

async def create_lead(tg_id: int, email: str) -> Lead | None:
    """Создаёт заявку с email. ``None``, если заявка уже была (повторное нажатие)."""
    async with get_sessionmaker()() as session:
        existing = await session.get(Lead, tg_id)
        if existing is not None:
            return None
        lead = Lead(user_tg_id=tg_id, email=email)
        session.add(lead)
        await session.commit()
        await session.refresh(lead)
        return lead


async def has_lead(tg_id: int) -> bool:
    async with get_sessionmaker()() as session:
        return await session.get(Lead, tg_id) is not None


async def get_unexported_leads() -> list[Lead]:
    async with get_sessionmaker()() as session:
        return list(await session.scalars(select(Lead).where(Lead.exported_at.is_(None))))


async def list_leads() -> list[tuple[Lead, User | None]]:
    """Все лиды с данными пользователя — для CSV-экспорта (/export_leads)."""
    async with get_sessionmaker()() as session:
        rows = await session.execute(
            select(Lead, User)
            .join(User, User.tg_id == Lead.user_tg_id, isouter=True)
            .order_by(Lead.created_at)
        )
        return [(lead, user) for lead, user in rows.all()]


async def mark_lead_exported(tg_id: int) -> None:
    async with get_sessionmaker()() as session:
        lead = await session.get(Lead, tg_id)
        if lead:
            lead.exported_at = utcnow()
            await session.commit()


async def get_undelivered_paid_purchases() -> list[Purchase]:
    """Оплаченные покупки, для которых ещё не отправлено уведомление владельцу."""
    async with get_sessionmaker()() as session:
        return list(await session.scalars(
            select(Purchase).where(Purchase.status == "paid", Purchase.delivered_at.is_(None))
        ))


# ---------- Напоминания R1-R6 ----------

async def due_reminder_users(checkpoint_codes: dict[str, str], delay: timedelta) -> list[tuple[User, str]]:
    """Пользователи, чей текущий checkpoint требует напоминания и кому оно ещё не отправлено.

    ``checkpoint_codes`` — карта checkpoint -> код напоминания (services/checkpoints.py).
    Один декларативный запрос на каждый checkpoint, без per-user таймеров/джобов.
    """
    cutoff = utcnow() - delay
    result: list[tuple[User, str]] = []
    async with get_sessionmaker()() as session:
        for checkpoint, code in checkpoint_codes.items():
            sent_subq = (
                select(ReminderSent.user_tg_id)
                .where(ReminderSent.reminder_code == code)
                .scalar_subquery()
            )
            users = await session.scalars(
                select(User).where(
                    User.checkpoint == checkpoint,
                    User.last_activity_at < cutoff,
                    User.tg_id.notin_(sent_subq),
                )
            )
            for user in users:
                result.append((user, code))
    return result


async def log_reminder(tg_id: int, code: str) -> bool:
    """Отмечает напоминание отправленным. False, если уже было (гонка/дубль)."""
    async with get_sessionmaker()() as session:
        session.add(ReminderSent(user_tg_id=tg_id, reminder_code=code))
        try:
            await session.commit()
            return True
        except IntegrityError:
            await session.rollback()
            return False


# ---------- Настройки (/settings) ----------

async def get_setting_value(key: str) -> str | None:
    async with get_sessionmaker()() as session:
        setting = await session.get(BotSetting, key)
        return setting.value if setting else None


async def set_setting_value(key: str, value: str) -> None:
    async with get_sessionmaker()() as session:
        setting = await session.get(BotSetting, key)
        if setting is None:
            session.add(BotSetting(key=key, value=value))
        else:
            setting.value = value
        await session.commit()


async def get_pending_setting_edit(admin_tg_id: int) -> str | None:
    """Ключ настройки, которую сейчас редактирует админ, или None."""
    async with get_sessionmaker()() as session:
        pending = await session.get(AdminPendingEdit, admin_tg_id)
        return pending.setting_key if pending else None


async def set_pending_setting_edit(admin_tg_id: int, setting_key: str) -> None:
    async with get_sessionmaker()() as session:
        pending = await session.get(AdminPendingEdit, admin_tg_id)
        if pending is None:
            session.add(AdminPendingEdit(admin_tg_id=admin_tg_id, setting_key=setting_key))
        else:
            pending.setting_key = setting_key
        await session.commit()


async def clear_pending_setting_edit(admin_tg_id: int) -> None:
    async with get_sessionmaker()() as session:
        pending = await session.get(AdminPendingEdit, admin_tg_id)
        if pending:
            await session.delete(pending)
            await session.commit()


# ---------- Админы (доступ к /settings, /export_leads, веб-панели) ----------

async def is_admin(tg_id: int) -> bool:
    async with get_sessionmaker()() as session:
        return await session.get(Admin, tg_id) is not None


async def add_admin(tg_id: int, added_by: int | None) -> bool:
    """True, если добавлен; False, если уже был админом (идемпотентно)."""
    async with get_sessionmaker()() as session:
        if await session.get(Admin, tg_id) is not None:
            return False
        session.add(Admin(tg_id=tg_id, added_by=added_by))
        await session.commit()
        return True


async def remove_admin(tg_id: int) -> bool:
    """True, если удалён; False, если не был админом."""
    async with get_sessionmaker()() as session:
        admin = await session.get(Admin, tg_id)
        if admin is None:
            return False
        await session.delete(admin)
        await session.commit()
        return True


async def count_admins() -> int:
    async with get_sessionmaker()() as session:
        result = await session.execute(select(func.count()).select_from(Admin))
        return result.scalar_one()


async def ensure_admin_seeded(env_owner_chat_id: int | None) -> None:
    """Если таблица admins пуста и задан env owner_chat_id — сделать его первым
    админом. Идемпотентно, безопасно вызывать на каждом старте процесса
    (см. asgi.py::_bot_lifecycle)."""
    if env_owner_chat_id is None:
        return
    if await count_admins() > 0:
        return
    await add_admin(env_owner_chat_id, added_by=None)
