from __future__ import annotations

from typing import Protocol

from meeting.intelligence.types import SuggestionKind


class _Llm(Protocol):
    def complete(self, messages) -> str: ...


_PROMPT = """\
Classifique a pergunta abaixo em uma única letra:
A) Pessoal — sobre experiência, opinião ou trajetória do entrevistado.
B) Técnica — conhecimento de domínio, conceito, definição.
C) Híbrida — técnica que pede experiência pessoal.

Responda apenas A, B ou C.

Pergunta: {q}
Contexto recente da reunião:
{ctx}
"""


class Classifier:
    def __init__(self, llm: _Llm, model: str) -> None:
        self.llm = llm
        self.model = model

    def classify(self, question: str, context: str) -> SuggestionKind:
        from meeting.intelligence.llm_client import LlmMessage
        msgs = [LlmMessage(role="user", content=_PROMPT.format(q=question, ctx=context))]
        try:
            answer = self.llm.complete(msgs).strip().upper()
        except Exception:
            return SuggestionKind.HYBRID
        if "A" in answer[:3]:
            return SuggestionKind.PERSONAL
        if "B" in answer[:3]:
            return SuggestionKind.TECHNICAL
        return SuggestionKind.HYBRID
