import threading
import time

import numpy as np

from meeting.audio.mic_capture import MicCapture


class _FakeStream:
    """Mimics sounddevice.InputStream: invokes callback in a thread until close."""

    def __init__(self, callback, samplerate, channels, dtype, blocksize, **_kw):
        self.callback = callback
        self.samplerate = samplerate
        self.blocksize = blocksize or 1024
        self._running = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._running = True

        def _loop():
            while self._running:
                buf = (np.random.randn(self.blocksize, 1) * 0.1).astype(np.float32)
                self.callback(buf, self.blocksize, None, None)
                time.sleep(self.blocksize / self.samplerate)

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)

    def close(self) -> None:
        self.stop()


def test_mic_capture_collects_samples(monkeypatch):
    import meeting.audio.mic_capture as mod
    monkeypatch.setattr(mod.sd, "InputStream", _FakeStream)

    received: list[np.ndarray] = []
    cap = MicCapture(sample_rate=16000, on_audio=lambda chunk: received.append(chunk))
    cap.open()
    time.sleep(0.3)
    cap.close()

    assert len(received) > 0
    total = sum(c.size for c in received)
    assert total > 0
    assert all(c.dtype == np.float32 for c in received)
