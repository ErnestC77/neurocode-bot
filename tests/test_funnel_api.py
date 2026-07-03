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


def test_answer_appends_and_keeps_in_test_checkpoint():
    client, headers = _client(705)
    with client:
        client.post("/api/funnel/consent", headers=headers)
        response = client.post(
            "/api/funnel/answers", headers=headers, json={"question_no": 1, "score": 2},
        )
    body = response.json()
    assert body["checkpoint"] == "in_test"
    assert body["answers"] == [{"question_no": 1, "score": 2}]
    assert body["result_type"] is None


def test_stale_answer_is_ignored():
    client, headers = _client(706)
    with client:
        client.post("/api/funnel/consent", headers=headers)
        client.post("/api/funnel/answers", headers=headers, json={"question_no": 1, "score": 2})
        # Повторный ответ на уже отвеченный вопрос — no-op, не ошибка.
        response = client.post(
            "/api/funnel/answers", headers=headers, json={"question_no": 1, "score": 0},
        )
    body = response.json()
    assert response.status_code == 200
    assert body["answers"] == [{"question_no": 1, "score": 2}]  # не перезаписалось


def test_seventh_answer_computes_result_and_sets_result_shown():
    client, headers = _client(707)
    # Да,Да,Нет,Иногда,Нет,Да,Иногда -> Q1=2,Q2=2,Q3=0,Q4=1,Q5=0,Q6=2,Q7=1
    # S_survival=Q1+Q2+Q6=6, S_impostor=Q3+Q5+Q7=1, S_others=Q4+Q6+Q7=4 -> survival
    # (тот же пример, что в LOGIC.MD, Блок 3)
    scores = [2, 2, 0, 1, 0, 2, 1]
    with client:
        client.post("/api/funnel/consent", headers=headers)
        response = None
        for q, s in enumerate(scores, start=1):
            response = client.post(
                "/api/funnel/answers", headers=headers, json={"question_no": q, "score": s},
            )
    body = response.json()
    assert body["checkpoint"] == "result_shown"
    assert body["result_type"] == "survival"
    assert len(body["answers"]) == 7


def test_offer_show_sets_offer_shown_and_lists_available_products():
    client, headers = _client(708)
    with client:
        client.post("/api/funnel/consent", headers=headers)
        for q, s in enumerate([2, 2, 0, 1, 0, 2, 1], start=1):
            client.post("/api/funnel/answers", headers=headers, json={"question_no": q, "score": s})
        response = client.post("/api/funnel/offer/show", headers=headers)
    body = response.json()
    assert body["checkpoint"] == "offer_shown"
    assert set(body["available_products"]) == {"book", "practicum", "consult"}


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
