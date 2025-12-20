from __future__ import annotations

import pytest

from app.config import settings
from app.services.llm_service import render_text


@pytest.mark.asyncio
async def test_llm_mock_constraints_links_money_questions(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_enabled", True)
    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(settings, "llm_api_key", "")
    monkeypatch.setattr(settings, "llm_model", "")

    plan = {
        "intent": "fallback",
        "facts": {},
        "rag_snippets": [],
        "answer_points": ["Текст с ценой 500 ₽ и ссылкой."],
        "questions": ["Ок?", "Ещё вопрос?", "Третий?"],
        "link": "https://example.test/x",
        "constraints": {"max_questions": 2, "max_links": 1, "no_prices_unless_facts": True, "no_currency_from_rag": True},
    }

    res = await render_text(plan, channel="telegram", voice="jucity_nn")

    assert res.text.count("http://") + res.text.count("https://") <= 1
    assert "₽" not in res.text
    assert "руб" not in res.text.lower()
    assert res.text.count("?") <= 2

