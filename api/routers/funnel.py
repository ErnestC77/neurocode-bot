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

router = APIRouter(prefix="/api/funnel")


class AnswerOut(BaseModel):
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
