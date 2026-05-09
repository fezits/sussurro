from __future__ import annotations

import threading
import wave
from pathlib import Path
from queue import Queue

import numpy as np


class AudioWriter:
    """Optional WAV writer for the mixed (system + mic) meeting audio.
    Mono float32 input gets quantized to int16 for portability.
    """

    def __init__(self, path: Path | str, sample_rate: int = 16000) -> None:
        self.path = Path(path)
        self.sample_rate = sample_rate
        self._queue: Queue = Queue()
        self._thread: threading.Thread | None = None
        self._wav: wave.Wave_write | None = None

    def start(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._wav = wave.open(str(self.path), "wb")
        self._wav.setnchannels(1)
        self._wav.setsampwidth(2)
        self._wav.setframerate(self.sample_rate)
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def append(self, audio: np.ndarray) -> None:
        self._queue.put(audio.astype(np.float32))

    def close(self) -> None:
        self._queue.put(None)
        if self._thread:
            self._thread.join(timeout=5)
        if self._wav is not None:
            self._wav.close()
            self._wav = None

    def _loop(self) -> None:
        assert self._wav is not None
        while True:
            chunk = self._queue.get()
            if chunk is None:
                return
            pcm = np.clip(chunk * 32767.0, -32768, 32767).astype(np.int16)
            self._wav.writeframes(pcm.tobytes())
