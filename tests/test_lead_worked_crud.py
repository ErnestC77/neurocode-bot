"""db/crud.py::toggle_lead_worked — переключение статуса «отработан» у лида."""
from db import crud


async def test_toggle_lead_worked_sets_timestamp_when_new(full_db):
    await crud.get_or_create_user(1)
    await crud.create_lead(1, "a@b.com")

    lead = await crud.toggle_lead_worked(1)

    assert lead is not None
    assert lead.worked_at is not None


async def test_toggle_lead_worked_clears_timestamp_when_already_worked(full_db):
    await crud.get_or_create_user(1)
    await crud.create_lead(1, "a@b.com")
    await crud.toggle_lead_worked(1)

    lead = await crud.toggle_lead_worked(1)

    assert lead is not None
    assert lead.worked_at is None


async def test_toggle_lead_worked_returns_none_for_unknown_lead(full_db):
    assert await crud.toggle_lead_worked(999) is None
