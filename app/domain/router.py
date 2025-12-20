from __future__ import annotations

from dataclasses import dataclass

from app.utils import normalize_text


@dataclass(frozen=True)
class RouteResult:
    intent: str
    mode: str
    confidence: float
    questions: list[str]
    link_intent: str | None
    required_slots: list[str]


class Router:
    def route(self, message: str) -> RouteResult:
        raw = (message or "").strip()
        raw_lower = raw.lower()
        text = normalize_text(message)

        def has_any(*needles: str) -> bool:
            return any(n in text for n in needles)

        intent = "fallback"
        link_intent: str | None = None
        required_slots: list[str] = []

        if raw_lower == "/help" or raw_lower.startswith("/start"):
            intent = "start"

        elif has_any("в смысле", "не понял", "что?", "чего", "поясни") or "??" in raw:
            intent = "clarify"

        elif has_any(
            "контакт",
            "телефон",
            "адрес",
            "как добрат",
            "как доехать",
            "проехать",
            "где вы",
            "часы работы",
            "время работы",
            "режим работы",
            "график",
            "работаете",
        ):
            intent = "contacts"
            link_intent = "contact"
        elif has_any("правила", "можно", "нельзя", "запрещ"):
            intent = "rules"
            link_intent = "rules"
        elif has_any("администратор", "оператор", "менеджер", "человек", "свяжитесь", "позвоните", "жалоб", "верните деньги"):
            intent = "handoff"
            link_intent = "rules"
        elif has_any("ресторан", "меню", "еда", "кафе"):
            intent = "restaurant"
            link_intent = "restaurant"
        elif has_any("афиша", "мероприят"):
            intent = "poster"
            link_intent = "poster"
        elif has_any("аттракцион", "что есть", "развлечен"):
            intent = "attractions"
            link_intent = "attractions"
        elif has_any("цены", "сколько стоит", "билет", "билеты", "стоимость"):
            intent = "prices_tickets"
            link_intent = "prices_tickets"
        elif has_any("vr", "виртуаль"):
            intent = "prices_vr"
            link_intent = "prices_vr"
        elif has_any("акци", "скидк", "промокод"):
            intent = "promotions"
            link_intent = "promotions"
        elif has_any("сертификат", "подарочн"):
            intent = "gift_cards"
            link_intent = "gift_cards"
        elif has_any("д/р", "день рождения", "праздник", "детский праздник"):
            intent = "party_main"
            link_intent = "party_main"
        elif has_any("выпускной"):
            intent = "graduation"
            link_intent = "graduation"
        elif has_any("елки", "ёлки", "утренник", "новый год"):
            intent = "new_year_trees"
            link_intent = "new_year_trees"

        if intent in {"party_main", "graduation", "new_year_trees"}:
            mode = "lead_mode"
            if intent == "party_main":
                required_slots = ["event_date", "kids_count", "kids_age_main", "client_phone"]
            elif intent == "graduation":
                required_slots = ["event_date", "kids_count", "client_phone"]
            else:
                required_slots = ["event_date", "client_phone"]
        elif intent == "handoff":
            mode = "handoff_mode"
            required_slots = ["client_phone"]
        elif intent in {"start", "clarify"}:
            mode = "consult_mode"
        elif intent == "rules":
            mode = "legal_mode"
        else:
            mode = "consult_mode"

        confidence = 1.0 if intent in {"start", "clarify"} else 0.7
        return RouteResult(
            intent=intent,
            mode=mode,
            confidence=confidence,
            questions=[],
            link_intent=link_intent,
            required_slots=required_slots,
        )
