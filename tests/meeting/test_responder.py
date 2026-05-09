import numpy as np

from meeting.intelligence.rag.indexer import IndexedChunk
from meeting.intelligence.rag.retriever import RagRetriever
from meeting.intelligence.responder import Responder
from meeting.intelligence.types import SuggestionKind


class _StubEmbedder:
    def encode(self, texts, normalize_embeddings=True):
        return np.ones((len(texts), 2), dtype=np.float32) / np.sqrt(2)


class _StubLlm:
    def __init__(self): self.calls = []
    def complete(self, messages):
        self.calls.append(messages)
        return "minha resposta"


def test_responder_personal_uses_rag():
    emb = _StubEmbedder()
    chunks = [IndexedChunk("python backend", "p.md", emb.encode(["python backend"])[0])]
    retriever = RagRetriever(chunks, emb)
    llm = _StubLlm()
    r = Responder(retriever=retriever, classifier=lambda q, c: SuggestionKind.PERSONAL,
                  llm=llm, model="x", system_prompt_personal="VOCE EH FERNANDO")
    s = r.respond(question="conta sua experiência", recent_context="")
    assert s.kind is SuggestionKind.PERSONAL
    assert "python backend" in llm.calls[0][-1].content
    assert "VOCE EH FERNANDO" in llm.calls[0][0].content


def test_responder_technical_skips_rag():
    emb = _StubEmbedder()
    chunks = [IndexedChunk("python", "p.md", emb.encode(["python"])[0])]
    retriever = RagRetriever(chunks, emb)
    llm = _StubLlm()
    r = Responder(retriever=retriever, classifier=lambda q, c: SuggestionKind.TECHNICAL,
                  llm=llm, model="x")
    s = r.respond(question="como funciona OAuth", recent_context="")
    assert s.kind is SuggestionKind.TECHNICAL
    assert "python" not in llm.calls[0][-1].content
