from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import settings


@dataclass(frozen=True)
class PlannerToolCall:
    name: str
    args: dict[str, Any]


@dataclass(frozen=True)
class PlannerOutput:
    intent: str
    mode: str
    reply: str
    questions: list[str]
    link: str | None
    tool_calls: list[PlannerToolCall]
    slot_updates: dict[str, Any]


@dataclass(frozen=True)
class PlannerResult:
    output: PlannerOutput
    provider: str
    model: str
    latency_ms: int


def _parse_strict_json(text: str) -> dict[str, Any]:
    text = text.strip()
    # tolerate code fences
    if text.startswith("```"):
        text = text.strip("`")
        # try to locate first { ... }
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Planner did not return JSON object")
    return json.loads(text[start : end + 1])


def _coerce_output(obj: dict[str, Any]) -> PlannerOutput:
    def _str(v: Any, field: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError(f"Planner field '{field}' must be non-empty string")
        return v.strip()

    intent = _str(obj.get("intent"), "intent")
    mode = _str(obj.get("mode"), "mode")
    reply = _str(obj.get("reply"), "reply")

    questions_raw = obj.get("questions") or []
    if not isinstance(questions_raw, list):
        raise ValueError("Planner field 'questions' must be list")
    questions = [str(q).strip() for q in questions_raw if str(q).strip()][:2]

    link = obj.get("link")
    if link is not None:
        link = str(link).strip() or None

    tool_calls_raw = obj.get("tool_calls") or []
    if not isinstance(tool_calls_raw, list):
        raise ValueError("Planner field 'tool_calls' must be list")
    tool_calls: list[PlannerToolCall] = []
    for item in tool_calls_raw[:2]:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        args = item.get("args") if isinstance(item.get("args"), dict) else {}
        if name:
            tool_calls.append(PlannerToolCall(name=name, args=dict(args)))

    slot_updates = obj.get("slot_updates") if isinstance(obj.get("slot_updates"), dict) else {}

    return PlannerOutput(
        intent=intent,
        mode=mode,
        reply=reply,
        questions=questions,
        link=link,
        tool_calls=tool_calls,
        slot_updates=dict(slot_updates),
    )


def _tool_schema() -> list[dict[str, Any]]:
    return [
        {"name": "tool_get_facts", "args": {"park_slug": "nn"}, "returns": {"facts": "object", "pages": "object"}},
        {"name": "tool_search_kb", "args": {"park_slug": "nn", "query": "..."}, "returns": {"chunks": "list"}},
        {
            "name": "tool_upsert_lead",
            "args": {"park_slug": "nn", "session_id": "uuid", "slot_updates": {"kids_count": 8}},
            "returns": {"lead_id": "uuid", "missing_slots": "list"},
        },
        {
            "name": "tool_create_handoff",
            "args": {"park_slug": "nn", "session_id": "uuid", "reason": "..."},
            "returns": {"handoff_created": True},
        },
    ]


def _planner_system_prompt() -> str:
    return (
        "Ты менеджер парка. Не задавай вопрос 'что вас интересует'. Всегда отвечай по делу.\n"
        "Верни СТРОГО JSON без пояснений и без markdown.\n"
        "Формат: { intent, mode, reply, questions, link, tool_calls, slot_updates }.\n"
        "questions: массив из 0..2 строк. link: строка или null. tool_calls: массив 0..2 объектов {name,args}.\n"
        "slot_updates: объект (может быть пустым).\n"
        "Если не хватает данных для ответа — задай 1 уточняющий вопрос (в questions) и в reply дай краткий контекст.\n"
        "Стиль: коротко, живо, 1–2 эмодзи, лёгкий юмор уместно.\n"
        "Нельзя: придумывать цены/суммы/рубли, добавлять ссылки кроме link.\n"
    )


async def run_planner(
    *,
    user_message: str,
    channel: str,
    park_slug: str,
    session_id: str,
    user_id: str | None,
    tool_results: dict[str, Any] | None = None,
) -> PlannerResult:
    provider = settings.llm_planner_provider
    model = settings.llm_planner_model
    t0 = time.monotonic()

    if provider == "mock":
        data = _mock_planner(
            user_message=user_message,
            channel=channel,
            park_slug=park_slug,
            session_id=session_id,
            user_id=user_id,
            tool_results=tool_results or {},
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        return PlannerResult(output=_coerce_output(data), provider=provider, model="mock", latency_ms=latency_ms)

    if provider == "openai":
        if not settings.llm_planner_api_key:
            raise RuntimeError("LLM_PLANNER_API_KEY is required for openai planner")
        if not model:
            model = "gpt-4o-mini"

        payload = {
            "model": model,
            "input": [
                {"role": "system", "content": _planner_system_prompt()},
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "park_slug": park_slug,
                            "channel": channel,
                            "session_id": session_id,
                            "user_id": user_id,
                            "user_message": user_message,
                            "tools": _tool_schema(),
                            "tool_results": tool_results or {},
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        async with httpx.AsyncClient(timeout=25) as client:
            r = await client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {settings.llm_planner_api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            r.raise_for_status()
            resp = r.json()
        text = ""
        for item in resp.get("output", []):
            for c in item.get("content", []):
                if c.get("type") == "output_text" and c.get("text"):
                    text += c["text"]
        if not text:
            raise RuntimeError("Planner response had no text")
        obj = _parse_strict_json(text)
        latency_ms = int((time.monotonic() - t0) * 1000)
        return PlannerResult(output=_coerce_output(obj), provider=provider, model=model, latency_ms=latency_ms)

    raise RuntimeError(f"Unsupported LLM_PLANNER_PROVIDER: {provider}")


def _mock_planner(
    *,
    user_message: str,
    channel: str,
    park_slug: str,
    session_id: str,
    user_id: str | None,
    tool_results: dict[str, Any],
) -> dict[str, Any]:
    t = user_message.lower()
    have_facts = "tool_get_facts" in tool_results

    def call_get_facts() -> dict[str, Any]:
        return {
            "intent": "info",
            "mode": "consult_mode",
            "reply": "Секунду, уточню по базе 👀",
            "questions": [],
            "link": None,
            "tool_calls": [{"name": "tool_get_facts", "args": {"park_slug": park_slug}}],
            "slot_updates": {},
        }

    if "/start" in t or t.strip() in {"/help", "/start"}:
        return {
            "intent": "start",
            "mode": "consult_mode",
            "reply": "Привет! Я Джуси — помощник парка «Джунгли Сити» 🐒🌴",
            "questions": ["С чего начнём?"],
            "link": None,
            "tool_calls": [],
            "slot_updates": {},
        }

    if "скучн" in t:
        return {
            "intent": "banter",
            "mode": "consult_mode",
            "reply": "Ой, приняла 😅 Давай сделаю полезно: спроси про график, как добраться или ресторан — отвечу по делу.",
            "questions": [],
            "link": None,
            "tool_calls": [],
            "slot_updates": {},
        }

    if any(w in t for w in ["поесть", "по кушать", "покушать", "ресторан", "меню", "еда", "кафе"]):
        if not have_facts:
            return call_get_facts()
        pages = tool_results["tool_get_facts"].get("pages") or {}
        link = pages.get("restaurant") or None
        return {
            "intent": "restaurant",
            "mode": "consult_mode",
            "reply": "Да, в парке есть ресторан/кафе 🙂 Меню и актуальные позиции — по ссылке.",
            "questions": ["Нужен перекус во время визита или для праздника?"],
            "link": link,
            "tool_calls": [],
            "slot_updates": {},
        }

    if any(w in t for w in ["др", "день рождения", "праздник", "д.р"]):
        return {
            "intent": "party_main",
            "mode": "lead_mode",
            "reply": "Класс! Помогу собрать заявку на праздник 🎂",
            "questions": ["На какую дату планируете?", "Сколько детей и какой возраст?"],
            "link": None,
            "tool_calls": [],
            "slot_updates": {},
        }

    return {
        "intent": "fallback",
        "mode": "consult_mode",
        "reply": "Поняла 🙂 Спроси, пожалуйста, конкретнее — про график, как добраться, цены или праздник.",
        "questions": [],
        "link": None,
        "tool_calls": [],
        "slot_updates": {},
    }

