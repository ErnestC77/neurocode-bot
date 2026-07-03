"""Тестовый эндпоинт для проверки инфраструктуры Mini App (Task E1)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import current_client

router = APIRouter(prefix="/api")


@router.get("/ping")
async def ping(tg_id: int = Depends(current_client)) -> dict:
    return {"tg_id": tg_id}
