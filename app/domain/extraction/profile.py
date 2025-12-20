from __future__ import annotations

from app.domain.patterns import NAME_I_AM_RE, NAME_INTRO_RE


_STOPWORDS = {
    "хочу",
    "могу",
    "буду",
    "будем",
    "приду",
    "иду",
    "еду",
    "спрошу",
    "узнаю",
    "не",
    "щас",
    "сейчас",
    "тут",
}


def extract_name(text: str) -> str | None:
    raw = (text or "").strip()
    if not raw:
        return None

    m = NAME_INTRO_RE.search(raw)
    if m:
        name = (m.group("name") or "").strip()
        return _normalize_name(name)

    m = NAME_I_AM_RE.match(raw)
    if m:
        name = (m.group("name") or "").strip()
        if name.lower() in _STOPWORDS:
            return None
        return _normalize_name(name)

    return None


def _normalize_name(name: str) -> str:
    name = name.strip()
    if not name:
        return name
    return name[0].upper() + name[1:].lower()

