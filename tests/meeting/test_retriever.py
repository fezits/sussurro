import numpy as np

from meeting.intelligence.rag.indexer import IndexedChunk
from meeting.intelligence.rag.retriever import RagRetriever


class _StubEmbedder:
    def encode(self, texts, normalize_embeddings=True):
        out = []
        for t in texts:
            v = np.zeros(4, dtype=np.float32)
            for w in t.split():
                v[hash(w) % 4] += 1.0
            n = np.linalg.norm(v)
            if normalize_embeddings and n > 0:
                v = v / n
            out.append(v)
        return np.stack(out)


def test_retriever_returns_top_k():
    embedder = _StubEmbedder()
    docs = ["python backend", "javascript frontend", "python data"]
    embs = embedder.encode(docs)
    chunks = [IndexedChunk(text=d, source="x.md", embedding=embs[i]) for i, d in enumerate(docs)]
    retriever = RagRetriever(chunks=chunks, embedder=embedder)
    hits = retriever.retrieve("python", top_k=2)
    assert len(hits) == 2
    assert "python" in hits[0].text


def test_retriever_empty_index():
    retriever = RagRetriever(chunks=[], embedder=_StubEmbedder())
    assert retriever.retrieve("anything", top_k=3) == []
