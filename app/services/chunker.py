from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    chunk_text: str
    chunk_index: int
    source_url: str | None
    title: str | None


def chunk_text(
    *,
    text: str,
    title: str | None,
    source_url: str | None,
    chunk_size_chars: int = 1600,
    overlap_chars: int = 200,
) -> list[Chunk]:
    raw = text.strip()
    if not raw:
        return []

    header = ""
    if title:
        header = f"{title}\n\n"

    chunks: list[Chunk] = []
    i = 0
    idx = 0
    n = len(raw)
    while i < n:
        start = max(0, i - overlap_chars) if idx > 0 else i
        end = min(n, start + chunk_size_chars)
        body = raw[start:end].strip()
        chunk_body = (header + body).strip()
        chunks.append(
            Chunk(
                chunk_id=f"{idx}:{_stable_id(source_url, title, start, end)}",
                chunk_text=chunk_body,
                chunk_index=idx,
                source_url=source_url,
                title=title,
            )
        )
        idx += 1
        if end >= n:
            break
        i = end
    return chunks


def _stable_id(source_url: str | None, title: str | None, start: int, end: int) -> str:
    base = (source_url or "") + "|" + (title or "") + f"|{start}:{end}"
    import hashlib

    return hashlib.md5(base.encode("utf-8")).hexdigest()

