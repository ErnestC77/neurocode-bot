"""Блоки 2-4: тест из 7 вопросов, подсчёт и выдача результата (M2.x, M4.x, M5.x)."""
from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery

from db import crud
from keyboards.inline import offer_kb, question_kb, result_next_kb
from services import checkpoints
from services.catalog import get_available_products
from services.scoring import compute_result
from texts.messages import QUESTIONS, TEXTS

router = Router()

_RESULT_TEXT_KEY = {"survival": "M4.A", "impostor": "M4.B", "others_goals": "M4.V"}
_OFFER_TEXT_KEY = {"survival": "M5.A", "impostor": "M5.B", "others_goals": "M5.V"}


async def send_question(bot: Bot, tg_id: int, question_no: int) -> None:
    text = f"Вопрос {question_no} из 7\n\n{QUESTIONS[question_no]}"
    await bot.send_message(tg_id, text, reply_markup=question_kb(question_no))


@router.callback_query(F.data.startswith("test:a:"))
async def answer_question(callback: CallbackQuery) -> None:
    tg_id = callback.from_user.id
    _, _, q_raw, s_raw = callback.data.split(":")
    question_no, score = int(q_raw), int(s_raw)

    # Номер текущего вопроса не хранится отдельно — выводится как count(answers)+1.
    # Если пришёл ответ на уже пройденный/будущий вопрос (двойной клик, старая
    # клавиатура) — тихо игнорируем, состояние в БД не трогаем.
    expected = await crud.next_question_no(tg_id)
    if question_no != expected:
        await callback.answer()
        return

    await crud.upsert_answer(tg_id, question_no, score)
    await callback.answer()

    if question_no < 7:
        await crud.set_checkpoint(tg_id, checkpoints.IN_TEST)
        await send_question(callback.bot, tg_id, question_no + 1)
        return

    scores = await crud.get_answer_scores(tg_id)
    result_type = compute_result(scores)
    await crud.set_result(tg_id, result_type)
    await crud.set_checkpoint(tg_id, checkpoints.RESULT_SHOWN)
    await callback.message.answer(TEXTS[_RESULT_TEXT_KEY[result_type]],
                                  reply_markup=result_next_kb())


@router.callback_query(F.data == "test:resume")
async def resume_test(callback: CallbackQuery) -> None:
    """Кнопка «Ответить» из напоминания R2 — повторно показывает вопрос,
    на котором пользователь остановился (сам вопрос, а не голые кнопки)."""
    tg_id = callback.from_user.id
    await callback.answer()
    await send_question(callback.bot, tg_id, await crud.next_question_no(tg_id))


@router.callback_query(F.data == "result:next")
async def show_offer(callback: CallbackQuery) -> None:
    tg_id = callback.from_user.id
    await callback.answer()
    user = await crud.get_user(tg_id)
    if user is None or user.result_type is None:
        return
    await crud.set_checkpoint(tg_id, checkpoints.OFFER_SHOWN)
    available = await get_available_products(tg_id)
    if not available:
        await callback.message.answer(TEXTS["M9_EMPTY"])
        return
    await callback.message.answer(TEXTS[_OFFER_TEXT_KEY[user.result_type]],
                                  reply_markup=offer_kb(available))
