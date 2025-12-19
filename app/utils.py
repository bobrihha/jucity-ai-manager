from __future__ import annotations

import re

from app.domain.patterns import PHONE_CANDIDATE_RE

def mask_phones(text: str) -> str:
    def _mask(match: re.Match[str]) -> str:
        raw = match.group("num")
        digits = re.sub(r"\D", "", raw)
        if len(digits) < 7:
            return raw
        masked_digits = ("*" * max(0, len(digits) - 2)) + digits[-2:]
        it = iter(masked_digits)

        out = []
        for ch in raw:
            if ch.isdigit():
                out.append(next(it))
            else:
                out.append(ch)
        return "".join(out)

    return PHONE_CANDIDATE_RE.sub(_mask, text)


def normalize_text(text: str) -> str:
    text = text.lower().strip()
    return text.replace("ё", "е")
