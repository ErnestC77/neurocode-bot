"""services/telegram_auth.py: HMAC-проверка initData — чистая логика, без БД/сети."""
import hashlib
import hmac
import time
from urllib.parse import urlencode

import pytest

from services.telegram_auth import InvalidInitDataError, parse_and_validate_init_data

BOT_TOKEN = "123456:test-token"


def _sign(fields: dict, bot_token: str = BOT_TOKEN) -> str:
    """Строит валидно подписанную initData-строку — тот же алгоритм, что и
    в проверяемом коде (иначе happy-path протестировать нечем: подпись
    нужно с чего-то посчитать)."""
    data_check_string = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": signature})


def test_valid_init_data_is_accepted():
    fields = {"auth_date": str(int(time.time())), "user": '{"id": 42, "first_name": "A"}'}
    result = parse_and_validate_init_data(_sign(fields), BOT_TOKEN)
    assert result["user"]["id"] == 42
    assert result["auth_date"] == int(fields["auth_date"])


def test_missing_hash_is_rejected():
    with pytest.raises(InvalidInitDataError):
        parse_and_validate_init_data("auth_date=1&user=%7B%7D", BOT_TOKEN)


def test_tampered_field_is_rejected():
    fields = {"auth_date": str(int(time.time())), "user": '{"id": 42}'}
    signed = _sign(fields)
    tampered = signed.replace("id%22%3A+42", "id%22%3A+999")
    with pytest.raises(InvalidInitDataError):
        parse_and_validate_init_data(tampered, BOT_TOKEN)


def test_wrong_bot_token_is_rejected():
    fields = {"auth_date": str(int(time.time())), "user": '{"id": 42}'}
    signed = _sign(fields, bot_token="999999:other-token")
    with pytest.raises(InvalidInitDataError):
        parse_and_validate_init_data(signed, BOT_TOKEN)


def test_expired_auth_date_is_rejected():
    old_timestamp = int(time.time()) - 100_000
    fields = {"auth_date": str(old_timestamp), "user": '{"id": 42}'}
    with pytest.raises(InvalidInitDataError):
        parse_and_validate_init_data(_sign(fields), BOT_TOKEN, max_age_seconds=86400)


def test_no_user_field_is_ok():
    fields = {"auth_date": str(int(time.time()))}
    result = parse_and_validate_init_data(_sign(fields), BOT_TOKEN)
    assert result["user"] is None
