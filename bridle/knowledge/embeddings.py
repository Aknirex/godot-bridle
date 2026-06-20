from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol


class EmbeddingProvider(Protocol):
    @property
    def index_identity(self) -> str: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class DeterministicEmbeddingProvider:
    """Offline embedding for tests and development, not semantic production search."""

    def __init__(self, dimensions: int = 64) -> None:
        if dimensions < 1:
            raise ValueError("Embedding dimensions must be positive.")
        self.dimensions = dimensions

    @property
    def index_identity(self) -> str:
        return f"deterministic-v1-{self.dimensions}"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in re.findall(r"\w+", text.casefold()):
            digest = hashlib.sha256(token.encode()).digest()
            index = int.from_bytes(digest[:4], "little") % self.dimensions
            vector[index] += -1.0 if digest[4] & 1 else 1.0
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector] if norm else vector
