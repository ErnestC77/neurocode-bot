"""Роутер воронки квиза: GET/POST под /api/funnel/*.

Бизнес-логика 1-в-1 повторяет handlers/start.py, handlers/consent.py,
handlers/test.py — тот же db/crud.py, services/scoring.py, services/catalog.py,
только вызывается из HTTP-обработчика вместо aiogram callback-хендлера. Один и
тот же checkpoint в БД — истинный источник состояния для чата и Mini App разом.
"""
from __future__ import annotations

import logging
from typing import Literal

from aiogram import Bot
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.deps import current_client
from config import Config
from db import crud
from exports.notifier import notify_lead
from payments.yookassa_client import create_payment
from services import checkpoints, settings
from services.catalog import get_available_products
from services.scoring import compute_result
from services.validation import is_valid_email

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/funnel")


class AnswerOut(BaseModel):
    question_no: int
    score: int


class AnswerIn(BaseModel):
    question_no: int
    score: int = Field(ge=0, le=2)


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


class PurchaseInitiatedOut(BaseModel):
    confirmation_url: str


class EmailIn(BaseModel):
    email: str


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
    user = await crud.get_user(tg_id)
    if user is None or user.result_type is None:
        return await _build_state(tg_id)
    await crud.set_checkpoint(tg_id, checkpoints.OFFER_SHOWN)
    return await _build_state(tg_id)


@router.post("/product/{product}/view")
async def view_product(
    product: Literal["book", "practicum"], tg_id: int = Depends(current_client),
) -> FunnelStateOut:
    available = await get_available_products(tg_id)
    if product in available:
        await crud.set_checkpoint(tg_id, _PRODUCT_CHECKPOINT[product])
    return await _build_state(tg_id)


@router.post("/product/{product}/buy")
async def buy_product(
    product: Literal["book", "practicum"], body: EmailIn, request: Request,
    tg_id: int = Depends(current_client),
) -> PurchaseInitiatedOut:
    # Email нужен для чека фискализации (54-ФЗ) — без него ЮKassa отклоняет платёж.
    email = body.email.strip()
    if not is_valid_email(email):
        raise HTTPException(status_code=422, detail="invalid_email")

    config: Config = request.app.state.config
    amount = await settings.get_int(f"{product}_price_rub")
    purchase = await crud.create_purchase(tg_id, product, amount)
    payment_id, confirmation_url = await create_payment(
        shop_id=await settings.get_str("yookassa_shop_id"), secret_key=config.yookassa_secret_key,
        amount_rub=amount, description=_PRODUCT_LABELS[product], customer_email=email,
        idempotence_key=str(purchase.id), return_url=config.webhook_base_url,
        metadata={"tg_id": tg_id, "product": product, "purchase_id": purchase.id},
    )
    await crud.attach_yk_payment_id(purchase.id, payment_id)
    return PurchaseInitiatedOut(confirmation_url=confirmation_url)


@router.post("/consult/book")
async def book_consult(tg_id: int = Depends(current_client)) -> FunnelStateOut:
    await crud.set_checkpoint(tg_id, checkpoints.AWAITING_EMAIL)
    return await _build_state(tg_id)


@router.post("/consult/view")
async def view_consult(tg_id: int = Depends(current_client)) -> FunnelStateOut:
    available = await get_available_products(tg_id)
    if "consult" in available:
        await crud.set_checkpoint(tg_id, checkpoints.CONSULT_VIEWED)
    return await _build_state(tg_id)


@router.post("/consult/email")
async def submit_consult_email(
    body: EmailIn, request: Request, tg_id: int = Depends(current_client),
) -> FunnelStateOut:
    if not is_valid_email(body.email):
        raise HTTPException(status_code=422, detail="invalid_email")

    bot: Bot = request.app.state.bot
    config: Config = request.app.state.config
    lead = await crud.create_lead(tg_id, body.email)
    await crud.set_checkpoint(tg_id, checkpoints.IDLE)
    if lead is not None:
        try:
            await notify_lead(bot, config, lead)
        except Exception:  # noqa: BLE001 — не выгрузилось сейчас, ретрай подхватит scheduler
            logger.exception("Не удалось выгрузить лид user=%s", tg_id)
    return await _build_state(tg_id)


@router.post("/back")
async def go_back(tg_id: int = Depends(current_client)) -> FunnelStateOut:
    user = await crud.get_user(tg_id)
    if user is not None and user.checkpoint in _BACK_ELIGIBLE_CHECKPOINTS:
        await crud.set_checkpoint(tg_id, checkpoints.IDLE)
    return await _build_state(tg_id)
