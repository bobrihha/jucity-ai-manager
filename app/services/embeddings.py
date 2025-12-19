from __future__ import annotations

import math
from dataclasses import dataclass

from app.config import settings


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    vector_size: int


class Embeddings:
    def __init__(self, provider: str | None = None, *, vector_size: int = 256) -> None:
        self._provider = provider or settings.embeddings_provider
        self._vector_size = vector_size
        if self._provider != "local_hash":
            raise ValueError(f"Unsupported EMBEDDINGS_PROVIDER: {self._provider} (supported: local_hash)")

    @property
    def vector_size(self) -> int:
        return self._vector_size

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        if self._provider == "local_hash":
            return EmbeddingResult(vectors=[_hash_embed(t, self._vector_size) for t in texts], vector_size=self._vector_size)
        raise ValueError(f"Unsupported provider: {self._provider}")


def _hash_embed(text: str, dim: int) -> list[float]:
    import re

    tokens = re.findall(r"[a-zа-я0-9]{2,}", text.lower())
    vec = [0.0] * dim
    for tok in tokens:
        h = _fnv1a_32(tok)
        idx = h % dim
        sign = 1.0 if ((h >> 31) & 1) == 0 else -1.0
        vec[idx] += sign

    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _fnv1a_32(s: str) -> int:
    h = 2166136261
    for b in s.encode("utf-8"):
        h ^= b
        h = (h * 16777619) & 0xFFFFFFFF
    return h

