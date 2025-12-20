from __future__ import annotations

import re

# Common reusable patterns (compiled once per process).

PHONE_CANDIDATE_RE = re.compile(r"(?P<num>(?:\+?\d)[\d\s\-()]{6,}\d)")

EXTRACT_PHONE_RE = PHONE_CANDIDATE_RE

TIME_HHMM_RE = re.compile(r"(?P<h>\d{1,2})[:.](?P<m>\d{2})")
DATE_DDMM_RE = re.compile(r"(?P<d>\d{1,2})[./](?P<m>\d{1,2})(?:[./](?P<y>\d{2,4}))?")
DATE_DD_MONTH_RE = re.compile(
    r"(?P<d>\d{1,2})\s*(?P<mon>январ[яь]|феврал[яь]|март[а]?|апрел[яь]|ма[йя]|июн[яь]|июл[яь]|август[а]?|сентябр[яь]|октябр[яь]|ноябр[яь]|декабр[яь])"
)

KIDS_COUNT_RE = re.compile(r"(?P<n>\d{1,2})\s*(?:дет|реб[её]н|ребят|чел\.?\b)")
AGE_RE = re.compile(r"(?P<n>\d{1,2})\s*(?:лет|года|год|л\b)")
NAS_COUNT_RE = re.compile(r"\bнас\s+(?P<n>\d{1,2})\b")
TIME_WORD_DAY_RE = re.compile(r"\bв\s*(?P<h>\d{1,2})\s*дня\b")

NAME_INTRO_RE = re.compile(
    r"\bменя\s+зовут\s+(?P<name>[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё-]{1,40})\b",
    re.IGNORECASE,
)

NAME_I_AM_RE = re.compile(
    r"^\s*я\s+(?P<name>[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё-]{1,40})\s*$",
    re.IGNORECASE,
)

MONEY_WITH_CURRENCY_RE = re.compile(
    r"\b\d[\d\s]*(?:[.,]\d+)?\s*(?:₽|руб\.?|р\.|рублей|рубля)(?!\w)",
    re.IGNORECASE,
)

PRICE_WORD_NUMBER_RE = re.compile(
    r"\b(?:цена|стоимость)\s*(?:от\s*)?\d[\d\s]*(?:[.,]\d+)?\b",
    re.IGNORECASE,
)
