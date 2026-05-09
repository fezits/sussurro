import json
from pathlib import Path

import numpy as np

from meeting.intelligence.rag.indexer import RagIndexer


class _StubEmbedder:
    """Deterministic 8-dim embedder: hashes word counts."""

    def encode(self, texts, normalize_embeddings=True):
        out = []
        for t in texts:
            v = np.zeros(8, dtype=np.float32)
            for w in t.split():
                v[hash(w) % 8] += 1.0
            if normalize_embeddings and np.linalg.norm(v) > 0:
                v = v / np.linalg.norm(v)
            out.append(v)
        return np.stack(out)


def test_indexer_indexes_md_and_persists(tmp_path: Path):
    (tmp_path / "perfil.md").write_text("Sou desenvolvedor Python há 12 anos.", encoding="utf-8")
    (tmp_path / "projeto.md").write_text("Construí um sistema de transcrição.", encoding="utf-8")
    idx = RagIndexer(knowledge_dir=tmp_path, embedder=_StubEmbedder(), chunk_size=50, overlap=5)
    n = idx.build_or_load(force=True)
    assert n >= 2
    assert (tmp_path / ".index.npz").exists()


def test_indexer_skips_when_unchanged(tmp_path: Path):
    (tmp_path / "perfil.md").write_text("conteudo", encoding="utf-8")
    idx = RagIndexer(knowledge_dir=tmp_path, embedder=_StubEmbedder(), chunk_size=50, overlap=5)
    n1 = idx.build_or_load(force=False)
    n2 = idx.build_or_load(force=False)
    assert n1 == n2
    assert idx.was_cached_last_call
