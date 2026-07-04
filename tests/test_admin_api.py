"""api/routers/admin.py — HTTP-контракт веб-панели: доступ только админам,
формат списков (JSON) и Excel-экспорта (добавится в Task 7)."""
from __future__ import annotations

import dataclasses

from fastapi.testclient import TestClient

from api.app import create_app
from conftest import _sqlite_lifecycle, _test_config, init_data_for


def _client(tg_id: int) -> tuple[TestClient, dict]:
    app = create_app(bot=object(), config=_test_config(), bot_lifecycle=_sqlite_lifecycle)
    return TestClient(app), {"X-Telegram-Init-Data": init_data_for(tg_id)}


def _admin_client(tg_id: int) -> tuple[TestClient, dict]:
    config = dataclasses.replace(_test_config(), owner_chat_id=tg_id)
    app = create_app(bot=object(), config=config, bot_lifecycle=_sqlite_lifecycle)
    return TestClient(app), {"X-Telegram-Init-Data": init_data_for(tg_id)}


def test_leads_rejected_for_non_admin():
    client, headers = _client(801)
    with client:
        response = client.get("/api/admin/leads", headers=headers)
    assert response.status_code == 403


def test_leads_empty_for_admin_with_no_leads():
    client, headers = _admin_client(802)
    with client:
        response = client.get("/api/admin/leads", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


def test_purchases_empty_for_admin_with_no_purchases():
    client, headers = _admin_client(803)
    with client:
        response = client.get("/api/admin/purchases", headers=headers)
    assert response.status_code == 200
    assert response.json() == []


def test_users_lists_self_after_first_request():
    # current_client() создаёт/трогает User-запись на каждый запрос — админ
    # уже появится в /api/admin/users после одного собственного запроса.
    client, headers = _admin_client(804)
    with client:
        response = client.get("/api/admin/users", headers=headers)
    assert response.status_code == 200
    users = response.json()
    assert len(users) == 1
    assert users[0]["tg_id"] == 804
    assert users[0]["checkpoint"] == "new"


def test_purchases_rejected_for_non_admin():
    client, headers = _client(805)
    with client:
        response = client.get("/api/admin/purchases", headers=headers)
    assert response.status_code == 403


def test_users_rejected_for_non_admin():
    client, headers = _client(806)
    with client:
        response = client.get("/api/admin/users", headers=headers)
    assert response.status_code == 403
