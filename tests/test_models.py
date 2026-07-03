"""Схема новых таблиц настроек — проверка через метаданные SQLAlchemy, без БД."""
from db.models import AdminPendingEdit, BotSetting


def test_bot_setting_columns():
    columns = set(BotSetting.__table__.columns.keys())
    assert columns == {"key", "value", "updated_at"}
    assert BotSetting.__table__.primary_key.columns.keys() == ["key"]


def test_admin_pending_edit_columns():
    columns = set(AdminPendingEdit.__table__.columns.keys())
    assert columns == {"admin_tg_id", "setting_key", "created_at"}
    assert AdminPendingEdit.__table__.primary_key.columns.keys() == ["admin_tg_id"]
