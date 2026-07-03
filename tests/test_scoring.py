"""Детерминированный подсчёт результата теста: чистые типы + все случаи ничьей."""
from services.scoring import IMPOSTOR, OTHERS_GOALS, SURVIVAL, compute_result


def _scores(*values: int) -> dict[int, int]:
    assert len(values) == 7
    return {i + 1: v for i, v in enumerate(values)}


def test_example_from_spec():
    # Да,Да,Нет,Иногда,Нет,Да,Иногда -> Q1..Q7 = 2,2,0,1,0,2,1 -> «Выживание»
    assert compute_result(_scores(2, 2, 0, 1, 0, 2, 1)) == SURVIVAL


def test_pure_survival():
    assert compute_result(_scores(2, 2, 0, 0, 0, 2, 0)) == SURVIVAL


def test_pure_impostor():
    assert compute_result(_scores(0, 0, 2, 0, 2, 0, 2)) == IMPOSTOR


def test_pure_others_goals():
    assert compute_result(_scores(0, 0, 0, 2, 0, 0, 0)) == OTHERS_GOALS


def test_full_tie_all_zero_prefers_impostor():
    assert compute_result(_scores(0, 0, 0, 0, 0, 0, 0)) == IMPOSTOR


def test_tie_impostor_survival_prefers_impostor():
    # survival=Q1+Q2+Q6=4, impostor=Q3+Q5+Q7=4, others=Q4+Q6+Q7=0
    assert compute_result(_scores(2, 2, 2, 0, 2, 0, 0)) == IMPOSTOR


def test_tie_survival_others_prefers_survival():
    # survival=Q1+Q2+Q6=4, others=Q4+Q6+Q7=4, impostor=Q3+Q5+Q7=0
    assert compute_result(_scores(2, 0, 0, 2, 0, 2, 0)) == SURVIVAL
