from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Speaker(str, Enum):
    YOU = "Você"
    THEM = "Eles"


@dataclass(frozen=True)
class Turn:
    speaker: Speaker
    start: float          # seconds since meeting start
    end: float
    text: str
    wall_clock: datetime  # absolute timestamp (used for the rendered line)

    def to_line(self) -> str:
        """One-line rendering used by transcript.txt and the live view."""
        ts = self.wall_clock.strftime("%H:%M:%S")
        speaker_box = f"[{self.speaker.value}]"
        # 8 chars covers both "[Eles]" (6) and "[Você]" (6) plus padding.
        padded = speaker_box.ljust(8)
        return f"{ts} {padded} {self.text}"
