"""Роутер воронки квиза: GET/POST под /api/funnel/*.

Бизнес-логика 1-в-1 повторяет handlers/start.py, handlers/consent.py,
handlers/test.py — тот же db/crud.py, services/scoring.py, services/catalog.py,
только вызывается из HTTP-обработчика вместо aiogram callback-хендлера. Один и
тот же checkpoint в БД — истинный источник состояния для чата и Mini App разом.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import current_client
from db import crud
from services import checkpoints, settings
from services.catalog import get_available_products
from services.scoring import compute_result

router = APIRouter(prefix="/api/funnel")


class AnswerOut(BaseModel):
    question_no: int
    score: int


class AnswerIn(BaseModel):
    question_no: int
    score: int


class FunnelStateOut(BaseModel):
    checkpoint: str
    consent_given: bool
    result_type: str | None
    answers: list[AnswerOut]
    available_products: list[str] | None
    book_price_rub: int
    practicum_price_rub: int


async def _build_state(tg_id: int) -> FunnelStateOut:
    user = await crud.get_user(tg_id)
    scores = await crud.get_answer_scores(tg_id)
    available: list[str] | None = None
    result_type = user.result_type if user is not None else None
    if result_type is not None:
        available = await get_available_products(tg_id)
    return FunnelStateOut(
        checkpoint=user.checkpoint if user is not None else checkpoints.NEW,
        consent_given=user is not None and user.consent_given_at is not None,
        result_type=result_type,
        answers=[AnswerOut(question_no=q, score=s) for q, s in sorted(scores.items())],
        available_products=available,
        book_price_rub=await settings.get_int("book_price_rub"),
        practicum_price_rub=await settings.get_int("practicum_price_rub"),
    )


@router.get("/state")
async def get_state(tg_id: int = Depends(current_client)) -> FunnelStateOut:
    return await _build_state(tg_id)


@router.post("/welcome/complete")
async def complete_welcome(tg_id: int = Depends(current_client)) -> FunnelStateOut:
    await crud.set_checkpoint(tg_id, checkpoints.AWAITING_CONSENT)
    return await _build_state(tg_id)


@router.post("/consent")
async def accept_consent(tg_id: int = Depends(current_client)) -> FunnelStateOut:
    await crud.set_consent(tg_id)
    await crud.set_checkpoint(tg_id, checkpoints.IN_TEST)
    return await _build_state(tg_id)


@router.post("/retake")
async def retake(tg_id: int = Depends(current_client)) -> FunnelStateOut:
    await crud.reset_test(tg_id)
    await crud.set_checkpoint(tg_id, checkpoints.IN_TEST)
    return await _build_state(tg_id)


@router.post("/answers")
async def submit_answer(body: AnswerIn, tg_id: int = Depends(current_client)) -> FunnelStateOut:
    expected = await crud.next_question_no(tg_id)
    if body.question_no != expected:
        return await _build_state(tg_id)

    await crud.upsert_answer(tg_id, body.question_no, body.score)

    if body.question_no < 7:
        await crud.set_checkpoint(tg_id, checkpoints.IN_TEST)
    else:
        scores = await crud.get_answer_scores(tg_id)
        result_type = compute_result(scores)
        await crud.set_result(tg_id, result_type)
        await crud.set_checkpoint(tg_id, checkpoints.RESULT_SHOWN)

    return await _build_state(tg_id)


@router.post("/offer/show")
async def show_offer(tg_id: int = Depends(current_client)) -> FunnelStateOut:
    await crud.set_checkpoint(tg_id, checkpoints.OFFER_SHOWN)
    return await _build_state(tg_id)
