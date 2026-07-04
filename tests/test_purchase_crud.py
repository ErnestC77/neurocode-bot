"""db/crud.py::mark_paid — идемпотентность и устойчивость к дублирующимся
брошенным pending-покупкам одного продукта (регресс: ЮKassa ретраила webhook
по payment_id брошенного дубля уже после того, как другая покупка того же
продукта была помечена paid, и необработанный IntegrityError от
uq_purchase_paid_product улетал наружу как 500 вместо чистого None)."""
from db import crud


async def test_mark_paid_marks_pending_purchase(full_db):
    await crud.get_or_create_user(1)
    purchase = await crud.create_purchase(1, "book", 990)
    await crud.attach_yk_payment_id(purchase.id, "pay-1")

    result = await crud.mark_paid("pay-1")

    assert result is not None
    assert result.id == purchase.id
    assert result.status == "paid"
    assert result.paid_at is not None


async def test_mark_paid_returns_none_for_unknown_payment_id(full_db):
    assert await crud.mark_paid("unknown") is None


async def test_mark_paid_returns_none_on_repeat_webhook_same_payment_id(full_db):
    await crud.get_or_create_user(1)
    purchase = await crud.create_purchase(1, "book", 990)
    await crud.attach_yk_payment_id(purchase.id, "pay-1")

    await crud.mark_paid("pay-1")
    assert await crud.mark_paid("pay-1") is None


async def test_mark_paid_returns_none_when_another_pending_dup_conflicts(full_db):
    """Два pending-платежа за одну и ту же книгу одного юзера (брошенный дубль).
    Первый корректно помечается paid; повторный webhook по ВТОРОМУ payment_id
    должен вернуть None, а не бросить IntegrityError наружу."""
    await crud.get_or_create_user(1)
    first = await crud.create_purchase(1, "book", 990)
    await crud.attach_yk_payment_id(first.id, "pay-1")
    second = await crud.create_purchase(1, "book", 990)
    await crud.attach_yk_payment_id(second.id, "pay-2")

    assert (await crud.mark_paid("pay-1")) is not None
    assert await crud.mark_paid("pay-2") is None
