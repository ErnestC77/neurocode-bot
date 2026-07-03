"""api/app.py: маршрутизация и auth на /health и /api/ping — без БД
(current_client не обращается к Postgres, только проверяет подпись
initData; current_admin — обращается, поэтому здесь не тестируется)."""
import hashlib
import hmac
import time
from urllib.parse import urlencode

from fastapi.testclient import TestClient

from api.app import create_app
from config import Config

BOT_TOKEN = "123456:test-token"


def _sign(fields: dict) -> str:
    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": signature})


async def _noop_lifecycle(bot, config):
    async def teardown() -> None:
        return None

    return teardown


def _test_config() -> Config:
    return Config(
        bot_token=BOT_TOKEN, database_url="postgresql+asyncpg://u:p@localhost/db",
        port=8080, owner_chat_id=None, yookassa_secret_key="secret",
        webhook_base_url="https://example.com",
    )


def test_health_returns_ok():
    app = create_app(bot=object(), config=_test_config(), bot_lifecycle=_noop_lifecycle)
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ping_without_init_data_is_rejected():
    app = create_app(bot=object(), config=_test_config(), bot_lifecycle=_noop_lifecycle)
    with TestClient(app) as client:
        response = client.get("/api/ping")
    assert response.status_code == 422  # заголовок обязателен (Header(...))


def test_ping_with_valid_init_data_returns_tg_id():
    app = create_app(bot=object(), config=_test_config(), bot_lifecycle=_noop_lifecycle)
    init_data = _sign({"auth_date": str(int(time.time())), "user": '{"id": 777}'})
    with TestClient(app) as client:
        response = client.get("/api/ping", headers={"X-Telegram-Init-Data": init_data})
    assert response.status_code == 200
    assert response.json() == {"tg_id": 777}


def test_ping_with_tampered_init_data_is_rejected():
    app = create_app(bot=object(), config=_test_config(), bot_lifecycle=_noop_lifecycle)
    init_data = _sign({"auth_date": str(int(time.time())), "user": '{"id": 777}'}).replace(
        "id%22%3A+777", "id%22%3A+1"
    )
    with TestClient(app) as client:
        response = client.get("/api/ping", headers={"X-Telegram-Init-Data": init_data})
    assert response.status_code == 401
