"""Подсчёт результата теста — чистая функция, без импортов aiogram/SQLAlchemy.

S_выживание = Q1+Q2+Q6, S_самозванец = Q3+Q5+Q7, S_чужие_цели = Q4+Q6+Q7.
Результат — тип с максимальной суммой; при ничьей побеждает фиксированный
приоритет: Самозванец → Выживание → Чужие цели (правило из ТЗ, Блок 3).
"""
from __future__ import annotations

SURVIVAL = "survival"
IMPOSTOR = "impostor"
OTHERS_GOALS = "others_goals"

_PRIORITY = {IMPOSTOR: 0, SURVIVAL: 1, OTHERS_GOALS: 2}


def compute_result(scores: dict[int, int]) -> str:
    """``scores`` — {1: 0|1|2, ..., 7: 0|1|2}, баллы за 7 ответов (Да=2, Иногда=1, Нет=0)."""
    sums = {
        SURVIVAL: scores[1] + scores[2] + scores[6],
        IMPOSTOR: scores[3] + scores[5] + scores[7],
        OTHERS_GOALS: scores[4] + scores[6] + scores[7],
    }
    return max(sums, key=lambda code: (sums[code], -_PRIORITY[code]))
