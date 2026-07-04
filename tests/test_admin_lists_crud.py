"""db/crud.py: list_purchases_with_user / list_users — данные для админ-панели."""
from db import crud


async def test_list_users_empty_when_no_users(full_db):
    assert await crud.list_users() == []


async def test_list_users_returns_created_user(full_db):
    await crud.get_or_create_user(42, username="ernest", first_name="Ernest")
    users = await crud.list_users()
    assert len(users) == 1
    assert users[0].tg_id == 42
    assert users[0].username == "ernest"
    assert users[0].checkpoint == "new"


async def test_list_purchases_with_user_empty_when_none(full_db):
    assert await crud.list_purchases_with_user() == []


async def test_list_purchases_with_user_joins_user(full_db):
    await crud.get_or_create_user(42, username="ernest", first_name="Ernest")
    purchase = await crud.create_purchase(42, "book", 990)
    rows = await crud.list_purchases_with_user()
    assert len(rows) == 1
    got_purchase, got_user = rows[0]
    assert got_purchase.id == purchase.id
    assert got_purchase.product == "book"
    assert got_purchase.status == "pending"
    assert got_user is not None
    assert got_user.username == "ernest"
