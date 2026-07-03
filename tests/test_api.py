"""api/app.py: маршрутизация и auth на /health и /api/ping.

current_client не обращается к БД, пока подпись/пользователь не провалидированы
(422/401-ветки не требуют БД) — но happy-path теперь вызывает touch_activity(),
поэтому ему нужна настоящая (sqlite-в-памяти) БД — см. conftest._sqlite_lifecycle.
"""
from fastapi.testclient import TestClient

from api.app import create_app
from conftest import _noop_lifecycle, _sqlite_lifecycle, _test_config, init_data_for


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
    app = create_app(bot=object(), config=_test_config(), bot_lifecycle=_sqlite_lifecycle)
    with TestClient(app) as client:
        response = client.get("/api/ping", headers={"X-Telegram-Init-Data": init_data_for(777)})
    assert response.status_code == 200
    assert response.json() == {"tg_id": 777}


def test_ping_with_tampered_init_data_is_rejected():
    app = create_app(bot=object(), config=_test_config(), bot_lifecycle=_noop_lifecycle)
    init_data = init_data_for(777).replace("id%22%3A+777", "id%22%3A+1")
    with TestClient(app) as client:
        response = client.get("/api/ping", headers={"X-Telegram-Init-Data": init_data})
    assert response.status_code == 401
