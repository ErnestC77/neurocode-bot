"""api/routers/funnel.py — HTTP-контракт воронки квиза.

Бизнес-логика переходов (guard на question_no, compute_result, checkpoint'ы)
1-в-1 копирует handlers/test.py и покрыта там же ручной regression-проверкой
чата; здесь проверяется HTTP-слой: коды ответов, форма JSON, фактический
переход checkpoint через полный HTTP-запрос.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import create_app
from conftest import _sqlite_lifecycle, _test_config, init_data_for


def _client(tg_id: int) -> tuple[TestClient, dict]:
    app = create_app(bot=object(), config=_test_config(), bot_lifecycle=_sqlite_lifecycle)
    return TestClient(app), {"X-Telegram-Init-Data": init_data_for(tg_id)}


def test_state_defaults_for_new_user():
    client, headers = _client(701)
    with client:
        response = client.get("/api/funnel/state", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "checkpoint": "new",
        "consent_given": False,
        "result_type": None,
        "answers": [],
        "available_products": None,
        "book_price_rub": 990,
        "practicum_price_rub": 2990,
    }
