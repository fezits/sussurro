from __future__ import annotations

from collections.abc import Callable

import numpy as np

from meeting.transcribe.turn import Speaker


class ChannelBuffer:
    """Per-channel buffer that accumulates audio and emits a chunk:
       1. when an external `on_turn_end()` is called, OR
       2. when accumulated audio exceeds `max_seconds`.
    Empty buffers (no audio since last flush) emit nothing.
    """

    def __init__(
        self,
        speaker: Speaker,
        on_chunk: Callable[[Speaker, np.ndarray], None],
        sample_rate: int = 16000,
        max_seconds: float = 30.0,
    ) -> None:
        self.speaker = speaker
        self.on_chunk = on_chunk
        self.sample_rate = sample_rate
        self.max_samples = int(max_seconds * sample_rate)
        self._parts: list[np.ndarray] = []
        self._size = 0

    def feed_audio(self, audio: np.ndarray) -> None:
        if audio.size == 0:
            return
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        self._parts.append(audio)
        self._size += audio.size
        if self._size >= self.max_samples:
            self._flush()

    def on_turn_end(self) -> None:
        self._flush()

    def _flush(self) -> None:
        if self._size == 0:
            return
        audio = np.concatenate(self._parts).astype(np.float32)
        self._parts.clear()
        self._size = 0
        self.on_chunk(self.speaker, audio)
