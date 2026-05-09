from __future__ import annotations

import uuid
from typing import Callable

from meeting.intelligence.llm_client import LlmMessage
from meeting.intelligence.rag.retriever import RagRetriever
from meeting.intelligence.types import Suggestion, SuggestionKind


_SYSTEM_PERSONAL_DEFAULT = (
    "Você está auxiliando um entrevistado numa reunião. "
    "Responda na primeira pessoa, profissional, direto, máximo 4 frases, em português. "
    "Use os trechos do perfil/CV abaixo como base. Não invente fatos não presentes nos trechos."
)
_SYSTEM_TECHNICAL_DEFAULT = (
    "Responda tecnicamente como se estivesse explicando numa entrevista. "
    "Claro, exemplos práticos, máximo 4 frases. Em português, mantendo termos técnicos em inglês."
)
_SYSTEM_HYBRID_DEFAULT = (
    "Combine conhecimento técnico padrão com a experiência pessoal nos trechos abaixo. "
    "Responda na primeira pessoa, máximo 4 frases. Em português."
)


class Responder:
    """Glues classifier + RAG + LLM into one Suggestion per question."""

    def __init__(
        self,
        retriever: RagRetriever,
        classifier: Callable[[str, str], SuggestionKind],
        llm,
        model: str,
        top_k: int = 5,
        system_prompt_personal: str = _SYSTEM_PERSONAL_DEFAULT,
        system_prompt_technical: str = _SYSTEM_TECHNICAL_DEFAULT,
        system_prompt_hybrid: str = _SYSTEM_HYBRID_DEFAULT,
    ) -> None:
        self.retriever = retriever
        self.classifier = classifier
        self.llm = llm
        self.model = model
        self.top_k = top_k
        self.system_prompts = {
            SuggestionKind.PERSONAL: system_prompt_personal,
            SuggestionKind.TECHNICAL: system_prompt_technical,
            SuggestionKind.HYBRID: system_prompt_hybrid,
        }

    def respond(self, question: str, recent_context: str) -> Suggestion:
        kind = self.classifier(question, recent_context)
        used: list[str] = []

        retrieved_block = ""
        if kind in (SuggestionKind.PERSONAL, SuggestionKind.HYBRID):
            hits = self.retriever.retrieve(f"{question}\n\n{recent_context}", top_k=self.top_k)
            if hits:
                blocks = []
                for h in hits:
                    blocks.append(f"[{h.source}]\n{h.text}")
                    used.append(h.source)
                retrieved_block = "\n\nTrechos relevantes:\n" + "\n---\n".join(blocks)

        user_prompt = (
            f"Pergunta: {question}\n\n"
            f"Contexto recente da reunião:\n{recent_context or '(vazio)'}"
            f"{retrieved_block}"
        )
        messages = [
            LlmMessage(role="system", content=self.system_prompts[kind]),
            LlmMessage(role="user", content=user_prompt),
        ]
        text = self.llm.complete(messages)
        return Suggestion(
            kind=kind,
            text=text,
            source_turn_id=uuid.uuid4().hex,
            used_chunks=tuple(used),
        )
