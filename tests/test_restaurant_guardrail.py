from __future__ import annotations

from app.domain.composer import Composer


def test_restaurant_guardrail_removes_money_keeps_other_numbers() -> None:
    c = Composer()
    text = "Режим 10:00–22:00. Детям 6 лет. Будет 8 детей. Длительность 2 часа. Комбо 500 ₽. Стоимость 900 руб."
    out = c._restaurant_safe(text)

    assert "10:00–22:00" in out
    assert "6 лет" in out
    assert "8 детей" in out
    assert "2 часа" in out

    assert "₽" not in out
    assert "500 ₽" not in out
    assert "900 руб" not in out.lower()

