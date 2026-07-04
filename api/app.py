"""FastAPI application factory.

``create_app`` принимает уже собранный ``bot`` и ``bot_lifecycle`` — callable,
который FastAPI ``lifespan`` вызывает на старте и должен вернуть teardown-
функцию для остановки. Сам ``create_app`` ничего не знает о том, как именно
бот запускается (polling/webhook) — эту развязку делает asgi.py.
"""
from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

from aiogram import Bot
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

from api.routers import admin, funnel, ping
from config import Config
from payments import webhook as yookassa_webhook

Teardown = Callable[[], Awaitable[None]]
BotLifecycle = Callable[[Bot, Config], Awaitable[Teardown]]


class _SpaStaticFiles(StaticFiles):
    """Раздаёт собранный SPA, но не даёт закэшировать index.html.

    Telegram WebView агрессивно кэширует index.html — после деплоя без этого
    он продолжал бы грузить старую сборку (старые хэшированные JS/CSS), пока
    пользователь не почистит кэш вручную. Хэшированные ассеты кэшируются
    нормально, не-cache — только у HTML-точки входа.
    """

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        if path in ("", ".") or path.endswith(".html"):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


def create_app(bot: Bot, config: Config, bot_lifecycle: BotLifecycle) -> FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        teardown = await bot_lifecycle(bot, config)
        try:
            yield
        finally:
            await teardown()

    app = FastAPI(lifespan=lifespan)
    app.state.bot = bot
    app.state.config = config

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    app.include_router(ping.router)
    app.include_router(funnel.router)
    app.include_router(admin.router)
    app.include_router(yookassa_webhook.router)

    # Собранный Mini App (Vite outDir=dist) — монтируется ПОСЛЕ /api/* и
    # /health//yookassa роутов: Starlette матчит по порядку регистрации,
    # так что /api/* никогда не будет перекрыт статикой. check_dir=False —
    # чтобы create_app() был импортируемым в тестах и до первой сборки
    # фронтенда (frontend/dist ещё не существует).
    dist_dir = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    app.mount("/", _SpaStaticFiles(directory=str(dist_dir), html=True, check_dir=False), name="static")
    return app
