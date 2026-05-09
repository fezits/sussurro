from __future__ import annotations

from typing import Protocol

import numpy as np

from meeting.intelligence.rag.indexer import IndexedChunk


class _Embedder(Protocol):
    def encode(self, texts, normalize_embeddings: bool = True) -> np.ndarray: ...


class RagRetriever:
    def __init__(self, chunks: list[IndexedChunk], embedder: _Embedder) -> None:
        self.chunks = chunks
        self.embedder = embedder
        if chunks:
            self._matrix = np.stack([c.embedding for c in chunks])
        else:
            self._matrix = np.zeros((0, 0), dtype=np.float32)

    def retrieve(self, query: str, top_k: int = 5) -> list[IndexedChunk]:
        if not self.chunks:
            return []
        q = self.embedder.encode([query], normalize_embeddings=True)[0]
        scores = self._matrix @ q
        order = np.argsort(-scores)[:top_k]
        return [self.chunks[int(i)] for i in order]
