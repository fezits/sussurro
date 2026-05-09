from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from meeting.intelligence.rag.chunker import chunk_text


class _Embedder(Protocol):
    def encode(self, texts, normalize_embeddings: bool = True) -> np.ndarray: ...


@dataclass
class IndexedChunk:
    text: str
    source: str  # relative path of source file
    embedding: np.ndarray


class RagIndexer:
    INDEX_NAME = ".index.npz"

    def __init__(
        self,
        knowledge_dir: Path | str,
        embedder: _Embedder,
        chunk_size: int = 500,
        overlap: int = 50,
    ) -> None:
        self.dir = Path(knowledge_dir)
        self.embedder = embedder
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.chunks: list[IndexedChunk] = []
        self.was_cached_last_call = False

    def _signature(self) -> str:
        h = hashlib.sha256()
        for p in sorted(self._iter_files()):
            try:
                stat = p.stat()
                h.update(str(p.relative_to(self.dir)).encode("utf-8"))
                h.update(str(stat.st_size).encode("utf-8"))
                h.update(str(int(stat.st_mtime)).encode("utf-8"))
            except OSError:
                continue
        h.update(str(self.chunk_size).encode())
        h.update(str(self.overlap).encode())
        return h.hexdigest()

    def _iter_files(self):
        for p in self.dir.rglob("*"):
            if not p.is_file():
                continue
            if p.name.startswith(".") or p.suffix.lower() not in {".md", ".txt", ".pdf"}:
                continue
            yield p

    def _read_file(self, path: Path) -> str:
        if path.suffix.lower() == ".pdf":
            try:
                from pypdf import PdfReader
                reader = PdfReader(str(path))
                return "\n".join((page.extract_text() or "") for page in reader.pages)
            except Exception:
                return ""
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""

    def build_or_load(self, force: bool = False) -> int:
        index_path = self.dir / self.INDEX_NAME
        sig = self._signature()
        self.was_cached_last_call = False

        if not force and index_path.exists():
            with np.load(index_path, allow_pickle=True) as data:
                stored_sig = str(data["signature"])
                if stored_sig == sig:
                    embeddings = data["embeddings"]
                    texts = list(data["texts"])
                    sources = list(data["sources"])
                    self.chunks = [
                        IndexedChunk(text=t, source=s, embedding=embeddings[i])
                        for i, (t, s) in enumerate(zip(texts, sources))
                    ]
                    self.was_cached_last_call = True
                    return len(self.chunks)

        texts: list[str] = []
        sources: list[str] = []
        for p in self._iter_files():
            content = self._read_file(p)
            for chunk in chunk_text(content, self.chunk_size, self.overlap):
                if not chunk.strip():
                    continue
                texts.append(chunk)
                sources.append(str(p.relative_to(self.dir)))

        if not texts:
            self.chunks = []
            np.savez(index_path, signature=sig, embeddings=np.zeros((0, 0)), texts=[], sources=[])
            return 0

        embeddings = self.embedder.encode(texts, normalize_embeddings=True)
        self.chunks = [
            IndexedChunk(text=t, source=s, embedding=embeddings[i])
            for i, (t, s) in enumerate(zip(texts, sources))
        ]
        np.savez(
            index_path,
            signature=sig,
            embeddings=embeddings,
            texts=np.array(texts, dtype=object),
            sources=np.array(sources, dtype=object),
        )
        return len(texts)

    def matrix(self) -> np.ndarray:
        if not self.chunks:
            return np.zeros((0, 0), dtype=np.float32)
        return np.stack([c.embedding for c in self.chunks])
