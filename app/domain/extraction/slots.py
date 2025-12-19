from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time

from app.utils import normalize_text


_PHONE_RE = re.compile(r"(?P<num>(?:\\+?\\d)[\\d\\s\\-()]{6,}\\d)")
_TIME_HHMM_RE = re.compile(r"(?P<h>\\d{1,2})[:.](?P<m>\\d{2})")
_DATE_DDMM_RE = re.compile(r"(?P<d>\\d{1,2})[./](?P<m>\\d{1,2})(?:[./](?P<y>\\d{2,4}))?")
_DATE_DD_MONTH_RE = re.compile(
    r"(?P<d>\\d{1,2})\\s*(?P<mon>январ[яь]|феврал[яь]|март[а]?|апрел[яь]|ма[йя]|июн[яь]|июл[яь]|август[а]?|сентябр[яь]|октябр[яь]|ноябр[яь]|декабр[яь])"
)
_KIDS_COUNT_RE = re.compile(r"(?P<n>\\d{1,2})\\s*(?:дет|реб[её]н|ребят|чел\\.?\\b)")
_AGE_RE = re.compile(r"(?P<n>\\d{1,2})\\s*(?:лет|года|год|л\\b)")


_MONTHS = {
    "январ": 1,
    "феврал": 2,
    "март": 3,
    "апрел": 4,
    "ма": 5,
    "июн": 6,
    "июл": 7,
    "август": 8,
    "сентябр": 9,
    "октябр": 10,
    "ноябр": 11,
    "декабр": 12,
}


@dataclass(frozen=True)
class SlotsPatch:
    client_phone: str | None = None
    event_date: date | None = None
    event_time: time | None = None
    day_of_week: int | None = None  # 0=Mon..6=Sun
    kids_count: int | None = None
    kids_age_main: int | None = None


def extract_phone(text: str) -> str | None:
    m = _PHONE_RE.search(text)
    if not m:
        return None
    raw = m.group("num")
    digits = re.sub(r"\\D", "", raw)
    if not digits:
        return None
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    if digits.startswith("7") and len(digits) == 11:
        return "+" + digits
    if digits.startswith("9") and len(digits) == 10:
        return "+7" + digits
    return None


def mask_phone(phone: str) -> str:
    digits = re.sub(r"\\D", "", phone)
    if len(digits) < 4:
        return phone
    keep_last = digits[-2:]
    if digits.startswith("7") and len(digits) == 11:
        return "+7" + ("*" * 7) + keep_last
    return ("*" * max(0, len(digits) - 2)) + keep_last


def extract_kids_count(text: str, *, party_context: bool) -> int | None:
    t = normalize_text(text)
    m = _KIDS_COUNT_RE.search(t)
    if m:
        n = int(m.group("n"))
        return n if 0 < n < 100 else None
    if party_context:
        m2 = re.search(r"\\bнас\\s+(?P<n>\\d{1,2})\\b", t)
        if m2:
            n = int(m2.group("n"))
            return n if 0 < n < 100 else None
    return None


def extract_age(text: str) -> int | None:
    t = normalize_text(text)
    m = _AGE_RE.search(t)
    if not m:
        return None
    n = int(m.group("n"))
    return n if 0 < n < 100 else None


def extract_date(text: str) -> tuple[date | None, int | None]:
    t = normalize_text(text)
    today = date.today()

    m = _DATE_DDMM_RE.search(t)
    if m:
        d = int(m.group("d"))
        mon = int(m.group("m"))
        y_raw = m.group("y")
        y = today.year
        if y_raw:
            y = int(y_raw)
            if y < 100:
                y += 2000
        try:
            return date(y, mon, d), None
        except ValueError:
            return None, None

    m2 = _DATE_DD_MONTH_RE.search(t)
    if m2:
        d = int(m2.group("d"))
        mon_token = m2.group("mon")
        mon_key = next((k for k in _MONTHS if mon_token.startswith(k)), None)
        if not mon_key:
            return None, None
        mon = _MONTHS[mon_key]
        y = today.year
        try:
            dt = date(y, mon, d)
            if dt < today:
                dt = date(y + 1, mon, d)
            return dt, None
        except ValueError:
            return None, None

    dow = extract_day_of_week(t)
    return None, dow


def extract_day_of_week(text_norm: str) -> int | None:
    t = text_norm
    if "понед" in t:
        return 0
    if "вторн" in t:
        return 1
    if "сред" in t:
        return 2
    if "четвер" in t:
        return 3
    if "пятниц" in t:
        return 4
    if "суббот" in t:
        return 5
    if "воскрес" in t:
        return 6
    return None


def extract_time(text: str) -> time | None:
    t = normalize_text(text)
    m = _TIME_HHMM_RE.search(t)
    if m:
        h = int(m.group("h"))
        mi = int(m.group("m"))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return time(h, mi)

    m2 = re.search(r"\\bв\\s*(?P<h>\\d{1,2})\\s*дня\\b", t)
    if m2:
        h = int(m2.group("h"))
        if 1 <= h <= 11:
            return time(h + 12, 0)
        if h == 12:
            return time(12, 0)
    return None


def extract_slots(text: str, *, party_context: bool) -> SlotsPatch:
    phone = extract_phone(text)
    kids_count = extract_kids_count(text, party_context=party_context)
    kids_age_main = extract_age(text) if party_context else None
    d, dow = extract_date(text)
    tm = extract_time(text)

    return SlotsPatch(
        client_phone=phone,
        event_date=d,
        event_time=tm,
        day_of_week=dow,
        kids_count=kids_count,
        kids_age_main=kids_age_main,
    )


def merge_slots(existing: dict, patch: SlotsPatch) -> dict:
    out = dict(existing)
    for key in (
        "client_phone",
        "event_date",
        "event_time",
        "day_of_week",
        "kids_count",
        "kids_age_main",
    ):
        val = getattr(patch, key)
        if val is None:
            continue
        if out.get(key) in (None, "", 0):
            out[key] = val
    return out

