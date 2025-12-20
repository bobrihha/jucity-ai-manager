from __future__ import annotations

from dataclasses import dataclass

from app.repos.facts_repo import FactsBundle
from app.repos.leads_repo import Lead
from app.services.rag_service import RetrievedChunk
from app.utils import normalize_text


@dataclass(frozen=True)
class ComposedAnswer:
    reply: str
    questions: list[str]
    link_url: str | None
    admin_message: str | None = None
    rag_used: bool = False


class Composer:
    def facts_keys_used(self, intent: str) -> list[str]:
        if intent == "contacts":
            return ["contacts", "location", "opening_hours", "transport", "site_pages"]
        if intent == "rules":
            return ["site_pages", "legal_documents"]
        if intent in {"start", "clarify"}:
            return []
        if intent in {
            "prices_tickets",
            "prices_vr",
            "promotions",
            "gift_cards",
            "poster",
            "attractions",
            "restaurant",
            "party_main",
            "graduation",
            "new_year_trees",
        }:
            return ["site_pages"]
        return []

    def compose(
        self,
        *,
        intent: str,
        facts: FactsBundle,
        link_url: str | None,
        user_message: str,
        lead: Lead | None = None,
        missing_slots: list[str] | None = None,
        handoff_created: bool = False,
        admin_message: str | None = None,
        rag_chunks: list[RetrievedChunk] | None = None,
    ) -> ComposedAnswer:
        questions: list[str] = []
        text = ""
        rag_used = bool(rag_chunks)

        if intent == "start":
            text = (
                "Привет! Я Джуси — помощник парка «Джунгли Сити» 🐒🌴\n"
                "Могу подсказать:\n"
                "• адрес и как добраться\n"
                "• график работы\n"
                "• цены и билеты\n"
                "• дни рождения/выпускные\n"
                "• ресторан и меню\n"
                "• правила посещения\n"
                "\n"
                "Напиши просто вопрос, например:\n"
                "«Как до вас добраться?»\n"
                "«Сколько стоит билет?»\n"
                "«Хочу день рождения на 15 января, 8 детей по 6 лет»\n"
                "\n"
                "С чего начнём? 🙂"
            )

        elif intent == "clarify":
            text = (
                "Ой, извини — я слишком сухо ответил 🙈\n"
                "Напиши, что тебе нужно, как будто пишешь администратору: "
                "«цены», «как добраться», «график», «день рождения», «меню», «правила».\n"
                "Я сразу отвечу и дам ссылку, если надо."
            )

        elif intent == "contacts":
            chunks: list[str] = []
            if facts.location and facts.location.get("address_text"):
                chunks.append(f"Адрес: {facts.location['address_text']}")

            opening = facts.opening_hours_text
            if opening:
                chunks.append(f"Часы работы: {opening}")

            transport_lines = [t["text"] for t in (facts.transport or []) if t.get("text")]
            if transport_lines:
                chunks.append("Как добраться:")
                chunks.extend([f"- {line}" for line in transport_lines[:2]])

            phone = facts.primary_phone
            if phone:
                chunks.append(f"Телефон: {phone}")

            text = "\n".join(chunks) if chunks else "Подскажите, что именно из контактов нужно: адрес или телефон?"

        elif intent == "rules":
            if rag_chunks:
                text = self._summarize_chunks(rag_chunks)
            else:
                text = "У нас есть правила посещения (безопасность, возрастные ограничения и т.п.). Подробности на странице."

        elif intent in {"prices_tickets", "prices_vr", "promotions", "gift_cards"}:
            text = "Подробная информация по этому вопросу — на странице."
            t = normalize_text(user_message)
            if intent in {"prices_tickets", "promotions"} and not any(
                w in t
                for w in [
                    "сегодня",
                    "завтра",
                    "выходн",
                    "будн",
                    "суббот",
                    "воскрес",
                    "пятниц",
                    "понедел",
                    "вторник",
                    "сред",
                    "четверг",
                ]
            ):
                questions.append("На какую дату планируете визит?")

        elif intent in {"party_main", "graduation", "new_year_trees"}:
            text, questions = self._compose_lead(intent=intent, lead=lead, missing_slots=missing_slots or [])

        elif intent == "handoff":
            if handoff_created:
                text = "Спасибо! Передала запрос менеджеру, с вами свяжутся по указанному номеру."
            else:
                text = "Поняла. Чтобы передать менеджеру и уточнить детали, напишите номер телефона для связи."
                questions.append("Напишите, пожалуйста, номер телефона для связи.")

        elif intent in {"poster", "attractions", "restaurant"}:
            if rag_chunks:
                text = self._summarize_chunks(rag_chunks)
                if intent == "restaurant":
                    text = self._restaurant_safe(text)
            else:
                text = "Подробности и актуальная информация — на странице."

        else:
            text = (
                "Понял! Чтобы помочь точнее — это про:\n"
                "• цены/билеты\n"
                "• как добраться/контакты\n"
                "• график работы\n"
                "• праздник/бронь\n"
                "• правила или ресторан?\n"
                "\n"
                "Напиши одним словом или сразу вопрос 🙂"
            )
            questions.append("Что именно интересует?")

        reply = self._with_single_link(text, link_url)
        return ComposedAnswer(
            reply=reply,
            questions=questions[:2],
            link_url=link_url,
            admin_message=admin_message,
            rag_used=rag_used,
        )

    def _compose_lead(self, *, intent: str, lead: Lead | None, missing_slots: list[str]) -> tuple[str, list[str]]:
        intro = {
            "party_main": "Можем помочь с праздником — уточню пару деталей и подберём вариант.",
            "graduation": "По выпускному уточню пару деталей — и предложу формат.",
            "new_year_trees": "По новогодним ёлкам/утренникам уточню пару деталей — и предложу варианты.",
        }.get(intent, "Уточню пару деталей.")

        summary_parts: list[str] = []
        if lead:
            if lead.event_date:
                summary_parts.append(f"дата: {lead.event_date.isoformat()}")
            elif lead.day_of_week is not None:
                summary_parts.append("день недели указан")
            if lead.kids_count:
                summary_parts.append(f"детей: {lead.kids_count}")
            if lead.kids_age_main and intent == "party_main":
                summary_parts.append(f"возраст: {lead.kids_age_main}")
            if lead.client_phone:
                summary_parts.append("телефон: есть")

        summary = f"Пока записала: {', '.join(summary_parts)}." if summary_parts else ""

        questions: list[str] = []

        def ask_date() -> None:
            questions.append("На какую дату планируете мероприятие? (можно день/месяц или день недели)")

        def ask_kids_count() -> None:
            questions.append("Сколько будет детей?")

        def ask_age() -> None:
            questions.append("Какой возраст детей (примерно)?")

        def ask_phone() -> None:
            questions.append("Чтобы закрепить бронь и уточнить детали, напишите номер телефона для связи.")

        if "event_date" in missing_slots:
            ask_date()
        if "kids_count" in missing_slots and len(questions) < 2:
            ask_kids_count()
        if "kids_age_main" in missing_slots and len(questions) < 2 and intent == "party_main":
            ask_age()

        if "client_phone" in missing_slots and len(questions) < 2:
            engaged = False
            if lead and (lead.event_date or lead.day_of_week is not None or lead.kids_count):
                engaged = True
            if engaged:
                ask_phone()
            else:
                if len(questions) < 2 and "event_date" not in missing_slots:
                    ask_date()

        text = intro
        if summary:
            text = f"{text}\n{summary}"
        return text, questions

    def _with_single_link(self, text: str, link_url: str | None) -> str:
        if not link_url:
            return text
        if "http://" in text or "https://" in text:
            return text
        return f"{text}\n{link_url}"

    def _summarize_chunks(self, chunks: list[RetrievedChunk]) -> str:
        if not chunks:
            return "Подробности и актуальная информация — на странице."
        parts: list[str] = []
        for c in chunks[:3]:
            snippet = (c.chunk_text or "").strip().replace("\n", " ")
            snippet = " ".join(snippet.split())
            if len(snippet) > 420:
                snippet = snippet[:420].rsplit(" ", 1)[0] + "…"
            if snippet:
                parts.append(snippet)
        if not parts:
            return "Подробности и актуальная информация — на странице."
        return "\n".join(parts[:2])

    def _restaurant_safe(self, text: str) -> str:
        from app.domain.patterns import MONEY_WITH_CURRENCY_RE, PRICE_WORD_NUMBER_RE

        text = MONEY_WITH_CURRENCY_RE.sub("—", text)
        text = PRICE_WORD_NUMBER_RE.sub("цена —", text)
        tail = "Меню на сайте носит информационный характер (не оферта); точные цены и состав уточняются у администратора."
        if tail.lower() in text.lower():
            return text
        return f"{text}\n{tail}"
