"""db/crud.py: admins — CRUD и бутстрап первого админа из env owner_chat_id."""
from db import crud


async def test_is_admin_false_when_not_added(full_db):
    assert await crud.is_admin(111) is False


async def test_add_admin_then_is_admin_true(full_db):
    added = await crud.add_admin(111, added_by=None)
    assert added is True
    assert await crud.is_admin(111) is True


async def test_add_admin_twice_returns_false_second_time(full_db):
    await crud.add_admin(111, added_by=None)
    added_again = await crud.add_admin(111, added_by=None)
    assert added_again is False


async def test_remove_admin_true_when_existed(full_db):
    await crud.add_admin(111, added_by=None)
    assert await crud.remove_admin(111) is True
    assert await crud.is_admin(111) is False


async def test_remove_admin_false_when_did_not_exist(full_db):
    assert await crud.remove_admin(999) is False


async def test_ensure_admin_seeded_adds_env_owner_when_empty(full_db):
    await crud.ensure_admin_seeded(555)
    assert await crud.is_admin(555) is True


async def test_ensure_admin_seeded_noop_when_admins_exist(full_db):
    await crud.add_admin(111, added_by=None)
    await crud.ensure_admin_seeded(555)
    assert await crud.is_admin(555) is False


async def test_ensure_admin_seeded_noop_when_env_owner_none(full_db):
    await crud.ensure_admin_seeded(None)
    assert await crud.count_admins() == 0
