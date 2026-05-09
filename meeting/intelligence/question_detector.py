from __future__ import annotations

import numpy as np


_KEYWORDS = (
    "como ", "por que ", "porque ", "qual ", "quando ", "onde ", "quem ",
    "o que ", "que tal ", "cadê ", "me conta", "me fala", "você ",
    "pra você", "na sua opinião", "experiência", "já trabalhou",
    "entende de", "sabe ", "saberia ", "consegue ", "explica",
)


class QuestionDetector:
    """Heuristic question detection. 2 of 3 wins:
    1. text ends with '?'
    2. matches keyword list
    3. prosody: tail RMS >= 1.3 * mean RMS of head
    """

    def __init__(self, prosody_ratio: float = 1.3) -> None:
        self.prosody_ratio = prosody_ratio

    def _keyword_hit(self, text: str) -> bool:
        t = " " + text.lower().strip() + " "
        return any(k in t for k in _KEYWORDS)

    def _keyword_count(self, text: str) -> int:
        t = " " + text.lower().strip() + " "
        return sum(1 for k in _KEYWORDS if k in t)

    def _prosody_rising(self, audio: np.ndarray | None) -> bool:
        if audio is None or audio.size < int(0.5 * 16000):
            return False
        tail_size = int(0.3 * 16000)
        head = audio[: -tail_size] if audio.size > tail_size else audio
        tail = audio[-tail_size:]
        head_rms = float(np.sqrt(np.mean(np.square(head)))) if head.size else 1e-9
        tail_rms = float(np.sqrt(np.mean(np.square(tail)))) if tail.size else 0.0
        if head_rms <= 1e-6:
            return False
        return tail_rms / head_rms >= self.prosody_ratio

    def is_question(self, text: str, audio_tail: np.ndarray | None) -> bool:
        signals = 0
        if text.strip().endswith("?"):
            signals += 1
        signals += self._keyword_count(text)
        if self._prosody_rising(audio_tail):
            signals += 1
        return signals >= 2
