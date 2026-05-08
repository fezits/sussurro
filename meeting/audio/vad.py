from __future__ import annotations

from collections.abc import Iterator

import numpy as np
import torch
from silero_vad import load_silero_vad


class Vad:
    """Streaming VAD that emits 'turn_end' events after `silence_ms` of silence
    following at least one chunk of detected speech.

    Uses silero-vad in 32ms (512-sample) frames at 16kHz. Stateless across
    instances, but tracks 'speaking' state internally so that 'turn_end' fires
    once per turn.
    """

    FRAME = 512  # 32ms @ 16kHz, the only size silero-vad supports

    def __init__(self, silence_ms: int = 800, sample_rate: int = 16000) -> None:
        if sample_rate != 16000:
            raise ValueError("Vad only supports 16kHz")
        self.model = load_silero_vad()
        self.silence_frames_threshold = max(1, silence_ms // 32)
        self.sample_rate = sample_rate

        self._buf = np.zeros(0, dtype=np.float32)
        self._was_speaking = False
        self._silent_frames = 0

    def feed(self, audio: np.ndarray) -> Iterator[str]:
        """Feed a mono float32 chunk; yields 'turn_end' when a turn closes."""
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
        self._buf = np.concatenate([self._buf, audio])

        while len(self._buf) >= self.FRAME:
            frame = self._buf[: self.FRAME]
            self._buf = self._buf[self.FRAME :]

            prob = float(self.model(torch.from_numpy(frame), self.sample_rate).item())
            speech = prob >= 0.5

            if speech:
                self._was_speaking = True
                self._silent_frames = 0
            else:
                if self._was_speaking:
                    self._silent_frames += 1
                    if self._silent_frames >= self.silence_frames_threshold:
                        self._was_speaking = False
                        self._silent_frames = 0
                        yield "turn_end"

    def reset(self) -> None:
        self._buf = np.zeros(0, dtype=np.float32)
        self._was_speaking = False
        self._silent_frames = 0
