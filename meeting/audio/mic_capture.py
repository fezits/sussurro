from __future__ import annotations

from collections.abc import Callable

import numpy as np
import sounddevice as sd


class MicCapture:
    """Continuous mic capture. Calls `on_audio` with mono float32 chunks at 16kHz.

    Designed to coexist with src/recorder.py from dictation: both can open the
    default input device simultaneously on Windows (WASAPI shared mode).
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        blocksize: int = 0,
        on_audio: Callable[[np.ndarray], None] | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.blocksize = blocksize
        self.on_audio = on_audio or (lambda _c: None)
        self._stream: sd.InputStream | None = None

    def _callback(self, indata, frames, time_info, status) -> None:
        mono = indata[:, 0] if indata.ndim > 1 else indata.reshape(-1)
        chunk = np.ascontiguousarray(mono, dtype=np.float32).copy()
        self.on_audio(chunk)

    def open(self) -> None:
        if self._stream is not None:
            return
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
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
