"""FastAPI-зависимости: аутентификация через initData Telegram Mini App SDK."""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request

from config import Config
from db import crud
from services.settings import is_authorized_admin
from services.telegram_auth import InvalidInitDataError, parse_and_validate_init_data


async def current_client(
    request: Request,
    x_telegram_init_data: str = Header(..., alias="X-Telegram-Init-Data"),
) -> int:
    config: Config = request.app.state.config
    try:
        data = parse_and_validate_init_data(x_telegram_init_data, config.bot_token)
    except InvalidInitDataError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    user = data.get("user") or {}
    tg_id = user.get("id")
    if tg_id is None:
        raise HTTPException(status_code=401, detail="no user in initData")
    await crud.touch_activity(tg_id, user.get("username"), user.get("first_name"))
    return tg_id


async def current_admin(
    request: Request,
    tg_id: int = Depends(current_client),
) -> int:
    config: Config = request.app.state.config
    if not await is_authorized_admin(tg_id, config):
        raise HTTPException(status_code=403, detail="not an admin")
    return tg_id
