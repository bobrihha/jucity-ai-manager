from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.domain.patterns import MONEY_WITH_CURRENCY_RE


@dataclass(frozen=True)
class LLMRenderResult:
    text: str
    provider: str
    model: str
    latency_ms: int


def _load_voice_prompt(voice: str) -> str:
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / f"{voice}.md"
    try:
        return prompt_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _enforce_constraints(text: str, *, plan: dict[str, Any]) -> str:
    constraints = (plan.get("constraints") or {}) if isinstance(plan, dict) else {}
    max_links = int(constraints.get("max_links", 1))
    max_questions = int(constraints.get("max_questions", 2))

    link = plan.get("link") if isinstance(plan, dict) else None
    if link and isinstance(link, str):
        # keep only first occurrence of the allowed link; remove other urls
        parts = text.split(link)
        if len(parts) > 2:
            text = link.join(parts[:2]) + "".join(parts[2:])

    # Remove all other http(s) links if max_links==1, and plan.link is the only allowed link.
    if max_links <= 1:
        allowed = link if isinstance(link, str) else None
        lines = []
        for line in text.splitlines():
            if "http://" in line or "https://" in line:
                if allowed and allowed in line:
                    lines.append(allowed)
                continue
            lines.append(line)
        text = "\n".join(lines)

    # Ensure not more than max_questions by trimming extra question marks.
    if max_questions >= 0:
        qcount = text.count("?")
        if qcount > max_questions:
            # naive: replace extra '?' with '.'
            out = []
            seen = 0
            for ch in text:
                if ch == "?":
                    seen += 1
                    out.append("?" if seen <= max_questions else ".")
                else:
                    out.append(ch)
            text = "".join(out)

    # No money markers unless explicitly allowed (we never allow in MVP).
    if constraints.get("no_prices_unless_facts", True):
        if MONEY_WITH_CURRENCY_RE.search(text):
            text = MONEY_WITH_CURRENCY_RE.sub("—", text)

    return text.strip()


def _render_mock(plan: dict[str, Any], *, channel: str, voice: str) -> str:
    points = plan.get("answer_points") or []
    if not isinstance(points, list):
        points = []
    questions = plan.get("questions") or []
    if not isinstance(questions, list):
        questions = []
    link = plan.get("link")

    intro = ""
    intent = (plan.get("intent") or "").strip()
    if intent == "start":
        intro = "Привет! "
    elif channel == "telegram":
        intro = "Поняла 🙂 "

    body = "\n".join([str(p).strip() for p in points if str(p).strip()])
    if not body:
        body = "Подскажите, пожалуйста, что именно интересует?"

    q_lines = [str(q).strip() for q in questions if str(q).strip()]
    q_lines = q_lines[:2]

    text = intro + body if intro else body
    if q_lines:
        text = f"{text}\n\n" + "\n".join(q_lines)
    if link:
        text = f"{text}\n{link}"
    return text


async def render_text(plan: dict[str, Any], *, channel: str, voice: str) -> LLMRenderResult:
    provider = settings.llm_provider
    model = settings.llm_model

    if not settings.llm_enabled:
        raise RuntimeError("LLM is disabled")

    t0 = time.monotonic()

    if provider == "mock":
        text = _render_mock(plan, channel=channel, voice=voice)
        latency_ms = int((time.monotonic() - t0) * 1000)
        return LLMRenderResult(text=_enforce_constraints(text, plan=plan), provider=provider, model="mock", latency_ms=latency_ms)

    # For real providers we still obey: "LLM as stylist", so we only pass plan and style rules.
    prompt = _load_voice_prompt(voice)
    if not settings.llm_api_key:
        raise RuntimeError("LLM_API_KEY is required")
    if provider == "openai":
        # Minimal OpenAI Responses API call (no SDK dependency).
        if not model:
            model = "gpt-4o-mini"
        payload = {
            "model": model,
            "input": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": "Сформируй финальный текст ответа по plan (строго по правилам).\n\nplan:\n" + json.dumps(plan, ensure_ascii=False)},
            ],
        }
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {settings.llm_api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            r.raise_for_status()
            data = r.json()
        # Best-effort extraction of text output.
        text = ""
        for item in data.get("output", []):
            for c in item.get("content", []):
                if c.get("type") == "output_text" and c.get("text"):
                    text += c["text"]
        if not text:
            raise RuntimeError("OpenAI response had no text")
        latency_ms = int((time.monotonic() - t0) * 1000)
        return LLMRenderResult(text=_enforce_constraints(text, plan=plan), provider=provider, model=model, latency_ms=latency_ms)

    raise RuntimeError(f"Unsupported LLM_PROVIDER: {provider}")

