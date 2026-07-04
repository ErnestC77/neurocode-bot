"""Роутер веб-админ-панели: /api/admin/* — списки лидов/покупок/пользователей
и (Task 7) их выгрузка в Excel. Доступ — только текущим админам
(router-level Depends(current_admin), см. api/deps.py)."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.deps import current_admin
from db import crud

router = APIRouter(prefix="/api/admin", dependencies=[Depends(current_admin)])


class LeadOut(BaseModel):
    tg_id: int
    username: str | None
    email: str | None
    created_at: datetime


class PurchaseOut(BaseModel):
    id: int
    tg_id: int
    username: str | None
    product: str
    amount_rub: int
    status: str
    paid_at: datetime | None
    delivered_at: datetime | None


class UserOut(BaseModel):
    tg_id: int
    username: str | None
    first_name: str | None
    checkpoint: str
    result_type: str | None
    test_attempt: int
    created_at: datetime


async def _leads_out() -> list[LeadOut]:
    return [
        LeadOut(tg_id=lead.user_tg_id, username=user.username if user else None,
               email=lead.email, created_at=lead.created_at)
        for lead, user in await crud.list_leads()
    ]


async def _purchases_out() -> list[PurchaseOut]:
    return [
        PurchaseOut(
            id=purchase.id, tg_id=purchase.user_tg_id,
            username=user.username if user else None, product=purchase.product,
            amount_rub=purchase.amount_rub, status=purchase.status,
            paid_at=purchase.paid_at, delivered_at=purchase.delivered_at,
        )
        for purchase, user in await crud.list_purchases_with_user()
    ]


async def _users_out() -> list[UserOut]:
    return [
        UserOut(
            tg_id=user.tg_id, username=user.username, first_name=user.first_name,
            checkpoint=user.checkpoint, result_type=user.result_type,
            test_attempt=user.test_attempt, created_at=user.created_at,
        )
        for user in await crud.list_users()
    ]


@router.get("/leads", response_model=list[LeadOut])
async def get_leads() -> list[LeadOut]:
    return await _leads_out()


@router.get("/purchases", response_model=list[PurchaseOut])
async def get_purchases() -> list[PurchaseOut]:
    return await _purchases_out()


@router.get("/users", response_model=list[UserOut])
async def get_users() -> list[UserOut]:
    return await _users_out()
