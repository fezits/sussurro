from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class MeetingState(str, Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PAUSED = "paused"
    STOPPED = "stopped"


@dataclass(frozen=True)
class SessionId:
    value: str

    @classmethod
    def now(cls, when: datetime | None = None) -> "SessionId":
        when = when or datetime.now()
        return cls(when.strftime("%Y-%m-%d_%H-%M"))
