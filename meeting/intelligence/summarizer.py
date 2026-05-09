from __future__ import annotations

from meeting.intelligence.llm_client import LlmMessage
from meeting.transcribe.turn import Turn


_SYSTEM = (
    "Você é um assistente que sumariza reuniões em Markdown. Gere seções: "
    "## Resumo, ## Tópicos discutidos, ## Decisões, ## Action items (com responsável quando claro). "
    "Em português. Seja conciso."
)


class Summarizer:
    def __init__(self, llm, model: str) -> None:
        self.llm = llm
        self.model = model

    def summarize(self, turns: list[Turn]) -> str:
        if not turns:
            return "## Resumo\nReunião sem turnos transcritos.\n"
        body = "\n".join(t.to_line() for t in turns)
        msgs = [
            LlmMessage(role="system", content=_SYSTEM),
            LlmMessage(role="user", content=f"Transcrição:\n\n{body}"),
        ]
        try:
            return self.llm.complete(msgs)
        except Exception as e:
            return f"## Resumo\n_Falha ao gerar sumário automático: {e}_\n"
