"""Роутер веб-админ-панели: /api/admin/* — списки лидов/покупок/пользователей
и (Task 7) их выгрузка в Excel. Доступ — только текущим админам
(router-level Depends(current_admin), см. api/deps.py)."""
from __future__ import annotations

import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
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


def _xlsx_response(headers: list[str], rows: list[list[object]], filename_prefix: str) -> StreamingResponse:
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"{filename_prefix}_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/leads/export")
async def export_leads() -> StreamingResponse:
    leads = await _leads_out()
    rows = [[l.tg_id, l.username or "", l.email or "", l.created_at.isoformat()] for l in leads]
    return _xlsx_response(["tg_id", "username", "email", "created_at"], rows, "leads")


@router.get("/purchases/export")
async def export_purchases() -> StreamingResponse:
    purchases = await _purchases_out()
    rows = [
        [p.id, p.tg_id, p.username or "", p.product, p.amount_rub, p.status,
         p.paid_at.isoformat() if p.paid_at else "",
         p.delivered_at.isoformat() if p.delivered_at else ""]
        for p in purchases
    ]
    return _xlsx_response(
        ["id", "tg_id", "username", "product", "amount_rub", "status", "paid_at", "delivered_at"],
        rows, "purchases",
    )


@router.get("/users/export")
async def export_users() -> StreamingResponse:
    users = await _users_out()
    rows = [
        [u.tg_id, u.username or "", u.first_name or "", u.checkpoint,
         u.result_type or "", u.test_attempt, u.created_at.isoformat()]
        for u in users
    ]
    return _xlsx_response(
        ["tg_id", "username", "first_name", "checkpoint", "result_type", "test_attempt", "created_at"],
        rows, "users",
    )
