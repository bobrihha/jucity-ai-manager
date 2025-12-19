from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from typing import Literal

import httpx

from app.repos.kb_sources_repo import KBSource


ContentType = Literal["text/plain", "text/html", "application/pdf"]


@dataclass(frozen=True)
class FetchedDocument:
    text: str
    title: str | None
    source_url: str | None
    content_type: str | None
    text_hash: str


class KBFetcher:
    async def fetch_source_text(self, source: KBSource) -> FetchedDocument:
        if source.source_type == "file_path":
            if not source.file_path:
                raise ValueError("kb_source.file_path is required for source_type=file_path")
            return self._fetch_file(source.file_path, title=source.title)

        if source.source_type == "url":
            if not source.source_url:
                raise ValueError("kb_source.source_url is required for source_type=url")
            return await self._fetch_url(source.source_url, title=source.title)

        if source.source_type == "pdf":
            if source.file_path:
                return self._fetch_pdf_file(source.file_path, title=source.title, source_url=source.source_url)
            if source.source_url:
                return await self._fetch_pdf_url(source.source_url, title=source.title)
            raise ValueError("kb_source requires file_path or source_url for source_type=pdf")

        raise ValueError(f"Unsupported source_type: {source.source_type}")

    def _fetch_file(self, file_path: str, *, title: str | None) -> FetchedDocument:
        if not os.path.exists(file_path):
            raise FileNotFoundError(file_path)
        with open(file_path, "rb") as f:
            raw = f.read()

        if file_path.lower().endswith(".html") or file_path.lower().endswith(".htm"):
            text = _html_to_text(raw.decode("utf-8", errors="ignore"))
            ct: str | None = "text/html"
        else:
            text = raw.decode("utf-8", errors="ignore")
            ct = "text/plain"

        norm = _normalize_text_for_hash(text)
        return FetchedDocument(
            text=text.strip(),
            title=title,
            source_url=None,
            content_type=ct,
            text_hash=_sha256(norm),
        )

    async def _fetch_url(self, url: str, *, title: str | None) -> FetchedDocument:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
            ct = r.headers.get("content-type", "").split(";")[0].strip() or None
            raw_text = r.text

        if ct == "application/pdf" or url.lower().endswith(".pdf"):
            return await self._fetch_pdf_url(url, title=title)

        text = _html_to_text(raw_text)
        norm = _normalize_text_for_hash(text)
        return FetchedDocument(
            text=text.strip(),
            title=title,
            source_url=url,
            content_type=ct or "text/html",
            text_hash=_sha256(norm),
        )

    async def _fetch_pdf_url(self, url: str, *, title: str | None) -> FetchedDocument:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            r = await client.get(url)
            r.raise_for_status()
            data = r.content
            ct = r.headers.get("content-type", "").split(";")[0].strip() or "application/pdf"
        text = _pdf_bytes_to_text(data)
        norm = _normalize_text_for_hash(text)
        return FetchedDocument(
            text=text.strip(),
            title=title,
            source_url=url,
            content_type=ct,
            text_hash=_sha256(norm),
        )

    def _fetch_pdf_file(self, file_path: str, *, title: str | None, source_url: str | None) -> FetchedDocument:
        if not os.path.exists(file_path):
            raise FileNotFoundError(file_path)
        with open(file_path, "rb") as f:
            data = f.read()
        text = _pdf_bytes_to_text(data)
        norm = _normalize_text_for_hash(text)
        return FetchedDocument(
            text=text.strip(),
            title=title,
            source_url=source_url,
            content_type="application/pdf",
            text_hash=_sha256(norm),
        )


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize_text_for_hash(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip().lower()


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\\1>", " ", html)
    html = re.sub(r"(?is)<br\\s*/?>", "\n", html)
    html = re.sub(r"(?is)</(p|div|li|h\\d)>", "\n", html)
    html = re.sub(r"(?is)<.*?>", " ", html)
    html = re.sub(r"[ \t]+", " ", html)
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()


def _pdf_bytes_to_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("pypdf is required for pdf sources") from e

    import io

    reader = PdfReader(io.BytesIO(data))
    parts: list[str] = []
    for page in reader.pages:
        txt = page.extract_text() or ""
        parts.append(txt)
    text = "\n".join(parts)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

