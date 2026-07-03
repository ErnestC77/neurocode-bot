"""api/routers/funnel.py — HTTP-контракт воронки квиза.

Бизнес-логика переходов (guard на question_no, compute_result, checkpoint'ы)
1-в-1 копирует handlers/test.py и покрыта там же ручной regression-проверкой
чата; здесь проверяется HTTP-слой: коды ответов, форма JSON, фактический
переход checkpoint через полный HTTP-запрос.
"""
from __future__ import annotations

import pytest
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


def test_welcome_complete_sets_awaiting_consent():
    client, headers = _client(702)
    with client:
        response = client.post("/api/funnel/welcome/complete", headers=headers)
    assert response.status_code == 200
    assert response.json()["checkpoint"] == "awaiting_consent"


def test_consent_sets_consent_given_and_in_test():
    client, headers = _client(703)
    with client:
        response = client.post("/api/funnel/consent", headers=headers)
    body = response.json()
    assert body["checkpoint"] == "in_test"
    assert body["consent_given"] is True


@pytest.mark.skip(reason="POST /api/funnel/answers появится в Task 3")
def test_retake_resets_answers_and_checkpoint():
    client, headers = _client(704)
    with client:
        client.post("/api/funnel/consent", headers=headers)
        for q in range(1, 8):
            client.post("/api/funnel/answers", headers=headers, json={"question_no": q, "score": 2})
        before = client.get("/api/funnel/state", headers=headers).json()
        assert before["result_type"] is not None

        response = client.post("/api/funnel/retake", headers=headers)
    body = response.json()
    assert body["checkpoint"] == "in_test"
    assert body["result_type"] is None
    assert body["answers"] == []
