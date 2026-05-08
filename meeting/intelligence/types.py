from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SuggestionKind(str, Enum):
    PERSONAL = "personal"     # 🧠 amarelo
    TECHNICAL = "technical"   # 📚 azul
    HYBRID = "hybrid"         # 🔀 roxo


@dataclass(frozen=True)
class Suggestion:
    kind: SuggestionKind
    text: str
    source_turn_id: str
    used_chunks: tuple[str, ...] = ()  # rag chunks that fed the prompt
