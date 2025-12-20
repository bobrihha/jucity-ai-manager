from __future__ import annotations

import re
from typing import Any

from app.domain.patterns import MONEY_WITH_CURRENCY_RE, PRICE_WORD_NUMBER_RE


def validate_planner_output(text: str, *, link: str | None, questions: list[str]) -> tuple[bool, list[str]]:
    issues: list[str] = []

    urls = re.findall(r"https?://[^\s]+", text)
    if len(urls) > 1:
        issues.append("Too many links")
    if link:
        for u in urls:
            if u.rstrip("/") != link.rstrip("/"):
                issues.append("Forbidden link")
    else:
        if urls:
            issues.append("Links are not allowed")

    if len(questions) > 2:
        issues.append("Too many questions in list")
    if text.count("?") > 2:
        issues.append("Too many question marks")

    if MONEY_WITH_CURRENCY_RE.search(text) or PRICE_WORD_NUMBER_RE.search(text):
        issues.append("Forbidden currency usage")

    if "что вас интересует" in text.lower():
        issues.append("Banned phrase")

    return (len(issues) == 0, issues)

