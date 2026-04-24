from __future__ import annotations

import threading
from collections import deque

import numpy as np
import sounddevice as sd


class Recorder:
    """Captures microphone audio with a rolling pre-roll buffer.

    The input stream runs continuously, so there is no start-up latency and
    we keep a ring buffer of the most recent ``prebuffer_seconds`` of audio.
    When recording is armed, that pre-roll is prepended to the captured
    chunks - this recovers the word or two the user says *just before*
    pressing the push-to-talk hotkey.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        blocksize: int = 0,
        prebuffer_seconds: float = 0.6,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.blocksize = blocksize
        self.prebuffer_seconds = max(0.0, prebuffer_seconds)

        self._preroll_max_samples = int(self.prebuffer_seconds * sample_rate)
        self._preroll: deque[np.ndarray] = deque()
        self._preroll_samples = 0

        self._chunks: list[np.ndarray] = []
        self._recent_rms: deque[float] = deque(maxlen=8)
        self._level: float = 0.0

        self._lock = threading.Lock()
        self._recording = False
        self._stream: sd.InputStream | None = None

    def _callback(self, indata, frames, time_info, status) -> None:
        mono = indata[:, 0] if indata.ndim > 1 else indata.reshape(-1)
        block = np.ascontiguousarray(mono, dtype=np.float32).copy()

        rms = float(np.sqrt(np.mean(np.square(block)))) if block.size else 0.0

        with self._lock:
            self._recent_rms.append(rms)
            self._level = float(np.mean(self._recent_rms)) if self._recent_rms else 0.0

            if self._recording:
                self._chunks.append(block)
                return

            self._preroll.append(block)
            self._preroll_samples += block.size
            while self._preroll_samples > self._preroll_max_samples and self._preroll:
                dropped = self._preroll.popleft()
                self._preroll_samples -= dropped.size

    def open(self) -> None:
        """Open the continuous stream once, at app startup."""
        if self._stream is not None:
            return
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
            blocksize=self.blocksize,
            callback=self._callback,
        )
        self._stream.start()

    def close(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        finally:
            self._stream = None

    def start(self) -> None:
        """Arm recording. Any buffered pre-roll is kept and prepended at stop."""
        if self._recording:
            return
        if self._stream is None:
            self.open()
        with self._lock:
            self._chunks.clear()
            self._recording = True

    def stop(self) -> np.ndarray:
        if not self._recording:
            return np.zeros(0, dtype=np.float32)
        with self._lock:
            self._recording = False
            preroll_chunks = list(self._preroll)
            rec_chunks = self._chunks
            self._chunks = []
            self._preroll.clear()
            self._preroll_samples = 0

        parts = preroll_chunks + rec_chunks
        if not parts:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(parts, axis=0).astype(np.float32)

    @property
    def level(self) -> float:
        return self._level

    @property
    def is_recording(self) -> bool:
        return self._recording
