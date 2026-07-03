"""Старт, приветствие (Блок 0) и повторное прохождение теста (retake)."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from db import crud
from handlers.test import send_question
from keyboards.inline import consent_kb, next_kb, retake_kb
from services import checkpoints
from texts.messages import RESULT_LABELS, TEXTS

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    tg_id = message.from_user.id
    user = await crud.get_or_create_user(
        tg_id, message.from_user.username, message.from_user.first_name,
    )

    if user.result_type:
        await message.answer(
            TEXTS["RETAKE_PROMPT"].format(result_label=RESULT_LABELS[user.result_type]),
            reply_markup=retake_kb(),
        )
        return

    if user.consent_given_at:
        # Согласие уже есть, тест не завершён — продолжаем с того вопроса, где остановились.
        await crud.set_checkpoint(tg_id, checkpoints.IN_TEST)
        await send_question(message.bot, tg_id, await crud.next_question_no(tg_id))
        return

    await crud.set_checkpoint(tg_id, checkpoints.NEW)
    await message.answer(TEXTS["M0.1"], reply_markup=next_kb("Да, начнём", "welcome:2"))


@router.callback_query(F.data == "welcome:2")
async def welcome_2(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        TEXTS["M0.2"], reply_markup=next_kb("Как проходить тест?", "welcome:3"),
    )


@router.callback_query(F.data == "welcome:3")
async def welcome_3(callback: CallbackQuery) -> None:
    await callback.answer()
    await callback.message.answer(
        TEXTS["M0.3"], reply_markup=next_kb("Продолжить", "welcome:4"),
    )


@router.callback_query(F.data == "welcome:4")
async def welcome_4(callback: CallbackQuery) -> None:
    tg_id = callback.from_user.id
    await callback.answer()
    await crud.set_checkpoint(tg_id, checkpoints.AWAITING_CONSENT)
    await callback.message.answer(TEXTS["M1.1"], reply_markup=consent_kb())


@router.callback_query(F.data == "retake:confirm")
async def retake_confirm(callback: CallbackQuery) -> None:
    tg_id = callback.from_user.id
    await callback.answer()
    await crud.reset_test(tg_id)
    await crud.set_checkpoint(tg_id, checkpoints.IN_TEST)
    await send_question(callback.bot, tg_id, 1)
