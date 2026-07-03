"""Валидация email — переиспользуется чатом (handlers/consult.py) и Mini App API
(api/routers/funnel.py), чтобы правило не могло разъехаться между интерфейсами."""
from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email))
